"""Prévisualisation et application contrôlée des propositions de fichiers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError, validate_coder_output, validate_relative_path

DEFAULT_PROTECTED_PATHS = {"docs/progress/tasks.json"}
_SECRET_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}


class ExecutionError(RuntimeError):
    """Une proposition ne peut pas être appliquée en sécurité."""


class FileConflictError(ExecutionError):
    """Un fichier a changé depuis sa dernière inspection."""


class ApprovalRequiredError(ExecutionError):
    """L'utilisateur doit approuver l'application après avoir lu l'aperçu."""


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    sha256: str | None


@dataclass(frozen=True)
class ApplyResult:
    status: str
    written: tuple[str, ...]
    refused: tuple[str, ...]
    backup_id: str | None = None


@dataclass(frozen=True)
class UndoPreview:
    backup_id: str
    files: tuple[str, ...]


class ExecutionManager:
    """Seul composant autorisé à écrire les contenus de proposition dans le projet."""

    def __init__(
        self,
        root: Path,
        *,
        protected_paths: set[str] | None = None,
        max_file_bytes: int = 204_800,
        backup_directory: str = ".vybelix-backups",
    ) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ExecutionError("La racine du projet n'est pas un dossier.")
        if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes < 1:
            raise ValueError("max_file_bytes doit être un entier positif.")
        self.max_file_bytes = max_file_bytes
        if backup_directory == ".vybelix-backups" and not (self.root / backup_directory).exists() and (self.root / ".codelix-backups").exists():
            backup_directory = ".codelix-backups"
        self.backup_directory = validate_relative_path(backup_directory)
        self.protected_paths = DEFAULT_PROTECTED_PATHS | (protected_paths or set())
        self.protected_paths_casefold = {path.casefold() for path in self.protected_paths}

    def _secure_path(self, relative_path: str, *, internal_backup: bool = False) -> Path:
        try:
            relative_path = validate_relative_path(relative_path)
        except ContractError as exc:
            raise ExecutionError(str(exc)) from exc
        parts = relative_path.split("/")
        lowered = [part.casefold() for part in parts]
        basename = lowered[-1]
        if ".git" in lowered:
            raise ExecutionError("Les chemins du dépôt Git sont protégés.")
        if basename in _SECRET_NAMES or (basename.startswith(".env.") and basename != ".env.example"):
            raise ExecutionError("Les fichiers secrets et de clés sont protégés.")
        if Path(relative_path).suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}:
            raise ExecutionError("Les fichiers de clés et certificats sont protégés.")
        folded_path = relative_path.casefold()
        if folded_path in self.protected_paths_casefold:
            raise ExecutionError(f"Le fichier protégé ne peut pas être modifié: {relative_path}.")
        backup_roots = {self.backup_directory.casefold(), ".codelix-backups", ".vybelix-backups"}
        if not internal_backup and any(
            folded_path == backup_root or folded_path.startswith(backup_root + "/")
            for backup_root in backup_roots
        ):
            raise ExecutionError("Le dossier des points de retour est protégé.")

        candidate = self.root.joinpath(*parts)
        cursor = self.root
        for part in parts:
            cursor = cursor / part
            if cursor.exists() and (cursor.is_symlink() or cursor.is_junction()):
                raise ExecutionError(f"Un lien symbolique ou une jonction est interdit: {relative_path}.")
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise ExecutionError(f"Le chemin sort de la racine du projet: {relative_path}.")
        return candidate

    @staticmethod
    def _hash(path: Path) -> str | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise ExecutionError(f"La cible existe mais n'est pas un fichier: {path}.")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def inspect(self, paths: list[str]) -> dict[str, FileSnapshot]:
        """Capture l'empreinte des fichiers autorisés avant la génération/apply."""
        snapshots: dict[str, FileSnapshot] = {}
        for raw_path in paths:
            path = self._secure_path(raw_path)
            normalized = path.relative_to(self.root).as_posix()
            if normalized in snapshots:
                raise ExecutionError(f"Chemin dupliqué à l'inspection: {normalized}.")
            snapshots[normalized] = FileSnapshot(normalized, self._hash(path))
        return snapshots

    def preview(
        self,
        proposal: Any,
        *,
        expected_task_id: str,
        snapshots: dict[str, FileSnapshot],
    ) -> tuple[dict[str, Any], ...]:
        """Valide le contrat, les chemins et l'absence de conflit, sans écrire."""
        try:
            validated = validate_coder_output(proposal, expected_task_id=expected_task_id)
        except ContractError as exc:
            raise ExecutionError(str(exc)) from exc
        preview: list[dict[str, Any]] = []
        for item in validated["files"]:
            path = self._secure_path(item["path"])
            relative_path = path.relative_to(self.root).as_posix()
            snapshot = snapshots.get(relative_path)
            if snapshot is None:
                raise ExecutionError(f"Fichier non inspecté avant proposition: {relative_path}.")
            current_hash = self._hash(path)
            if current_hash != snapshot.sha256:
                raise FileConflictError(f"Le fichier a changé depuis l'inspection: {relative_path}.")
            content = item["content"]
            content_size = len(content.encode("utf-8"))
            if content_size > self.max_file_bytes:
                raise ExecutionError(f"Le contenu dépasse {self.max_file_bytes} octets: {relative_path}.")
            preview.append({
                "path": relative_path,
                "operation": "create" if current_hash is None else "replace",
                "previous_sha256": current_hash,
                "new_size_bytes": content_size,
            })
        return tuple(preview)

    def apply(
        self,
        proposal: Any,
        *,
        expected_task_id: str,
        snapshots: dict[str, FileSnapshot],
        approved: bool = False,
    ) -> ApplyResult:
        """Applique après approbation explicite et crée d'abord un point de retour."""
        preview = self.preview(proposal, expected_task_id=expected_task_id, snapshots=snapshots)
        if not approved:
            return ApplyResult("needs_approval", (), tuple(item["path"] for item in preview))
        validated = validate_coder_output(proposal, expected_task_id=expected_task_id)
        backup_id = uuid.uuid4().hex
        backup_root = self._secure_path(f"{self.backup_directory}/{backup_id}", internal_backup=True)
        if backup_root.exists():
            raise ExecutionError("Identifiant de point de retour déjà utilisé.")

        original_bytes: dict[str, bytes | None] = {}
        paths: dict[str, Path] = {}
        for item in validated["files"]:
            relative_path = item["path"]
            path = self._secure_path(relative_path)
            original_bytes[relative_path] = path.read_bytes() if path.exists() else None
            paths[relative_path] = path

        backup_root.mkdir(parents=True, exist_ok=False)
        try:
            for relative_path, content in original_bytes.items():
                if content is None:
                    continue
                backup_file = backup_root.joinpath(*relative_path.split("/"))
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                with backup_file.open("xb") as backup:
                    backup.write(content)
                    backup.flush()
                    os.fsync(backup.fileno())

            written: list[str] = []
            try:
                for item in validated["files"]:
                    relative_path = item["path"]
                    path = paths[relative_path]
                    if self._hash(path) != snapshots[relative_path].sha256:
                        raise FileConflictError(f"Le fichier a changé juste avant l'écriture: {relative_path}.")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_path: str | None = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            "wb", dir=path.parent, prefix=".vybelix-", delete=False
                        ) as temporary:
                            temporary_path = temporary.name
                            temporary.write(item["content"].encode("utf-8"))
                            temporary.flush()
                            os.fsync(temporary.fileno())
                        os.replace(temporary_path, path)
                    finally:
                        if temporary_path and os.path.exists(temporary_path):
                            os.unlink(temporary_path)
                    written.append(relative_path)
                manifest = {
                    "schema_version": "1.0",
                    "backup_id": backup_id,
                    "created_at_ns": time.time_ns(),
                    "undone_at_ns": None,
                    "files": [
                        {
                            "path": relative_path,
                            "previous_exists": original_bytes[relative_path] is not None,
                            "previous_sha256": snapshots[relative_path].sha256,
                            "applied_sha256": self._hash(paths[relative_path]),
                        }
                        for relative_path in written
                    ],
                }
                manifest_path = backup_root / "manifest.json"
                with manifest_path.open("x", encoding="utf-8", newline="\n") as manifest_file:
                    json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
                    manifest_file.write("\n")
                    manifest_file.flush()
                    os.fsync(manifest_file.fileno())
            except Exception:
                for relative_path in reversed(written):
                    path = paths[relative_path]
                    content = original_bytes[relative_path]
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(content)
                raise
            return ApplyResult("applied", tuple(written), (), backup_id)
        except Exception:
            shutil.rmtree(backup_root, ignore_errors=True)
            raise

    def _latest_undo_manifest(self) -> tuple[Path, dict[str, Any]]:
        backup_root = self._secure_path(self.backup_directory, internal_backup=True)
        if not backup_root.exists():
            raise ExecutionError("Aucun point de retour Vybelix disponible.")
        manifests: list[tuple[int, Path, dict[str, Any]]] = []
        for manifest_path in backup_root.glob("*/manifest.json"):
            if manifest_path.is_symlink() or manifest_path.is_junction():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != "1.0"
                or manifest.get("undone_at_ns") is not None
                or manifest.get("backup_id") != manifest_path.parent.name
                or not isinstance(manifest.get("created_at_ns"), int)
                or not isinstance(manifest.get("files"), list)
                or not manifest["files"]
            ):
                continue
            manifests.append((manifest["created_at_ns"], manifest_path, manifest))
        if not manifests:
            raise ExecutionError("Aucun point de retour récent et annulable n'est disponible.")
        _, manifest_path, manifest = max(manifests, key=lambda item: item[0])
        return manifest_path, manifest

    def _validate_undo_manifest(self, manifest_path: Path, manifest: dict[str, Any]) -> list[tuple[str, Path, dict[str, Any], bytes | None]]:
        backup_root = manifest_path.parent
        entries: list[tuple[str, Path, dict[str, Any], bytes | None]] = []
        conflicts: list[str] = []
        seen: set[str] = set()
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ExecutionError("Manifeste de point de retour invalide.")
            relative_path = entry["path"]
            if relative_path in seen:
                raise ExecutionError("Manifeste de point de retour contenant des chemins dupliqués.")
            seen.add(relative_path)
            path = self._secure_path(relative_path)
            if self._hash(path) != entry.get("applied_sha256"):
                conflicts.append(relative_path)
                continue
            previous: bytes | None = None
            if entry.get("previous_exists") is True:
                backup_file = self._secure_path(
                    f"{self.backup_directory}/{manifest['backup_id']}/{relative_path}",
                    internal_backup=True,
                )
                if not backup_file.is_file() or backup_file.is_symlink() or backup_file.is_junction():
                    raise ExecutionError(f"Copie précédente manquante pour {relative_path}.")
                previous = backup_file.read_bytes()
                if hashlib.sha256(previous).hexdigest() != entry.get("previous_sha256"):
                    raise ExecutionError(f"Copie précédente altérée pour {relative_path}.")
            elif entry.get("previous_exists") is not False or entry.get("previous_sha256") is not None:
                raise ExecutionError("Métadonnées du point de retour incohérentes.")
            entries.append((relative_path, path, entry, previous))
        if conflicts:
            raise FileConflictError(
                "Annulation refusée : fichiers modifiés depuis l'application : " + ", ".join(conflicts)
            )
        return entries

    def preview_latest_undo(self) -> UndoPreview:
        manifest_path, manifest = self._latest_undo_manifest()
        entries = self._validate_undo_manifest(manifest_path, manifest)
        return UndoPreview(
            manifest["backup_id"],
            tuple(relative_path for relative_path, _, _, _ in entries),
        )

    def undo_latest(self, *, expected_backup_id: str) -> tuple[str, ...]:
        """Restore the previewed Vybelix apply point, refusing changed files or a stale preview."""
        manifest_path, manifest = self._latest_undo_manifest()
        if manifest["backup_id"] != expected_backup_id:
            raise FileConflictError("Un nouveau changement est apparu depuis l'aperçu. Relancez vybelix undo.")
        entries = self._validate_undo_manifest(manifest_path, manifest)
        current = {relative: path.read_bytes() if path.exists() else None for relative, path, _, _ in entries}
        restored: list[str] = []
        try:
            for relative_path, path, entry, previous in entries:
                if self._hash(path) != entry["applied_sha256"]:
                    raise FileConflictError(f"Annulation refusée : {relative_path} a changé pendant l'opération.")
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path: str | None = None
                    try:
                        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".vybelix-undo-", delete=False) as temp:
                            temp_path = temp.name
                            temp.write(previous)
                            temp.flush()
                            os.fsync(temp.fileno())
                        os.replace(temp_path, path)
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            os.unlink(temp_path)
                restored.append(relative_path)
            manifest["undone_at_ns"] = time.time_ns()
            temporary = manifest_path.with_name(".manifest-undo.tmp")
            try:
                with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(manifest, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, manifest_path)
            finally:
                temporary.unlink(missing_ok=True)
        except Exception:
            for relative_path, path, _, _ in entries:
                if relative_path not in restored:
                    continue
                content = current[relative_path]
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)
            raise
        return tuple(restored)
