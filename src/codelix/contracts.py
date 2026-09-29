"""Validation déterministe des contrats JSON utilisés par Codelix."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


class ContractError(ValueError):
    """Une donnée ne respecte pas son contrat Codelix."""


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


def validate_planner_output(value: Any, *, expected_project_id: str | None = None) -> dict[str, Any]:
    """Valide et retourne un plan Planner conforme à planner-v1."""
    payload = _object(value, "plan")
    _required_keys(
        payload,
        {"schema_version", "project_id", "request_summary", "affected_paths", "tasks"},
        "plan",
    )
    if payload["schema_version"] != "1.0":
        raise ContractError("Version de schéma Planner non prise en charge.")
    project_id = _text(payload["project_id"], "project_id")
    if expected_project_id is not None and project_id != expected_project_id:
        raise ContractError("project_id ne correspond pas au projet actif.")
    _text(payload["request_summary"], "request_summary")
    if not isinstance(payload["affected_paths"], list):
        raise ContractError("affected_paths doit être une liste.")
    for path in payload["affected_paths"]:
        validate_relative_path(path)

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
        if task["type"] not in {"analysis", "code", "test", "documentation"}:
            raise ContractError(f"Type de tâche invalide pour {task_id}.")
        if task["role"] not in {"planner", "coder", "tester", "verifier"}:
            raise ContractError(f"Rôle invalide pour {task_id}.")
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
    return dict(payload)


def validate_coder_output(value: Any, *, expected_task_id: str) -> dict[str, Any]:
    """Valide une proposition Coder sans appliquer les fichiers."""
    payload = _object(value, "proposition Coder")
    _required_keys(
        payload,
        {"schema_version", "task_id", "summary", "files", "notes", "verification_hints"},
        "proposition Coder",
    )
    if payload["schema_version"] != "1.0":
        raise ContractError("Version de schéma Coder non prise en charge.")
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
