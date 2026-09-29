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
from .gemini import GeminiAdapter
from .router import ModelRouter, RouteAttempt, build_router

__all__ = [
    "AccessDeniedError",
    "AuthenticationError",
    "GeminiAdapter",
    "InvalidResponseError",
    "ModelNotFoundError",
    "ModelRouter",
    "NetworkError",
    "ProviderError",
    "RateLimitError",
    "RouteAttempt",
    "RoutingError",
    "TransientProviderError",
    "build_router",
]
