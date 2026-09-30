"""Project path naming and non-destructive legacy compatibility."""

from pathlib import Path


def project_config_path(project: Path) -> Path:
    new = project / "vybelix.toml"
    legacy = project / "codelix.toml"
    return new if new.exists() or not legacy.exists() else legacy


def project_cache_root(project: Path) -> Path:
    new = project / ".vybelix-cache"
    legacy = project / ".codelix-cache"
    return new if new.exists() or not legacy.exists() else legacy
