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


def create_provider(provider_name: str, model: str, api_key: str, **kwargs) -> AgentProvider:
    cls = PROVIDER_MAP.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Unknown provider {provider_name!r}. "
            f"Choose from: {', '.join(PROVIDER_MAP)}"
        )
    # Pass only kwargs the provider's constructor accepts (e.g.
    # reasoning_effort for OpenAI, thinking_effort for Anthropic).
    import inspect

    sig = inspect.signature(cls.__init__)
    accepted = {
        k: v for k, v in kwargs.items()
        if k in sig.parameters and v is not None
    }
    return cls(api_key=api_key, model=model, **accepted)
