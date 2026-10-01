"""Registre et validation locale des skills. Aucun code de skill n’est exécuté."""
from __future__ import annotations
import hashlib, importlib.metadata, json, os, re, shutil, stat, threading, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from ..contracts import validate_relative_path
from .. import __version__
from ..paths import project_cache_root

class SkillError(RuntimeError):
    """Opération Skill Manager invalide ou refusée."""

KNOWN_PERMISSIONS = {
    "filesystem.read": {"level": 0, "risk": "low"},
    "network.read": {"level": 1, "risk": "low"},
    "network.write": {"level": 2, "risk": "medium"},
    "filesystem.write": {"level": 2, "risk": "medium"},
    "process.execute": {"level": 3, "risk": "high"},
    "credentials.read": {"level": 4, "risk": "critical"},
    "browser.session": {"level": 4, "risk": "critical"},
}
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_CAP = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_FORBIDDEN_DIRS = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv"}
_FORBIDDEN_SUFFIXES = {".env", ".pem", ".p12", ".pfx", ".key", ".keystore", ".exe", ".dll", ".so", ".dylib", ".msi"}
_TEXT = {".md", ".json", ".py", ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".sh", ".ps1", ".bat", ".cmd", ".xml", ".html", ".js", ".ts", ".css"}
_MAX_FILES, _MAX_FILE, _MAX_TOTAL = 512, 1_048_576, 8_388_608
_SECRETS = [re.compile(p) for p in (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)\bAIza[0-9A-Za-z_-]{25,}\b", r"\bnvapi-[A-Za-z0-9_-]{20,}\b",
    r"\bgsk_[A-Za-z0-9_-]{20,}\b", r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*['\"]([A-Za-z0-9_./+=-]{24,})['\"]",
)]

@dataclass(frozen=True)
class SkillValidation:
    valid: bool
    skill: dict[str, Any] | None
    errors: tuple[dict[str, str], ...]
    warnings: tuple[dict[str, str], ...]
    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "skill": self.skill, "errors": list(self.errors), "warnings": list(self.warnings)}

class PermissionManager:
    """Autorisation explicite; aucune permission n’est accordée implicitement."""
    @staticmethod
    def check(requested: list[str], granted: list[str]) -> tuple[bool, list[str]]:
        denied = (set(requested) - set(granted)) | (set(requested) - KNOWN_PERMISSIONS.keys())
        denied |= set(granted) - set(requested)
        return not denied, sorted(denied)
    @staticmethod
    def describe(permission: str) -> dict[str, Any] | None:
        value = KNOWN_PERMISSIONS.get(permission)
        return {"id": permission, **value} if value else None

