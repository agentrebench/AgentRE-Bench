"""OpenAI-compatible provider message conversion tests."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))

from agentre_bench.harness.providers.openai_provider import _convert_message_impl


def test_reasoning_only_assistant_content_is_non_null():
    converted = _convert_message_impl({
        "role": "assistant",
        "content": [{"type": "reasoning", "text": "continued analysis"}],
    })

    assert converted == [{
        "role": "assistant",
        "content": "",
        "reasoning_content": "continued analysis",
    }]


def test_reasoning_and_tool_call_are_replayed_together():
    converted = _convert_message_impl({
        "role": "assistant",
        "content": [
            {"type": "reasoning", "text": "inspect headers"},
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "pe_info",
                "input": {"path": "sample.bin"},
            },
        ],
    })

    assert converted[0]["content"] == ""
    assert converted[0]["reasoning_content"] == "inspect headers"
    assert converted[0]["tool_calls"][0]["id"] == "call_1"
