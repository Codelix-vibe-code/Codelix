"""Adaptateur REST de l'API Anthropic Messages pour Claude."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..config import ProviderSettings, provider_api_key
from .errors import (
    AccessDeniedError,
    AuthenticationError,
    InvalidResponseError,
    ModelNotFoundError,
    NetworkError,
    ProviderError,
    RateLimitError,
    TransientProviderError,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AnthropicAdapter:
    """Traduit les messages internes vers POST /v1/messages (réponse JSON)."""

    name = "anthropic"
    api_version = "2023-06-01"

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        api_key: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
            raise ValueError("timeout_seconds doit être compris entre 1 et 300.")
        self.settings = settings
        self._api_key = api_key if api_key is not None else provider_api_key(settings)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _request_body(messages: list[dict[str, str]], model: str, options: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages doit contenir au moins un message.")
        system: list[str] = []
        conversation: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError(f"messages[{index}] doit contenir role et content.")
            role, content = message["role"], message["content"]
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise ValueError(f"Message invalide à l'index {index}.")
            if role == "system":
                system.append(content)
            else:
                conversation.append({"role": role, "content": content})
        if not conversation:
            raise ValueError("Au moins un message user ou assistant est requis.")
        body: dict[str, Any] = {"model": model, "max_tokens": 4096, "messages": conversation}
        if system:
            body["system"] = "\n\n".join(system)
        if options is not None:
            if not isinstance(options, dict) or options.keys() - {"max_tokens", "stop_sequences"}:
                raise ValueError("Options Messages Anthropic non prises en charge.")
            if "max_tokens" in options:
                value = options["max_tokens"]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError("max_tokens doit être un entier positif.")
            if "stop_sequences" in options and (
                not isinstance(options["stop_sequences"], list)
                or any(not isinstance(item, str) for item in options["stop_sequences"])
            ):
                raise ValueError("stop_sequences doit être une liste de chaînes.")
            body.update(options)
        return body

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not isinstance(model, str) or not model.strip() or ":" in model:
            raise ValueError("model doit être un identifiant Anthropic non vide.")
        if not self.settings.base_url:
            raise ProviderError("URL de base Anthropic non configurée.", provider=self.name, model=model, fatal=True)
        if not self._api_key:
            raise AuthenticationError(
                f"Clé absente : définissez la variable {self.settings.api_key_env}.",
                provider=self.name,
                model=model,
                fatal=True,
            )
        body = self._request_body(messages, model, options)
        request = Request(
            f"{self.settings.base_url.rstrip('/')}/messages",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": self.api_version,
            },
            method="POST",
        )
        try:
            with build_opener(_NoRedirect).open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            common = {"provider": self.name, "model": model, "status_code": status}
            if status == 401:
                raise AuthenticationError("Anthropic a refusé la clé API configurée.", fatal=True, **common) from exc
            if status == 403:
                raise AccessDeniedError("Anthropic a refusé l'accès à cette ressource.", fallback=True, **common) from exc
            if status == 404:
                raise ModelNotFoundError("Anthropic n'a pas trouvé le modèle configuré.", fallback=True, **common) from exc
            if status == 429:
                raise RateLimitError("Anthropic a signalé une limite de débit ou de quota.", retryable=True, fallback=True, **common) from exc
            if status == 408:
                raise NetworkError("Anthropic a expiré la requête.", retryable=True, fallback=True, **common) from exc
            if 500 <= status <= 599:
                raise TransientProviderError("Anthropic a renvoyé une erreur serveur.", retryable=True, fallback=True, **common) from exc
            if status in (400, 422):
                # Requête ou modèle rejeté : essayer le candidat suivant.
                raise ProviderError(f"Anthropic a rejeté la requête (HTTP {status}).", fallback=True, **common) from exc
            raise ProviderError(f"Anthropic a renvoyé HTTP {status}.", fatal=True, **common) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkError("Délai dépassé lors de l'appel Anthropic.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        except URLError as exc:
            raise NetworkError("Erreur réseau lors de l'appel Anthropic.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        try:
            payload = json.loads(raw)
            blocks = payload["content"]
            if not isinstance(blocks, list):
                raise TypeError
            text = "".join(block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidResponseError("Réponse Anthropic non conforme au contrat Messages.", provider=self.name, model=model, fatal=True) from exc
        if not text:
            raise InvalidResponseError("Réponse Anthropic sans texte exploitable.", provider=self.name, model=model, fatal=True)
        return text
