from __future__ import annotations

from .openai_provider import OpenAIProvider

MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"


class MoonshotProvider(OpenAIProvider):
    def __init__(self, api_key: str, model: str, reasoning_effort: str | None = None):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=MOONSHOT_BASE_URL,
            reasoning_effort=reasoning_effort,
        )

    def _token_param(self) -> str:
        return "max_completion_tokens"