class SkillManager:
    """Création de brouillons, validation et registre des packages locaux inertes."""
    def __init__(self, project: Path):
        try: self.project = project.resolve(strict=True)
        except OSError as exc: raise SkillError("Le dossier du projet est introuvable.") from exc
        if not self.project.is_dir() or _path_has_link(project): raise SkillError("Le projet doit être un dossier local valide.")
        self.cache = project_cache_root(self.project)
        if _is_link(self.cache): raise SkillError("Le cache projet ne peut pas être un lien.")
        self.home = self.cache / "skills"
        self.installed = self.home / "installed"
        self.registry_path = self.home / "registry.json"
        self.audit_path = self.home / "audit.jsonl"
        self._lock = threading.RLock()

    def create_draft(self, skill_id: str, *, name: str, description: str, author: str = "Unknown", license_name: str = "Unknown", version: str = "0.1.0") -> Path:
        if not _valid_id(skill_id): raise SkillError("ID invalide : minuscules, chiffres et tirets uniquement.")
        if not name.strip() or not description.strip(): raise SkillError("Le nom et la description sont obligatoires.")
        if not _SEMVER.fullmatch(version): raise SkillError("La version doit suivre MAJOR.MINOR.PATCH.")
        skills_root = self.project / "skills"
        if _is_link(skills_root): raise SkillError("Le dossier skills ne peut pas être un lien.")
        target = skills_root / skill_id
        if target.exists(): raise SkillError(f"Le skill {skill_id} existe déjà.")
        skills_root.mkdir(parents=True, exist_ok=True); target.mkdir()
        manifest = {"schema_version":"1.0", "id":skill_id, "name":name.strip(), "version":version,
                    "description":description.strip(), "author":author.strip() or "Unknown", "license":license_name,
                    "capabilities":[], "permissions":[], "dependencies":[]}
        caps = {"schema_version":"1.0", "capabilities":[]}
        (target/"skill.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (target/"capabilities.json").write_text(json.dumps(caps,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (target/"SKILL.md").write_text(f"# {name.strip()}\n\n{description.strip()}\n\n## Instructions\n\nDécris la capacité, ses entrées, sorties et limites.\n",encoding="utf-8")
        self._audit("SKILL_DRAFT_CREATED",skill_id,version=version,license=license_name)
        return target

    def validate(self, source: Path) -> SkillValidation:
        errors: list[dict[str,str]]=[]; warnings: list[dict[str,str]]=[]
        try:
            if _path_has_link(source): raise SkillError("La source du skill ne peut pas passer par un lien symbolique.")
            package=source.resolve(strict=True)
            if not package.is_dir(): raise SkillError("La source du skill doit être un dossier.")
            files=_files(package,errors)
            manifest=_read_json(package/"skill.json",errors)
            caps=_read_json(package/"capabilities.json",errors)
            if manifest is None or caps is None: return SkillValidation(False,None,tuple(errors),tuple(warnings))
            result=_validate_manifest(manifest,caps,package,files,errors,warnings)
            _scan_secrets(package,files,errors)
            code_suffixes={".py",".sh",".ps1",".bat",".cmd"}
            if any(p.suffix.casefold() in code_suffixes for p in files):
                warnings.append(_issue("CODE_INERT","Le code est inspecté mais jamais exécuté par cette version.","warning"))
            return SkillValidation(not errors,result,tuple(errors),tuple(warnings))
        except (OSError,ValueError,TypeError,SkillError) as exc:
            errors.append(_issue("SOURCE_UNAVAILABLE",str(exc)))
            return SkillValidation(False,None,tuple(errors),tuple(warnings))

    def list_installed(self) -> list[dict[str,Any]]:
        with self._lock:
            result=[]
            for entry in self._registry()["skills"]:
                path=self._installed_path(entry["id"],entry["version"]); status=entry["status"]
                if not path.is_dir() or _is_link(path): status="missing"
                else:
                    try:
                        if _tree_digest(path)!=entry.get("sha256"): status="tampered"
                    except (OSError,SkillError): status="tampered"
                result.append({**entry,"status":status})
            return result

    def install_local(self, source: Path, *, approved: bool=False) -> dict[str,Any]:
        if not approved: raise SkillError("L’installation nécessite une approbation explicite.")
        validation=self.validate(source)
        if not validation.valid or not validation.skill:
            raise SkillError("Skill refusé : "+"; ".join(e["message"] for e in validation.errors))
        meta=validation.skill; sid=meta["id"]; version=meta["version"]
        with self._lock:
            registry=self._registry()
            if any(x["id"]==sid for x in registry["skills"]): raise SkillError(f"{sid} est déjà installé; les mises à jour ne sont pas encore disponibles.")
            self.installed.mkdir(parents=True,exist_ok=True)
            if _is_link(self.installed): raise SkillError("Le dossier d’installation ne peut pas être un lien.")
            id_dir=self.installed/sid
            if _is_link(id_dir): raise SkillError("Le dossier cible ne peut pas être un lien.")
            id_dir.mkdir(exist_ok=True); target=self._installed_path(sid,version)
            if target.exists(): raise SkillError("La version cible existe déjà.")
            stage=id_dir/f".{version}.{uuid.uuid4().hex}.tmp"
            try:
                shutil.copytree(Path(source).resolve(strict=True),stage,symlinks=True)
                copied=self.validate(stage)
                if not copied.valid or not copied.skill or copied.skill["id"]!=sid: raise SkillError("La copie n’a pas passé la validation.")
                digest=_tree_digest(stage); os.replace(stage,target)
                entry={"id":sid,"name":meta["name"],"version":version,"description":meta["description"],"license":meta["license"],"source":"local","status":"disabled","permissions":meta["permissions"],"granted_permissions":[],"installed_at":_now(),"sha256":digest}
                registry["skills"].append(entry); self._save_registry(registry)
            except Exception:
                if stage.exists(): shutil.rmtree(stage,ignore_errors=True)
                if target.exists(): shutil.rmtree(target,ignore_errors=True)
                raise
            self._audit("SKILL_INSTALLED",sid,version=version,status="disabled")
            return dict(entry)

    def update_local(self, source: Path, *, approved: bool=False) -> dict[str,Any]:
        """Install a strictly newer local version, disabled until reviewed again."""
        if not approved: raise SkillError("La mise à jour nécessite une approbation explicite.")
        validation=self.validate(source)
        if not validation.valid or not validation.skill:
            raise SkillError("Mise à jour refusée : "+"; ".join(e["message"] for e in validation.errors))
        meta=validation.skill; sid=meta["id"]; version=meta["version"]
        with self._lock:
            registry=self._registry(); current=_entry(registry,sid)
            if _version_tuple(version) is None or _version_tuple(version) <= _version_tuple(current["version"]):
                raise SkillError("La mise à jour doit avoir une version MAJOR.MINOR.PATCH plus récente.")
            self.installed.mkdir(parents=True,exist_ok=True)
            id_dir=self.installed/sid
            if _is_link(id_dir): raise SkillError("Le dossier cible ne peut pas être un lien.")
            id_dir.mkdir(exist_ok=True)
            target=self._installed_path(sid,version)
            if target.exists(): raise SkillError("Cette version est déjà présente.")
            stage=id_dir/f".{version}.{uuid.uuid4().hex}.tmp"
            try:
                shutil.copytree(Path(source).resolve(strict=True),stage,symlinks=True)
                copied=self.validate(stage)
                if not copied.valid or not copied.skill or copied.skill["id"]!=sid or copied.skill["version"]!=version:
                    raise SkillError("La copie de mise à jour n’a pas passé la validation.")
                digest=_tree_digest(stage); os.replace(stage,target)
                entry={"id":sid,"name":meta["name"],"version":version,"description":meta["description"],
                       "license":meta["license"],"source":"local","status":"disabled","permissions":meta["permissions"],
                       "granted_permissions":[],"installed_at":_now(),"sha256":digest}
                registry["skills"]=[entry if item["id"]==sid else item for item in registry["skills"]]
                self._save_registry(registry)
            except Exception:
                if stage.exists(): shutil.rmtree(stage,ignore_errors=True)
                if target.exists(): shutil.rmtree(target,ignore_errors=True)
                raise
            self._audit("SKILL_UPDATED",sid,version=version,status="disabled")
            return dict(entry)

    def dependency_status(self, skill_id: str) -> list[dict[str,Any]]:
        entry=_entry(self._registry(),skill_id)
        path=self._installed_path(skill_id,entry["version"])
        validation=self.validate(path)
        if not validation.valid or not validation.skill: raise SkillError("Skill invalide; dépendances indisponibles.")
        return _dependency_status(validation.skill["dependencies"])

    def test(self, skill_id: str) -> dict[str,Any]:
        """Run safe package checks; never execute skill-supplied tests or code."""
        entry=_entry(self._registry(),skill_id)
        path=self._installed_path(skill_id,entry["version"])
        validation=self.validate(path)
        dependencies=_dependency_status(validation.skill["dependencies"] if validation.skill else [])
        try:
            integrity=path.is_dir() and _tree_digest(path)==entry.get("sha256")
        except (OSError,SkillError):
            integrity=False
        checks=[{"id":"package_validation","ok":validation.valid},
                {"id":"integrity","ok":integrity},
                {"id":"dependencies","ok":all(item["available"] for item in dependencies)}]
        return {"skill_id":skill_id,"version":entry["version"],"passed":all(x["ok"] for x in checks),
                "checks":checks,"dependencies":dependencies,
                "execution_tests":"not_run_sandbox_unavailable"}

    def configure(self, skill_id: str, values: dict[str,Any]) -> dict[str,Any]:
        """Validate settings and store secrets separately with Windows user-bound DPAPI."""
        entry=_entry(self._registry(),skill_id)
        path=self._installed_path(skill_id,entry["version"])
        validation=self.validate(path)
        if not validation.valid or not validation.skill: raise SkillError("Skill invalide; configuration refusée.")
        manifest=_read_json(path/"skill.json",[])
        schema_name=(manifest or {}).get("config_schema")
        if not schema_name: raise SkillError("Ce skill ne déclare pas de schéma de configuration.")
        schema_path=path/validate_relative_path(schema_name)
        schema=json.loads(schema_path.read_text(encoding="utf-8"))
        errors=_validate_config(values,schema)
        if errors: raise SkillError("Configuration invalide : "+"; ".join(errors))
        secrets={key:value for key,value in values.items() if _is_secret_schema(schema.get("properties",{}).get(key))}
        public={key:value for key,value in values.items() if key not in secrets}
        config_dir=self.home/"config"/skill_id
        if _path_has_link(config_dir): raise SkillError("Chemin de configuration sous lien symbolique.")
        config_dir.mkdir(parents=True,exist_ok=True)
        if secrets:
            from .secure_store import SecretStoreError, protect
            try: encrypted=protect(json.dumps(secrets,ensure_ascii=False,separators=(",",":")).encode("utf-8"))
            except SecretStoreError as exc: raise SkillError(str(exc)) from exc
            _atomic_bytes(config_dir/f"{entry['version']}.secrets.dpapi",encrypted)
        _atomic_json(config_dir/f"{entry['version']}.json",public)
        self._audit("SKILL_CONFIGURED",skill_id,version=entry["version"],fields=sorted(values),secret_field_names=sorted(secrets))
        return {"skill_id":skill_id,"version":entry["version"],"configured":True,"fields":sorted(values),"secret_fields":sorted(secrets)}

    def configuration_status(self, skill_id: str) -> dict[str,Any]:
        entry=_entry(self._registry(),skill_id)
        config_dir=self.home/"config"/skill_id
        public_path=config_dir/f"{entry['version']}.json"
        secret_path=config_dir/f"{entry['version']}.secrets.dpapi"
        if _path_has_link(public_path) or _path_has_link(secret_path): raise SkillError("Fichier de configuration sous lien symbolique.")
        if not public_path.exists() and not secret_path.exists(): return {"skill_id":skill_id,"configured":False,"fields":[],"secret_fields":[]}
        try: public=json.loads(public_path.read_text(encoding="utf-8")) if public_path.exists() else {}
        except (OSError,json.JSONDecodeError) as exc: raise SkillError("Configuration publique illisible.") from exc
        # Secret values are never decrypted or returned by the management API.
        schema=self.configuration_schema(skill_id).get("schema") or {}
        secret_names=sorted(key for key,field in schema.get("properties",{}).items() if _is_secret_schema(field))
        return {"skill_id":skill_id,"configured":True,"fields":sorted(public) if isinstance(public,dict) else [],
                "secret_fields":secret_names if secret_path.is_file() else [],"secrets_stored":secret_path.is_file()}

    def configuration_schema(self, skill_id: str) -> dict[str,Any]:
        entry=_entry(self._registry(),skill_id)
        path=self._installed_path(skill_id,entry["version"])
        validation=self.validate(path)
        if not validation.valid or not validation.skill: raise SkillError("Skill invalide; schéma indisponible.")
        errors=[]; manifest=_read_json(path/"skill.json",errors)
        name=(manifest or {}).get("config_schema")
        if not name:return {"skill_id":skill_id,"schema":None}
        try:schema=json.loads((path/validate_relative_path(name)).read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError,ValueError) as exc:raise SkillError("Schéma de configuration illisible.") from exc
        return {"skill_id":skill_id,"schema":schema}

    def agent_context(self, role: str, skill_ids: list[str] | None=None) -> list[dict[str,str]]:
        """Return explicitly selected, enabled skill instructions as untrusted context."""
        if role not in {"planner","coder","tester"}: raise SkillError("Rôle d’agent invalide.")
        selected=skill_ids or []
        if len(selected)>10 or any(not _valid_id(item) for item in selected) or len(set(selected))!=len(selected):
            raise SkillError("Sélection de skills invalide ou trop volumineuse.")
        result=[]
        for skill_id in selected:
            entry=_entry(self._registry(),skill_id)
            if entry["status"]!="enabled": raise SkillError(f"Le skill {skill_id} n’est pas activé.")
            path=self._installed_path(skill_id,entry["version"])
            if not path.is_dir() or _is_link(path) or _tree_digest(path)!=entry.get("sha256"):
                raise SkillError(f"Intégrité invalide pour {skill_id}.")
            if not all(item["available"] for item in _dependency_status(_validate_and_read_dependencies(path))):
                raise SkillError(f"Dépendance indisponible pour {skill_id}.")
            content=(path/"SKILL.md").read_text(encoding="utf-8")
            if len(content.encode("utf-8"))>32_000: raise SkillError("Instructions de skill trop volumineuses.")
            result.append({"skill_id":skill_id,"role":role,"trust":"UNTRUSTED_SKILL_DATA","content":content})
        return result

    def enable(self, skill_id: str, *, approved_permissions: set[str] | None=None) -> dict[str,Any]:
        with self._lock:
            registry=self._registry(); entry=_entry(registry,skill_id); path=self._installed_path(skill_id,entry["version"])
            if not path.is_dir() or _is_link(path) or _tree_digest(path)!=entry.get("sha256"): raise SkillError("Intégrité compromise; activation refusée.")
            checked=self.validate(path)
            if not checked.valid or not checked.skill: raise SkillError("Skill invalide; activation refusée.")
            granted=sorted(approved_permissions or set()); allowed,denied=PermissionManager.check(checked.skill["permissions"],granted)
            if not allowed: raise SkillError("Permissions non approuvées/inconnues : "+", ".join(denied))
            entry.update(status="enabled",granted_permissions=granted,enabled_at=_now())
            self._save_registry(registry); self._audit("SKILL_ENABLED",skill_id,permissions=granted)
            return dict(entry)

    def disable(self, skill_id: str) -> dict[str,Any]:
        with self._lock:
            registry=self._registry(); entry=_entry(registry,skill_id)
            entry.update(status="disabled",granted_permissions=[]); entry.pop("enabled_at",None)
            self._save_registry(registry); self._audit("SKILL_DISABLED",skill_id)
            return dict(entry)

    def uninstall(self, skill_id: str, *, approved: bool=False) -> None:
        if not approved: raise SkillError("La désinstallation nécessite une approbation explicite.")
        with self._lock:
            registry=self._registry(); entry=_entry(registry,skill_id); path=self._installed_path(skill_id,entry["version"])
            if _is_link(path): raise SkillError("Destination lien symbolique; suppression refusée.")
            registry["skills"]=[x for x in registry["skills"] if x["id"]!=skill_id]
            quarantine=path.with_name(f".{path.name}.{uuid.uuid4().hex}.remove")
            moved=False
            try:
                if path.exists(): os.replace(path,quarantine); moved=True
                self._save_registry(registry)
            except Exception:
                if moved and quarantine.exists(): os.replace(quarantine,path)
                raise
            if moved: shutil.rmtree(quarantine)
            self._audit("SKILL_UNINSTALLED",skill_id,version=entry["version"])

    def execute(self, skill_id: str, capability: str, payload: dict[str,Any]) -> dict[str,Any]:
        raise SkillError("L’exécution reste désactivée jusqu’à l’intégration d’un sandbox isolé.")

    def _installed_path(self,sid:str,version:str)->Path:
        if not _valid_id(sid) or not _SEMVER.fullmatch(version): raise SkillError("ID/version de skill invalide.")
        target=self.installed/sid/version
        for path in (self.cache,self.home,self.installed,self.installed/sid,target):
            if _is_link(path): raise SkillError("Chemin d’installation sous lien symbolique; opération refusée.")
        return target

    def _registry(self)->dict[str,Any]:
        if _is_link(self.home) or _is_link(self.registry_path): raise SkillError("Registre de skills sous lien symbolique.")
        if not self.registry_path.exists(): return {"schema_version":"1.0","skills":[]}
        if self.registry_path.stat().st_size > 1_048_576: raise SkillError("Registre des skills trop volumineux.")
        try: data=json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc: raise SkillError("Registre des skills illisible.") from exc
        if not isinstance(data,dict) or data.get("schema_version")!="1.0" or not isinstance(data.get("skills"),list): raise SkillError("Format de registre invalide.")
        if len(data["skills"])>1000: raise SkillError("Le registre contient trop de skills.")
        ids=set()
        for item in data["skills"]:
            if not isinstance(item,dict) or not _valid_id(item.get("id")) or not isinstance(item.get("version"),str) or not _SEMVER.fullmatch(item["version"]): raise SkillError("Entrée du registre invalide.")
            if not isinstance(item.get("status"),str) or item["status"] not in {"disabled","enabled"} or not isinstance(item.get("sha256"),str) or not re.fullmatch(r"[a-f0-9]{64}",item["sha256"]): raise SkillError("État ou empreinte de registre invalide.")
            if not isinstance(item.get("permissions"),list) or not isinstance(item.get("granted_permissions"),list): raise SkillError("Permissions de registre invalides.")
            if item["id"] in ids: raise SkillError("Identifiant de skill dupliqué dans le registre.")
            ids.add(item["id"])
        return data

    def _save_registry(self,value:dict[str,Any])->None:
        self.home.mkdir(parents=True,exist_ok=True)
        if _is_link(self.home) or _is_link(self.registry_path): raise SkillError("Registre de skills sous lien symbolique.")
        _atomic_json(self.registry_path,value)

    def _audit(self,event:str,sid:str,**details:Any)->None:
        self.home.mkdir(parents=True,exist_ok=True)
        if _is_link(self.home) or _is_link(self.audit_path): raise SkillError("Journal des skills sous lien symbolique.")
        with self.audit_path.open("a",encoding="utf-8",newline="\n") as f:
            f.write(json.dumps({"event":event,"skill_id":sid,"timestamp":_now(),**details},ensure_ascii=False,sort_keys=True)+"\n")
            f.flush(); os.fsync(f.fileno())


def _validate_manifest(manifest:dict[str,Any],capdoc:dict[str,Any],package:Path,files:list[Path],errors:list[dict[str,str]],warnings:list[dict[str,str]])->dict[str,Any]:
    required={"schema_version","id","name","version","description","author","license","capabilities","permissions","dependencies"}
    allowed=required|{"entrypoint","config_schema","codelix"}
    if required-manifest.keys(): errors.append(_issue("MANIFEST_REQUIRED","Champs manquants : "+", ".join(sorted(required-manifest.keys()))))
    if manifest.keys()-allowed: errors.append(_issue("MANIFEST_UNKNOWN","Champs inconnus : "+", ".join(sorted(manifest.keys()-allowed))))
    if manifest.get("schema_version")!="1.0": errors.append(_issue("SCHEMA_VERSION","schema_version doit être 1.0."))
    sid=manifest.get("id")
    if not _valid_id(sid): errors.append(_issue("SKILL_ID","id invalide; utilise des minuscules, chiffres et tirets."))
    for key in ("name","description","author","license"):
        if not isinstance(manifest.get(key),str) or not manifest[key].strip(): errors.append(_issue("MANIFEST_TEXT",f"{key} doit être un texte non vide."))
    version=manifest.get("version")
    if not isinstance(version,str) or not _SEMVER.fullmatch(version): errors.append(_issue("SKILL_VERSION","version doit suivre MAJOR.MINOR.PATCH."))
    if manifest.get("license")=="Unknown": warnings.append(_issue("LICENSE_UNKNOWN","Licence inconnue; vérifie les droits avant distribution.","warning"))
    caps=manifest.get("capabilities")
    if not isinstance(caps,list) or any(not isinstance(x,str) or not _CAP.fullmatch(x) for x in caps):
        errors.append(_issue("CAPABILITIES_LIST","capabilities doit être une liste d’identifiants.")); caps=[]
    if len(set(caps))!=len(caps): errors.append(_issue("CAPABILITY_DUPLICATE","Capacité déclarée plusieurs fois."))
    detail=[]
    if set(capdoc)!={"schema_version","capabilities"} or capdoc.get("schema_version")!="1.0" or not isinstance(capdoc.get("capabilities"),list):
        errors.append(_issue("CAPABILITIES_SHAPE","capabilities.json doit contenir schema_version et capabilities."))
    else:
        for i,item in enumerate(capdoc["capabilities"]):
            if not isinstance(item,dict) or set(item)!={"id","description","risk"}:
                errors.append(_issue("CAPABILITY_ENTRY",f"capabilities[{i}] doit contenir id, description et risk.")); continue
            cid=item["id"]
            if not isinstance(cid,str) or not _CAP.fullmatch(cid): errors.append(_issue("CAPABILITY_ID",f"ID invalide dans capabilities[{i}].")); continue
            detail.append(cid)
            if not isinstance(item["description"],str) or not item["description"].strip(): errors.append(_issue("CAPABILITY_DESCRIPTION",f"Description absente dans capabilities[{i}]."))
            if not isinstance(item["risk"],str) or item["risk"] not in {"low","medium","high","critical"}: errors.append(_issue("CAPABILITY_RISK",f"Risque invalide dans capabilities[{i}]."))
    if len(set(detail))!=len(detail): errors.append(_issue("CAPABILITY_DUPLICATE","Capacité détaillée dupliquée."))
    if set(caps)!=set(detail): errors.append(_issue("CAPABILITIES_MISMATCH","Les IDs de skill.json et capabilities.json doivent correspondre."))
    permissions=manifest.get("permissions")
    if not isinstance(permissions,list) or any(not isinstance(x,str) for x in permissions):
        errors.append(_issue("PERMISSIONS_LIST","permissions doit être une liste d’identifiants.")); permissions=[]
    if len(set(permissions))!=len(permissions): errors.append(_issue("PERMISSION_DUPLICATE","Permission déclarée plusieurs fois."))
    for permission in permissions:
        if permission not in KNOWN_PERMISSIONS: errors.append(_issue("PERMISSION_UNKNOWN",f"Permission non reconnue : {permission}."))
    dependencies=manifest.get("dependencies")
    if not isinstance(dependencies,list): errors.append(_issue("DEPENDENCIES_LIST","dependencies doit être une liste.")); dependencies=[]
    for i,item in enumerate(dependencies):
        if not isinstance(item,dict) or set(item)!={"name","version"} or any(not isinstance(item.get(k),str) or not item[k].strip() for k in ("name","version")):
            errors.append(_issue("DEPENDENCY_ENTRY",f"dependencies[{i}] doit contenir name et version."))
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",item["name"]):
            errors.append(_issue("DEPENDENCY_NAME",f"Nom de dépendance invalide dans dependencies[{i}]."))
        elif not _valid_version_spec(item["version"]):
            errors.append(_issue("DEPENDENCY_VERSION",f"Contrainte de version invalide dans dependencies[{i}]."))
    if dependencies:
        statuses=_dependency_status(dependencies)
        missing=[item["name"] for item in statuses if not item["available"]]
        if missing:
            warnings.append(_issue("DEPENDENCIES_MISSING","Dépendances absentes ou incompatibles : "+", ".join(missing)+". Aucune installation automatique n’a été effectuée.","warning"))
    rels={path.relative_to(package).as_posix() for path in files}
    for key in ("entrypoint","config_schema"):
        value=manifest.get(key)
        if value is not None:
            try:
                normalized=validate_relative_path(value)
                if normalized not in rels: errors.append(_issue(f"{key.upper()}_MISSING",f"{key} ne désigne pas un fichier du skill."))
                if key=="entrypoint": warnings.append(_issue("ENTRYPOINT_INERT","Le point d’entrée est référencé mais ne sera jamais lancé par cette version.","warning"))
                if key=="config_schema" and normalized in rels:
                    schema=json.loads((package/normalized).read_text(encoding="utf-8"))
                    schema_errors=_validate_config_schema(schema)
                    if schema_errors: errors.extend(_issue("CONFIG_SCHEMA_INVALID",message) for message in schema_errors)
            except (ValueError,OSError,json.JSONDecodeError): errors.append(_issue(f"{key.upper()}_INVALID",f"{key} invalide."))
    compatibility=manifest.get("codelix")
    if compatibility is not None:
        if not isinstance(compatibility,dict) or set(compatibility)-{"min","max"} or any(not isinstance(v,str) for v in compatibility.values()):
            errors.append(_issue("COMPATIBILITY_INVALID","codelix accepte uniquement les bornes min/max textuelles."))
        else:
            current=_version_tuple(__version__)
            lower=_compatibility_bound(compatibility.get("min"),upper=False)
            upper=_compatibility_bound(compatibility.get("max"),upper=True)
            if ("min" in compatibility and lower is None) or ("max" in compatibility and upper is None):
                errors.append(_issue("COMPATIBILITY_INVALID","Bornes min/max invalides; formats acceptés : 1.2 ou 2.x."))
            elif current is not None and ((lower is not None and current<lower) or (upper is not None and current>upper)):
                errors.append(_issue("INCOMPATIBLE_VYBELIX",f"Skill incompatible avec Vybelix {__version__}."))
    if "SKILL.md" not in rels: errors.append(_issue("SKILL_INSTRUCTIONS_MISSING","SKILL.md est obligatoire."))
    return {"id":sid if isinstance(sid,str) else None,"name":manifest.get("name"),"version":version,
            "description":manifest.get("description"),"author":manifest.get("author"),"license":manifest.get("license"),
            "capabilities":caps,"permissions":permissions,"dependencies":dependencies}


def _files(package:Path,errors:list[dict[str,str]])->list[Path]:
    result=[]; total=0
    for current,dirs,names in os.walk(package,topdown=True,followlinks=False):
        parent=Path(current); keep=[]
        for name in dirs:
            path=parent/name
            if name.casefold() in _FORBIDDEN_DIRS: errors.append(_issue("FORBIDDEN_DIRECTORY",f"Dossier interdit : {name}."))
            elif _is_link(path): errors.append(_issue("SYMLINK_FORBIDDEN",f"Lien interdit : {path.relative_to(package).as_posix()} ."))
            else: keep.append(name)
        dirs[:]=keep
        for name in names:
            path=parent/name; rel=path.relative_to(package).as_posix(); suffix=path.suffix.casefold()
            if _is_link(path): errors.append(_issue("SYMLINK_FORBIDDEN",f"Lien interdit : {rel}.")); continue
            if name.casefold()==".env" or suffix in _FORBIDDEN_SUFFIXES or name.casefold().startswith(".env."):
                errors.append(_issue("SENSITIVE_FILE",f"Fichier secret/interdit : {rel}.")); continue
            try:
                info=path.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode): errors.append(_issue("NOT_REGULAR_FILE",f"Type de fichier refusé : {rel}.")); continue
                size=info.st_size
            except OSError: errors.append(_issue("FILE_UNREADABLE",f"Fichier illisible : {rel}.")); continue
            if size>_MAX_FILE: errors.append(_issue("FILE_TOO_LARGE",f"Fichier supérieur à 1 Mio : {rel}.")); continue
            total+=size; result.append(path)
    if len(result)>_MAX_FILES: errors.append(_issue("TOO_MANY_FILES",f"Limite de {_MAX_FILES} fichiers dépassée."))
    if total>_MAX_TOTAL: errors.append(_issue("PACKAGE_TOO_LARGE","Le package dépasse 8 Mio."))
    return result


