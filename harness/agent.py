from __future__ import annotations

import json
import logging
import time
from typing import Any

from .providers.base import AgentProvider, ProviderResponse
from .tools import ToolExecutor, get_tool_schemas

log = logging.getLogger(__name__)


class AgentLoop:
    def __init__(
        self,
        provider: AgentProvider,
        tool_executor: ToolExecutor,
        system_prompt: str,
        task_id: str,
        max_tool_calls: int = 25,
        max_tokens: int = 4096,
        verbose: bool = False,
    ):
        self.provider = provider
        self.tool_executor = tool_executor
        self.system_prompt = system_prompt
        self.task_id = task_id
        self.max_tool_calls = max_tool_calls
        self.max_tokens = max_tokens
        self.verbose = verbose

        self.messages: list[dict] = []
        self.tool_call_count = 0
        self.tool_calls_log: list[dict] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.invalid_tool_calls = 0
        self.invalid_json_attempts = 0

    def _vprint(self, *args, **kwargs):
        """Print only in verbose mode."""
        if self.verbose:
            print(*args, **kwargs, flush=True)

    def _dot(self):
        """Print a progress dot in non-verbose mode."""
        if not self.verbose:
            print(".", end="", flush=True)

    def run(self) -> dict[str, Any]:
        start_time = time.time()
        tools = get_tool_schemas(include_final_answer=True)

        # Initial user message
        self.messages.append({
            "role": "user",
            "content": (
                "Analyze the binary file in the workspace and submit your findings "
                "using the final_answer tool. The binary is located at the path "
                "shown in the system prompt. Use the available RE tools to examine it."
            ),
        })

        final_answer = None
        max_steps_hit = False

        while self.tool_call_count < self.max_tool_calls:
            try:
                response = self.provider.create_message(
                    system=self.system_prompt,
                    messages=self.messages,
                    tools=tools,
                    max_tokens=self.max_tokens,
                )
            except Exception as e:
                log.error("[%s] Provider error: %s", self.task_id, e)
                self._vprint(f"\n  !! Provider error: {e}")
                break

            self.input_tokens += response.input_tokens
            self.output_tokens += response.output_tokens

            if response.stop_reason == "tool_use" and response.tool_calls:
                # Show agent reasoning (verbose only)
                if response.text_content:
                    self._vprint(f"\n  Agent:")
                    for line in response.text_content.strip().splitlines():
                        self._vprint(f"    {line}")

                # Build assistant content blocks
                assistant_content = []
                if response.text_content:
                    assistant_content.append({
                        "type": "text",
                        "text": response.text_content,
                    })

                for tc in response.tool_calls:
                    block = {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    }
                    if tc.metadata:
                        block["metadata"] = tc.metadata
                    assistant_content.append(block)

                self.messages.append({"role": "assistant", "content": assistant_content})

                # Execute each tool call
                tool_results = []
                for tc in response.tool_calls:
                    self.tool_call_count += 1
                    self.tool_calls_log.append({
                        "call_number": self.tool_call_count,
                        "tool": tc.name,
                        "input": tc.input,
                    })

                    # Verbose: show step and tool info
                    args_str = json.dumps(tc.input, default=str)
                    if len(args_str) > 120:
                        args_str = args_str[:120] + "..."
                    self._vprint(
                        f"\n  [{self.tool_call_count}/{self.max_tool_calls}] "
                        f"{tc.name}  {args_str}"
                    )

                    result = self.tool_executor.execute(tc.name, tc.input)

                    if result.get("is_final_answer"):
                        final_answer = result["answer"]
                        self.tool_calls_log[-1]["is_final_answer"] = True
                        self._vprint(f"\n  Final answer submitted")
                        self._dot()
                        break

                    if result.get("error"):
                        self.invalid_tool_calls += 1
                        output_text = f"Error: {result['error']}"
                    else:
                        output_text = result.get("output", "(no output)")

                    self.tool_calls_log[-1]["output_preview"] = output_text[:500]

                    # Verbose: show output preview
                    self._vprint(f"    -> {len(output_text)} chars")
                    preview_lines = output_text[:1500].splitlines()[:20]
                    for line in preview_lines:
                        self._vprint(f"       {line[:120]}")
                    if len(output_text) > 1500 or len(output_text.splitlines()) > 20:
                        self._vprint(f"       ... [truncated]")

                    # Non-verbose: progress dot
                    self._dot()

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": output_text,
                    })

                if final_answer is not None:
                    break

                if tool_results:
                    self.messages.append({"role": "user", "content": tool_results})

                    # Budget warnings
                    remaining = self.max_tool_calls - self.tool_call_count
                    if remaining == 5:
                        self.messages.append({
                            "role": "user",
                            "content": (
                                "IMPORTANT: You have only 5 tool calls remaining. "
                                "Start wrapping up your analysis and submit your "
                                "findings using the final_answer tool soon. "
                                "Submit your best answer with what you've found so far "
                                "rather than running out of tool calls."
                            ),
                        })
                        self._vprint(f"\n  ** Budget warning: 5 calls left **")
                    elif remaining == 2:
                        self.messages.append({
                            "role": "user",
                            "content": (
                                "CRITICAL: You have only 2 tool calls left. "
                                "You MUST call the final_answer tool NOW with your "
                                "best analysis. Do not use any more investigation tools."
                            ),
                        })
                        self._vprint(f"\n  ** Budget warning: 2 calls left **")

            elif response.stop_reason == "end_turn":
                if response.text_content:
                    self._vprint(f"\n  Agent (no tool call):")
                    for line in response.text_content.strip().splitlines()[:10]:
                        self._vprint(f"    {line}")

                # Agent stopped without calling a tool — try to extract JSON
                extracted = self._try_extract_json(response.text_content)
                if extracted is not None:
                    final_answer = extracted
                    self._vprint(f"  (extracted answer from text)")
                    break

                # Prompt agent to use final_answer tool
                self.invalid_json_attempts += 1
                self._vprint(f"  (nudging agent to use final_answer tool)")
                self.messages.append({
                    "role": "assistant",
                    "content": response.text_content,
                })
                self.messages.append({
                    "role": "user",
                    "content": (
                        "Please submit your analysis using the final_answer tool. "
                        "Do not respond with plain text — you must call the "
                        "final_answer tool with your findings."
                    ),
                })

            elif response.stop_reason == "max_tokens":
                self._vprint(f"\n  !! Hit max_tokens — continuing")
                if response.text_content:
                    self.messages.append({
                        "role": "assistant",
                        "content": response.text_content,
                    })
                    self.messages.append({
                        "role": "user",
                        "content": "Please continue your analysis and submit via final_answer tool.",
                    })
            else:
                self._vprint(f"\n  !! Unexpected stop: {response.stop_reason}")
                break

        else:
            max_steps_hit = True
            self._vprint(f"\n  !! Hit max tool calls limit ({self.max_tool_calls})")

        wall_time = time.time() - start_time

        self._vprint(
            f"\n  Done: {self.tool_call_count} calls, "
            f"{wall_time:.1f}s, "
            f"{self.input_tokens + self.output_tokens:,} tokens"
        )

        # Compute tool usage stats
        tool_calls_by_type: dict[str, int] = {}
        seen_calls: set[str] = set()
        redundant_tool_calls = 0
        for entry in self.tool_calls_log:
            name = entry["tool"]
            tool_calls_by_type[name] = tool_calls_by_type.get(name, 0) + 1
            call_key = f"{name}:{json.dumps(entry['input'], sort_keys=True, default=str)}"
            if call_key in seen_calls:
                redundant_tool_calls += 1
            seen_calls.add(call_key)

        return {
            "task_id": self.task_id,
            "final_answer": final_answer,
            "transcript": self.messages,
            "tool_call_count": self.tool_call_count,
            "tool_calls_by_type": tool_calls_by_type,
            "tool_calls_log": self.tool_calls_log,
            "redundant_tool_calls": redundant_tool_calls,
            "invalid_tool_calls": self.invalid_tool_calls,
            "invalid_json_attempts": self.invalid_json_attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "wall_time_seconds": round(wall_time, 2),
            "max_steps_hit": max_steps_hit,
            "has_valid_answer": final_answer is not None,
        }

    def _try_extract_json(self, text: str) -> dict | None:
        if not text:
            return None
        import re
        patterns = [
            r"```json\s*(.*?)```",
            r"```\s*(.*?)```",
            r"\{[^{}]*\"file_type\"[^{}]*\}",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.DOTALL):
                try:
                    data = json.loads(match.group(1) if match.lastindex else match.group(0))
                    if isinstance(data, dict) and "file_type" in data:
                        return data
                except (json.JSONDecodeError, IndexError):
                    continue
        return None
