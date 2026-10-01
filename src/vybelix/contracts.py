"""Validation déterministe des contrats JSON utilisés par Vybelix."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


class ContractError(ValueError):
    """Une donnée ne respecte pas son contrat Vybelix."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} doit être un objet JSON.")
    return value


def _required_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    missing = keys - value.keys()
    extra = value.keys() - keys
    if missing:
        raise ContractError(f"{label}: champs obligatoires manquants: {', '.join(sorted(missing))}.")
    if extra:
        raise ContractError(f"{label}: champs non reconnus: {', '.join(sorted(extra))}.")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} doit être un texte non vide.")
    return value


def validate_relative_path(value: Any) -> str:
    """Accepte les chemins relatifs normalisés en séparateurs `/` seulement."""
    path = _text(value, "path")
    win_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    if (
        path.startswith("/")
        or "\\" in path
        or win_path.is_absolute()
        or bool(win_path.drive)
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or posix_path.as_posix() != path
    ):
        raise ContractError(f"Chemin relatif non sûr ou non normalisé: {path!r}.")
    return path


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = " non vide" if nonempty else ""
        raise ContractError(f"{label} doit être une liste{qualifier} de textes.")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ContractError(f"{label}[{index}] doit être un texte non vide.")
        result.append(item)
    return result


