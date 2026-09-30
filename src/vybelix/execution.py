"""Prévisualisation et application contrôlée des propositions de fichiers."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
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
