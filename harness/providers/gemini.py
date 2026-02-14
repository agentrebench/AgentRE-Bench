from __future__ import annotations

import json
import logging
import urllib.request

from .base import AgentProvider, ProviderResponse, ToolCall
from ..tools import schemas_to_gemini_declarations

log = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AgentProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def create_message(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        declarations = schemas_to_gemini_declarations(tools)

        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": self._convert_messages(messages),
            "tools": [{"function_declarations": declarations}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        url = f"{API_URL}/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error("Gemini API error %s: %s", e.code, error_body)
            raise

        candidate = result["candidates"][0]
        text_parts = []
        tool_calls = []

        for part in candidate.get("content", {}).get("parts", []):
            if "functionCall" in part:
                fc = part["functionCall"]
                meta = {}
                if "thoughtSignature" in part:
                    meta["thoughtSignature"] = part["thoughtSignature"]
                tool_calls.append(
                    ToolCall(
                        id=f"gemini_{fc['name']}_{len(tool_calls)}",
                        name=fc["name"],
                        input=fc.get("args", {}),
                        metadata=meta,
                    )
                )
            elif "text" in part:
                text_parts.append(part["text"])

        stop_reason = "end_turn"
        if tool_calls:
            stop_reason = "tool_use"
        elif candidate.get("finishReason") == "MAX_TOKENS":
            stop_reason = "max_tokens"

        usage = result.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return ProviderResponse(
            stop_reason=stop_reason,
            text_content="\n".join(text_parts),
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        gemini_msgs = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                parts = []
                if isinstance(content, str):
                    parts.append({"text": content})
                else:
                    for block in content:
                        if isinstance(block, str):
                            parts.append({"text": block})
                        elif isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append({"text": block.get("text", "")})
                            elif block.get("type") == "tool_result":
                                result_content = block.get("content", "")
                                if isinstance(result_content, list):
                                    result_content = "\n".join(
                                        b.get("text", "") for b in result_content
                                        if isinstance(b, dict)
                                    )
                                parts.append({
                                    "functionResponse": {
                                        "name": block.get("tool_name", "unknown"),
                                        "response": {"result": str(result_content)},
                                    }
                                })
                gemini_msgs.append({"role": "user", "parts": parts or [{"text": ""}]})

            elif role == "assistant":
                parts = []
                if isinstance(content, str):
                    parts.append({"text": content})
                else:
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append({"text": block.get("text", "")})
                            elif block.get("type") == "tool_use":
                                fc_part = {
                                    "functionCall": {
                                        "name": block["name"],
                                        "args": block.get("input", {}),
                                    }
                                }
                                sig = block.get("metadata", {}).get("thoughtSignature")
                                if sig:
                                    fc_part["thoughtSignature"] = sig
                                parts.append(fc_part)
                gemini_msgs.append({"role": "model", "parts": parts or [{"text": ""}]})

        return gemini_msgs
