"""Interface Web locale Vybelix, raccordée au workflow et aux outils contrôlés."""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
import webbrowser
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .progress import ProgressStore
from .ui_actions import UIActionError, UIActions


def _git_state(project: Path) -> dict[str, Any]:
    """Lit branche et état Git avec des arguments fixes, sans shell."""
    try:
        branch = subprocess.run(
            ["git", "-c", f"safe.directory={project}", "-C", str(project), "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8", timeout=2, check=True,
            shell=False,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "-c", f"safe.directory={project}", "-C", str(project), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", timeout=2, check=True,
            shell=False,
        ).stdout.strip())
        return {"available": True, "branch": branch or None, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "branch": None, "dirty": None}


def _project_file_count(root: Path) -> int:
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name not in ignored]
        total += len(files)
    return total


def _verification_snapshot(tasks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for task in tasks:
        for item in task.get("verifications", []):
            if not isinstance(item, dict):
                continue
            execution_id = item.get("execution_id")
            if not isinstance(execution_id, str):
                continue
            exit_code = item.get("exit_code")
            command = item.get("command") if isinstance(item.get("command"), str) else ""
            if command == "codelix apply":
                continue
            status = "passed" if exit_code == 0 else "timeout" if exit_code is None else "failed"
            records.append({
                "task_id": task["id"],
                "execution_id": execution_id,
                "status": status,
                "command": command or None,
                "duration_seconds": item.get("duration_seconds") if isinstance(item.get("duration_seconds"), (int, float)) else None,
            })
    records.sort(key=lambda item: item["execution_id"], reverse=True)
    passed = sum(item["status"] == "passed" for item in records)
    return {"total": len(records), "passed": passed, "failed": len(records) - passed, "latest": records[0] if records else None}, records[:5]


def _safe_project_files(root: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    ignored_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".codelix-cache", ".codelix-backups"}
    ignored_files = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
    entries: list[dict[str, Any]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in ignored_dirs and not (Path(current) / name).is_symlink())
        parent = Path(current)
        for name in sorted(directories):
            relative = (parent / name).relative_to(root).as_posix()
            entries.append({"path": relative, "type": "directory"})
            if len(entries) >= limit:
                return entries
        for name in sorted(files):
            candidate = parent / name
            if name.casefold() in ignored_files or (name.casefold().startswith(".env.") and name.casefold() != ".env.example"):
                continue
            if candidate.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"} or candidate.is_symlink():
                continue
            try:
                size = candidate.stat().st_size
            except OSError:
                size = None
            entries.append({"path": candidate.relative_to(root).as_posix(), "type": "file", "size_bytes": size})
            if len(entries) >= limit:
                return entries
    return entries


def _git_details(project: Path) -> dict[str, Any]:
    state = _git_state(project)
    if not state["available"]:
        return {**state, "commits": []}
    try:
        output = subprocess.run(
            ["git", "-c", f"safe.directory={project}", "-C", str(project), "log", "-8", "--format=%h%x09%cs%x09%s"],
            capture_output=True, text=True, encoding="utf-8", timeout=3, check=True, shell=False,
        ).stdout
        commits = []
        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2][:240]})
        return {**state, "commits": commits}
    except (OSError, subprocess.SubprocessError):
        return {**state, "commits": [], "history_available": False}


def _proposal_snapshot(root: Path) -> list[dict[str, Any]]:
    directory = root / ".codelix-cache" / "proposals"
    if not directory.is_dir() or directory.is_symlink():
        return []
    proposals = []
    for file in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            continue
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get("files"), list):
            continue
        entries = []
        for item in value["files"]:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                entries.append({"path": item["path"], "operation": item.get("operation") if isinstance(item.get("operation"), str) else "unknown"})
        proposals.append({"task_id": value.get("task_id") if isinstance(value.get("task_id"), str) else file.stem, "files": entries})
    return proposals


def _pending_plan(root: Path, project_id: str, approved_ids: set[str] | None = None) -> dict[str, Any] | None:
    file = root / ".codelix-cache" / "plan.json"
    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):
        return None
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("project_id") != project_id or not isinstance(value.get("tasks"), list):
        return None
    tasks = []
    for task in value["tasks"]:
        if isinstance(task, dict):
            fields = ("id", "title", "role", "description", "dependencies", "acceptance_criteria", "affected_paths", "priority", "verification_strategy")
            tasks.append({key: task[key] for key in fields if key in task and isinstance(task[key], (str, list, int)) and not isinstance(task[key], bool)})
    summary = value.get("request_summary")
    approved_ids = approved_ids or set()
    task_ids = {task.get("id") for task in tasks if isinstance(task.get("id"), str)}
    return {"request_summary": summary[:1000] if isinstance(summary, str) else "Plan en attente", "tasks": tasks, "approved": bool(task_ids) and task_ids.issubset(approved_ids)}


