from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderResponse:
    stop_reason: str        # "tool_use" | "end_turn" | "max_tokens"
    text_content: str       # concatenated text blocks
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class AgentProvider(ABC):
    @abstractmethod
    def create_message(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        ...
