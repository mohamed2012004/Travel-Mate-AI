import os

from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

_PROVIDERS: dict[str, type] = {
    "groq": ChatGroq,
}

_DEFAULT_PROVIDER = "groq"
_DEFAULT_MODELS: dict[str, str] = {
    "groq": "openai/gpt-oss-120b",
}


class LLM:
    """Create a chat LLM by provider/model name.

    Change only the environment to switch models:
        LLM_PROVIDER=groq GROQ_MODEL=openai/gpt-oss-120b
    or pass them explicitly: LLM(provider="groq", model="...").get_llm()
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", _DEFAULT_PROVIDER)).lower()
        if self.provider not in _PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider {self.provider!r}. "
                f"Supported: {sorted(_PROVIDERS)}"
            )
        env_prefix = self.provider.upper()
        self.model = (
            model
            or os.getenv(f"{env_prefix}_MODEL")
            or _DEFAULT_MODELS[self.provider]
        )
        self.api_key = api_key or os.getenv(f"{env_prefix}_API_KEY")
        if not self.api_key:
            raise ValueError(
                f"{env_prefix}_API_KEY is missing. Please add it to your .env file."
            )
        self._kwargs = kwargs
        self._client: BaseChatModel | None = None

    def get_llm(self) -> BaseChatModel:
        """Return the configured chat model, creating it on first use."""
        if self._client is None:
            self._client = _PROVIDERS[self.provider](
                model=self.model,
                api_key=self.api_key,
                **self._kwargs,
            )
        return self._client


def create_llm(**kwargs) -> BaseChatModel:
    """Factory shortcut: create_llm() / create_llm(model="...")"""
    return LLM(**kwargs).get_llm()