def _scan_secrets(package:Path,files:list[Path],errors:list[dict[str,str]])->None:
    for path in files:
        try:
            raw=path.read_bytes()
            if b"\0" in raw: continue
            text=raw.decode("utf-8")
        except (OSError,UnicodeError):
            if path.suffix.casefold() in _TEXT: errors.append(_issue("TEXT_FILE_INVALID",f"Fichier texte non UTF-8 : {path.relative_to(package).as_posix()}."))
            continue
        if any(pattern.search(text) for pattern in _SECRETS): errors.append(_issue("POSSIBLE_SECRET",f"Secret potentiel dans {path.relative_to(package).as_posix()}; retire-le."))


def _read_json(path:Path,errors:list[dict[str,str]])->dict[str,Any]|None:
    if _is_link(path): errors.append(_issue("SYMLINK_FORBIDDEN",f"Lien symbolique interdit : {path.name}.")); return None
    try:
        info=path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode): errors.append(_issue("NOT_REGULAR_FILE",f"Fichier JSON non régulier : {path.name}.")); return None
        if info.st_size>_MAX_FILE: errors.append(_issue("FILE_TOO_LARGE",f"Fichier supérieur à 1 Mio : {path.name}.")); return None
        value=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: errors.append(_issue("REQUIRED_FILE_MISSING",f"Fichier obligatoire manquant : {path.name}.")); return None
    except (OSError,UnicodeError,json.JSONDecodeError): errors.append(_issue("JSON_INVALID",f"JSON invalide ou illisible : {path.name}.")); return None
    if not isinstance(value,dict): errors.append(_issue("JSON_OBJECT_REQUIRED",f"{path.name} doit être un objet JSON.")); return None
    return value


