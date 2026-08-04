from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import AgentLoop
from .config import BenchmarkConfig
from .metrics import (
    AggregateMetrics,
    TaskMetrics,
    collect_task_metrics,
    compute_aggregate,
)
from .providers import create_provider
from .tools import ToolExecutor

log = logging.getLogger(__name__)


@dataclass
class TaskConfig:
    task_id: str
    binary_path: Path
    ground_truth_path: Path
    difficulty: int
    # Name the agent sees inside the sandbox (neutral in v3 so the
    # filename can't leak the technique). Defaults to the real filename.
    display_name: str = ""


def load_tasks(manifest_path: Path, project_root: Path) -> list[TaskConfig]:
    with open(manifest_path) as f:
        data = json.load(f)

    # Manifests may keep their artifacts in a versioned release directory.
    # The legacy default remains ``<project>/binaries`` for tasks.json.
    binary_root = project_root / data.get("binary_root", "binaries")

    tasks = []
    for entry in data["tasks"]:
        binary_path = binary_root / entry["binary_name"]
        tasks.append(
            TaskConfig(
                task_id=entry["task_id"],
                binary_path=binary_path,
                ground_truth_path=project_root / entry["ground_truth"],
                difficulty=entry["difficulty"],
                display_name=entry.get("display_name") or binary_path.name,
            )
        )
    return tasks


SYSTEM_PROMPT_TEMPLATE = """\
You are an expert reverse engineer analyzing a binary executable.

Your task is to analyze the binary located at: {binary_path}

Use the available tools to examine the binary and determine:
1. **File type** (e.g. ELF64)
2. **Whether strings are encoded/encrypted** (true/false)
3. **The decoded C2 (command and control) address** — the IP:port or URL the binary connects to. If the binary has no C2 (some samples don't), report null.
4. **Techniques used** — specific techniques like socket_connect, xor_encoding, anti_debug_ptrace, etc.
5. **C2 protocol** — the communication protocol (TCP, HTTP, DNS, ICMP, etc.), or null if there is no C2.

{bonus_instructions}

When you have completed your analysis, call the **final_answer** tool with your findings.
Be precise with technique names — only claim techniques you have evidence for.
Do not guess or hallucinate techniques you cannot confirm from the binary analysis.
"""

PE_PROMPT_TEMPLATE = """\
You are an expert reverse engineer analyzing a Windows PE binary.

Your task is to analyze the binary located at: {binary_path}

The isolated workspace contains only this compiled PE artifact. Analyze it
in place with the provided static Windows/PE reverse-engineering tools.
Do not look for source code, reconstruct a build environment, or compile source code.

Use the available tools to examine the binary and determine:
1. **File type** (e.g. PE32+ / PE64)
2. **Whether strings are encoded/encrypted** (true/false)
3. **Techniques used** — specific techniques (e.g. dll_injection, manual_getprocaddress, peb_antidebug)
4. **Injection details** — if the binary performs process injection: the method, the target process, how the target is located, and how the payload is written
5. **Encryption details** — algorithm, key, and how the key is stored
6. **Decoded strings** — any encrypted/encoded strings you can recover
7. **Anti-analysis techniques** — specific anti-debugging and anti-analysis methods
8. **C2 address and protocol** — ONLY if the binary actually has command-and-control networking. Many of these samples do not; report null in that case.

{bonus_instructions}

When you have completed your analysis, call the **final_answer** tool with your findings.
Be precise with technique names — only claim techniques you have evidence for.
Do not guess or hallucinate techniques you cannot confirm from the binary analysis.
Do not invent a C2 address for a binary that has none.
"""

BONUS_INSTRUCTIONS = """\
This is an advanced sample. In addition to the standard fields, also determine:
- **Encryption details**: algorithm (e.g. RC4, AES), key, and how the key is stored
- **Decoded strings**: any encrypted/encoded strings you can recover
- **Anti-analysis techniques**: specific anti-debugging and anti-analysis methods

Provide these in the encryption_details, decoded_strings, and anti_analysis fields of your final_answer.
"""


def stage_task_workspace(task: TaskConfig, staging_root: Path) -> Path:
    """Isolated per-task workspace: contains only this task's binary,
    under its display name. Prevents the agent from enumerating the
    rest of the ladder from inside the sandbox.
    """
    ws = staging_root / task.task_id
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    shutil.copy2(task.binary_path, ws / task.display_name)
    return ws


def _safe_run_namespace(config: BenchmarkConfig) -> str:
    raw = f"{config.provider}_{config.model}"
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)


