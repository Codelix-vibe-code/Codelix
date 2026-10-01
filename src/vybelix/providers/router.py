"""Routeur ordonné avec retry borné et journal d'essais sans secrets."""

from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Any, Protocol

from ..config import VybelixConfig
from .errors import AuthenticationError, ProviderError, RoutingError
from .anthropic import AnthropicAdapter
from .gemini import GeminiAdapter
from .groq import GroqAdapter
from .nvidia import NvidiaAdapter
from .mistral import MistralAdapter
from .openai import OpenAIAdapter
from .openrouter import OpenRouterAdapter


class Provider(Protocol):
    name: str

    def complete(
        self, messages: list[dict[str, str]], model: str, options: dict[str, Any] | None = None
    ) -> str: ...


@dataclass(frozen=True)
class RouteAttempt:
    provider: str
    model: str
    attempt: int
    outcome: str
    status_code: int | None = None
    message: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "status_code": self.status_code,
            "message": self.message,
        }


class ModelRouter:
    """Essaie les candidats configurés dans l'ordre et conserve une trace compacte."""

    def __init__(
        self,
        providers: dict[str, Provider],
        routes: dict[str, tuple[str, ...] | list[str]],
        *,
        transient_retries: int = 1,
    ) -> None:
        if isinstance(transient_retries, bool) or not isinstance(transient_retries, int) or not 0 <= transient_retries <= 3:
            raise ValueError("transient_retries doit être compris entre 0 et 3.")
        self.providers = providers
        self.routes = {role: tuple(candidates) for role, candidates in routes.items()}
        self.transient_retries = transient_retries
        self.last_trace: tuple[RouteAttempt, ...] = ()

    @staticmethod
    def _candidate(candidate: str) -> tuple[str, str]:
        if not isinstance(candidate, str) or ":" not in candidate:
            raise RoutingError("Candidat invalide ; format attendu : fournisseur:modèle.")
        provider, model = candidate.split(":", 1)
        if not provider or not model:
            raise RoutingError("Candidat invalide ; format attendu : fournisseur:modèle.")
        return provider, model

    def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> str:
        candidates = self.routes.get(role, ())
        trace: list[RouteAttempt] = []
        if not candidates:
            self.last_trace = ()
            raise RoutingError(f"Aucun modèle configuré pour le rôle {role}.")

        for candidate_index, candidate in enumerate(candidates):
            provider_name, model = self._candidate(candidate)
            provider = self.providers.get(provider_name)
            if provider is None:
                trace.append(RouteAttempt(provider_name, model, 0, "provider_unavailable", message="Fournisseur non configuré."))
                continue
            candidate_options = options
            if candidate_options is None:
                # Keep JSON-producing workflow calls from relying on each
                # vendor's undocumented output limit. Option names differ by
                # API, so choose them per candidate to preserve fallbacks.
                if provider_name == "gemini":
                    candidate_options = {"max_output_tokens": 4096}
                elif provider_name == "anthropic":
                    candidate_options = {"max_tokens": 4096}
                elif provider_name == "openai":
                    candidate_options = {"max_completion_tokens": 4096}
                elif provider_name == "openrouter":
                    candidate_options = {"max_tokens": 8192}
                    if "nemotron" in model.lower():
                        candidate_options["reasoning"] = {"effort": "low"}
                elif provider_name in {"nvidia", "groq", "mistral"}:
                    candidate_options = {"max_tokens": 4096}
            attempts_allowed = 1 + self.transient_retries
            for attempt_number in range(1, attempts_allowed + 1):
                try:
                    result = provider.complete(messages, model, candidate_options)
                    trace.append(RouteAttempt(provider_name, model, attempt_number, "success"))
                    self.last_trace = tuple(trace)
                    return result
                except ProviderError as exc:
                    trace.append(
                        RouteAttempt(
                            provider_name,
                            model,
                            attempt_number,
                            "error",
                            status_code=exc.status_code,
                            message=str(exc),
                        )
                    )
                    if isinstance(exc, AuthenticationError):
                        # A missing or rejected key disables only this candidate.
                        # Keep walking the route, including when this is the last one,
                        # so its error cannot hide an earlier provider failure.
                        break
                    if exc.fatal:
                        self.last_trace = tuple(trace)
                        raise RoutingError(str(exc), tuple(item.as_dict() for item in trace)) from exc
                    if exc.retryable and attempt_number < attempts_allowed:
                        # Bounded exponential backoff (1s, 2s, 4s) plus jitter.
                        delay = min(8.0, 2.0 ** (attempt_number - 1))
                        jitter = random.uniform(0.0, min(0.5, delay * 0.25))
                        time.sleep(delay + jitter)
                        continue
                    if exc.fallback:
                        break
                    self.last_trace = tuple(trace)
                    raise RoutingError(str(exc), tuple(item.as_dict() for item in trace)) from exc
                except Exception as exc:
                    trace.append(RouteAttempt(provider_name, model, attempt_number, "provider_error", message=type(exc).__name__))
                    break

        self.last_trace = tuple(trace)
        failures = [
            f"{item.provider}:{item.model} — {item.message or item.outcome}"
            for item in trace
            if item.outcome != "success"
        ]
        summary = "Aucun candidat configuré n'a fourni de réponse."
        if failures:
            summary += " Détail des essais : " + " ; ".join(failures)
        raise RoutingError(summary, tuple(item.as_dict() for item in trace))


def build_router(config: VybelixConfig) -> ModelRouter:
    """Construit le routeur depuis la configuration validée, sans clés codées en dur."""
    providers: dict[str, Provider] = {}
    gemini_settings = config.providers.get("gemini")
    if gemini_settings is not None:
        providers["gemini"] = GeminiAdapter(
            gemini_settings,
            timeout_seconds=config.runtime.request_timeout_seconds,
        )
    compatible_adapters = {
        "openai": OpenAIAdapter,
        "nvidia": NvidiaAdapter,
        "groq": GroqAdapter,
        "openrouter": OpenRouterAdapter,
        "mistral": MistralAdapter,
    }
    for provider_name, adapter_type in compatible_adapters.items():
        settings = config.providers.get(provider_name)
        if settings is not None:
            providers[provider_name] = adapter_type(
                settings, timeout_seconds=config.runtime.request_timeout_seconds,
            )
    anthropic_settings = config.providers.get("anthropic")
    if anthropic_settings is not None:
        providers["anthropic"] = AnthropicAdapter(
            anthropic_settings,
            timeout_seconds=config.runtime.request_timeout_seconds,
        )
    return ModelRouter(
        providers,
        config.models,
        transient_retries=config.runtime.network_retries,
    )
