from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from agentre_bench.harness.config import BenchmarkConfig, _read_api_file
from agentre_bench.harness.providers import create_provider
from agentre_bench.harness.providers.anthropic import _sanitize_messages
from agentre_bench.harness.runner import (
    TaskConfig,
    _safe_run_namespace,
    build_system_prompt,
    load_tasks,
    stage_task_workspace,
)


def _config(root: Path, provider: str = "openai", model: str = "gpt/test") -> BenchmarkConfig:
    return BenchmarkConfig(
        project_root=root,
        workspace_dir=root,
        ground_truths_dir=root,
        provider=provider,
        model=model,
        use_docker=False,
    )


def test_api_file_friendly_labels(tmp_path):
    api_file = tmp_path / "api"
    api_file.write_text(
        "OPenAI: openai-test\n"
        "Claude = anthropic-test\n"
        "Kimi: moonshot-test\n"
        "DeepSeek=deepseek-test\n"
    )

    keys = _read_api_file(api_file)
    assert keys == {
        "OPENAI_API_KEY": "openai-test",
        "ANTHROPIC_API_KEY": "anthropic-test",
        "MOONSHOT_API_KEY": "moonshot-test",
        "DEEPSEEK_API_KEY": "deepseek-test",
    }


def test_api_file_standalone_anthropic_key_overrides_claude_descriptor(tmp_path):
    api_file = tmp_path / "api"
    api_file.write_text(
        "Claude: claude-opus-5\n"
        "\n"
        "sk-ant-test\n"
    )

    keys = _read_api_file(api_file)
    assert keys["ANTHROPIC_API_KEY"] == "sk-ant-test"


def test_api_file_precedes_environment(tmp_path, monkeypatch):
    (tmp_path / "api").write_text("OPenAI: file-key\n")
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    assert _config(tmp_path).resolve_api_key() == "file-key"


def test_pe_workspace_and_prompt_are_binary_only(tmp_path):
    binary = tmp_path / "original-technique-name.exe"
    binary.write_bytes(b"MZ" + b"\0" * 32)
    task = TaskConfig(
        task_id="v3_l14_u",
        binary_path=binary,
        ground_truth_path=tmp_path / "ground-truth.json",
        difficulty=14,
        display_name="sample_5281a1.bin",
    )
    config = _config(tmp_path)
    staging = tmp_path / ".workspaces" / _safe_run_namespace(config)
    workspace = stage_task_workspace(task, staging)

    assert [path.name for path in workspace.iterdir()] == ["sample_5281a1.bin"]
    prompt = build_system_prompt(task, config, {"file_type": "PE32+"})
    assert "sample_5281a1.bin" in prompt
    assert "original-technique-name" not in prompt
    assert "only this compiled PE artifact" in prompt
    assert "compile source code" in prompt
    assert _safe_run_namespace(config) == "openai_gpt_test"


def test_v3_manifest_resolves_versioned_artifacts():
    root = Path(__file__).parents[1]
    tasks = load_tasks(root / "version3" / "tasks_v3.json", root)

    assert len(tasks) == 20
    assert all(task.binary_path.is_file() for task in tasks)
    assert all(task.ground_truth_path.is_file() for task in tasks)
    assert tasks[0].binary_path == (
        root / "version3" / "binaries" / "windows"
        / "windows_level14_DLLInjection.exe"
    )


def test_none_provider_options_do_not_override_adapter_defaults():
    provider = create_provider(
        "anthropic", "test-model", "test-key", thinking_effort=None
    )
    assert provider.thinking_effort == "high"


def test_anthropic_removes_internal_tool_name():
    original = [{
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": "call-1",
            "tool_name": "file",
            "content": "PE32+",
        }],
    }]
    sanitized = _sanitize_messages(original)
    assert sanitized[0]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call-1",
        "content": "PE32+",
    }
    assert original[0]["content"][0]["tool_name"] == "file"
