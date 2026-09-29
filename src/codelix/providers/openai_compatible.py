"""Adaptateur REST pour les endpoints compatibles avec OpenAI Chat Completions."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..config import ProviderSettings, provider_api_key
from .errors import (
    AccessDeniedError, AuthenticationError, InvalidResponseError, ModelNotFoundError,
    NetworkError, ProviderError, RateLimitError, TransientProviderError,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleAdapter:
    """Adaptateur commun NVIDIA/Groq, sans SDK externe ni redirection de clé."""

    def __init__(
        self, name: str, settings: ProviderSettings, *, api_key: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        if name not in {"nvidia", "groq"}:
            raise ValueError("Fournisseur compatible non pris en charge.")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
            raise ValueError("timeout_seconds doit être compris entre 1 et 300.")
        self.name = name
        self.settings = settings
        self._api_key = api_key if api_key is not None else provider_api_key(settings)
        self.timeout_seconds = timeout_seconds

    def complete(
        self, messages: list[dict[str, str]], model: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model doit être un identifiant non vide.")
        if not self.settings.base_url:
            raise ProviderError(f"URL de base {self.name} non configurée.", provider=self.name, model=model, fatal=True)
        if not self._api_key:
            raise AuthenticationError(
                f"Clé absente : définissez la variable {self.settings.api_key_env}.",
                provider=self.name, model=model, fatal=True,
            )
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages doit contenir au moins un message.")
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError(f"messages[{index}] doit contenir role et content.")
            if message["role"] not in {"system", "user", "assistant"} or not isinstance(message["content"], str):
                raise ValueError(f"Message invalide à l'index {index}.")
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if options is not None:
            if not isinstance(options, dict) or options.keys() - {"max_tokens", "temperature", "top_p", "seed"}:
                raise ValueError("Options Chat Completions invalides ou non prises en charge.")
            body.update(options)
        request = Request(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
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
                raise AuthenticationError(f"{self.name} a refusé la clé API configurée.", fatal=True, **common) from exc
            if status == 403:
                raise AccessDeniedError(f"{self.name} a refusé l'accès à cette ressource.", fatal=True, **common) from exc
            if status == 404:
                raise ModelNotFoundError(f"{self.name} n'a pas trouvé le modèle configuré.", fallback=True, **common) from exc
            if status == 429:
                raise RateLimitError(f"{self.name} a signalé une limite de débit ou de quota.", fallback=True, **common) from exc
            if status == 408:
                raise NetworkError(f"{self.name} a expiré la requête.", retryable=True, fallback=True, **common) from exc
            if 500 <= status <= 599:
                raise TransientProviderError(f"{self.name} a renvoyé une erreur serveur.", retryable=True, fallback=True, **common) from exc
            raise ProviderError(f"{self.name} a renvoyé HTTP {status}.", fatal=True, **common) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkError(f"Délai dépassé lors de l'appel {self.name}.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        except URLError as exc:
            raise NetworkError(f"Erreur réseau lors de l'appel {self.name}.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        try:
            payload = json.loads(raw)
            text = payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise InvalidResponseError(f"Réponse {self.name} non conforme au contrat Chat Completions.", provider=self.name, model=model, fatal=True) from exc
        if not isinstance(text, str) or not text:
            raise InvalidResponseError(f"Réponse {self.name} sans texte exploitable.", provider=self.name, model=model, fatal=True)
        return text