def _entry(registry:dict[str,Any],sid:str)->dict[str,Any]:
    if not _valid_id(sid): raise SkillError("ID de skill invalide.")
    for item in registry["skills"]:
        if item["id"]==sid: return item
    raise SkillError(f"Skill non installé : {sid}.")


def _tree_digest(root:Path)->str:
    digest=hashlib.sha256(); count=0; total=0
    for path in sorted(root.rglob("*"),key=lambda p:p.relative_to(root).as_posix()):
        if _is_link(path): raise SkillError("Lien détecté dans le package installé.")
        if path.is_file():
            info=path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size>_MAX_FILE: raise SkillError("Type ou taille de fichier installé invalide.")
            count+=1; total+=info.st_size
            if count>_MAX_FILES or total>_MAX_TOTAL: raise SkillError("Taille du package installé hors limites.")
            relative=path.relative_to(root).as_posix().encode(); digest.update(len(relative).to_bytes(4,"big")); digest.update(relative)
            with path.open("rb") as stream:
                while chunk:=stream.read(65536): digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path:Path,value:dict[str,Any])->None:
    temporary=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x",encoding="utf-8",newline="\n") as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)

def _atomic_bytes(path:Path,value:bytes)->None:
    temporary=path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)


def _version_tuple(value:str)->tuple[int,int,int]|None:
    match=_SEMVER.fullmatch(value)
    return tuple(int(match.group(i)) for i in (1,2,3)) if match else None

