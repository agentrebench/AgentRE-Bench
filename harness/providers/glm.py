from __future__ import annotations

from .openai_provider import OpenAIProvider

GLM_BASE_URL = "https://api.z.ai/api/paas/v4"


class GLMProvider(OpenAIProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model, base_url=GLM_BASE_URL)

    def _token_param(self) -> str:
        return "max_tokens"
