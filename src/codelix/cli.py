"""Interface de commande initiale de Codelix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigurationError, load_config
from .execution import ExecutionError, ExecutionManager
from .progress import ProgressError, ProgressStore
from .verifier import VerificationError, Verifier
from .providers.router import build_router
from .workflow import CodelixWorkflow, WorkflowError
from .contracts import validate_planner_output, validate_relative_path


def _progress_path(project: Path) -> Path:
    return project / "docs" / "progress" / "tasks.json"


def _config_path(project: Path) -> Path:
    return project / "codelix.toml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codelix", description="Orchestrateur local de développement assisté par IA")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Initialiser un projet Codelix local")
    init.add_argument("project", type=Path, nargs="?", default=Path.cwd())
    status = commands.add_parser("status", help="Afficher les tâches du projet")
    status.add_argument("--project", type=Path, default=Path.cwd())
    config = commands.add_parser("config", help="Valider la configuration et afficher les routes")
    config.add_argument("--project", type=Path, default=Path.cwd())
    plan = commands.add_parser("plan", help="Soumettre une demande à l'IA et prévisualiser son plan")
    plan.add_argument("request", help="Demande de développement")
    plan.add_argument("--project", type=Path, default=Path.cwd())
    approve = commands.add_parser("approve-plan", help="Examiner puis approuver le plan en attente")
    approve.add_argument("--project", type=Path, default=Path.cwd())
    code = commands.add_parser("code", help="Générer une proposition pour une tâche du plan approuvé")
    code.add_argument("--project", type=Path, default=Path.cwd())
    code.add_argument("--task-id", required=True)
    verify = commands.add_parser("verify", help="Exécuter une commande exacte de la liste autorisée")
    verify.add_argument("--project", type=Path, default=Path.cwd())
    verify.add_argument("--task-id", required=True)
    verify.add_argument("--command", required=True)
    apply_cmd = commands.add_parser("apply", help="Prévisualiser puis approuver une proposition JSON")
    apply_cmd.add_argument("proposal", type=Path)
    apply_cmd.add_argument("--project", type=Path, default=Path.cwd())
    apply_cmd.add_argument("--task-id", required=True)
    return parser


def _init(project: Path) -> int:
    project.mkdir(parents=True, exist_ok=True)
    config_path = _config_path(project)
    if config_path.exists():
        print(f"Configuration déjà présente : {config_path}")
    else:
        template = Path(__file__).resolve().parents[2] / "config.example.toml"
        if not template.is_file():
            raise ConfigurationError("Modèle config.example.toml introuvable à côté du paquet source.")
        shutil.copyfile(template, config_path)
        print(f"Configuration créée : {config_path}")
    progress_path = _progress_path(project)
    if progress_path.exists():
        print(f"Progression déjà présente : {progress_path}")
    else:
        project_id = re.sub(r"[^a-z0-9-]+", "-", project.name.casefold()).strip("-") or "codelix-project"
        ProgressStore(progress_path).save({
            "schema_version": "1.0",
            "project_id": project_id,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tasks": [],
        })
        print(f"Progression initialisée : {progress_path}")
    print("Aucune clé ni aucun modèle n'a été copié. Configurez .env et codelix.toml localement.")
    return 0


def _status(project: Path) -> int:
    data = ProgressStore(_progress_path(project)).load()
    print(f"Projet : {data['project_id']} — {len(data['tasks'])} tâche(s)")
    for task in data["tasks"]:
        print(f"[{task['status']}] {task['id']} — {task['title']} (tentatives: {task['attempts']}/2)")
        if task["last_result"]:
            print(f"  Résultat : {task['last_result']}")
    if not data["tasks"]:
        print("Aucune tâche enregistrée.")
    return 0


def _config(project: Path) -> int:
    config = load_config(_config_path(project))
    print("Configuration valide.")
    print("Fournisseurs configurés : " + (", ".join(sorted(config.providers)) or "aucun"))
    for role, candidates in config.models.items():
        print(f"{role}: " + (", ".join(candidates) or "aucun modèle activé"))
    print(f"Commandes de vérification autorisées : {len(config.allowed_commands)}")
    return 0


def _plan_path(project: Path) -> Path:
    return _cache_file(project, "plan.json")


def _cache_file(project: Path, *parts: str) -> Path:
    relative = validate_relative_path(".codelix-cache/" + "/".join(parts))
    root = project.resolve(strict=True)
    candidate = root.joinpath(*relative.split("/"))
    cursor = root
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.exists() and (cursor.is_symlink() or cursor.is_junction()):
            raise WorkflowError("Un lien ou une jonction interdit l'accès au cache Codelix.")
    if not candidate.resolve(strict=False).is_relative_to(root):
        raise WorkflowError("Le cache Codelix sort de la racine du projet.")
    return candidate


def _plan(project: Path, request: str) -> int:
    config = load_config(_config_path(project))
    progress = ProgressStore(_progress_path(project)).load()
    router = build_router(config)
    plan = CodelixWorkflow(config, router, progress["project_id"]).create_plan(request)
    plan_path = _plan_path(project)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Plan généré et enregistré en attente d'approbation :")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _approve_plan(project: Path) -> int:
    path = _plan_path(project)
    try:
        plan = validate_planner_output(json.loads(path.read_text(encoding="utf-8")), expected_project_id=ProgressStore(_progress_path(project)).load()["project_id"])
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("Aucun plan valide en attente. Lancez d'abord codelix plan.") from exc
    print(f"Plan proposé : {plan['request_summary']}")
    for task in plan["tasks"]:
        print(f"- [{task['id']}] {task['title']} — rôle: {task['role']} — priorité: {task['priority']}")
        for criterion in task["acceptance_criteria"]:
            print(f"    Critère : {criterion}")
    try:
        answer = input("Approuver et ajouter ces tâches à la progression ? [o/N] ").strip().casefold()
    except EOFError:
        answer = ""
    if answer not in {"o", "oui", "y", "yes"}:
        print("Plan refusé ; aucune tâche ajoutée.")
        return 0
    store = ProgressStore(_progress_path(project))
    progress = store.load()
    current_ids = {task["id"] for task in progress["tasks"]}
    if current_ids.intersection(task["id"] for task in plan["tasks"]):
        raise WorkflowError("Le plan contient un identifiant déjà utilisé dans la progression.")
    for task in plan["tasks"]:
        progress["tasks"].append({
            "id": task["id"], "title": task["title"], "status": "todo",
            "dependencies": task["dependencies"], "acceptance_criteria": task["acceptance_criteria"],
            "attempts": 0, "files_modified": [], "verifications": [], "last_result": "Plan approuvé.",
        })
    progress["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.save(progress)
    print("Plan approuvé et tâches ajoutées à la progression.")
    return 0


def _code(project: Path, task_id: str) -> int:
    config = load_config(_config_path(project))
    try:
        plan = json.loads(_plan_path(project).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("Plan approuvé introuvable ou invalide.") from exc
    progress = ProgressStore(_progress_path(project)).load()
    progress_task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
    if progress_task is None:
        raise WorkflowError(f"Tâche non approuvée : {task_id}.")
    if progress_task["status"] not in {"todo", "needs_review"}:
        raise WorkflowError("La tâche doit être en attente ou en revue après une vérification échouée.")
    correction = progress_task["status"] == "needs_review"
    if correction and progress_task["attempts"] >= config.runtime.correction_attempts:
        raise WorkflowError("La limite de corrections est atteinte ; la tâche reste en revue.")
    task = next((item for item in plan["tasks"] if item["id"] == task_id), None)
    if task is None or task["role"] not in {"coder", "tester"}:
        raise WorkflowError("La tâche approuvée n'est pas une tâche de génération de fichiers.")
    feedback = []
    if correction and progress_task["verifications"]:
        feedback = progress_task["verifications"][-1].get("errors", [])
    task = {**task, "affected_paths": plan["affected_paths"], "verification_feedback": feedback}
    proposal = CodelixWorkflow(config, build_router(config), progress["project_id"]).create_code_proposal(task, project)
    proposal_id = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:20]
    proposal_path = _cache_file(project, "proposals", f"{proposal_id}.json")
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if correction:
        progress_task["attempts"] += 1
        progress_task["last_result"] = f"Correction {progress_task['attempts']}/{config.runtime.correction_attempts} générée ; en attente d'approbation."
        progress["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ProgressStore(_progress_path(project)).save(progress)
    manager = ExecutionManager(project, max_file_bytes=config.runtime.max_file_bytes)
    snapshots = manager.inspect([item["path"] for item in proposal["files"]])
    preview = manager.preview(proposal, expected_task_id=task_id, snapshots=snapshots)
    print("Proposition validée et prévisualisée (aucune écriture effectuée) :")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    print(f"Détail JSON : {proposal_path}")
    print("Pour approuver l'écriture : codelix apply " + str(proposal_path) + f" --task-id {task_id}")
    return 0


def _record(project: Path, task_id: str, result: dict[str, object], *, status: str | None = None, files: list[str] | None = None) -> None:
    store = ProgressStore(_progress_path(project))
    progress = store.load()
    task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise ProgressError(f"Tâche inconnue : {task_id}.")
    task["verifications"].append(result)
    task["last_result"] = str(result.get("summary", result.get("status", "Résultat enregistré.")))[:500]
    if status:
        task["status"] = status
    if files:
        task["files_modified"] = list(dict.fromkeys([*task["files_modified"], *files]))
    progress["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.save(progress)


def _verify(project: Path, task_id: str, command: str) -> int:
    config = load_config(_config_path(project))
    progress = ProgressStore(_progress_path(project)).load()
    task = next((item for item in progress["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise ProgressError(f"Tâche inconnue : {task_id}.")
    result = Verifier(project, config.allowed_commands, timeout_seconds=config.runtime.request_timeout_seconds).run(
        command, acceptance_criteria=task["acceptance_criteria"]
    )
    _record(project, task_id, result.as_dict(), status=None if result.passed else "needs_review")
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


def _apply(project: Path, proposal_path: Path, task_id: str) -> int:
    config = load_config(_config_path(project))
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionError("La proposition JSON est illisible ou invalide.") from exc
    manager = ExecutionManager(project, max_file_bytes=config.runtime.max_file_bytes)
    file_paths = [item.get("path") for item in proposal.get("files", []) if isinstance(item, dict)] if isinstance(proposal, dict) else []
    if not file_paths or any(not isinstance(item, str) for item in file_paths):
        raise ExecutionError("La proposition doit contenir des fichiers à prévisualiser.")
    snapshots = manager.inspect(file_paths)
    preview = manager.preview(proposal, expected_task_id=task_id, snapshots=snapshots)
    print("Aperçu des changements :")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    try:
        answer = input("Appliquer ces fichiers et créer un point de retour ? [o/N] ").strip().casefold()
    except EOFError:
        answer = ""
    if answer not in {"o", "oui", "y", "yes"}:
        print("Application annulée ; aucun fichier modifié.")
        return 0
    result = manager.apply(proposal, expected_task_id=task_id, snapshots=snapshots, approved=True)
    record = {
        "command": "codelix apply",
        "exit_code": 0,
        "summary": f"Fichiers appliqués : {', '.join(result.written)}",
        "errors": [],
        "execution_id": result.backup_id,
        "acceptance_criteria": [],
    }
    _record(project, task_id, record, status="in_progress", files=list(result.written))
    print(f"Application terminée. Point de retour : {result.backup_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "init":
            return _init(args.project.resolve())
        project = args.project.resolve(strict=True)
        if args.action == "status":
            return _status(project)
        if args.action == "config":
            return _config(project)
        if args.action == "plan":
            return _plan(project, args.request)
        if args.action == "approve-plan":
            return _approve_plan(project)
        if args.action == "code":
            return _code(project, args.task_id)
        if args.action == "verify":
            return _verify(project, args.task_id, args.command)
        if args.action == "apply":
            return _apply(project, args.proposal.resolve(strict=True), args.task_id)
    except (OSError, ValueError, ConfigurationError, ExecutionError, ProgressError, VerificationError, WorkflowError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
