"""End-to-end harness test: mock provider through the real agent loop.

Exercises run_single_task in Docker mode: family-aware prompts, tool
dispatch (ELF + PE), final-answer capture, scoring, metrics, transcripts.

Requires docker + the agentre-bench-tools image; skips otherwise.
"""

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agentre_bench.harness import runner  # noqa: E402
from agentre_bench.harness.config import BenchmarkConfig  # noqa: E402
from agentre_bench.harness.metrics import compute_aggregate  # noqa: E402
from agentre_bench.harness.providers.base import (  # noqa: E402
    AgentProvider,
    ProviderResponse,
    ToolCall,
)
from scorer import _enc_algorithms, _enc_key_candidates  # noqa: E402

docker_available = (
    shutil.which("docker") is not None
    and subprocess.run(
        ["docker", "image", "inspect", "agentre-bench-tools:latest"],
        capture_output=True,
    ).returncode == 0
)
pytestmark = pytest.mark.skipif(
    not docker_available, reason="docker + agentre-bench-tools image required"
)


class MockProvider(AgentProvider):
    """Plays a scripted sequence of tool calls, then ends the turn."""

    last_system: str = ""

    def __init__(self, script):
        self.script = script
        self.pos = 0

    def create_message(self, system, messages, tools, max_tokens=4096):
        MockProvider.last_system = system
        if self.pos >= len(self.script):
            return ProviderResponse(stop_reason="end_turn", text_content="done")
        name, inp = self.script[self.pos]
        self.pos += 1
        return ProviderResponse(
            stop_reason="tool_use",
            text_content="mock step",
            tool_calls=[ToolCall(id=f"tc{self.pos}", name=name, input=inp)],
            input_tokens=100,
            output_tokens=50,
        )


def perfect_answer(gt):
    a = {
        "file_type": gt.get("file_type"),
        "encoded_strings": gt.get("encoded_strings"),
        "decoded_c2": gt.get("decoded_c2"),
        "c2_protocol": gt.get("c2_protocol"),
        "techniques": gt.get("techniques", []),
    }
    for k in ("anti_analysis", "decoded_strings", "injection_details"):
        if gt.get(k):
            a[k] = gt[k]
    algos = _enc_algorithms(gt.get("encryption_details"))
    keys = _enc_key_candidates(gt.get("encryption_details"))
    if algos or keys:
        a["encryption_details"] = {}
        if algos:
            a["encryption_details"]["algorithm"] = algos[0]
        if keys:
            a["encryption_details"]["key"] = sorted(keys)[0]
        ks = gt.get("encryption_details", {}).get("key_storage")
        if ks:
            a["encryption_details"]["key_storage"] = ks
    return a


def make_config(tmp_path):
    return BenchmarkConfig(
        project_root=ROOT,
        workspace_dir=ROOT / "binaries",
        ground_truths_dir=ROOT / "ground_truths",
        provider="mock",
        model="mock-v1",
        use_docker=True,
        results_dir=tmp_path / "results",
    )


def run_task(task_id, script, tmp_path, monkeypatch):
    manifest = ROOT / "tasks.json"
    if task_id.startswith("v3_"):
        manifest = ROOT / "version3" / "tasks_v3.json"
    tasks = {t.task_id: t for t in runner.load_tasks(manifest, ROOT)}
    task = tasks[task_id]
    mock = MockProvider(script)
    monkeypatch.setattr(runner, "create_provider", lambda *a, **k: mock)
    config = make_config(tmp_path)
    monkeypatch.setattr(
        BenchmarkConfig, "resolve_api_key", lambda self: "dummy", raising=False
    )
    metrics, score_result = runner.run_single_task(task, config)
    return metrics, score_result, task, config


def test_elf_level_end_to_end(tmp_path, monkeypatch):
    gt = json.loads((ROOT / "ground_truths/level1_TCPServer.json").read_text())
    script = [
        ("file", {"path": "level1_TCPServer"}),
        ("readelf", {"path": "level1_TCPServer", "flags": "-h"}),
        ("final_answer", perfect_answer(gt)),
    ]
    metrics, score, task, config = run_task("level1_TCPServer", script, tmp_path, monkeypatch)

    assert score["final_score"] == 1.0, score["field_scores"]
    assert score["tier"] == "standard"
    assert metrics.has_valid_answer is True
    assert metrics.tool_calls_total == 3
    assert metrics.tool_calls_by_type == {"file": 1, "readelf": 1, "final_answer": 1}
    assert "binary executable" in MockProvider.last_system
    # transcripts + agent output saved
    saved = json.loads((config.agent_outputs_dir / "level1_TCPServer.json").read_text())
    assert saved["decoded_c2"] == gt["decoded_c2"]
    assert (config.transcripts_dir / "level1_TCPServer_transcript.json").exists()
    assert (config.transcripts_dir / "level1_TCPServer_full_transcript.json").exists()


def test_pe_level_end_to_end(tmp_path, monkeypatch):
    gt = json.loads(
        (ROOT / "version3/ground_truths/windows_level14_DLLInjection.json").read_text()
    )
    script = [
        ("file", {"path": "sample_5281a1.bin"}),
        ("pe_info", {"path": "sample_5281a1.bin"}),
        ("objdump", {"path": "sample_5281a1.bin", "flags": "-p"}),
        ("strings", {"path": "sample_5281a1.bin", "encoding": "l"}),
        ("entropy", {"path": "sample_5281a1.bin", "section": ".text"}),
        ("final_answer", perfect_answer(gt)),
    ]
    metrics, score, task, config = run_task(
        "v3_l14_u", script, tmp_path, monkeypatch
    )

    assert score["final_score"] == 1.0, score["field_scores"]
    assert score["tier"] == "pe_injection"
    assert metrics.has_valid_answer is True
    assert metrics.tool_calls_total == 6
    assert metrics.spurious_count == 0
    # PE-family prompt was used
    assert "Windows PE binary" in MockProvider.last_system
    assert "Do not invent a C2" in MockProvider.last_system


def test_aggregate_includes_pe_in_main(tmp_path, monkeypatch):
    """main_score must average standard + pe_injection tiers."""
    gt1 = json.loads((ROOT / "ground_truths/level1_TCPServer.json").read_text())
    gt14 = json.loads(
        (ROOT / "version3/ground_truths/windows_level14_DLLInjection.json").read_text()
    )
    m1, _, _, _ = run_task(
        "level1_TCPServer",
        [("final_answer", perfect_answer(gt1))],
        tmp_path, monkeypatch,
    )
    m14, _, _, _ = run_task(
        "v3_l14_u",
        [("final_answer", perfect_answer(gt14))],
        tmp_path, monkeypatch,
    )
    agg = compute_aggregate([m1, m14])
    assert agg.main_score == pytest.approx(1.0)  # would be 0.5 if PE excluded
    assert agg.bonus_score == 0.0
    assert agg.total_score == pytest.approx(1.0)
