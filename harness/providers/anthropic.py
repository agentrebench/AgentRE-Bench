from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .base import AgentProvider, ProviderResponse, ToolCall

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(AgentProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        thinking_effort: str = "high",
    ):
        self.api_key = api_key
        self.model = model
        self.thinking_effort = thinking_effort

    def create_message(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        # Adaptive thinking + high effort gives the model headroom; raise
        # max_tokens since reasoning + answer + tool args all share the budget.
        effective_max = max(max_tokens, 16000)

        body = {
            "model": self.model,
            "max_tokens": effective_max,
            "system": system,
            "messages": messages,
            "tools": tools,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.thinking_effort},
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error("Anthropic API error %d: %s", e.code, error_body)
            raise

        text_parts = []
        tool_calls = []
        thinking_blocks = []
        thinking_chars = 0

        for block in result.get("content", []):
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block["text"])
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        input=block["input"],
                    )
                )
            elif btype in ("thinking", "redacted_thinking"):
                # Preserve verbatim — signature must round-trip on next turn.
                thinking_blocks.append(block)
                if btype == "thinking":
                    thinking_chars += len(block.get("thinking", ""))

        usage = result.get("usage", {})

        # Anthropic doesn't break out reasoning tokens in usage; estimate from
        # thinking block character length (~4 chars/token is the standard rule).
        est_reasoning_tokens = thinking_chars // 4

        return ProviderResponse(
            stop_reason=result.get("stop_reason", "end_turn"),
            text_content="\n".join(text_parts),
            tool_calls=tool_calls,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            reasoning_tokens=est_reasoning_tokens,
            thinking_blocks=thinking_blocks,
        )
