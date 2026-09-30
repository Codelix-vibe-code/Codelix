"""Adaptateur Mistral AI via l'API Chat Completions compatible OpenAI."""
from ..config import ProviderSettings
from .openai_compatible import OpenAICompatibleAdapter


class MistralAdapter(OpenAICompatibleAdapter):
    def __init__(self, settings: ProviderSettings, *, api_key: str | None = None, timeout_seconds: int = 300):
        super().__init__("mistral", settings, api_key=api_key, timeout_seconds=timeout_seconds)
