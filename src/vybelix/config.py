"""Chargement et validation de la configuration TOML locale."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """La configuration locale est invalide."""


@dataclass(frozen=True)
class RuntimeSettings:
    request_timeout_seconds: int = 300
    max_file_bytes: int = 204_800
    correction_attempts: int = 2
    network_retries: int = 1


@dataclass(frozen=True)
class ProviderSettings:
    base_url: str
    api_key_env: str


@dataclass(frozen=True)
class VybelixConfig:
    runtime: RuntimeSettings
    providers: dict[str, ProviderSettings]
    models: dict[str, tuple[str, ...]]
    allowed_commands: tuple[str, ...]


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} doit être une table TOML.")
    return value


def _only_keys(value: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = value.keys() - allowed
    if unknown:
        raise ConfigurationError(f"Clés inconnues dans {name}: {', '.join(sorted(unknown))}.")


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} doit être un entier entre {minimum} et {maximum}.")
    return value


def validate_config(raw: Any) -> VybelixConfig:
    data = _mapping(raw, "racine")
    _only_keys(data, {"schema_version", "runtime", "providers", "models", "verifier"}, "racine")
    if data.get("schema_version") != "1.0":
        raise ConfigurationError("schema_version doit être '1.0'.")

    runtime_data = _mapping(data.get("runtime", {}), "runtime")
    _only_keys(
        runtime_data,
        {"request_timeout_seconds", "max_file_bytes", "correction_attempts", "network_retries"},
        "runtime",
    )
    runtime = RuntimeSettings(
        request_timeout_seconds=_integer(runtime_data.get("request_timeout_seconds", 300), "request_timeout_seconds", 1, 300),
        max_file_bytes=_integer(runtime_data.get("max_file_bytes", 204_800), "max_file_bytes", 1, 204_800),
        correction_attempts=_integer(runtime_data.get("correction_attempts", 2), "correction_attempts", 0, 2),
        network_retries=_integer(runtime_data.get("network_retries", 1), "network_retries", 0, 1),
    )

    provider_data = _mapping(data.get("providers", {}), "providers")
    providers: dict[str, ProviderSettings] = {}
    for name, raw_provider in provider_data.items():
        provider = _mapping(raw_provider, f"providers.{name}")
        _only_keys(provider, {"base_url", "api_key_env"}, f"providers.{name}")
        base_url = provider.get("base_url", "")
        key_env = provider.get("api_key_env", "")
        if not isinstance(base_url, str) or (base_url and not base_url.startswith("https://")):
            raise ConfigurationError(f"providers.{name}.base_url doit être vide ou commencer par https://.")
        if not isinstance(key_env, str) or (key_env and not key_env.replace("_", "").isalnum()):
            raise ConfigurationError(f"providers.{name}.api_key_env doit être un nom de variable valide.")
        providers[name] = ProviderSettings(base_url=base_url, api_key_env=key_env)

    model_data = _mapping(data.get("models", {}), "models")
    _only_keys(model_data, {"planner", "coder", "tester"}, "models")
    models: dict[str, tuple[str, ...]] = {}
    for role in ("planner", "coder", "tester"):
        candidates = model_data.get(role, [])
        if not isinstance(candidates, list) or any(not isinstance(item, str) or not item.strip() for item in candidates):
            raise ConfigurationError(f"models.{role} doit être une liste de chaînes non vides.")
        if len(set(candidates)) != len(candidates):
            raise ConfigurationError(f"models.{role} ne peut pas contenir de doublons.")
        models[role] = tuple(candidates)

    verifier = _mapping(data.get("verifier", {}), "verifier")
    _only_keys(verifier, {"allowed_commands"}, "verifier")
    allowed = verifier.get("allowed_commands", [])
    if not isinstance(allowed, list) or any(not isinstance(item, str) or not item.strip() for item in allowed):
        raise ConfigurationError("verifier.allowed_commands doit être une liste de commandes non vides.")
    return VybelixConfig(runtime, providers, models, tuple(allowed))


def load_config(path: Path) -> VybelixConfig:
    """Charge un TOML UTF-8 et n'inclut jamais les valeurs secrètes dans les erreurs."""
    try:
        load_env_file(path.parent / ".env")
        with path.open("rb") as source:
            return validate_config(tomllib.load(source))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Fichier de configuration introuvable: {path}.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Syntaxe TOML invalide dans {path}.") from exc


def load_env_file(path: Path) -> None:
    """Charge les affectations simples d'un .env local sans écraser l'environnement."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ConfigurationError(f"Impossible de lire le fichier d'environnement {path}.") from exc
    for number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            raise ConfigurationError(f"Ligne {number} invalide dans le fichier d'environnement.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(name, value)


def provider_api_key(provider: ProviderSettings) -> str | None:
    """Lit une clé à l'exécution sans la copier dans la configuration ou les journaux."""
    return os.environ.get(provider.api_key_env) if provider.api_key_env else None


# Compatibility alias for integrations using the previous package name.
CodelixConfig = VybelixConfig