def _ensure_acyclic(graph: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ContractError(f"Dépendance circulaire détectée dans {label}: {node}.")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def validate_planner_output(
    value: Any,
    *,
    expected_project_id: str | None = None,
    require_role_match: bool = False,
) -> dict[str, Any]:
    """Valide et retourne un plan Planner conforme à planner-v1."""
    payload = _object(value, "plan")
    required = {"schema_version", "project_id", "request_summary", "affected_paths", "tasks"}
    missing = required - payload.keys()
    extra = payload.keys() - required - {"plain_summary"}
    if missing or extra:
        raise ContractError(
            "plan: champs obligatoires manquants ou champs non reconnus: "
            + ", ".join(sorted(missing | extra)) + "."
        )
    if payload["schema_version"] not in {"1.0", "1.1"}:
        raise ContractError("Version de schéma Planner non prise en charge.")
    if "plain_summary" in payload:
        _text(payload["plain_summary"], "plain_summary")
    project_id = _text(payload["project_id"], "project_id")
    if expected_project_id is not None and project_id != expected_project_id:
        raise ContractError("project_id ne correspond pas au projet actif.")
    _text(payload["request_summary"], "request_summary")
    if not isinstance(payload["affected_paths"], list):
        raise ContractError("affected_paths doit être une liste.")
    # Planner may describe a directory with a trailing slash (for example "src/").
    # Canonicalize that harmless notation while retaining strict traversal checks.
    affected_paths = []
    for path in payload["affected_paths"]:
        if isinstance(path, str) and path.endswith("/") and not path.endswith("//"):
            path = path[:-1]
        affected_paths.append(validate_relative_path(path))

    tasks = payload["tasks"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 50:
        raise ContractError("tasks doit contenir entre 1 et 50 tâches.")
    task_keys = {
        "id", "parent_id", "title", "description", "type", "role", "priority",
        "dependencies", "acceptance_criteria", "verification_strategy",
    }
    ids: set[str] = set()
    task_graph: dict[str, list[str]] = {}
    parents: dict[str, str | None] = {}
    for index, raw_task in enumerate(tasks):
        task = _object(raw_task, f"tasks[{index}]")
        _required_keys(task, task_keys, f"tasks[{index}]")
        task_id = _text(task["id"], f"tasks[{index}].id")
        if task_id in ids:
            raise ContractError(f"Identifiant de tâche dupliqué: {task_id}.")
        ids.add(task_id)
        parent_id = task["parent_id"]
        if parent_id is not None:
            parent_id = _text(parent_id, f"tasks[{index}].parent_id")
        parents[task_id] = parent_id
        _text(task["title"], f"tasks[{index}].title")
        _text(task["description"], f"tasks[{index}].description")
        _text(task["verification_strategy"], f"tasks[{index}].verification_strategy")
        task_type = task["type"]
        type_aliases = {
            "planning": "analysis",
            "research": "analysis",
            "implementation": "code",
            "coding": "code",
            "verification": "test",
            "testing": "test",
            "docs": "documentation",
        }
        if isinstance(task_type, str):
            task_type = type_aliases.get(task_type.strip().lower(), task_type)
        if task_type not in {"analysis", "code", "test", "documentation"}:
            raise ContractError(f"Type de tâche invalide pour {task_id}: {task['type']!r}.")
        task["type"] = task_type
        task_role = task["role"]
        role_aliases = {
            "analyst": "planner",
            "developer": "coder",
            "implementer": "coder",
            "programmer": "coder",
            "quality assurance": "tester",
            "quality_assurance": "tester",
            "qa": "tester",
            "review": "verifier",
            "reviewer": "verifier",
        }
        if isinstance(task_role, str):
            task_role = role_aliases.get(task_role.strip().lower(), task_role)
        if task_role not in {"planner", "coder", "tester", "verifier"}:
            raise ContractError(f"Rôle invalide pour {task_id}: {task['role']!r}.")
        task["role"] = task_role
        if require_role_match:
            if task_role in {"planner", "verifier"} or task_type == "analysis":
                raise ContractError(
                    f"Tâche non exécutable dans le plan pour {task_id}: l'analyse appartient au Planner; "
                    "les tâches différées doivent être réalisables par coder ou tester."
                )
            expected_role = {"code": "coder", "test": "tester", "documentation": "coder"}[task_type]
            if task_role != expected_role:
                raise ContractError(
                    f"Rôle incohérent pour {task_id}: le type {task_type!r} doit être assigné à {expected_role!r}, "
                    f"pas à {task_role!r}."
                )
        if isinstance(task["priority"], bool) or not isinstance(task["priority"], int) or not 1 <= task["priority"] <= 5:
            raise ContractError(f"priority doit être un entier de 1 à 5 pour {task_id}.")
        dependencies = _string_list(task["dependencies"], f"tasks[{index}].dependencies")
        if len(set(dependencies)) != len(dependencies):
            raise ContractError(f"Dépendance dupliquée dans {task_id}.")
        task["acceptance_criteria"] = _string_list(
            task["acceptance_criteria"], f"tasks[{index}].acceptance_criteria", nonempty=True
        )
        task_graph[task_id] = dependencies

    for task_id, dependencies in task_graph.items():
        if task_id in dependencies:
            raise ContractError(f"Une tâche ne peut pas dépendre d'elle-même: {task_id}.")
        unknown = set(dependencies) - ids
        if unknown:
            raise ContractError(f"Dépendances inconnues pour {task_id}: {', '.join(sorted(unknown))}.")
        parent_id = parents[task_id]
        if parent_id is not None and parent_id not in ids:
            raise ContractError(f"parent_id inconnu pour {task_id}: {parent_id}.")
        if parent_id == task_id:
            raise ContractError(f"Une tâche ne peut pas être son propre parent: {task_id}.")
    _ensure_acyclic(task_graph, "les dépendances")
    _ensure_acyclic(
        {task_id: ([parent] if parent else []) for task_id, parent in parents.items()},
        "la hiérarchie des tâches",
    )
    result = dict(payload)
    result["affected_paths"] = affected_paths
    return result


def validate_coder_output(value: Any, *, expected_task_id: str) -> dict[str, Any]:
    """Valide une proposition Coder sans appliquer les fichiers."""
    payload = _object(value, "proposition Coder")
    required = {"schema_version", "task_id", "summary", "files", "notes", "verification_hints"}
    missing = required - payload.keys()
    extra = payload.keys() - required - {"explanation"}
    if missing or extra:
        raise ContractError(
            "proposition Coder: champs obligatoires manquants ou champs non reconnus: "
            + ", ".join(sorted(missing | extra)) + "."
        )
    if payload["schema_version"] not in {"1.0", "1.1"}:
        raise ContractError("Version de schéma Coder non prise en charge.")
    if "explanation" in payload:
        explanation = _object(payload["explanation"], "explanation")
        _required_keys(explanation, {"what_changed", "why", "how_to_verify"}, "explanation")
        _string_list(explanation["what_changed"], "explanation.what_changed", nonempty=True)
        _text(explanation["why"], "explanation.why")
        _string_list(explanation["how_to_verify"], "explanation.how_to_verify", nonempty=True)
    if _text(payload["task_id"], "task_id") != expected_task_id:
        raise ContractError("task_id ne correspond pas à la tâche active.")
    _text(payload["summary"], "summary")
    files = payload["files"]
    if not isinstance(files, list) or len(files) > 50:
        raise ContractError("files doit être une liste de 0 à 50 fichiers.")
    seen_paths: set[str] = set()
    for index, raw_file in enumerate(files):
        file = _object(raw_file, f"files[{index}]")
        _required_keys(file, {"path", "operation", "content"}, f"files[{index}]")
        path = validate_relative_path(file["path"])
        if path in seen_paths:
            raise ContractError(f"Chemin de fichier dupliqué: {path}.")
        seen_paths.add(path)
        if file["operation"] != "write":
            raise ContractError("Seule l'opération 'write' est prise en charge.")
        if not isinstance(file["content"], str):
            raise ContractError(f"content doit être un texte pour {path}.")
    _string_list(payload["notes"], "notes")
    _string_list(payload["verification_hints"], "verification_hints")
    return dict(payload)