def _valid_version_spec(spec:str)->bool:
    return bool(spec and all(re.fullmatch(r"(?:==|!=|~=|>=|<=|>|<)?\s*\d+(?:\.\d+){0,3}(?:[A-Za-z0-9.+-]*)",part.strip()) for part in spec.split(",")))

def _version_parts(value:str)->tuple[int,...]|None:
    match=re.match(r"^\s*(\d+(?:\.\d+){0,3})",value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None

def _dependency_status(dependencies:list[dict[str,str]])->list[dict[str,Any]]:
    result=[]
    for dep in dependencies:
        name=dep.get("name",""); spec=dep.get("version","")
        try: installed=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: installed=None
        satisfies=bool(installed and _satisfies(installed,spec))
        result.append({"name":name,"required":spec,"installed_version":installed,
                       "available":satisfies,"status":"available" if satisfies else ("missing" if installed is None else "version_mismatch")})
    return result

def _satisfies(installed:str,spec:str)->bool:
    actual=_version_parts(installed)
    if actual is None: return False
    for part in spec.split(","):
        match=re.fullmatch(r"(==|!=|~=|>=|<=|>|<)?\s*(\d+(?:\.\d+){0,3})[A-Za-z0-9.+-]*",part.strip())
        if not match: return False
        op=match.group(1) or "=="; wanted=tuple(int(x) for x in match.group(2).split("."))
        width=max(len(actual),len(wanted)); left=actual+(0,)*(width-len(actual)); right=wanted+(0,)*(width-len(wanted))
        ok={"==":left==right,"!=":left!=right,">=":left>=right,"<=":left<=right,">":left>right,"<":left<right,"~=":left>=right and left[:max(1,len(wanted)-1)]==right[:max(1,len(wanted)-1)]}[op]
        if not ok:return False
    return True

def _validate_and_read_dependencies(path:Path)->list[dict[str,str]]:
    errors=[]; manifest=_read_json(path/"skill.json",errors)
    if errors or not isinstance((manifest or {}).get("dependencies",[]),list): raise SkillError("Manifeste de dépendances invalide.")
    return manifest.get("dependencies",[])

def _is_secret_schema(schema:Any)->bool:
    return isinstance(schema,dict) and (schema.get("type")=="secret" or schema.get("x-secret") is True)

def _validate_config(values:Any,schema:Any)->list[str]:
    if not isinstance(values,dict) or not isinstance(schema,dict) or schema.get("type")!="object":return ["un objet JSON est attendu"]
    errors=[]; properties=schema.get("properties",{}); required=schema.get("required",[])
    if not isinstance(properties,dict) or not isinstance(required,list):return ["schéma de configuration invalide"]
    for key in required:
        if key not in values:errors.append(f"{key} est obligatoire")
    if schema.get("additionalProperties",False) is False:
        for key in values.keys()-properties.keys():errors.append(f"{key} n’est pas déclaré")
    for key,value in values.items():
        field=properties.get(key)
        if not isinstance(field,dict):continue
        if _is_secret_schema(field):
            if not isinstance(value,str) or not value:errors.append(f"{key} doit être un secret non vide")
            continue
        kind=field.get("type"); valid={"string":lambda:isinstance(value,str),"integer":lambda:isinstance(value,int) and not isinstance(value,bool),"number":lambda:isinstance(value,(int,float)) and not isinstance(value,bool),"boolean":lambda:isinstance(value,bool),"array":lambda:isinstance(value,list),"object":lambda:isinstance(value,dict)}.get(kind,lambda:False)()
        if not valid:errors.append(f"{key} doit respecter le type {kind}");continue
        if isinstance(value,str):
            if len(value)<field.get("minLength",0) or len(value)>field.get("maxLength",100_000):errors.append(f"{key} a une longueur invalide")
            if "pattern" in field and (not isinstance(field["pattern"],str) or not re.fullmatch(field["pattern"],value)):errors.append(f"{key} ne respecte pas le format attendu")
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            if value<field.get("minimum",float("-inf")) or value>field.get("maximum",float("inf")):errors.append(f"{key} est hors limites")
        if "enum" in field and value not in field["enum"]:errors.append(f"{key} n’appartient pas aux valeurs autorisées")
    for key,field in properties.items():
        if isinstance(field,dict) and field.get("required") is True and key not in values:errors.append(f"{key} est obligatoire")
    return errors

def _validate_config_schema(schema:Any)->list[str]:
    if not isinstance(schema,dict) or schema.get("type")!="object":return ["Le schéma config doit décrire un objet JSON."]
    properties=schema.get("properties",{}); required=schema.get("required",[])
    if not isinstance(properties,dict) or not isinstance(required,list) or any(not isinstance(item,str) for item in required):return ["properties ou required invalide"]
    if any(item not in properties for item in required):return ["required référence un champ absent de properties"]
    allowed={"string","integer","number","boolean","array","object","secret"}; errors=[]
    for key,field in properties.items():
        if not isinstance(key,str) or not isinstance(field,dict) or field.get("type") not in allowed:errors.append(f"Définition invalide pour {key}");continue
        if "required" in field and not isinstance(field["required"],bool):errors.append(f"required invalide pour {key}")
        if "enum" in field and (not isinstance(field["enum"],list) or not field["enum"]):errors.append(f"enum invalide pour {key}")
        if "pattern" in field:
            try:re.compile(field["pattern"])
            except (TypeError,re.error):errors.append(f"pattern invalide pour {key}")
    return errors

def _compatibility_bound(value:str|None,*,upper:bool)->tuple[int,int,int]|None:
    if value is None: return None
    match=re.fullmatch(r"(0|[1-9]\d*)(?:\.(0|[1-9]\d*|x|\*))?(?:\.(0|[1-9]\d*|x|\*))?",value,flags=re.IGNORECASE)
    if not match: return None
    parts=[]
    for item in match.groups():
        if item is None: parts.append(999999 if upper else 0)
        elif item.casefold() in {"x","*"}: parts.append(999999 if upper else 0)
        else: parts.append(int(item))
    return tuple(parts)

def _path_has_link(path:Path)->bool:
    absolute=path.absolute()
    return any(_is_link(component) for component in reversed((absolute,*absolute.parents)))

def _valid_id(value:Any)->bool: return isinstance(value,str) and len(value)<=64 and bool(_ID.fullmatch(value))
def _is_link(path:Path)->bool: return path.is_symlink() or bool(getattr(path,"is_junction",lambda:False)())
def _issue(code:str,message:str,severity:str="error")->dict[str,str]: return {"code":code,"message":message,"severity":severity}
def _now()->str: return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
