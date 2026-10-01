"""Exécution bornée de commandes de vérification explicitement autorisées."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_SAFE_VERIFIER_ENV = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC",
    "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "VIRTUAL_ENV", "CONDA_PREFIX", "LANG", "LC_ALL", "TZ",
})


def _verifier_environment() -> dict[str, str]:
    """Pass only common runtime variables; do not expose inherited API credentials."""
    return {name: value for name, value in os.environ.items() if name.upper() in _SAFE_VERIFIER_ENV}


class VerificationError(RuntimeError):
    """Une vérification n'est pas autorisée ou ne peut pas être exécutée."""


@dataclass(frozen=True)
class VerificationResult:
    command: str
    exit_code: int | None
    summary: str
    errors: tuple[str, ...]
    execution_id: str
    duration_seconds: float
    acceptance_criteria: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "errors": list(self.errors),
            "execution_id": self.execution_id,
            "duration_seconds": self.duration_seconds,
            "acceptance_criteria": list(self.acceptance_criteria),
        }


class Verifier:
    """Lance une ligne exacte de la liste autorisée, sans shell ni argument implicite."""

    def __init__(self, root: Path, allowed_commands: tuple[str, ...] | list[str], *, timeout_seconds: int = 300):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise VerificationError("La racine du projet n'est pas un dossier.")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
            raise ValueError("timeout_seconds doit être compris entre 1 et 300.")
        if any(not isinstance(item, str) or not item.strip() for item in allowed_commands):
            raise ValueError("Chaque commande autorisée doit être une chaîne non vide.")
        self.allowed_commands = tuple(allowed_commands)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _redact(text: str) -> str:
        for value in set(os.environ.values()):
            if value and len(value) >= 8:
                text = text.replace(value, "[SECRET REDACTED]")
        return text

    def run(self, command: str, *, acceptance_criteria: tuple[str, ...] | list[str] = ()) -> VerificationResult:
        if command not in self.allowed_commands:
            raise VerificationError("Cette commande n'est pas dans la liste explicitement autorisée.")
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
            if os.name == "nt":
                argv = [token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"} else token for token in argv]
        except ValueError as exc:
            raise VerificationError("La syntaxe de la commande autorisée est invalide.") from exc
        if not argv or any(token in {"|", "||", "&", "&&", ";", ">", "<"} for token in argv):
            raise VerificationError("La commande vide ou les opérateurs shell sont interdits.")

        started = time.monotonic()
        execution_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            completed = subprocess.run(
                argv,
                cwd=self.root,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                env=_verifier_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = round(time.monotonic() - started, 3)
            partial = exc.stderr or exc.stdout or ""
            detail = self._redact(partial if isinstance(partial, str) else partial.decode("utf-8", "replace"))
            errors = tuple(line for line in detail.splitlines() if line.strip())[-20:]
            return VerificationResult(command, None, f"Délai dépassé après {self.timeout_seconds} s.", errors, execution_id, elapsed, tuple(acceptance_criteria))
        except OSError as exc:
            raise VerificationError(f"Impossible de lancer la commande autorisée ({type(exc).__name__}).") from exc

        elapsed = round(time.monotonic() - started, 3)
        output = self._redact("\n".join(part for part in (completed.stdout, completed.stderr) if part))
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        summary = (lines[-1][:500] if lines else ("Vérification réussie." if completed.returncode == 0 else "La commande a échoué sans détail."))
        errors = tuple(lines[-20:]) if completed.returncode != 0 else ()
        # La sortie complète est bornée avant d'être persistée dans la progression.
        errors = tuple(line[:500] for line in errors)
        return VerificationResult(command, completed.returncode, summary, errors, execution_id, elapsed, tuple(acceptance_criteria))


def correction_limit(attempts: int, configured_limit: int = 2) -> int:
    """Valide le compteur d'essais et retourne le nombre de corrections restantes."""
    for value, label in ((attempts, "attempts"), (configured_limit, "configured_limit")):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2:
            raise ValueError(f"{label} doit être un entier de 0 à 2.")
    return max(0, configured_limit - attempts)
