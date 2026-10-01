"""Interface de commande initiale de Vybelix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigurationError, load_config, validate_config
from .execution import ExecutionError, ExecutionManager
from .progress import ProgressError, ProgressStore
from .verifier import VerificationError, Verifier
from .providers.router import build_router
from .workflow import VybelixWorkflow, WorkflowError
from .contracts import validate_planner_output, validate_relative_path
from .paths import project_cache_root, project_config_path
from .ui import run_ui
from .skills import PermissionManager, SkillError, SkillManager
from .project_context import ProjectContextError, ProjectContextStore


def _progress_path(project: Path) -> Path:
    return project / "docs" / "progress" / "tasks.json"


def _config_path(project: Path) -> Path:
    return project_config_path(project)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vybelix", description="Orchestrateur local de développement assisté par IA")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Initialiser un projet Vybelix local")
    init.add_argument("project", type=Path, nargs="?", default=Path.cwd())
    status = commands.add_parser("status", help="Afficher les tâches du projet")
    status.add_argument("--project", type=Path, default=Path.cwd())
    resume = commands.add_parser("resume", help="Reprendre une tâche bloquée ou interrompue après confirmation")
    resume.add_argument("--project", type=Path, default=Path.cwd())
    resume.add_argument("--task-id", required=True)
    context=commands.add_parser("context",help="Afficher ou enregistrer le contexte compact du projet")
    context_commands=context.add_subparsers(dest="context_action",required=True)
    for action,help_text in (("show","Afficher le contexte local"),("update","Valider et enregistrer un contexte JSON")):
        sub=context_commands.add_parser(action,help=help_text);sub.add_argument("--project",type=Path,default=Path.cwd())
    context_commands.choices["update"].add_argument("source",type=Path)
    config = commands.add_parser("config", help="Valider la configuration et afficher les routes")
    config.add_argument("--project", type=Path, default=Path.cwd())
    level = commands.add_parser("level", help="Afficher ou modifier le niveau d'explications")
    level.add_argument("value", choices=("beginner", "intermediate", "pro"))
    level.add_argument("--project", type=Path, default=Path.cwd())
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
    apply_cmd.add_argument("--explain", action="store_true", help="Afficher l'explication du changement après application")
    undo = commands.add_parser("undo", help="Annuler le dernier changement Vybelix sans écraser de modifications externes")
    undo.add_argument("--project", type=Path, default=Path.cwd())
    skills = commands.add_parser("skills", help="Créer, valider et gérer les skills locaux")
    skill_commands = skills.add_subparsers(dest="skills_action", required=True)
    for action, help_text in [("list", "Lister le registre local"), ("create", "Créer un brouillon de skill"), ("validate", "Valider un dossier sans l’exécuter"), ("install", "Installer un dossier local inactif"), ("update", "Mettre à jour depuis un package local"), ("test", "Lancer les contrôles statiques sans exécuter le code"), ("dependencies", "Vérifier les dépendances installées"), ("configure", "Valider et enregistrer une configuration JSON"), ("enable", "Activer après approbation"), ("disable", "Désactiver"), ("uninstall", "Désinstaller")]:
        sub = skill_commands.add_parser(action, help=help_text)
        sub.add_argument("--project", type=Path, default=Path.cwd())
    skill_commands.choices["create"].add_argument("id")
    skill_commands.choices["create"].add_argument("--name", required=True)
    skill_commands.choices["create"].add_argument("--description", required=True)
    skill_commands.choices["create"].add_argument("--author", default="Unknown")
    skill_commands.choices["create"].add_argument("--license", dest="license_name", default="Unknown")
    for action in ("validate", "install", "update"):
        skill_commands.choices[action].add_argument("source", type=Path)
    for action in ("enable", "disable", "uninstall", "test", "dependencies"):
        skill_commands.choices[action].add_argument("id")
    skill_commands.choices["configure"].add_argument("id")
    skill_commands.choices["configure"].add_argument("config", type=Path, help="Fichier JSON local contenant les valeurs à valider")
    ui = commands.add_parser("ui", help="Ouvrir le cockpit Vybelix local")
    ui.add_argument("--project", type=Path, default=Path.cwd())
    ui.add_argument("--port", type=int, default=0, help="Port local (0 = port libre automatique)")
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
        project_id = re.sub(r"[^a-z0-9-]+", "-", project.name.casefold()).strip("-") or "vybelix-project"
        ProgressStore(progress_path).save({
            "schema_version": "1.0",
            "project_id": project_id,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tasks": [],
        })
        print(f"Progression initialisée : {progress_path}")
    print("Aucune clé ni aucun modèle n'a été copié. Configurez .env et vybelix.toml localement.")
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


def _resume(project: Path, task_id: str) -> int:
    store=ProgressStore(_progress_path(project)); progress=store.load()
    task=next((item for item in progress["tasks"] if item["id"]==task_id),None)
    if task is None: raise ProgressError(f"Tâche inconnue : {task_id}.")
    if task["status"] not in {"blocked","interrupted"}:
        raise ProgressError(f"Seules les tâches blocked/interrupted peuvent être reprises; état actuel : {task['status']}.")
    states={item["id"]:item["status"] for item in progress["tasks"]}
    waiting=[dependency for dependency in task["dependencies"] if states.get(dependency)!="done"]
    if waiting:
        raise ProgressError("Reprise impossible; dépendances non terminées : "+", ".join(waiting)+".")
    print(f"Tâche : {task['title']} ({task_id})")
    print(f"État : {task['status']} · tentatives conservées : {task['attempts']}/2")
    try: answer=input("Remettre la tâche en attente ? Aucun agent ne sera lancé par cette commande. [o/N] ").strip().casefold()
    except EOFError: answer=""
    if answer not in {"o","oui","y","yes"}:
        print("Reprise annulée; progression inchangée."); return 0
    previous=task["status"]
    task["status"]="todo"
    task["last_result"]=(f"Tâche reprise explicitement depuis {previous}; aucune génération lancée.")
    progress["updated_at"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.save(progress)
    print(f"{task_id} est de nouveau en attente. Lance vybelix code --task-id {task_id} lorsque tu veux reprendre le travail.")
    return 0


def _context_command(args:argparse.Namespace,project:Path)->int:
    progress=ProgressStore(_progress_path(project)).load()
    store=ProjectContextStore(_cache_file(project,"context.json"),progress["project_id"])
    if args.context_action=="show":
        print(json.dumps(store.load(),ensure_ascii=False,indent=2));return 0
    source=args.source
    if source.is_symlink() or bool(getattr(source,"is_junction",lambda:False)()) or not source.is_file():
        raise ProjectContextError("Le fichier JSON source est introuvable ou est un lien symbolique.")
    if source.stat().st_size>64_000:raise ProjectContextError("Le fichier JSON source dépasse 64 Ko.")
    try: value=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise ProjectContextError("Le fichier JSON source est invalide.") from exc
    saved=store.save(value)
    print("Contexte local validé et enregistré (sans appel modèle) :")
    print(json.dumps(saved,ensure_ascii=False,indent=2));return 0


def _config(project: Path) -> int:
    config = load_config(_config_path(project))
    print("Configuration valide.")
    print("Fournisseurs configurés : " + (", ".join(sorted(config.providers)) or "aucun"))
    for role, candidates in config.models.items():
        print(f"{role}: " + (", ".join(candidates) or "aucun modèle activé"))
    print(f"Commandes de vérification autorisées : {len(config.allowed_commands)}")
    print(f"Niveau utilisateur : {config.user_level}")
    return 0


def _plan_path(project: Path) -> Path:
    return _cache_file(project, "plan.json")


def _cache_file(project: Path, *parts: str) -> Path:
    cache_root = project_cache_root(project)
    relative = validate_relative_path(cache_root.name + "/" + "/".join(parts))
    root = project.resolve(strict=True)
    candidate = root.joinpath(*relative.split("/"))
    cursor = root
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.exists() and (cursor.is_symlink() or cursor.is_junction()):
            raise WorkflowError("Un lien ou une jonction interdit l'accès au cache Vybelix.")
    if not candidate.resolve(strict=False).is_relative_to(root):
        raise WorkflowError("Le cache Vybelix sort de la racine du projet.")
    return candidate


def _set_level(project: Path, level: str) -> int:
    path = _config_path(project)
    original = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    user_match = re.search(r"(?m)^\[user\][ \t]*$", original)
    if user_match:
        next_section = re.search(r"(?m)^\[[^\r\n]+\][ \t]*$", original[user_match.end():])
        end = user_match.end() + next_section.start() if next_section else len(original)
        block = original[user_match.end():end]
        level_match = re.search(r"(?m)^[ \t]*level[ \t]*=.*$", block)
        if level_match:
            block = block[:level_match.start()] + f"level = \"{level}\"" + block[level_match.end():]
        else:
            block = newline + f"level = \"{level}\"" + block
        selected_match = re.search(r"(?m)^[ \t]*level_selected[ \t]*=.*$", block)
        if selected_match:
            block = block[:selected_match.start()] + "level_selected = true" + block[selected_match.end():]
        else:
            block += ("" if block.endswith(("\n", "\r")) else newline) + "level_selected = true" + newline
        updated = original[:user_match.end()] + block + original[end:]
    else:
        updated = original.rstrip() + newline + newline + "[user]" + newline + f"level = \"{level}\"" + newline + "level_selected = true" + newline
    validate_config(__import__("tomllib").loads(updated))
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Niveau utilisateur enregistré : {level}")
    return 0


def _plan(project: Path, request: str) -> int:
    config = load_config(_config_path(project))
    progress = ProgressStore(_progress_path(project)).load()
    router = build_router(config)
    plan = VybelixWorkflow(config, router, progress["project_id"]).create_plan(request)
    plan_path = _plan_path(project)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Plan généré et enregistré en attente d'approbation :")
    if config.user_level == "beginner":
        print("Résumé : " + (plan.get("plain_summary") or plan["request_summary"]))
        print("Étapes proposées :")
        for item in plan["tasks"]:
            print(f"- {item['title']}")
    elif config.user_level == "pro":
        print(f"Demande : {plan['request_summary']}")
        for item in plan["tasks"]:
            dependencies = ", ".join(item["dependencies"]) or "aucune"
            print(f"- [{item['id']}] {item['role']} P{item['priority']} — {item['title']} (dépend de : {dependencies})")
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _approve_plan(project: Path) -> int:
    path = _plan_path(project)
    try:
        plan = validate_planner_output(json.loads(path.read_text(encoding="utf-8")), expected_project_id=ProgressStore(_progress_path(project)).load()["project_id"])
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("Aucun plan valide en attente. Lancez d'abord vybelix plan.") from exc
    level = load_config(_config_path(project)).user_level
    summary = plan.get("plain_summary") if level == "beginner" else None
    print(f"Plan proposé : {summary or plan['request_summary']}")
    for task in plan["tasks"]:
        if level == "beginner":
            print(f"- Étape {task['id']} : {task['title']}")
        elif level == "pro":
            dependencies = ", ".join(task["dependencies"]) or "aucune"
            print(f"- [{task['id']}] {task['role']} P{task['priority']} — {task['title']} — dépend de : {dependencies}")
        else:
            print(f"- [{task['id']}] {task['title']} — rôle: {task['role']} — priorité: {task['priority']}")
        for criterion in task["acceptance_criteria"]:
            label = "À vérifier" if level == "beginner" else "Critère"
            print(f"    {label} : {criterion}")
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
    proposal = VybelixWorkflow(config, build_router(config), progress["project_id"]).create_code_proposal(task, project)
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
    print("Pour approuver l'écriture : vybelix apply " + str(proposal_path) + f" --task-id {task_id}")
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
    if config.user_level == "beginner":
        print("Vérification réussie." if result.passed else "Vérification échouée.")
        print(result.summary)
        if result.errors:
            print("Détails à corriger :")
            for error in result.errors:
                print(f"- {error}")
    else:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


def _print_explanation(explanation: object) -> None:
    if not isinstance(explanation, dict):
        print("Aucune explication structurée n'a été fournie par le Coder.")
        return
    print("Ce qui a changé :")
    for item in explanation.get("what_changed", []):
        print(f"- {item}")
    print("Pourquoi : " + str(explanation.get("why", "")))
    print("Comment vérifier :")
    for item in explanation.get("how_to_verify", []):
        print(f"- {item}")


def _apply(project: Path, proposal_path: Path, task_id: str, *, explain: bool = False) -> int:
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
        "command": "vybelix apply",
        "exit_code": 0,
        "summary": f"Fichiers appliqués : {', '.join(result.written)}",
        "errors": [],
        "execution_id": result.backup_id,
        "acceptance_criteria": [],
    }
    _record(project, task_id, record, status="in_progress", files=list(result.written))
    print(f"Application terminée. Point de retour : {result.backup_id}")
    if config.user_level == "beginner" or explain:
        _print_explanation(proposal.get("explanation"))
    return 0


def _undo(project: Path) -> int:
    config = load_config(_config_path(project))
    manager = ExecutionManager(project, max_file_bytes=config.runtime.max_file_bytes)
    preview = manager.preview_latest_undo()
    if not preview.files:
        print("Aucune annulation disponible.")
        return 0
    print("Fichiers qui seront restaurés :")
    for item in preview.files:
        print(f"- {item}")
    try:
        answer = input("Confirmer cette annulation ? [o/N] ").strip().casefold()
    except EOFError:
        answer = ""
    if answer not in {"o", "oui", "y", "yes"}:
        print("Annulation refusée ; aucun fichier modifié.")
        return 0
    restored = manager.undo_latest(expected_backup_id=preview.backup_id)
    print("Annulation appliquée : " + ", ".join(restored))
    return 0


def _confirm_skill(prompt: str) -> bool:
    try:
        return input(prompt + " [o/N] ").strip().casefold() in {"o", "oui", "y", "yes"}
    except EOFError:
        return False


def _skills_command(args: argparse.Namespace, project: Path) -> int:
    manager = SkillManager(project)
    if args.skills_action == "list":
        print(json.dumps(manager.list_installed(), ensure_ascii=False, indent=2))
        return 0
    if args.skills_action == "create":
        path = manager.create_draft(args.id, name=args.name, description=args.description, author=args.author, license_name=args.license_name)
        print(f"Brouillon inerte créé : {path}")
        print("Complète les fichiers puis lance `vybelix skills validate`.")
        return 0
    if args.skills_action == "validate":
        result = manager.validate(args.source)
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.valid else 1
    if args.skills_action == "install":
        result = manager.validate(args.source)
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        if not result.valid or not result.skill:
            return 1
        print("Permissions demandées :")
        if not result.skill["permissions"]:
            print("  aucune")
        for permission in result.skill["permissions"]:
            details = PermissionManager.describe(permission)
            print(f"  - {permission} (niveau {details['level']}, risque {details['risk']})")
        if not _confirm_skill("Installer ce skill sans l’activer ni exécuter son code ?"):
            print("Installation annulée.")
            return 0
        entry = manager.install_local(args.source, approved=True)
        print(f"{entry['id']} {entry['version']} installé à l’état désactivé.")
        return 0
    if args.skills_action == "update":
        result=manager.validate(args.source)
        print(json.dumps(result.as_dict(),ensure_ascii=False,indent=2))
        if not result.valid or not result.skill:return 1
        if not _confirm_skill(f"Installer {result.skill['id']} v{result.skill['version']} comme nouvelle version désactivée ?"):
            print("Mise à jour annulée."); return 0
        entry=manager.update_local(args.source,approved=True)
        print(f"{entry['id']} mis à jour vers {entry['version']} et désactivé pour revue.")
        return 0
    if args.skills_action == "test":
        result=manager.test(args.id); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result["passed"] else 1
    if args.skills_action == "dependencies":
        result=manager.dependency_status(args.id); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if all(item["available"] for item in result) else 1
    if args.skills_action == "configure":
        if args.config.is_symlink() or not args.config.is_file(): raise SkillError("Fichier JSON de configuration invalide.")
        try: values=json.loads(args.config.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc: raise SkillError("Fichier JSON de configuration invalide.") from exc
        result=manager.configure(args.id,values); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    if args.skills_action == "enable":
        entry = next((item for item in manager.list_installed() if item["id"] == args.id), None)
        if entry is None:
            raise SkillError(f"Skill non installé : {args.id}.")
        if entry["status"] in {"tampered", "missing"}:
            raise SkillError("Intégrité invalide; activation refusée.")
        permissions = entry["permissions"]
        print("Permissions demandées : " + (", ".join(permissions) if permissions else "aucune"))
        if not _confirm_skill("Approuver exactement ces permissions et activer ?"):
            print("Activation annulée.")
            return 0
        enabled = manager.enable(args.id, approved_permissions=set(permissions))
        print(f"{enabled['id']} activé; aucun adapter n’est exécuté par cette version.")
        return 0
    if args.skills_action == "disable":
        entry = manager.disable(args.id)
        print(f"{entry['id']} désactivé.")
        return 0
    if args.skills_action == "uninstall":
        if not _confirm_skill(f"Désinstaller {args.id} et supprimer sa copie locale ?"):
            print("Désinstallation annulée.")
            return 0
        manager.uninstall(args.id, approved=True)
        print(f"{args.id} désinstallé.")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "init":
            return _init(args.project.resolve())
        project = args.project.resolve(strict=True)
        if args.action == "skills":
            return _skills_command(args, project)
        if args.action == "ui":
            if not 0 <= args.port <= 65535:
                raise ValueError("Le port doit être compris entre 0 et 65535.")
            run_ui(project, port=args.port)
            return 0
        if args.action == "status":
            return _status(project)
        if args.action == "resume":
            return _resume(project,args.task_id)
        if args.action == "context":
            return _context_command(args,project)
        if args.action == "config":
            return _config(project)
        if args.action == "level":
            return _set_level(project, args.value)
        if args.action == "undo":
            return _undo(project)
        if args.action == "plan":
            return _plan(project, args.request)
        if args.action == "approve-plan":
            return _approve_plan(project)
        if args.action == "code":
            return _code(project, args.task_id)
        if args.action == "verify":
            return _verify(project, args.task_id, args.command)
        if args.action == "apply":
            return _apply(project, args.proposal.resolve(strict=True), args.task_id, explain=args.explain)
    except (OSError, ValueError, ConfigurationError, ExecutionError, ProgressError, ProjectContextError, VerificationError, WorkflowError, SkillError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
