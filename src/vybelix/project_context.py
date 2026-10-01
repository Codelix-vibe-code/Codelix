"""Compact, user-curated project memory stored outside tracked source files."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import validate_relative_path

CONTEXT_FIELDS={"goal","verified_facts","assumptions","entry_points","conventions","decisions","open_issues","next_steps","relevant_files"}
_SECRET_PATTERNS=(
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bAIza[0-9A-Za-z_-]{25,}\b"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
)
_SENSITIVE_NAMES={".env","credentials.json","secrets.json","id_rsa","id_ed25519"}
_MAX_CONTEXT_BYTES=64_000
_MAX_LIST_ITEMS=100


class ProjectContextError(ValueError):
    """Project context is malformed, too large, or contains sensitive data."""


def empty_context(project_id: str) -> dict[str,Any]:
    return {"schema_version":"1.0","project_id":project_id,"updated_at":None,"goal":"",
            "verified_facts":[],"assumptions":[],"entry_points":[],"conventions":[],"decisions":[],
            "open_issues":[],"next_steps":[],"relevant_files":[]}


class ProjectContextStore:
    def __init__(self,path:Path,project_id:str):
        self.path=path
        self.project_id=project_id

    def load(self)->dict[str,Any]:
        if self.path.is_symlink() or bool(getattr(self.path,"is_junction",lambda:False)()):
            raise ProjectContextError("Le contexte projet ne peut pas être un lien symbolique.")
        if not self.path.exists():return empty_context(self.project_id)
        if self.path.stat().st_size>_MAX_CONTEXT_BYTES:raise ProjectContextError("Le contexte projet dépasse 64 Ko.")
        try:value=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise ProjectContextError("Le contexte projet est illisible ou invalide.") from exc
        return validate_context(value,expected_project_id=self.project_id)

    def save(self,value:dict[str,Any])->dict[str,Any]:
        clean=validate_context(value,expected_project_id=self.project_id,allow_missing_metadata=True)
        clean["updated_at"]=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
        serialized=json.dumps(clean,ensure_ascii=False,indent=2)+"\n"
        if len(serialized.encode("utf-8"))>_MAX_CONTEXT_BYTES:raise ProjectContextError("Le contexte projet dépasse 64 Ko.")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink() or bool(getattr(self.path,"is_junction",lambda:False)()):raise ProjectContextError("Le contexte projet ne peut pas être un lien symbolique.")
        temporary=None
        try:
            with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=self.path.parent,delete=False,newline="\n") as stream:
                temporary=Path(stream.name);stream.write(serialized);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
        finally:
            if temporary and temporary.exists():temporary.unlink()
        return clean


def validate_context(value:Any,*,expected_project_id:str,allow_missing_metadata:bool=False)->dict[str,Any]:
    if not isinstance(value,dict):raise ProjectContextError("Le contexte doit être un objet JSON.")
    expected={"schema_version","project_id","updated_at",*CONTEXT_FIELDS}
    if allow_missing_metadata:
        unknown=value.keys()-expected
        if unknown:raise ProjectContextError("Champs de contexte inconnus : "+", ".join(sorted(unknown))+".")
        if "project_id" in value and value["project_id"] != expected_project_id:
            raise ProjectContextError("Le contexte appartient à un autre projet.")
        context={**empty_context(expected_project_id),**value,"project_id":expected_project_id}
    else:
        if set(value)!=expected:raise ProjectContextError("Champs manquants ou inconnus dans le contexte projet.")
        context=value
    if context.get("schema_version")!="1.0":raise ProjectContextError("Version de contexte non prise en charge.")
    if context.get("project_id")!=expected_project_id:raise ProjectContextError("Le contexte appartient à un autre projet.")
    updated=context.get("updated_at")
    if updated is not None and (not isinstance(updated,str) or not updated.strip()):raise ProjectContextError("updated_at doit être une date ou null.")
    if not isinstance(context.get("goal"),str):raise ProjectContextError("goal doit être du texte.")
    for field in CONTEXT_FIELDS-{"goal","relevant_files"}:
        items=context.get(field)
        if not isinstance(items,list) or len(items)>_MAX_LIST_ITEMS or any(not isinstance(item,str) or not item.strip() or len(item)>2000 for item in items):
            raise ProjectContextError(f"{field} doit être une liste de textes non vides limitée à {_MAX_LIST_ITEMS} éléments.")
    files=context.get("relevant_files")
    if not isinstance(files,list) or len(files)>_MAX_LIST_ITEMS:raise ProjectContextError("relevant_files doit être une liste limitée à 100 éléments.")
    normalized=[]
    for item in files:
        if not isinstance(item,dict) or set(item)!={"path","summary"} or not isinstance(item["summary"],str) or not item["summary"].strip() or len(item["summary"])>2000:
            raise ProjectContextError("Chaque relevant_file doit contenir path et summary valides.")
        try:path=validate_relative_path(item["path"])
        except (TypeError,ValueError) as exc:raise ProjectContextError("Chemin non sûr dans relevant_files.") from exc
        if any(part.casefold() in _SENSITIVE_NAMES or part.casefold().startswith(".env") for part in path.split("/")):
            raise ProjectContextError("Un fichier secret ne peut pas être ajouté au contexte.")
        normalized.append({"path":path,"summary":item["summary"]})
    context["relevant_files"]=normalized
    rendered=json.dumps(context,ensure_ascii=False)
    if any(pattern.search(rendered) for pattern in _SECRET_PATTERNS):raise ProjectContextError("Le contexte contient une valeur ressemblant à un secret; aucune donnée n’a été enregistrée.")
    if len(rendered.encode("utf-8"))>_MAX_CONTEXT_BYTES:raise ProjectContextError("Le contexte projet dépasse 64 Ko.")
    return context