def build_system_prompt(
    task: TaskConfig,
    config: BenchmarkConfig,
    ground_truth: dict | None = None,
) -> str:
    if config.use_docker:
        binary_display = f"/workspace/{task.display_name}"
    else:
        binary_display = task.display_name

    # Family-aware prompt: PE binaries get an injection-oriented brief;
    # bonus levels (13, 23) get the deep-rubric addendum either way.
    is_pe = task.task_id.startswith("windows_")
    if ground_truth is not None:
        ft = str(ground_truth.get("file_type") or "").lower()
        is_pe = ft.startswith("pe") or is_pe

    bonus = BONUS_INSTRUCTIONS if task.difficulty >= 13 else ""

    if is_pe:
        return PE_PROMPT_TEMPLATE.format(
            binary_path=binary_display,
            bonus_instructions=bonus,
        )
    return SYSTEM_PROMPT_TEMPLATE.format(
        binary_path=binary_display,
        bonus_instructions=bonus,
    )


def run_single_task(
    task: TaskConfig,
    config: BenchmarkConfig,
) -> tuple[TaskMetrics, dict[str, Any]]:
    # Validate binary exists
    if not task.binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {task.binary_path}")

    # Load ground truth
    gt = json.loads(task.ground_truth_path.read_text())

    # Namespace staging by provider/model so parallel benchmark agents cannot
    # delete one another's active per-task workspace.
    staging_root = config.project_root / ".workspaces" / _safe_run_namespace(config)
    workspace = stage_task_workspace(task, staging_root)

    # Create tool executor bound to the isolated workspace
    tool_executor = ToolExecutor(config, task.binary_path, workspace_dir=workspace)

    # Create provider
    api_key = config.resolve_api_key()
    provider = create_provider(
        config.provider,
        config.model,
        api_key,
        reasoning_effort=config.reasoning_effort,
        thinking_effort=config.thinking_effort,
    )

    # Build system prompt (family-aware: PE vs ELF)
    system_prompt = build_system_prompt(task, config, gt)
    is_pe = str(gt.get("file_type") or "").lower().startswith("pe")
    pe_tool_names = {
        "file", "strings", "objdump", "nm", "hexdump", "xxd", "entropy",
        "pe_info", "final_answer",
    }

    # Run agent loop
    agent_loop = AgentLoop(
        provider=provider,
        tool_executor=tool_executor,
        system_prompt=system_prompt,
        task_id=task.task_id,
        max_tool_calls=config.max_tool_calls,
        max_tokens=config.max_tokens,
        verbose=config.verbose,
        tool_names=pe_tool_names if is_pe else None,
    )
    agent_result = agent_loop.run()

    # Save agent output
    config.agent_outputs_dir.mkdir(parents=True, exist_ok=True)
    agent_output_path = config.agent_outputs_dir / f"{task.task_id}.json"

    final_answer = agent_result.get("final_answer") or {}
    with open(agent_output_path, "w") as f:
        json.dump(final_answer, f, indent=2)

    # Score using the existing scorer
    sys.path.insert(0, str(config.project_root))
    from scorer import score_sample

    score_result = score_sample(gt, final_answer, str(task.ground_truth_path))
    score_result["sample"] = task.task_id

    # Collect metrics
    metrics = collect_task_metrics(task.task_id, agent_result, score_result)

    # Save transcript
    config.transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = config.transcripts_dir / f"{task.task_id}_transcript.json"
    transcript_data = {
        "task_id": task.task_id,
        "model": config.model,
        "provider": config.provider,
        "difficulty": task.difficulty,
        "score": score_result,
        "agent_result": {
            k: v
            for k, v in agent_result.items()
            if k != "transcript"  # transcript can be huge; save separately if needed
        },
        "metrics": metrics.to_dict(),
    }
    with open(transcript_path, "w") as f:
        json.dump(transcript_data, f, indent=2, default=str)

    # Save full transcript separately
    full_transcript_path = config.transcripts_dir / f"{task.task_id}_full_transcript.json"
    with open(full_transcript_path, "w") as f:
        json.dump(agent_result.get("transcript", []), f, indent=2, default=str)

    return metrics, score_result


def load_resumable_task(
    task: TaskConfig,
    config: BenchmarkConfig,
) -> tuple[TaskMetrics, dict[str, Any]] | None:
    """Load and rescore a saved terminal task, or return None to rerun it.

    Provider-error records are deliberately not resumable: those episodes did
    not reach a model answer and must be retried after adapter fixes. Refusals
    and other error-free terminal responses remain benchmark outcomes.
    """
    if not config.resume:
        return None

    transcript_path = config.transcripts_dir / f"{task.task_id}_transcript.json"
    agent_output_path = config.agent_outputs_dir / f"{task.task_id}.json"
    if not transcript_path.is_file() or not agent_output_path.is_file():
        return None

    try:
        transcript_data = json.loads(transcript_path.read_text())
        agent_result = transcript_data.get("agent_result") or {}
        if agent_result.get("last_error") is not None:
            return None

        final_answer = json.loads(agent_output_path.read_text())
        gt = json.loads(task.ground_truth_path.read_text())

        sys.path.insert(0, str(config.project_root))
        from scorer import score_sample

        score_result = score_sample(gt, final_answer, str(task.ground_truth_path))
        score_result["sample"] = task.task_id
        metrics = collect_task_metrics(task.task_id, agent_result, score_result)

        transcript_data["score"] = score_result
        transcript_data["metrics"] = metrics.to_dict()
        transcript_path.write_text(json.dumps(transcript_data, indent=2, default=str))
        return metrics, score_result
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("Could not resume saved task %s: %s", task.task_id, exc)
        return None

