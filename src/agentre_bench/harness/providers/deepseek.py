from __future__ import annotations

from .openai_provider import OpenAIProvider

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(OpenAIProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model, base_url=DEEPSEEK_BASE_URL)

    def _token_param(self) -> str:
        return "max_tokens"