def _agent_progress(tasks: list[dict[str, Any]], operations: list[dict[str, Any]], history: list[dict[str, Any]], proposals: list[dict[str, Any]], pending_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    by_id = {task["id"]: task for task in tasks}
    proposal_ids = {proposal["task_id"] for proposal in proposals}
    active_ops = [operation for operation in operations if operation["status"] in {"queued", "running"}]
    latest_plan = next((event for event in reversed(history) if event["type"] in {"plan_created", "plan_approved", "plan_rejected"}), None)
    applied_ids = {task_id for event in history if event["type"] == "changes_applied" for task_id in event.get("task_ids", [])}
    verified_ids = {task_id for event in history if event["type"] == "verification_completed" for task_id in event.get("task_ids", [])}

    result = []
    for role, label, subtitle in (("planner", "Planner", "Analyse et planification"), ("coder", "Coder", "Propositions de code"), ("tester", "Tester", "Préparation des tests"), ("verifier", "Verifier", "Vérification déterministe")):
        role_tasks = [task for task in tasks if task.get("role") == role]
        if role in {"coder", "tester"}:
            complete_ids = {task["id"] for task in role_tasks if task["status"] == "done"}
            total = len(role_tasks)
            completed = len(complete_ids)
            progress = round(completed * 100 / total) if total else 0
            active = next((op for op in active_ops if op["kind"] == "code" and by_id.get(op.get("task_id"), {}).get("role") == role), None)
            waiting = sum(task["id"] in proposal_ids for task in role_tasks)
            status = "En cours" if active else "Proposition à examiner" if waiting else "Terminée" if total and completed == total else "Prêt" if total else "Aucune tâche assignée"
            detail = f"{completed}/{total} tâche(s) terminée(s)" if total else "Aucune tâche affectée"
            current = by_id.get(active.get("task_id"), {}).get("title") if active else None
        elif role == "planner":
            active = next((op for op in active_ops if op["kind"] == "plan"), None)
            approved = bool(pending_plan and pending_plan.get("approved"))
            has_plan = pending_plan is not None
            progress = 0 if active else 100 if has_plan else 0
            status = "En cours" if active else "Plan approuvé" if approved else "Plan à approuver" if has_plan else "En attente"
            total = len(pending_plan["tasks"]) if pending_plan else 0
            detail = f"Plan · {total} tâche(s)" if has_plan else "Aucun plan enregistré"
            current = "Planification" if active else None
        else:
            active = next((op for op in active_ops if op["kind"] == "verify"), None)
            total = len(applied_ids)
            completed = len(verified_ids & applied_ids)
            progress = round(completed * 100 / total) if total else 0
            status = "En cours" if active else "Terminée" if total and completed == total else "Prêt" if total else "Aucune vérification en attente"
            detail = f"{completed}/{total} tâche(s) vérifiée(s)" if total else "Aucune tâche appliquée à vérifier"
            current = by_id.get(active.get("task_id"), {}).get("title") if active else None
        result.append({"role": role, "name": label, "subtitle": subtitle, "status": status, "progress": progress, "detail": detail, "current_task": current})
    return result


def project_snapshot(project: Path, actions: UIActions | None = None) -> dict[str, Any]:
    """Retourne uniquement des données locales non secrètes, sans appeler de provider."""
    root = project.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Le projet doit être un dossier existant.")
    config_path = root / "codelix.toml"
    with config_path.open("rb") as source:
        config = tomllib.load(source)
    progress = ProgressStore(root / "docs" / "progress" / "tasks.json").load()
    tasks = progress["tasks"]
    counts = Counter(task["status"] for task in tasks)
    verification, activity = _verification_snapshot(tasks)
    routes = []
    for role in ("planner", "coder", "tester"):
        candidates = config.get("models", {}).get(role, [])
        for order, candidate in enumerate(candidates, start=1):
            provider, separator, model = candidate.partition(":")
            routes.append({
                "role": role,
                "provider": provider if separator else "unknown",
                "model": model if separator else candidate,
                "order": order,
                "availability": "not_checked",
            })
    history = actions.history() if actions else []
    operations = actions.recent_operations() if actions else []
    pending_plan = _pending_plan(root, progress["project_id"], {task["id"] for task in tasks})
    plan_tasks = {}
    for event in history:
        if event.get("type") == "plan_approved":
            for task in event.get("tasks", []):
                if isinstance(task, dict) and isinstance(task.get("id"), str):
                    plan_tasks[task["id"]] = task
    plan_tasks.update({task["id"]: task for task in (pending_plan["tasks"] if pending_plan else []) if isinstance(task.get("id"), str)})
    task_details = []
    for task in tasks:
        planned = plan_tasks.get(task["id"], {})
        task_details.append({
            "id": task["id"], "title": task["title"], "status": task["status"],
            "dependencies": task["dependencies"], "acceptance_criteria": task["acceptance_criteria"],
            "files_modified": task["files_modified"], "attempts": task["attempts"],
            "role": planned.get("role"), "description": planned.get("description", ""),
            "affected_paths": planned.get("affected_paths", []),
        })
    return {
        "project": {"name": root.name, "id": progress["project_id"], "file_count": _project_file_count(root)},
        "git": _git_state(root),
        "tasks": {"total": len(tasks), "by_status": dict(counts)},
        "verification": verification,
        "activity": activity,
        "tasks_detail": task_details,
        "files": _safe_project_files(root),
        "git_details": _git_details(root),
        "proposals": _proposal_snapshot(root),
        "pending_plan": pending_plan,
        "verification_history": [
            {"task_id": task["id"], "records": [
                {key: item.get(key) for key in ("command", "exit_code", "summary", "execution_id", "duration_seconds", "acceptance_criteria") if key in item}
                for item in task["verifications"][-10:] if isinstance(item, dict)
            ]} for task in tasks if task["verifications"]
        ],
        "allowed_commands": config.get("verifier", {}).get("allowed_commands", []),
        "runtime": config.get("runtime", {}),
        "routes": routes,
        "providers": sorted({route["provider"] for route in routes}),
        "operations": operations,
        "history": history,
        "agents": _agent_progress(task_details, operations, history, _proposal_snapshot(root), pending_plan),
        "capabilities": {
            "provider_calls": True,
            "writes": True,
            "api_status": "user_initiated",
        },
    }


def _safe_ui_error(exc: Exception) -> str:
    from .ui_actions import _safe_error
    return _safe_error(exc)


def make_handler(project: Path, static_root: Path):
    actions = UIActions(project)

    class CodelixUIHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.actions = actions
            super().__init__(*args, directory=str(static_root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            super().end_headers()

        def _json(self, status: int, value: dict[str, Any]) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/state":
                try:
                    payload = json.dumps(project_snapshot(project, self.actions), ensure_ascii=False).encode("utf-8")
                except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError):
                    self.send_error(503, "État local Vybelix indisponible.")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if path.startswith("/api/operations/"):
                operation = self.actions.operation(path.rsplit("/", 1)[-1])
                self._json(200 if operation else 404, operation or {"error": "Opération introuvable."})
                return
            if path.startswith("/api/proposals/"):
                task_id = path.rsplit("/", 1)[-1]
                try:
                    self._json(200, self.actions.proposal_diff(task_id))
                except Exception as exc:
                    self._json(400, {"error": _safe_ui_error(exc)})
                return
            if path.startswith("/api/files/"):
                relative = unquote(path[len("/api/files/"):])
                try:
                    self._json(200, self.actions.project_file(relative))
                except Exception as exc:
                    self._json(400, {"error": _safe_ui_error(exc)})
                return
            self.path = path or "/"
            if self.path == "/":
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self):
            if self.client_address[0] not in {"127.0.0.1", "::1"}:
                self._json(403, {"error": "Accès local uniquement."})
                return
            host = self.headers.get("Host", "")
            if self.headers.get("Origin") != f"http://{host}" or not host.startswith(("127.0.0.1:", "localhost:", "[::1]:")):
                self._json(403, {"error": "Origine de requête refusée."})
                return
            if self.headers.get_content_type() != "application/json":
                self._json(415, {"error": "Content-Type application/json requis."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 1 <= length <= 64_000:
                self._json(413, {"error": "Taille de requête invalide."})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                self._json(400, {"error": "Corps JSON invalide."})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/plan":
                    operation_id = self.actions.submit("plan", payload)
                    self._json(202, {"operation_id": operation_id})
                elif path == "/api/code":
                    operation_id = self.actions.submit("code", payload)
                    self._json(202, {"operation_id": operation_id})
                elif path == "/api/verify":
                    operation_id = self.actions.submit("verify", payload)
                    self._json(202, {"operation_id": operation_id})
                elif path == "/api/approve-plan":
                    self._json(200, self.actions.approve_plan())
                elif path == "/api/reject-plan":
                    self._json(200, self.actions.reject_plan())
                elif path == "/api/apply":
                    self._json(200, self.actions.apply(payload))
                elif path == "/api/reject-proposal":
                    self._json(200, self.actions.reject_proposal(payload.get("task_id")))
                else:
                    self._json(404, {"error": "Action UI inconnue."})
            except Exception as exc:
                self._json(400, {"error": _safe_ui_error(exc)})

        def log_message(self, format, *args):
            # Les requêtes et leurs éventuels paramètres ne sont pas journalisés.
            return

    return CodelixUIHandler


def run_ui(project: Path, *, port: int = 0, open_browser: bool = True) -> None:
    """Démarre le shell local sur loopback uniquement, sans écriture projet."""
    root = project.resolve(strict=True)
    static_root = Path(__file__).with_name("ui_assets")
    if not (static_root / "index.html").is_file():
        raise FileNotFoundError("Les ressources de l'interface Vybelix sont absentes.")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, static_root))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Interface Vybelix locale : {url}")
    print("Actions disponibles sur demande ; appels IA et applications nécessitent une action explicite.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Arrêt de l'interface Vybelix.")
    finally:
        server.server_close()
