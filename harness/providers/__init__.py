from .base import AgentProvider, ProviderResponse, ToolCall
from .anthropic import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini import GeminiProvider
from .deepseek import DeepSeekProvider
from .glm import GLMProvider
from .moonshot import MoonshotProvider

PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
    "glm": GLMProvider,
    "moonshot": MoonshotProvider,
}


def create_provider(provider_name: str, model: str, api_key: str) -> AgentProvider:
    cls = PROVIDER_MAP.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Unknown provider {provider_name!r}. "
            f"Choose from: {', '.join(PROVIDER_MAP)}"
        )
    return cls(api_key=api_key, model=model)
