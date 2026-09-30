"""Erreurs de fournisseur sans contenu de requête ni secret."""


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        status_code: int | None = None,
        retryable: bool = False,
        fallback: bool = False,
        fatal: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.retryable = retryable
        self.fallback = fallback
        self.fatal = fatal


class AuthenticationError(ProviderError):
    """Clé absente ou refusée ; aucun nouvel essai n'est fait."""


class AccessDeniedError(ProviderError):
    """Accès refusé pour ce candidat ; un candidat de secours explicite peut être essayé."""


class RateLimitError(ProviderError):
    """Limite de débit ou quota ; retry borné puis candidat suivant."""


class ModelNotFoundError(ProviderError):
    """Modèle introuvable ; passer au prochain candidat."""


class TransientProviderError(ProviderError):
    """Erreur 5xx réessayable avec backoff borné avant le fallback."""


class NetworkError(ProviderError):
    """Erreur réseau ou délai dépassé, réessayable avec backoff borné."""


class InvalidResponseError(ProviderError):
    """Réponse fournisseur absente ou mal formée."""


class RoutingError(RuntimeError):
    """Aucun modèle candidat n'a fourni de réponse exploitable."""

    def __init__(self, message: str, attempts: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(message)
        self.attempts = attempts
