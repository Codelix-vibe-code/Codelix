"""UI/API bridge calling Vybelix's existing workflow and deterministic managers."""
from __future__ import annotations

import difflib
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
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
from .skills import SkillError, SkillManager
from .project_context import ProjectContextStore


class UIActionError(RuntimeError):
    """A user-requested UI operation could not safely be completed."""


def _semantic_version(value: Any) -> tuple[int,int,int]:
    match=re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?",value) if isinstance(value,str) else None
    return tuple(int(match.group(i)) for i in range(1,4)) if match else (0,0,0)


def _sandbox_status() -> dict[str,Any]:
    import shutil
    runtime=shutil.which("WindowsSandbox.exe") or shutil.which("wsl.exe") or shutil.which("docker.exe") or shutil.which("podman.exe")
    if runtime:
        return {"available":False,"status":"runtime_detected_backend_unavailable","runtime":Path(runtime).name,
                "detail":"Le runtime est détecté, mais aucun backend isolé validé n’est configuré."}
    return {"available":False,"status":"runtime_missing","runtime":None,
            "detail":"Windows Sandbox, WSL et conteneur isolé indisponibles; exécution des skills désactivée."}


class UIActions:
    def __init__(self, project: Path):
        self.root = project.resolve(strict=True)
        self._operations: dict[str, dict[str, Any]] = {}
        self._operations_lock = threading.Lock()
        self._project_lock = threading.RLock()
        self._api_key_sessions: dict[str, float] = {}
        self._pin_failures = 0
        self._pin_locked_until = 0.0

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

    def project_context(self) -> dict[str, Any]:
        progress = ProgressStore(self.root / "docs" / "progress" / "tasks.json").load()
        return ProjectContextStore(self._cache_path("context.json"), progress["project_id"]).load()

    def save_project_context(self, value: Any) -> dict[str, Any]:
        with self._project_lock:
            progress = ProgressStore(self.root / "docs" / "progress" / "tasks.json").load()
            saved = ProjectContextStore(self._cache_path("context.json"), progress["project_id"]).save(value)
            return {"saved": True, "updated_at": saved["updated_at"]}

    def resume_task(self, task_id: Any, approved: Any) -> dict[str, Any]:
        if approved is not True:
            raise UIActionError("La reprise nécessite une confirmation explicite.")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", task_id):
            raise UIActionError("Identifiant de tâche invalide.")
        with self._project_lock:
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
            if task is None:
                raise UIActionError("Tâche inconnue.")
            if task["status"] not in {"blocked", "interrupted"}:
                raise UIActionError("Seules les tâches bloquées ou interrompues peuvent être reprises.")
            states = {item["id"]: item["status"] for item in progress["tasks"]}
            waiting = [dependency for dependency in task["dependencies"] if states.get(dependency) != "done"]
            if waiting:
                raise UIActionError("Dépendances non terminées : " + ", ".join(waiting) + ".")
            previous = task["status"]
            task["status"] = "todo"
            task["last_result"] = f"Tâche reprise explicitement depuis {previous}; aucun agent n’a été lancé."
            progress["updated_at"] = _now()
            store.save(progress)
            self._record_event("task_resumed", task_id=task_id, previous_status=previous)
            return {"resumed": True, "task_id": task_id, "status": "todo"}

    def api_key_access_state(self) -> dict[str, bool]:
        """Expose only whether a local PIN has been initialized."""
        pin_file = self._api_key_pin_file()
        return {"setup_required": not pin_file.exists(), "locked": pin_file.exists()}

    def unlock_api_keys(self, action: Any, pin: Any, confirmation: Any = None) -> dict[str, str]:
        """Create the first six-digit PIN or verify it and issue a short-lived in-memory token."""
        if action not in {"setup", "unlock"} or not isinstance(pin, str) or not re.fullmatch(r"\d{6}", pin):
            raise UIActionError("Le code PIN doit contenir exactement 6 chiffres.")
        with self._project_lock:
            pin_file = self._api_key_pin_file()
            if action == "setup":
                if pin_file.exists():
                    raise UIActionError("Un code PIN est déjà configuré.")
                if confirmation != pin:
                    raise UIActionError("Les deux codes PIN ne correspondent pas.")
                salt = secrets.token_bytes(16)
                pin_hash = hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), salt, 600_000)
                _write_json(pin_file, {"schema_version": 1, "salt": salt.hex(), "hash": pin_hash.hex()})
                self._pin_failures = 0
            else:
                now = time.monotonic()
                if now < self._pin_locked_until:
                    raise UIActionError("Trop de tentatives. Réessaie dans quelques instants.")
                record = self._read_api_key_pin(pin_file)
                try:
                    salt = bytes.fromhex(record["salt"])
                    expected = bytes.fromhex(record["hash"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise UIActionError("Le code PIN local est illisible; les clés restent verrouillées.") from exc
                actual = hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), salt, 600_000)
                if not hmac.compare_digest(actual, expected):
                    self._pin_failures += 1
                    if self._pin_failures >= 5:
                        self._pin_locked_until = now + 60
                        self._pin_failures = 0
                    raise UIActionError("Code PIN incorrect.")
                self._pin_failures = 0
            token = secrets.token_urlsafe(32)
            self._api_key_sessions[token] = time.monotonic()
            return {"session_token": token}

    def api_key_status(self, session_token: Any) -> dict[str, Any]:
        """Return API key names and presence only; values never leave the process."""
        with self._project_lock:
            self._require_api_key_session(session_token)
            config = load_config(project_config_path(self.root))
            provider_envs: dict[str, list[str]] = {}
            for provider_id, settings in config.providers.items():
                if settings.api_key_env:
                    provider_envs.setdefault(settings.api_key_env, []).append(provider_id)
            env_values = _local_api_key_entries(self.root / ".env")
            names = set(provider_envs) | set(env_values)
            return {"keys": [
                {
                    "name": name,
                    "configured": bool(env_values.get(name) or os.environ.get(name)),
                    "used_by": sorted(provider_envs.get(name, [])),
                }
                for name in sorted(names, key=str.casefold)
            ]}

    def set_api_key(self, env_name: Any, value: Any, session_token: Any) -> dict[str, Any]:
        """Save or remove one API key by its environment variable name."""
        if not isinstance(env_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", env_name):
            raise UIActionError("Nom de clé invalide.")
        if not isinstance(value, str) or len(value) > 4096:
            raise UIActionError("La clé API doit contenir au maximum 4096 caractères.")
        value = value.strip()
        if value and not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value):
            raise UIActionError("Format de clé invalide : seuls les caractères usuels d’une clé API sont acceptés.")
        with self._project_lock:
            self._require_api_key_session(session_token)
            config = load_config(project_config_path(self.root))
            configured_names = {settings.api_key_env for settings in config.providers.values() if settings.api_key_env}
            if not env_name.upper().endswith("_API_KEY") and env_name not in configured_names:
                raise UIActionError("Le nom doit finir par _API_KEY ou être utilisé dans vybelix.toml.")
            _set_local_env_value(self.root / ".env", env_name, value)
            if value:
                os.environ[env_name] = value
            else:
                os.environ.pop(env_name, None)
            return {"name": env_name, "configured": bool(value)}

    def test_api_call(self, provider_id: Any, model: Any, api_key: Any, session_token: Any) -> dict[str, Any]:
        """Send one small provider request using an unsaved key; never persist it."""
        if not isinstance(provider_id, str) or provider_id not in {
            "openai", "anthropic", "gemini", "nvidia", "openrouter", "mistral",
        }:
            raise UIActionError("Fournisseur non pris en charge pour le test.")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,159}", model.strip()):
            raise UIActionError("Identifiant de modèle invalide.")
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
            raise UIActionError("Renseigne une clé API valide avant le test.")
        api_key = api_key.strip()
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", api_key):
            raise UIActionError("Format de clé API invalide.")

        with self._project_lock:
            self._require_api_key_session(session_token)
            config = load_config(project_config_path(self.root))
            settings = config.providers.get(provider_id)
            if settings is None or not settings.base_url:
                raise UIActionError("Ce fournisseur n’est pas configuré dans vybelix.toml.")

        try:
            from .providers.anthropic import AnthropicAdapter
            from .providers.gemini import GeminiAdapter
            from .providers.mistral import MistralAdapter
            from .providers.nvidia import NvidiaAdapter
            from .providers.openai import OpenAIAdapter
            from .providers.openrouter import OpenRouterAdapter

            adapters = {
                "openai": OpenAIAdapter, "anthropic": AnthropicAdapter, "gemini": GeminiAdapter,
                "nvidia": NvidiaAdapter, "mistral": MistralAdapter,
                "openrouter": OpenRouterAdapter,
            }
            # NVIDIA inference can take longer than the normal project timeout.
            # Keep the API Keys connectivity test bounded, but give NVIDIA up to 200 s.
            test_timeout = 200 if provider_id == "nvidia" else min(
                120 if provider_id == "gemini" else 30,
                config.runtime.request_timeout_seconds,
            )
            adapter = adapters[provider_id](settings, api_key=api_key, timeout_seconds=test_timeout)
            if provider_id == "gemini":
                options = {"max_output_tokens": 256, "temperature": 0.1}
            elif provider_id == "anthropic":
                options = {"max_tokens": 256}
            elif provider_id == "nvidia":
                # Leave max_tokens unset; NVIDIA applies the model's own output limit.
                options = {"temperature": 0.1, "stream": True}
            else:
                options = {"max_tokens": 256, "temperature": 0.1, "stream": True}
            started = time.monotonic()
            adapter.complete([{"role": "user", "content": "ping"}], model.strip(), options)
            latency_ms = round((time.monotonic() - started) * 1000)
        except Exception as exc:
            # Never return arbitrary provider response text or the submitted credential.
            from .providers.errors import ProviderError
            if isinstance(exc, ProviderError):
                raise UIActionError(_safe_error(exc)) from exc
            if isinstance(exc, UIActionError):
                raise
            raise UIActionError("L’appel de test a échoué. Vérifie le fournisseur, le modèle et la clé API.") from exc
        finally:
            api_key = ""
        return {"ok": True, "provider": provider_id, "model": model.strip(), "latencyMs": latency_ms}

    def update_user_level(self, level: Any) -> dict[str, str]:
        """Persist the selected communication level and mark first-run setup complete."""
        if not isinstance(level, str) or level not in {"beginner", "intermediate", "pro"}:
            raise UIActionError("Choisis beginner, intermediate ou pro.")
        with self._project_lock:
            path = project_config_path(self.root)
            if path.is_symlink():
                raise UIActionError("Le fichier de configuration ne peut pas être un lien symbolique.")
            load_config(path)
            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise UIActionError("Impossible de lire le fichier de configuration.") from exc
            newline = "\r\n" if "\r\n" in original else "\n"
            user_match = re.search(r"(?m)^\[user\][ \t]*$", original)
            temporary = None
            if user_match:
                next_section = re.search(r"(?m)^\[[^\r\n]+\][ \t]*$", original[user_match.end():])
                end = user_match.end() + next_section.start() if next_section else len(original)
                block = original[user_match.end():end]
                for key, value in (("level", json.dumps(level)), ("level_selected", "true")):
                    setting = re.search(rf"(?m)^[ \t]*{key}[ \t]*=.*$", block)
                    if setting:
                        block = block[:setting.start()] + f"{key} = {value}" + block[setting.end():]
                    else:
                        if block and not block.endswith(("\n", "\r")):
                            block += newline
                        block += f"{key} = {value}" + newline
                updated = original[:user_match.end()] + block + original[end:]
            else:
                updated = original.rstrip() + newline + newline + "[user]" + newline
                updated += f"level = {json.dumps(level)}" + newline + "level_selected = true" + newline
            try:
                from .config import validate_config
                validate_config(__import__("tomllib").loads(updated))
                temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
                with temporary.open("x", encoding="utf-8", newline="") as stream:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except (OSError, ValueError) as exc:
                raise UIActionError("Impossible d’enregistrer le niveau utilisateur.") from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return {"level": level}

    def remove_model_route(self, role: Any, candidate: Any) -> dict[str, Any]:
        """Remove one exact candidate from the current persisted route without stale UI state."""
        roles = ("planner", "coder", "tester")
        if role not in roles or not isinstance(candidate, str):
            raise UIActionError("Agent ou modèle invalide pour le retrait.")
        with self._project_lock:
            config = load_config(project_config_path(self.root))
            routes = {name: list(config.models.get(name, ())) for name in roles}
            if candidate not in routes[role]:
                raise UIActionError("Ce modèle ne figure plus dans la route de cet agent.")
            routes[role].remove(candidate)
            saved = self.update_model_routes(routes)
            return {"removed": candidate, "role": role, "routes": saved["routes"]}

    def update_model_routes(self, routes: Any) -> dict[str, Any]:
        """Persist user-selected provider/model candidates without touching secrets."""
        roles = ("planner", "coder", "tester")
        supported = {"openai", "anthropic", "gemini", "nvidia", "openrouter", "mistral"}
        if not isinstance(routes, dict) or set(routes) != set(roles):
            raise UIActionError("Les routes doivent contenir Planner, Coder et Tester.")
        with self._project_lock:
            path = project_config_path(self.root)
            if path.is_symlink():
                raise UIActionError("Le fichier de configuration ne peut pas être un lien symbolique.")
            config = load_config(path)
            normalized: dict[str, list[str]] = {}
            for role in roles:
                candidates = routes[role]
                if not isinstance(candidates, list) or len(candidates) > 5:
                    raise UIActionError(f"La route {role} doit contenir au maximum cinq modèles.")
                values: list[str] = []
                for candidate in candidates:
                    if not isinstance(candidate, str) or ":" not in candidate:
                        raise UIActionError("Chaque modèle doit respecter le format fournisseur:identifiant.")
                    provider, model = candidate.split(":", 1)
                    if provider not in supported or provider not in config.providers:
                        raise UIActionError(f"Le fournisseur {provider} n’est pas configuré dans ce projet.")
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,159}", model):
                        raise UIActionError("Identifiant de modèle invalide.")
                    if candidate in values:
                        raise UIActionError(f"Le modèle {candidate} apparaît plusieurs fois dans {role}.")
                    values.append(candidate)
                normalized[role] = values

            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise UIActionError("Impossible de lire le fichier de configuration.") from exc
            section = "[models]\n" + "".join(
                f"{role} = {json.dumps(normalized[role], ensure_ascii=False)}\n" for role in roles
            )
            pattern = re.compile(r"(?ms)^\[models\][ \t]*\r?\n.*?(?=^\[[^\r\n]+\][ \t]*$|\Z)")
            updated, count = pattern.subn(section + "\n", original, count=1)
            if not count:
                updated = original.rstrip() + "\n\n" + section
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except OSError as exc:
                raise UIActionError("Impossible d’enregistrer les routes de modèles.") from exc
            finally:
                temporary.unlink(missing_ok=True)
            return {"routes": normalized}

    def _api_key_pin_file(self) -> Path:
        cache_root = project_cache_root(self.root)
        if cache_root.is_symlink():
            raise UIActionError("Le dossier local de sécurité contient un lien interdit.")
        cache_root.mkdir(parents=True, exist_ok=True)
        pin_file = cache_root / "api-key-access.json"
        if pin_file.is_symlink():
            raise UIActionError("Le fichier local de sécurité contient un lien interdit.")
        return pin_file

    @staticmethod
    def _read_api_key_pin(pin_file: Path) -> dict[str, Any]:
        try:
            value = json.loads(pin_file.read_text(encoding="utf-8"))
            if value.get("schema_version") != 1 or not isinstance(value.get("salt"), str) or not isinstance(value.get("hash"), str):
                raise ValueError
            return value
        except (OSError, json.JSONDecodeError, AttributeError, ValueError) as exc:
            raise UIActionError("Le code PIN local est illisible; les clés restent verrouillées.") from exc

    def _require_api_key_session(self, token: Any) -> None:
        now = time.monotonic()
        for old_token, last_seen in tuple(self._api_key_sessions.items()):
            if now - last_seen > 900:
                self._api_key_sessions.pop(old_token, None)
        if not isinstance(token, str) or token not in self._api_key_sessions:
            raise UIActionError("La section API Keys est verrouillée; saisis ton code PIN.")
        self._api_key_sessions[token] = now

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
            self._record_event(
                "plan_approved",
                tasks=[{"id": task["id"], "role": task["role"], "title": task["title"], "affected_paths": plan["affected_paths"]} for task in plan["tasks"]],
                plan=plan,
            )
            return {"approved": True, "task_ids": task_ids}

    def reject_plan(self) -> dict[str, Any]:
        with self._project_lock:
            store = ProgressStore(self.root / "docs" / "progress" / "tasks.json")
            progress = store.load()
            path = self._cache_path("plan.json")
            if path.is_symlink():
                raise UIActionError("Le cache de plan contient un lien interdit.")
            try:
                plan = validate_planner_output(
                    json.loads(path.read_text(encoding="utf-8")),
                    expected_project_id=progress["project_id"],
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise UIActionError("Aucun plan valide à refuser ou désapprouver.") from exc

            task_ids = {task["id"] for task in plan["tasks"]}
            progress_tasks = {task["id"]: task for task in progress["tasks"]}
            recorded_ids = task_ids & progress_tasks.keys()
            approval_reverted = bool(task_ids) and recorded_ids == task_ids
            if recorded_ids and not approval_reverted:
                raise UIActionError("Le plan n’est présent que partiellement dans la progression; aucune tâche n’a été retirée.")
            if approval_reverted:
                for task_id in task_ids:
                    task = progress_tasks[task_id]
                    untouched = (
                        task["status"] == "todo"
                        and task["attempts"] == 0
                        and not task["files_modified"]
                        and not task["verifications"]
                    )
                    if not untouched:
                        raise UIActionError(
                            f"Impossible de désapprouver : la tâche {task_id} a déjà commencé ou possède des résultats."
                        )
                dependents = [
                    task["id"] for task in progress["tasks"]
                    if task["id"] not in task_ids and task_ids.intersection(task["dependencies"])
                ]
                if dependents:
                    raise UIActionError(
                        "Impossible de désapprouver : d’autres tâches dépendent déjà de ce plan."
                    )
                progress["tasks"] = [task for task in progress["tasks"] if task["id"] not in task_ids]
                progress["updated_at"] = _now()
                store.save(progress)

            path.unlink(missing_ok=True)
            self._record_event(
                "plan_rejected", task_ids=sorted(task_ids), approval_reverted=approval_reverted
            )
            return {
                "rejected": True,
                "approval_reverted": approval_reverted,
                "removed_task_ids": sorted(task_ids) if approval_reverted else [],
            }

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
            planned_role = None
            try:
                plan = validate_planner_output(
                    json.loads(self._cache_path("plan.json").read_text(encoding="utf-8")),
                    expected_project_id=progress["project_id"],
                )
                planned_task = next((item for item in plan["tasks"] if item["id"] == task_id), None)
                planned_role = planned_task.get("role") if planned_task else None
            except (OSError, json.JSONDecodeError, ValueError):
                pass
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
            task["status"] = "done"
            task["last_result"] = "Tâche terminée après approbation et application depuis l’interface. La vérification déterministe reste disponible séparément."
            task["verifications"].append({"command": "vybelix apply", "exit_code": 0, "summary": f"Fichiers appliqués : {', '.join(result.written)}", "errors": [], "execution_id": result.backup_id, "acceptance_criteria": []})
            progress["updated_at"] = _now()
            store.save(progress)
            self._proposal_path(task_id).unlink(missing_ok=True)
            self._record_event("changes_applied", task_ids=[task_id], files=list(result.written), rollback_id=result.backup_id)
            auto_verification = None
            if planned_role == "tester":
                command = config.allowed_commands[0] if config.allowed_commands else None
                if command is None:
                    auto_verification = {
                        "command": None,
                        "exit_code": None,
                        "summary": "Aucune commande autorisée à lancer automatiquement ; la vérification reste disponible manuellement après configuration.",
                        "errors": [],
                        "fallback_available": False,
                    }
                else:
                    started = time.monotonic()
                    try:
                        verification_result = Verifier(
                            self.root,
                            config.allowed_commands,
                            timeout_seconds=config.runtime.request_timeout_seconds,
                        ).run(command, acceptance_criteria=task["acceptance_criteria"])
                        auto_verification = {**verification_result.as_dict(), "fallback_available": True}
                    except Exception as exc:
                        auto_verification = {
                            "command": command,
                            "exit_code": None,
                            "summary": "Le lancement automatique du Verifier a été interrompu ; relance possible dans Vérification.",
                            "errors": [type(exc).__name__],
                            "execution_id": uuid.uuid4().hex,
                            "duration_seconds": round(time.monotonic() - started, 3),
                            "acceptance_criteria": list(task["acceptance_criteria"]),
                            "fallback_available": True,
                        }
                    task["verifications"].append({key: value for key, value in auto_verification.items() if key != "fallback_available"})
                    task["last_result"] = str(auto_verification["summary"])[:500]
                    task["status"] = "done" if auto_verification["exit_code"] == 0 else "needs_review"
                    progress["updated_at"] = _now()
                    store.save(progress)
                    self._record_event(
                        "verification_completed",
                        task_ids=[task_id],
                        command=command,
                        exit_code=auto_verification["exit_code"],
                        passed=auto_verification["exit_code"] == 0,
                        rollback_id=result.backup_id,
                        duration_seconds=auto_verification.get("duration_seconds"),
                        automatic=True,
                    )
            return {
                "applied": True,
                "files": list(result.written),
                "rollback_id": result.backup_id,
                "preview": list(preview),
                "auto_verification": auto_verification,
            }

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
            was_applied = any(isinstance(item, dict) and item.get("command") == "vybelix apply" for item in task["verifications"])
            if not was_applied or task["status"] not in {"in_progress", "needs_review", "done"}:
                raise UIActionError("La vérification est disponible après l’application approuvée d’une proposition.")
            result = Verifier(self.root, config.allowed_commands, timeout_seconds=config.runtime.request_timeout_seconds).run(command, acceptance_criteria=task["acceptance_criteria"])
            task["verifications"].append(result.as_dict())
            task["last_result"] = str(result.summary)[:500]
            task["status"] = "done" if result.passed else "needs_review"
            progress["updated_at"] = _now()
            store.save(progress)
            latest_apply = next((item for item in reversed(task["verifications"]) if isinstance(item, dict) and item.get("command") == "vybelix apply"), None)
            self._record_event("verification_completed", task_ids=[task_id], command=result.command, exit_code=result.exit_code, passed=result.passed, rollback_id=latest_apply.get("execution_id") if latest_apply else None, duration_seconds=result.duration_seconds)
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

    def skills_catalog(self) -> dict[str, Any]:
        """Expose the local registry and validated project skills; never executes them."""
        manager = SkillManager(self.root)
        installed = manager.list_installed()
        installed_by_id = {item["id"]: item for item in installed}
        candidates = []
        root = self.root / "skills"
        if root.is_symlink():
            raise UIActionError("Le dossier skills du projet ne peut pas être un lien.")
        if root.is_dir():
            for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
                if not path.is_dir() or path.is_symlink():
                    continue
                validation = manager.validate(path)
                skill = validation.skill
                skill_id = skill.get("id") if skill else None
                existing = installed_by_id.get(skill_id)
                if existing and skill and existing["version"] == skill.get("version"):
                    continue
                update_available=bool(existing and skill and _semantic_version(skill.get("version")) > _semantic_version(existing["version"]))
                if existing and not update_available:
                    continue
                candidates.append({
                    "source": path.relative_to(self.root).as_posix(),
                    "update_available": update_available,
                    "valid": validation.valid,
                    "skill": validation.skill,
                    "errors": list(validation.errors),
                    "warnings": list(validation.warnings),
                })
        return {"installed": installed, "candidates": candidates, "execution_enabled": False,
                "sandbox": _sandbox_status(),
                "agent_context_enabled": True}

    def validate_skill(self, source: Any) -> dict[str, Any]:
        path = self._skill_source(source)
        return SkillManager(self.root).validate(path).as_dict()

    def create_skill_draft(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            raise UIActionError("Informations du brouillon invalides.")
        path = SkillManager(self.root).create_draft(
            payload.get("id"), name=payload.get("name", ""),
            description=payload.get("description", ""), author=payload.get("author", "Unknown"),
            license_name=payload.get("license", "Unknown"),
        )
        return {"source": path.relative_to(self.root).as_posix()}

    def install_skill(self, source: Any, approved: Any) -> dict[str, Any]:
        if approved is not True:
            raise UIActionError("L’installation requiert une confirmation explicite dans l’interface.")
        path = self._skill_source(source)
        return SkillManager(self.root).install_local(path, approved=True)

    def update_skill(self, source: Any, approved: Any) -> dict[str, Any]:
        if approved is not True: raise UIActionError("La mise à jour requiert une confirmation explicite.")
        path=self._skill_source(source)
        return SkillManager(self.root).update_local(path,approved=True)

    def test_skill(self, skill_id: Any) -> dict[str, Any]:
        if not isinstance(skill_id,str): raise UIActionError("Identifiant de skill invalide.")
        return SkillManager(self.root).test(skill_id)

    def skill_dependencies(self, skill_id: Any) -> dict[str, Any]:
        if not isinstance(skill_id,str): raise UIActionError("Identifiant de skill invalide.")
        return {"skill_id":skill_id,"dependencies":SkillManager(self.root).dependency_status(skill_id)}

    def configure_skill(self, skill_id: Any, values: Any) -> dict[str, Any]:
        if not isinstance(skill_id,str) or not isinstance(values,dict): raise UIActionError("Configuration de skill invalide.")
        return SkillManager(self.root).configure(skill_id,values)

    def skill_configuration_status(self, skill_id: Any) -> dict[str, Any]:
        if not isinstance(skill_id,str): raise UIActionError("Identifiant de skill invalide.")
        return SkillManager(self.root).configuration_status(skill_id)

    def skill_configuration_schema(self, skill_id: Any) -> dict[str, Any]:
        if not isinstance(skill_id,str): raise UIActionError("Identifiant de skill invalide.")
        return SkillManager(self.root).configuration_schema(skill_id)

    def skill_agent_context(self, skill_ids: Any, role: Any) -> dict[str, Any]:
        if not isinstance(skill_ids,list) or any(not isinstance(item,str) for item in skill_ids) or not isinstance(role,str):
            raise UIActionError("Sélection de skills invalide.")
        from .skills.bridge import SkillBridge
        return {"role":role,"skills":SkillBridge(SkillManager(self.root)).context_for(role,skill_ids)}

    def set_skill_enabled(self, skill_id: Any, enabled: Any, permissions: Any = None) -> dict[str, Any]:
        if not isinstance(skill_id, str) or enabled not in {True, False}:
            raise UIActionError("Action Skill invalide.")
        manager = SkillManager(self.root)
        if enabled:
            if not isinstance(permissions, list) or any(not isinstance(item, str) for item in permissions):
                raise UIActionError("Confirme explicitement les permissions demandées.")
            return manager.enable(skill_id, approved_permissions=set(permissions))
        return manager.disable(skill_id)

    def uninstall_skill(self, skill_id: Any, approved: Any) -> dict[str, bool]:
        if approved is not True or not isinstance(skill_id, str):
            raise UIActionError("La désinstallation requiert une confirmation explicite.")
        SkillManager(self.root).uninstall(skill_id, approved=True)
        return {"removed": True}

    def _skill_source(self, source: Any) -> Path:
        try:
            relative = validate_relative_path(source)
        except ValueError as exc:
            raise UIActionError("Chemin de skill invalide.") from exc
        if not relative.startswith("skills/"):
            raise UIActionError("Seuls les skills présents dans le dossier projet skills/ sont disponibles.")
        path = self.root / relative
        try:
            path.resolve(strict=True).relative_to((self.root / "skills").resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise UIActionError("Le skill doit rester dans skills/ et exister localement.") from exc
        if path.is_symlink() or not path.is_dir():
            raise UIActionError("Le dossier de skill est invalide ou est un lien.")
        return path

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
            raw = path.read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise UIActionError("Aperçu indisponible : le fichier n’est pas lisible en UTF-8.") from exc
        return {"path": relative, "content": content, "sha256": hashlib.sha256(raw).hexdigest(), "newline": "\r\n" if b"\r\n" in raw else "\n"}

    def save_project_file(self, relative: Any, content: Any, expected_sha256: Any, approved: Any) -> dict[str, Any]:
        if not isinstance(relative, str) or not isinstance(content, str):
            raise UIActionError("Fichier ou contenu invalide.")
        if approved is not True:
            raise UIActionError("L’enregistrement nécessite une approbation explicite.")
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise UIActionError("Empreinte du fichier invalide ; rouvrez le fichier avant de réessayer.")
        with self._project_lock:
            current = self.project_file(relative)
            if not hmac.compare_digest(current["sha256"], expected_sha256):
                raise UIActionError("Le fichier a changé depuis son ouverture. Rouvrez-le pour éviter d’écraser ses changements.")
            config = load_config(project_config_path(self.root))
            manager = ExecutionManager(self.root, max_file_bytes=config.runtime.max_file_bytes)
            snapshots = manager.inspect([relative])
            if snapshots[relative].sha256 != expected_sha256:
                raise UIActionError("Le fichier a changé depuis son ouverture. Rouvrez-le pour éviter d’écraser ses changements.")
            proposal = {
                "schema_version": "1.0", "task_id": "manual-file-edit",
                "summary": "Modification manuelle approuvée depuis l’explorateur Vybelix",
                "files": [{"path": relative, "operation": "write", "content": content}],
                "notes": [], "verification_hints": [],
            }
            manager.preview(proposal, expected_task_id="manual-file-edit", snapshots=snapshots)
            result = manager.apply(proposal, expected_task_id="manual-file-edit", snapshots=snapshots, approved=True)
            updated = self.project_file(relative)
            try:
                self._record_event("manual_file_saved", files=[relative], rollback_id=result.backup_id)
            except (OSError, ValueError, UIActionError):
                pass
            return {"saved": True, "path": relative, "sha256": updated["sha256"], "rollback_id": result.backup_id}

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


def _local_api_key_entries(path: Path) -> dict[str, str]:
    """Read names and values of API_KEY variables internally; callers expose names only."""
    if path.is_symlink():
        raise UIActionError("Le fichier .env ne peut pas être un lien symbolique.")
    try:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
    except (OSError, UnicodeError) as exc:
        raise UIActionError("Impossible de lire le fichier .env local.") from exc
    if len(content.encode("utf-8")) > 1_048_576:
        raise UIActionError("Le fichier .env dépasse la taille autorisée.")
    entries: dict[str, str] = {}
    assignment = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
    for line in content.splitlines():
        match = assignment.match(line)
        if not match or not match.group(1).upper().endswith("_API_KEY"):
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        entries[match.group(1)] = value
    return entries


def _set_local_env_value(path: Path, name: str, value: str) -> None:
    """Atomically update one variable in the ignored local .env without exposing it."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise UIActionError("Nom de variable d’environnement invalide.")
    if path.is_symlink():
        raise UIActionError("Le fichier .env ne peut pas être un lien symbolique.")
    try:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
    except (OSError, UnicodeError) as exc:
        raise UIActionError("Impossible de lire le fichier .env local.") from exc
    if len(content.encode("utf-8")) > 1_048_576:
        raise UIActionError("Le fichier .env dépasse la taille autorisée.")

    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    lines = content.splitlines()
    updated: list[str] = []
    inserted = False
    for line in lines:
        match = pattern.match(line)
        if match and match.group(1) == name:
            if value and not inserted:
                updated.append(f"{name}={value}")
                inserted = True
            continue
        updated.append(line)
    if value and not inserted:
        updated.append(f"{name}={value}")
    serialized = "\n".join(updated) + ("\n" if updated else "")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise UIActionError("Impossible d’enregistrer la clé dans le fichier .env local.") from exc
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
