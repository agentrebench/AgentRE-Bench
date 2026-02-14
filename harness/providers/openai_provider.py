from __future__ import annotations

import json
import logging
import urllib.request

from .base import AgentProvider, ProviderResponse, ToolCall
from ..tools import schemas_to_openai

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(AgentProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    def create_message(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        openai_tools = schemas_to_openai(tools)

        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.extend(self._convert_message(msg))

        # GPT-5+ models require max_output_tokens instead of max_tokens
        if self.model.startswith(("gpt-5", "o3", "o4")):
            token_param = {"max_output_tokens": max_tokens}
        else:
            token_param = {"max_tokens": max_tokens}

        body = {
            "model": self.model,
            "messages": oai_messages,
            "tools": openai_tools,
            **token_param,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = json.dumps(body).encode("utf-8")
        url = f"{self.base_url}/chat/completions"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        choice = result["choices"][0]
        message = choice["message"]

        tool_calls = []
        for tc in message.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            tool_calls.append(
                ToolCall(id=tc["id"], name=tc["function"]["name"], input=args)
            )

        stop_reason = "end_turn"
        if choice.get("finish_reason") == "tool_calls":
            stop_reason = "tool_use"
        elif choice.get("finish_reason") == "length":
            stop_reason = "max_tokens"

        usage = result.get("usage", {})

        return ProviderResponse(
            stop_reason=stop_reason,
            text_content=message.get("content") or "",
            tool_calls=tool_calls,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def _convert_message(self, msg: dict) -> list[dict]:
        role = msg["role"]

        if role == "user":
            content = msg["content"]
            if isinstance(content, str):
                return [{"role": "user", "content": content}]

            parts = []
            tool_results = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    if block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            result_content = "\n".join(
                                b.get("text", "") for b in result_content
                                if isinstance(b, dict)
                            )
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": str(result_content),
                        })
                    elif block.get("type") == "text":
                        parts.append(block.get("text", ""))

            result = []
            if parts:
                result.append({"role": "user", "content": "\n".join(parts)})
            result.extend(tool_results)
            return result

        if role == "assistant":
            content = msg["content"]
            if isinstance(content, str):
                return [{"role": "assistant", "content": content}]

            text_parts = []
            oai_tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        oai_tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            },
                        })

            assistant_msg = {"role": "assistant"}
            assistant_msg["content"] = "\n".join(text_parts) if text_parts else None
            if oai_tool_calls:
                assistant_msg["tool_calls"] = oai_tool_calls
            return [assistant_msg]

        return [msg]
