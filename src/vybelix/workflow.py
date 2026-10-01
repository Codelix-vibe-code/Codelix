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

    def _level_instruction(self) -> str:
        instructions = {
            "beginner": "Niveau beginner : langage simple, explique les termes techniques et donne des explications automatiques. La sécurité et les validations ne changent jamais.",
            "intermediate": "Niveau intermediate : plan standard, résultats utiles et erreurs actionnables. La sécurité et les validations ne changent jamais.",
            "pro": "Niveau pro : formulation concise et technique, paramètres détaillés, sans explications spontanées. La sécurité et les validations ne changent jamais.",
        }
        return instructions[self.config.user_level]

    def create_plan(self, request: str) -> dict[str, Any]:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("La demande ne peut pas être vide.")
        if len(request.encode("utf-8")) > self.config.runtime.max_file_bytes:
            raise ValueError("La demande dépasse la taille maximale autorisée.")
        instructions = (
            "Tu es le Planner de Vybelix. Décompose la demande en tâches vérifiables. "
            "Réponds uniquement avec un objet JSON valide conforme au schéma Planner Vybelix v1.1. "
            "Utilise le project_id fourni, des chemins relatifs normalisés, des identifiants stables, "
            "des dépendances valides, au plus 50 tâches, et des critères d'acceptation vérifiables. "
            "Ne propose aucune commande d'exécution. Le JSON racine doit contenir schema_version (la chaîne exacte 1.1), "
            "project_id, request_summary, plain_summary, affected_paths et tasks. plain_summary est un résumé simple "
            "optionnel du plan. Chaque tâche doit "
            "contenir exactement id, parent_id (chaîne ou null), title, description, type "
            "(analysis/code/test/documentation), role (planner/coder/tester/verifier), priority "
            "(entier de 1 à 5), dependencies (liste d'identifiants), acceptance_criteria (liste non vide) "
            "et verification_strategy. Le Planner effectue lui-même l'analyse et la conception pendant "
            "la préparation du plan : ne crée pas de tâches différées de rôle planner pour ces étapes. "
            "Chaque tâche du plan doit être exécutable après approbation : attribue code et rédaction de "
            "documentation au rôle coder, et les tests au rôle tester. N'utilise pas les rôles planner ou "
            "verifier dans les tâches; Verifier est une étape déterministe séparée après application approuvée. "
            "Pour une demande d'implémentation, planifie les livrables concrets à réaliser, pas seulement "
            "des tâches préparatoires (analyse des besoins, conception, maquettes, architecture) sauf si "
            "l'utilisateur les demande comme livrables eux-mêmes et qu'un agent coder/tester peut les réaliser. "
            "Les tâches de test doivent être des tâches tester, dépendantes de l'implémentation concernée. "
            "N'ajoute aucun champ path dans une tâche; les chemins sont "
            "uniquement dans affected_paths. Réponds sans bloc Markdown. " + self._level_instruction()
        )
        raw = self.router.complete("planner", [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"project_id": self.project_id, "request": request}, ensure_ascii=False)},
        ])
        try:
            return validate_planner_output(
                _json_response(raw, "Planner"),
                expected_project_id=self.project_id,
                require_role_match=True,
            )
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

        role = task.get("role", "coder")
        if role not in {"coder", "tester"}:
            raise WorkflowError("Le rôle doit être coder ou tester pour générer une proposition.")
        output_contract = (
            "Réponds avec un objet JSON strict conforme au contrat de proposition Vybelix v1.1. "
            "Reprends le task_id fourni. Le JSON contient schema_version (la chaîne exacte 1.1), task_id, "
            "summary, files, notes, verification_hints et le champ optionnel explanation. explanation contient "
            "what_changed (liste non vide), why (texte) et how_to_verify (liste non vide). Chaque élément de files "
            "contient path, operation avec la valeur write et content. Utilise uniquement les chemins autorisés "
            "dans affected_paths. N'exécute aucune commande, ne supprime et ne renomme aucun fichier. "
            "Ne renvoie ni Markdown ni texte avant ou après le JSON. Toute proposition sera examinée puis soumise "
            "à approbation humaine avant application. "
        )
        if role == "coder":
            role_instruction = (
                "Tu es le Coder de Vybelix. Implémente la tâche en respectant le langage, l'architecture et les "
                "conventions observés dans les fichiers de contexte. Modifie uniquement les fichiers nécessaires "
                "à l'implémentation. Si verification_feedback est présent, corrige les erreurs utiles sans ignorer "
                "les critères d'acceptation. Ta réponse doit être du JSON brut syntaxiquement valide, jamais un bloc "
                "Markdown, jamais du code seul et jamais accompagnée de texte avant ou après. Respecte exactement "
                "les clés du contrat : schema_version (chaîne \"1.1\"), task_id, summary, files, notes et "
                "verification_hints; explanation est facultatif et doit contenir exactement what_changed (liste non "
                "vide), why (texte) et how_to_verify (liste non vide). files doit contenir au moins un élément; "
                "chaque élément contient exactement path, operation (\"write\") et content. Utilise des guillemets "
                "JSON doubles, aucune virgule finale et aucun champ supplémentaire. Pour une tâche de code "
                "qui nécessite une modification, files contient au moins un élément. N'invente pas de changement "
                "si la tâche n'en demande aucun; explique alors le blocage dans summary et notes."
            )
            output_label = "Coder"
        else:
            role_instruction = (
                "Tu es le Tester de Vybelix. Crée ou adapte uniquement les fichiers de tests nécessaires à la tâche. "
                "Respecte le framework, la structure et les conventions de tests déjà présents dans le contexte du "
                "projet. N'implémente pas la fonctionnalité et ne modifie pas le code de production. Les tests doivent "
                "couvrir les critères d'acceptation et rester déterministes; ne les exécute pas."
            )
            output_label = "Tester"
        instructions = role_instruction + " " + output_contract + self._level_instruction()
        raw = self.router.complete(role, [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"task": task, "context_files": contexts}, ensure_ascii=False)},
        ])
        try:
            return validate_coder_output(_json_response(raw, output_label), expected_task_id=task_id)
        except ContractError as exc:
            raise WorkflowError(f"Proposition rejetée par le contrat {output_label} : {exc}") from exc


# Compatibility alias for integrations using the previous package name.
CodelixWorkflow = VybelixWorkflow
