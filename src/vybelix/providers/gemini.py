"""Adaptateur REST Gemini GenerateContent, basé sur la bibliothèque standard."""

from __future__ import annotations

import json
import re
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
    """Traduit les messages Vybelix vers l'API Gemini GenerateContent."""

    name = "gemini"
    _OPTION_NAMES = {
        "max_output_tokens": "maxOutputTokens",
        "seed": "seed",
        "thinking_level": "thinkingConfig",
        "temperature": "temperature",
        "top_p": "topP",
        "response_mime_type": "responseMimeType",
        "response_schema": "responseSchema",
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
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise ValueError(f"messages[{index}] doit contenir role et content.")
            role, content = message["role"], message["content"]
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise ValueError(f"Message invalide a l'index {index}.")
            if role == "system":
                system_parts.append({"text": content})
            else:
                contents.append({
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                })
        if not contents:
            raise ValueError("Au moins un message user ou assistant est requis.")

        body: dict[str, Any] = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        if options is not None:
            if not isinstance(options, dict):
                raise ValueError("options doit etre un objet.")
            unknown = options.keys() - GeminiAdapter._OPTION_NAMES.keys()
            if unknown:
                raise ValueError(f"Options Gemini non prises en charge: {', '.join(sorted(unknown))}.")
            generation_config: dict[str, Any] = {}
            for name, value in options.items():
                target = GeminiAdapter._OPTION_NAMES[name]
                if name == "thinking_level":
                    if not isinstance(value, str) or value.lower() not in {"low", "medium", "high"}:
                        raise ValueError("thinking_level Gemini invalide pour les modèles Gemini 3 (low, medium, high).")
                    generation_config[target] = {"thinkingLevel": value.upper()}
                else:
                    generation_config[target] = value
            body["generationConfig"] = generation_config
        return body

    def _safe_error_detail(self, error: HTTPError) -> str | None:
        """Extrait le message Google sans exposer une clé éventuellement répercutée."""
        try:
            payload = json.loads(error.read().decode("utf-8", errors="replace"))
            message = payload.get("error", {}).get("message")
        except (json.JSONDecodeError, AttributeError, TypeError, UnicodeError):
            return None
        if not isinstance(message, str) or not message.strip():
            return None
        if self._api_key:
            message = message.replace(self._api_key, "[MASKED]")
        message = re.sub(r"(?i)AIza[0-9A-Za-z_-]{20,}", "[MASKED]", message)
        message = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [MASKED]", message)
        message = re.sub(r"(?i)([?&](?:key|api_key)=)[^&\s]+", r"\1[MASKED]", message)
        return " ".join(message.split())[:240]

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

        url = f"{self.settings.base_url.rstrip('/')}/models/{model}:generateContent"
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
            detail = self._safe_error_detail(exc)
            exc.close()
            common = {"provider": self.name, "model": model, "status_code": status}
            if status == 401:
                raise AuthenticationError("Gemini a refusé la clé API configurée.", fatal=True, **common) from exc
            if status == 403:
                raise AccessDeniedError("Gemini a refusé l'accès à cette ressource.", fallback=True, **common) from exc
            if status == 429:
                raise RateLimitError("Gemini a signalé une limite de débit.", retryable=True, fallback=True, **common) from exc
            if status == 404:
                raise ModelNotFoundError("Gemini n'a pas trouvé le modèle configuré.", fallback=True, **common) from exc
            if status == 408:
                raise NetworkError(
                    "Gemini a expiré la requête.", retryable=True, fallback=True, **common
                ) from exc
            if 500 <= status <= 599:
                message = "Gemini a renvoyé une erreur serveur."
                if detail:
                    message += f" Détail fournisseur : {detail}"
                raise TransientProviderError(
                    message, retryable=True, fallback=True, **common
                ) from exc
            raise ProviderError(f"Gemini a renvoyé HTTP {status}.", fatal=True, **common) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkError("Délai dépassé lors de l'appel Gemini.", provider=self.name, model=model, retryable=True, fallback=True) from exc
        except URLError as exc:
            raise NetworkError("Erreur réseau lors de l'appel Gemini.", provider=self.name, model=model, retryable=True, fallback=True) from exc

        try:
            payload = json.loads(raw_response)
            candidates = payload["candidates"]
            if not isinstance(candidates, list):
                raise TypeError
            text = "".join(
                part["text"]
                for candidate in candidates
                for part in candidate.get("content", {}).get("parts", [])
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
            raise InvalidResponseError(
                "Réponse Gemini vide ou non conforme au contrat GenerateContent.",
                provider=self.name,
                model=model,
                fatal=True,
            ) from exc
        if not text:
            raise InvalidResponseError(
                "Réponse Gemini sans texte exploitable.", provider=self.name, model=model, fatal=True
            )
        return text
