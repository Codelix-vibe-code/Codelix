"""Source unique de vérité pour la progression des tâches du projet."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import ContractError, _ensure_acyclic

TASK_STATUSES = {"todo", "in_progress", "blocked", "needs_review", "done", "interrupted", "cancelled"}
TASK_FIELDS = {
    "id", "title", "status", "dependencies", "acceptance_criteria", "attempts",
    "files_modified", "verifications", "last_result",
}


class ProgressError(ValueError):
    """Le fichier de progression est invalide."""


def validate_progress(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProgressError("La progression doit être un objet JSON.")
    if set(value) != {"schema_version", "project_id", "updated_at", "tasks"}:
        raise ProgressError("La progression contient des champs manquants ou inconnus.")
    if value["schema_version"] != "1.0":
        raise ProgressError("Version de schéma de progression non prise en charge.")
    for name in ("project_id", "updated_at"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ProgressError(f"{name} doit être un texte non vide.")
    try:
        timestamp = datetime.fromisoformat(value["updated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgressError("updated_at doit être une date ISO 8601 avec fuseau horaire.") from exc
    if timestamp.tzinfo is None:
        raise ProgressError("updated_at doit inclure un fuseau horaire.")
    if not isinstance(value["tasks"], list):
        raise ProgressError("tasks doit être une liste.")

    ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    for index, task in enumerate(value["tasks"]):
        if not isinstance(task, dict) or set(task) != TASK_FIELDS:
            raise ProgressError(f"tasks[{index}] contient des champs manquants ou inconnus.")
        task_id = task["id"]
        if not isinstance(task_id, str) or not task_id.strip() or task_id in ids:
            raise ProgressError(f"Identifiant de tâche invalide ou dupliqué à tasks[{index}].")
        ids.add(task_id)
        if not isinstance(task["title"], str) or not task["title"].strip():
            raise ProgressError(f"title invalide pour {task_id}.")
        if task["status"] not in TASK_STATUSES:
            raise ProgressError(f"État invalide pour {task_id}.")
        dependencies = task["dependencies"]
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
            raise ProgressError(f"dependencies invalide pour {task_id}.")
        if len(set(dependencies)) != len(dependencies):
            raise ProgressError(f"Dépendance dupliquée pour {task_id}.")
        if not isinstance(task["acceptance_criteria"], list) or any(not isinstance(item, str) for item in task["acceptance_criteria"]):
            raise ProgressError(f"acceptance_criteria invalide pour {task_id}.")
        if isinstance(task["attempts"], bool) or not isinstance(task["attempts"], int) or not 0 <= task["attempts"] <= 2:
            raise ProgressError(f"attempts doit être compris entre 0 et 2 pour {task_id}.")
        for field in ("files_modified", "verifications"):
            if not isinstance(task[field], list):
                raise ProgressError(f"{field} doit être une liste pour {task_id}.")
        graph[task_id] = dependencies
    for task_id, dependencies in graph.items():
        unknown = set(dependencies) - ids
        if unknown:
            raise ProgressError(f"Dépendances inconnues pour {task_id}: {', '.join(sorted(unknown))}.")
    try:
        _ensure_acyclic(graph, "la progression")
    except ContractError as exc:
        raise ProgressError(str(exc)) from exc
    return value


class ProgressStore:
    """Lit et écrit l'unique document JSON de progression du projet."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as source:
                return validate_progress(json.load(source))
        except FileNotFoundError as exc:
            raise ProgressError(f"Fichier de progression introuvable: {self.path}.") from exc
        except json.JSONDecodeError as exc:
            raise ProgressError(f"JSON de progression invalide dans {self.path}.") from exc

    def save(self, data: dict[str, Any]) -> None:
        validated = validate_progress(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False, newline="\n"
            ) as temporary:
                temporary_path = temporary.name
                json.dump(validated, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
