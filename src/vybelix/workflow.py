"""Planification et génération de propositions avec validation stricte des contrats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import VybelixConfig
from .contracts import ContractError, validate_coder_output, validate_planner_output, validate_relative_path
from .providers.router import ModelRouter
from .execution import ExecutionError, ExecutionManager


class WorkflowError(RuntimeError):
    """Une réponse IA ne peut pas être utilisée comme proposition Vybelix."""


def _json_response(text: str, label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Réponse {label} invalide : un objet JSON strict est attendu.") from exc


class VybelixWorkflow:
    def __init__(self, config: VybelixConfig, router: ModelRouter, project_id: str):
        self.config = config
        self.router = router
        self.project_id = project_id

    def create_plan(self, request: str) -> dict[str, Any]:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("La demande ne peut pas être vide.")
        if len(request.encode("utf-8")) > self.config.runtime.max_file_bytes:
            raise ValueError("La demande dépasse la taille maximale autorisée.")
        instructions = (
            "Tu es le Planner de Vybelix. Décompose la demande en tâches vérifiables. "
            "Réponds uniquement avec un objet JSON valide conforme au schéma Planner Vybelix v1. "
            "Utilise le project_id fourni, des chemins relatifs normalisés, des identifiants stables, "
            "des dépendances valides, au plus 50 tâches, et des critères d'acceptation vérifiables. "
            "Ne propose aucune commande d'exécution."
        )
        raw = self.router.complete("planner", [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"project_id": self.project_id, "request": request}, ensure_ascii=False)},
        ])
        try:
            return validate_planner_output(_json_response(raw, "Planner"), expected_project_id=self.project_id)
        except ContractError as exc:
            raise WorkflowError(f"Plan rejeté par le contrat Planner : {exc}") from exc

    def create_code_proposal(self, task: dict[str, Any], root: Path) -> dict[str, Any]:
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise WorkflowError("Tâche invalide pour la génération de code.")
        manager = ExecutionManager(root, max_file_bytes=self.config.runtime.max_file_bytes)
        contexts: list[dict[str, str]] = []
        paths = task.get("affected_paths", [])
        if not isinstance(paths, list):
            raise WorkflowError("affected_paths doit être une liste.")
        normalized = [validate_relative_path(path) for path in paths]
        manager.inspect(normalized)
        for relative in normalized:
            path = root.joinpath(*relative.split("/"))
            if not path.exists():
                continue
            data = path.read_bytes()
            if len(data) > self.config.runtime.max_file_bytes:
                raise WorkflowError(f"Contexte trop volumineux, aucune troncature appliquée : {relative}.")
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WorkflowError(f"Le fichier de contexte n'est pas UTF-8 : {relative}.") from exc
            contexts.append({"path": relative, "content": content})

        instructions = (
            "Tu es le Coder de Vybelix. Propose uniquement des écritures de fichiers dans un objet JSON "
            "strict conforme au contrat Coder Vybelix v1. Reprends le task_id fourni. "
            "N'exécute aucune commande, ne supprime et ne renomme aucun fichier. "
            "Si verification_feedback est présent, corrige les erreurs utiles sans ignorer les critères. "
            "Les changements seront affichés puis soumis à approbation humaine."
        )
        role = task.get("role", "coder")
        if role not in {"coder", "tester"}:
            raise WorkflowError("Le rôle doit être coder ou tester pour générer une proposition.")
        raw = self.router.complete(role, [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"task": task, "context_files": contexts}, ensure_ascii=False)},
        ])
        try:
            return validate_coder_output(_json_response(raw, "Coder"), expected_task_id=task_id)
        except ContractError as exc:
            raise WorkflowError(f"Proposition rejetée par le contrat Coder : {exc}") from exc


# Compatibility alias for integrations using the previous package name.
CodelixWorkflow = VybelixWorkflow