def run_benchmark(
    config: BenchmarkConfig,
    task_filter: str | None = None,
    skip_tasks: list[str] | None = None,
    only_tasks: list[str] | None = None,
) -> tuple[AggregateMetrics, list[TaskMetrics], list[dict]]:
    manifest_path = config.manifest_path or (config.project_root / "tasks.json")
    tasks = load_tasks(manifest_path, config.project_root)

    if task_filter:
        tasks = [t for t in tasks if t.task_id == task_filter]
        if not tasks:
            raise ValueError(f"No task found matching {task_filter!r}")

    if only_tasks:
        only_set = set(only_tasks)
        tasks = [t for t in tasks if t.task_id in only_set]
        if not tasks:
            raise ValueError(f"No tasks matched --only-tasks {only_set}")

    if skip_tasks:
        skip_set = set(skip_tasks)
        before = len(tasks)
        tasks = [t for t in tasks if t.task_id not in skip_set]
        if len(tasks) < before:
            print(f"  (skipping {before - len(tasks)} tasks: {', '.join(sorted(skip_set))})")

    total = len(tasks)
    mode = "docker" if config.use_docker else "local"

    # Banner
    print(f"\n{'='*60}")
    print(f"  AgentRE-Bench")
    print(f"  {config.provider}/{config.model} | {total} task{'s' if total != 1 else ''} | {mode}")
    print(f"{'='*60}")

    all_metrics: list[TaskMetrics] = []
    all_scores: list[dict] = []

    for i, task in enumerate(tasks, 1):
        resumed = load_resumable_task(task, config)
        if resumed is not None:
            metrics, score_result = resumed
            all_metrics.append(metrics)
            all_scores.append(score_result)
            print(
                f"  [{i:>{len(str(total))}}/{total}] {task.task_id} "
                f"resumed/rescored {metrics.score:.4f}",
                flush=True,
            )
            continue

        # Pacing pause for providers with strict per-minute caps.
        if i > 1 and config.inter_task_sleep_seconds > 0:
            print(
                f"  ... sleeping {config.inter_task_sleep_seconds:.0f}s "
                f"to let provider rate-limit window reset",
                flush=True,
            )
            time.sleep(config.inter_task_sleep_seconds)

        if config.verbose:
            # Verbose: full header, agent prints detailed output
            print(f"\n{'─'*60}")
            print(f"  [{i}/{total}] {task.task_id}  (difficulty {task.difficulty})")
            print(f"{'─'*60}")
        else:
            # Non-verbose: print task name, dots will follow from agent
            label = f"  [{i:>{len(str(total))}}/{total}] {task.task_id}"
            print(f"{label} ", end="", flush=True)

        try:
            metrics, score_result = run_single_task(task, config)
            all_metrics.append(metrics)
            all_scores.append(score_result)

            if config.verbose:
                print(
                    f"\n  Score: {metrics.score:.4f}  "
                    f"({metrics.tool_calls_total} calls, "
                    f"{metrics.wall_time_seconds:.1f}s, "
                    f"{metrics.total_tokens:,} tokens)"
                )
            else:
                # Complete the line after dots
                print(
                    f" {metrics.score:.4f}  "
                    f"({metrics.tool_calls_total} calls, "
                    f"{metrics.wall_time_seconds:.1f}s)"
                )
        except Exception as e:
            log.error("Task %s failed: %s", task.task_id, e, exc_info=True)
            if config.verbose:
                print(f"\n  FAILED: {e}")
            else:
                print(f" FAILED")
            continue

    # Compute aggregate metrics
    aggregate = compute_aggregate(all_metrics)

    # Print summary via scorer
    sys.path.insert(0, str(config.project_root))
    from scorer import print_summary

    print_summary(all_scores)

    # Save benchmark report
    config.results_dir.mkdir(parents=True, exist_ok=True)
    report_path = config.results_dir / "benchmark_report.json"
    report = {
        "config": {
            "model": config.model,
            "provider": config.provider,
            "max_tool_calls": config.max_tool_calls,
            "use_docker": config.use_docker,
            "resume": config.resume,
        },
        "aggregate_metrics": aggregate.to_dict(),
        "task_metrics": [m.to_dict() for m in all_metrics],
        "score_results": all_scores,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport saved to {report_path}")

    return aggregate, all_metrics, all_scores
