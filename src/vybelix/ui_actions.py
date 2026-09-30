"""UI/API bridge calling Vybelix's existing workflow and deterministic managers."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import load_config
from .contracts import validate_coder_output, validate_planner_output, validate_relative_path
from .execution import ExecutionManager
from .progress import ProgressStore
from .providers.errors import RoutingError
from .providers.router import build_router
from .verifier import Verifier
from .workflow import VybelixWorkflow
from .paths import project_cache_root, project_config_path


class UIActionError(RuntimeError):
    """A user-requested UI operation could not safely be completed."""


class UIActions:
    def __init__(self, project: Path):
        self.root = project.resolve(strict=True)
        self._operations: dict[str, dict[str, Any]] = {}
        self._operations_lock = threading.Lock()
        self._project_lock = threading.RLock()

    def submit(self, kind: str, payload: dict[str, Any]) -> str:
        operations: dict[str, Callable[[], dict[str, Any]]] = {
            "plan": lambda: self._plan(payload),
            "code": lambda: self._code(payload),
            "verify": lambda: self._verify(payload),
        }
        if kind not in operations:
            raise UIActionError("Opération UI inconnue.")
        operation_id = uuid.uuid4().hex
        with self._operations_lock:
            if len(self._operations) >= 100:
                for old_id in [key for key, value in self._operations.items() if value["status"] in {"done", "failed"}][:20]:
                    self._operations.pop(old_id, None)
            self._operations[operation_id] = {"id": operation_id, "kind": kind, "task_id": payload.get("task_id") if isinstance(payload.get("task_id"), str) else None, "status": "queued", "created_at": _now(), "result": None, "error": None}
        thread = threading.Thread(target=self._run_operation, args=(operation_id, operations[kind]), daemon=True)
        thread.start()
        return operation_id

    def _run_operation(self, operation_id: str, action: Callable[[], dict[str, Any]]) -> None:
        with self._operations_lock:
            self._operations[operation_id]["status"] = "running"
        try:
            result = action()
            with self._operations_lock:
                self._operations[operation_id].update(status="done", result=result)
        except Exception as exc:
            error: dict[str, Any] = {"type": type(exc).__name__, "message": _safe_error(exc)}
            if isinstance(exc, RoutingError):
                error["attempts"] = [
                    {**{key: item.get(key) for key in ("provider", "model", "attempt", "outcome", "status_code")}, "message": _safe_error(Exception(str(item.get("message", "Erreur fournisseur."))))}
                    for item in exc.attempts
                ]
            with self._operations_lock:
                self._operations[operation_id].update(status="failed", error=error)

    def operation(self, operation_id: str) -> dict[str, Any] | None:
        with self._operations_lock:
            value = self._operations.get(operation_id)
            return dict(value) if value is not None else None

    def recent_operations(self) -> list[dict[str, Any]]:
        with self._operations_lock:
            values = sorted(self._operations.values(), key=lambda item: item["created_at"], reverse=True)[:20]
            result = []
            for item in values:
                entry = {key: item[key] for key in ("id", "kind", "task_id", "status", "created_at")}
                outcome = item.get("result") or {}
                if isinstance(outcome, dict) and isinstance(outcome.get("routing"), list):
                    entry["routing"] = outcome["routing"]
                result.append(entry)
            return result

    def _plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = payload.get("request")
        if not isinstance(request, str) or not request.strip() or len(request.encode("utf-8")) > 20_000:
            raise UIActionError("La demande doit contenir entre 1 et 20 000 octets.")
        with self._project_lock:
            config = load_config(project_config_path(self.root))
            progress = ProgressStore(self.root / "docs" / "progress" / "tasks.json").load()
            router = build_router(config)
            plan = VybelixWorkflow(config, router, progress["project_id"]).create_plan(request)
            path = self._cache_path("plan.json")
            _write_json(path, plan)
            routing = [item.as_dict() for item in router.last_trace]
            self._record_event("plan_created", task_ids=[task["id"] for task in plan["tasks"]], routing=routing)
            return {"plan": plan, "routing": routing}

    def approve_plan(self) -> dict[str, Any]:
        with self._project_lock:
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            plan_path = self._cache_path("plan.json")
            try:
                plan = validate_planner_output(json.loads(plan_path.read_text(encoding="utf-8")), expected_project_id=progress["project_id"])
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise UIActionError("Aucun plan valide en attente d’approbation.") from exc
            current_ids = {item["id"] for item in progress["tasks"]}
            if current_ids.intersection(item["id"] for item in plan["tasks"]):
                raise UIActionError("Le plan contient un identifiant de tâche déjà utilisé.")
            for task in plan["tasks"]:
                progress["tasks"].append({
                    "id": task["id"], "title": task["title"], "status": "todo",
                    "dependencies": task["dependencies"], "acceptance_criteria": task["acceptance_criteria"],
                    "attempts": 0, "files_modified": [], "verifications": [], "last_result": "Plan approuvé depuis l’interface.",
                })
            progress["updated_at"] = _now()
            store.save(progress)
            task_ids = [task["id"] for task in plan["tasks"]]
            self._record_event("plan_approved", tasks=[{"id": task["id"], "role": task["role"], "title": task["title"], "affected_paths": plan["affected_paths"]} for task in plan["tasks"]])
            return {"approved": True, "task_ids": task_ids}

    def reject_plan(self) -> dict[str, Any]:
        with self._project_lock:
            path = self._cache_path("plan.json")
            if path.is_symlink():
                raise UIActionError("Le cache de plan contient un lien interdit.")
            path.unlink(missing_ok=True)
            self._record_event("plan_rejected")
            return {"rejected": True}

    def _code(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = _task_id(payload)
        with self._project_lock:
            config = load_config(project_config_path(self.root))
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task_record = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task_record is None or task_record["status"] not in {"todo", "needs_review"}:
                raise UIActionError("La tâche n’est pas approuvée ou n’est pas disponible pour génération.")
            plan = validate_planner_output(json.loads(self._cache_path("plan.json").read_text(encoding="utf-8")), expected_project_id=progress["project_id"])
            task = next((item for item in plan["tasks"] if item["id"] == task_id), None)
            if task is None or task["role"] not in {"coder", "tester"}:
                raise UIActionError("Cette tâche n’est pas une tâche Coder ou Tester générable.")
            states = {item["id"]: item["status"] for item in progress["tasks"]}
            if any(states.get(dep) != "done" for dep in task["dependencies"]):
                raise UIActionError("Les dépendances de cette tâche ne sont pas terminées.")
            if task_record["status"] == "needs_review" and task_record["attempts"] >= config.runtime.correction_attempts:
                raise UIActionError("La limite de corrections configurée est atteinte.")
            feedback = task_record["verifications"][-1].get("errors", []) if task_record["status"] == "needs_review" and task_record["verifications"] else []
            workflow_task = {**task, "affected_paths": plan["affected_paths"], "verification_feedback": feedback}
            router = build_router(config)
            proposal = VybelixWorkflow(config, router, progress["project_id"]).create_code_proposal(workflow_task, self.root)
            if not proposal["files"]:
                raise UIActionError("La proposition ne contient aucun fichier à examiner.")
            manager = ExecutionManager(self.root, max_file_bytes=config.runtime.max_file_bytes)
            snapshots = manager.inspect([item["path"] for item in proposal["files"]])
            manager.preview(proposal, expected_task_id=task_id, snapshots=snapshots)
            path = self._cache_path("proposals", f"{hashlib.sha256(task_id.encode('utf-8')).hexdigest()[:20]}.json")
            _write_json(path, proposal)
            if task_record["status"] == "needs_review":
                task_record["attempts"] += 1
            task_record["last_result"] = "Proposition générée ; approbation humaine requise avant application."
            task_record["status"] = "needs_review"
            progress["updated_at"] = _now()
            store.save(progress)
            routing = [item.as_dict() for item in router.last_trace]
            self._record_event("proposal_created", task_ids=[task_id], files=[item["path"] for item in proposal["files"]], routing=routing)
            return {"proposal": {"task_id": task_id, "files": [item["path"] for item in proposal["files"]]}, "routing": routing}

    def proposal_diff(self, task_id: str) -> dict[str, Any]:
        task_id = _valid_task_id(task_id)
        config = load_config(project_config_path(self.root))
        proposal = self._load_proposal(task_id)
        manager = ExecutionManager(self.root, max_file_bytes=config.runtime.max_file_bytes)
        snapshots = manager.inspect([item["path"] for item in proposal["files"]])
        manager.preview(proposal, expected_task_id=task_id, snapshots=snapshots)
        files = []
        for item in proposal["files"]:
            path = self.root.joinpath(*item["path"].split("/"))
            try:
                before = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
            except (OSError, UnicodeError) as exc:
                raise UIActionError(f"Impossible de prévisualiser {item['path']} en texte UTF-8.") from exc
            after = item["content"].splitlines(keepends=True)
            diff = "".join(difflib.unified_diff(before, after, fromfile=f"a/{item['path']}", tofile=f"b/{item['path']}"))
            if len(diff) > 100_000:
                raise UIActionError(f"Le diff de {item['path']} dépasse la limite d’aperçu ; application refusée depuis l’interface.")
            files.append({"path": item["path"], "diff": diff, "added": sum(line.startswith("+") and not line.startswith("+++") for line in diff.splitlines()), "removed": sum(line.startswith("-") and not line.startswith("---") for line in diff.splitlines())})
        return {"task_id": task_id, "summary": proposal["summary"], "notes": proposal["notes"], "files": files, "approved_hashes": {key: value.sha256 for key, value in snapshots.items()}}

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = _task_id(payload)
        if payload.get("approved") is not True:
            raise UIActionError("Une approbation explicite est requise avant l’application.")
        with self._project_lock:
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task is None or task["status"] != "needs_review":
                raise UIActionError("La tâche doit être en revue avec une proposition active avant son application.")
            config = load_config(project_config_path(self.root))
            proposal = self._load_proposal(task_id)
            paths = [item["path"] for item in proposal["files"]]
            approved_hashes = payload.get("approved_hashes")
            if payload.get("approved_paths") != paths or not isinstance(approved_hashes, dict):
                raise UIActionError("La liste ou l’empreinte approuvée ne correspond pas à la proposition affichée.")
            manager = ExecutionManager(self.root, max_file_bytes=config.runtime.max_file_bytes)
            snapshots = manager.inspect(paths)
            if approved_hashes != {key: value.sha256 for key, value in snapshots.items()}:
                raise UIActionError("Un fichier a changé depuis l’affichage de l’aperçu ; recharge le diff avant l’approbation.")
            preview = manager.preview(proposal, expected_task_id=task_id, snapshots=snapshots)
            result = manager.apply(proposal, expected_task_id=task_id, snapshots=snapshots, approved=True)
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task is None:
                raise UIActionError("Tâche disparue après l’application ; vérifiez le workspace.")
            task["files_modified"] = list(dict.fromkeys([*task["files_modified"], *result.written]))
            task["status"] = "in_progress"
            task["last_result"] = "Proposition appliquée après approbation depuis l’interface."
            task["verifications"].append({"command": "vybelix apply", "exit_code": 0, "summary": f"Fichiers appliqués : {', '.join(result.written)}", "errors": [], "execution_id": result.backup_id, "acceptance_criteria": []})
            progress["updated_at"] = _now()
            store.save(progress)
            self._record_event("changes_applied", task_ids=[task_id], files=list(result.written), rollback_id=result.backup_id)
            return {"applied": True, "files": list(result.written), "rollback_id": result.backup_id, "preview": list(preview)}

    def reject_proposal(self, task_id: str) -> dict[str, Any]:
        task_id = _valid_task_id(task_id)
        with self._project_lock:
            path = self._proposal_path(task_id)
            if path.is_symlink():
                raise UIActionError("Le cache de proposition contient un lien interdit.")
            path.unlink(missing_ok=True)
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task and task["status"] == "needs_review":
                task["status"] = "todo"
                task["last_result"] = "Proposition refusée par l’utilisateur ; aucun fichier modifié."
                progress["updated_at"] = _now()
                store.save(progress)
            self._record_event("proposal_rejected", task_ids=[task_id])
            return {"rejected": True, "task_id": task_id}

    def _verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = _task_id(payload)
        command = payload.get("command")
        with self._project_lock:
            config = load_config(project_config_path(self.root))
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task is None:
                raise UIActionError("Tâche inconnue.")
            if task["status"] != "in_progress":
                raise UIActionError("La vérification est disponible après l’application approuvée d’une proposition.")
            result = Verifier(self.root, config.allowed_commands, timeout_seconds=config.runtime.request_timeout_seconds).run(command, acceptance_criteria=task["acceptance_criteria"])
            task["verifications"].append(result.as_dict())
            task["last_result"] = str(result.summary)[:500]
            task["status"] = "done" if result.passed else "needs_review"
            progress["updated_at"] = _now()
            store.save(progress)
            self._record_event("verification_completed", task_ids=[task_id], command=result.command, exit_code=result.exit_code, duration_seconds=result.duration_seconds)
            return result.as_dict()

    def history(self) -> list[dict[str, Any]]:
        path = self._cache_path("events.json")
        if path.is_symlink() or not path.is_file():
            return []
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [item for item in events[-200:] if isinstance(item, dict)] if isinstance(events, list) else []

    def _record_event(self, kind: str, **details: Any) -> None:
        path = self._cache_path("events.json")
        if path.is_symlink():
            raise UIActionError("Le journal Vybelix contient un lien interdit.")
        events = self.history()
        event = {"id": uuid.uuid4().hex, "type": kind, "timestamp": _now(), **details}
        events.append(event)
        _write_json(path, events[-200:])

    def project_file(self, relative: str) -> dict[str, Any]:
        try:
            relative = validate_relative_path(relative)
        except ValueError as exc:
            raise UIActionError("Chemin de fichier invalide.") from exc
        parts = relative.split("/")
        lowered = [part.casefold() for part in parts]
        if any(part in {".git", ".vybelix-cache", ".codelix-cache", ".vybelix-backups", ".codelix-backups", "node_modules", ".venv", "venv"} for part in lowered):
            raise UIActionError("Ce chemin système n’est pas consultable dans Files.")
        name = lowered[-1]
        if name in {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"} or (name.startswith(".env.") and name != ".env.example") or Path(name).suffix in {".pem", ".key", ".p12", ".pfx"}:
            raise UIActionError("Les fichiers secrets ne sont pas consultables dans Files.")
        path = self.root.joinpath(*parts)
        cursor = self.root
        for part in parts:
            cursor = cursor / part
            if cursor.exists() and cursor.is_symlink():
                raise UIActionError("Les liens symboliques ne sont pas consultables dans Files.")
        if not path.resolve(strict=True).is_relative_to(self.root) or not path.is_file():
            raise UIActionError("Fichier introuvable ou chemin hors du projet.")
        if path.stat().st_size > 204_800:
            raise UIActionError("Fichier trop volumineux pour l’aperçu UI (limite 200 Ko).")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise UIActionError("Aperçu indisponible : le fichier n’est pas lisible en UTF-8.") from exc
        return {"path": relative, "content": content}

    def _load_proposal(self, task_id: str) -> dict[str, Any]:
        try:
            raw = json.loads(self._proposal_path(task_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UIActionError("Aucune proposition valide n’est enregistrée pour cette tâche.") from exc
        return validate_coder_output(raw, expected_task_id=task_id)

    def _proposal_path(self, task_id: str) -> Path:
        return self._cache_path("proposals", f"{hashlib.sha256(task_id.encode('utf-8')).hexdigest()[:20]}.json")

    def _cache_path(self, *parts: str) -> Path:
        root = project_cache_root(self.root)
        path = root.joinpath(*parts)
        cursor = self.root
        for part in (root.name, *parts):
            cursor = cursor / part
            if cursor.exists() and (cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)()):
                raise UIActionError("Un lien ou une jonction interdit l’accès au cache Vybelix.")
        if not path.resolve(strict=False).is_relative_to(self.root):
            raise UIActionError("Le cache Vybelix sort de la racine du projet.")
        return path


def _task_id(payload: dict[str, Any]) -> str:
    return _valid_task_id(payload.get("task_id"))


def _valid_task_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in value):
        raise UIActionError("Identifiant de tâche invalide.")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_error(exc: Exception) -> str:
    # Provider and workflow errors are deliberately concise; redact credential-shaped substrings as a final guard.
    message = str(exc)
    import re
    patterns = (r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\bAIza[0-9A-Za-z_-]{20,}\b", r"\bnvapi-[A-Za-z0-9_-]{16,}\b", r"\bgsk_[A-Za-z0-9_-]{16,}\b", r"\bsk-[A-Za-z0-9_-]{16,}\b")
    for pattern in patterns:
        message = re.sub(pattern, "[MASQUÉ]", message)
    return message[:1000]
