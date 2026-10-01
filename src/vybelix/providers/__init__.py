"""Adaptateurs de fournisseurs et routage de modèles."""

from .errors import (
    AccessDeniedError,
    AuthenticationError,
    InvalidResponseError,
    ModelNotFoundError,
    NetworkError,
    ProviderError,
    RateLimitError,
    RoutingError,
    TransientProviderError,
)
from .anthropic import AnthropicAdapter
from .gemini import GeminiAdapter
from .groq import GroqAdapter
from .nvidia import NvidiaAdapter
from .mistral import MistralAdapter
from .openrouter import OpenRouterAdapter
from .openai_compatible import OpenAICompatibleAdapter
from .openai import OpenAIAdapter
from .router import ModelRouter, RouteAttempt, build_router

__all__ = [
    "AccessDeniedError",
    "AnthropicAdapter",
    "AuthenticationError",
    "GeminiAdapter",
    "GroqAdapter",
    "InvalidResponseError",
    "ModelNotFoundError",
    "ModelRouter",
    "MistralAdapter",
    "OpenAICompatibleAdapter",
    "OpenAIAdapter",
    "NetworkError",
    "NvidiaAdapter",
    "OpenRouterAdapter",
    "ProviderError",
    "RateLimitError",
    "RouteAttempt",
    "RoutingError",
    "TransientProviderError",
    "build_router",
]
