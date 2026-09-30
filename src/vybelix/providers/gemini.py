"""Adaptateur REST Gemini Interactions, basé sur la bibliothèque standard."""

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
    """Ne transmet pas l'en-tête contenant la clé à une URL de redirection."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_without_redirect(request: Request, timeout: int):
    return build_opener(_NoRedirect).open(request, timeout=timeout)


class GeminiAdapter:
    """Traduit les messages communs Vybelix vers la Gemini Interactions API."""

    name = "gemini"
    _OPTION_NAMES = {
        "max_output_tokens": "max_output_tokens",
        "seed": "seed",
        "thinking_level": "thinking_level",
    }

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
    def _request_body(
        messages: list[dict[str, str]], model: str, options: dict[str, Any] | None
    ) -> dict[str, Any]:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages doit contenir au moins un message.")
        conversation: list[str] = []
        system_text: list[str] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError(f"messages[{index}] doit contenir role et content.")
            role, content = message["role"], message["content"]
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise ValueError(f"Message invalide à l'index {index}.")
            if role == "system":
                system_text.append(content)
            else:
                speaker = "Assistant" if role == "assistant" else "User"
                conversation.append(f"{speaker}:\n{content}")
        if not conversation:
            raise ValueError("Au moins un message user ou assistant est requis.")

        body: dict[str, Any] = {
            "model": model,
            "input": "\n\n".join(conversation),
            "store": False,
        }
        if system_text:
            body["system_instruction"] = "\n\n".join(system_text)
        if options is not None:
            if not isinstance(options, dict):
                raise ValueError("options doit être un objet.")
            unknown = options.keys() - GeminiAdapter._OPTION_NAMES.keys()
            if unknown:
                raise ValueError(f"Options Gemini non prises en charge: {', '.join(sorted(unknown))}.")
            body["generation_config"] = {
                GeminiAdapter._OPTION_NAMES[name]: value for name, value in options.items()
            }
        return body

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not isinstance(model, str) or not model.strip() or "/" in model or ":" in model:
            raise ValueError("model doit être un identifiant Gemini simple configuré par l'utilisateur.")
        if not self.settings.base_url:
            raise ProviderError(
                "URL de base Gemini non configurée.", provider=self.name, model=model, fatal=True
            )
        if not self._api_key:
            raise AuthenticationError(
                f"Clé absente : définissez la variable {self.settings.api_key_env}.",
                provider=self.name,
                model=model,
                fatal=True,
            )

        url = f"{self.settings.base_url.rstrip('/')}/interactions"
        body = self._request_body(messages, model, options)
        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            method="POST",
        )
        try:
            with _open_without_redirect(request, timeout=self.timeout_seconds) as response:
                raw_response = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            common = {"provider": self.name, "model": model, "status_code": status}
            if status == 401:
                raise AuthenticationError("Gemini a refusé la clé API configurée.", fatal=True, **common) from exc
            if status == 403:
                raise AccessDeniedError("Gemini a refusé l'accès à cette ressource.", fatal=True, **common) from exc
            if status == 429:
                raise RateLimitError("Gemini a signalé une limite de débit.", fallback=True, **common) from exc
            if status == 404:
                raise ModelNotFoundError("Gemini n'a pas trouvé le modèle configuré.", fallback=True, **common) from exc
            if status == 408:
                raise NetworkError(
                    "Gemini a expiré la requête.", retryable=True, fallback=True, **common
                ) from exc
            if 500 <= status <= 599:
                raise TransientProviderError(
                    "Gemini a renvoyé une erreur serveur.", retryable=True, fallback=True, **common
                ) from exc
            raise ProviderError(f"Gemini a renvoyé HTTP {status}.", fatal=True, **common) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkError("Délai dépassé lors de l'appel Gemini.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        except URLError as exc:
            raise NetworkError("Erreur réseau lors de l'appel Gemini.", provider=self.name, model=model, retryable=True, fallback=True) from exc

        try:
            payload = json.loads(raw_response)
            if payload["status"] != "completed":
                raise ValueError("Interaction Gemini non terminée.")
            steps = payload["steps"]
            text = "".join(
                item["text"]
                for step in steps
                if step.get("type") == "model_output"
                for item in step.get("content", [])
                if item.get("type") == "text" and isinstance(item.get("text"), str)
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
            raise InvalidResponseError(
                "Réponse Gemini vide ou non conforme au contrat attendu.",
                provider=self.name,
                model=model,
                fatal=True,
            ) from exc
        if not text:
            raise InvalidResponseError(
                "Réponse Gemini sans texte exploitable.", provider=self.name, model=model, fatal=True
            )
        return text
