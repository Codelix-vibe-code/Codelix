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
    """Accès refusé ; la tâche s'arrête sans essayer un autre modèle."""


class RateLimitError(ProviderError):
    """Limite de débit ; passer au prochain candidat."""


class ModelNotFoundError(ProviderError):
    """Modèle introuvable ; passer au prochain candidat."""


class TransientProviderError(ProviderError):
    """Erreur 5xx susceptible de réussir après une seule nouvelle tentative."""


class NetworkError(ProviderError):
    """Erreur réseau ou délai dépassé, avec une seule nouvelle tentative permise."""


class InvalidResponseError(ProviderError):
    """Réponse fournisseur absente ou mal formée."""


class RoutingError(RuntimeError):
    """Aucun modèle candidat n'a fourni de réponse exploitable."""

    def __init__(self, message: str, attempts: tuple[dict[str, object], ...] = ()) -> None:
        super().__init__(message)
        self.attempts = attempts
