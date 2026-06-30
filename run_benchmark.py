#!/usr/bin/env python3
"""
AgentRE-Bench — CLI entry point

API keys are loaded from .env in the project root. Create one with:
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-...
    GOOGLE_API_KEY=AI...
    DEEPSEEK_API_KEY=sk-...

Then just pick a provider/model:
    python run_benchmark.py --all --provider anthropic --model claude-opus-4-6
    python run_benchmark.py --all --provider openai --model gpt-4o
    python run_benchmark.py --all --provider gemini --model gemini-2.0-flash
    python run_benchmark.py --all --provider deepseek --model deepseek-chat
    python run_benchmark.py --task level1_TCPServer --model claude-opus-4-6
    python run_benchmark.py --task level1_TCPServer --model claude-opus-4-6 -v
"""

import argparse
import logging
import sys
from pathlib import Path

from agentre_bench.harness.config import BenchmarkConfig
from agentre_bench.harness.runner import run_benchmark


def main():
    parser = argparse.ArgumentParser(
        description="AgentRE-Bench: Evaluate LLM agents on reverse engineering tasks",
        epilog="API keys are read from .env file in the project root (or from environment variables).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all 13 tasks",
    )
    group.add_argument(
        "--task",
        type=str,
        help="Run a single task by ID (e.g. level1_TCPServer)",
    )

    parser.add_argument(
        "--provider",
        type=str,
        default="anthropic",
        choices=["anthropic", "openai", "gemini", "deepseek", "glm", "moonshot"],
        help="LLM provider (default: anthropic)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: provider-specific default)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="API key override (normally loaded from .env or environment)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Custom results directory path",
    )
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=25,
        help="Max tool calls per task (default: 25)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Max tokens per LLM response (default: 4096)",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Run tools via subprocess instead of Docker",
    )
    parser.add_argument(
        "--inter-task-sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between tasks (e.g. 90 for Gemini rate-limit pacing)",
    )
    parser.add_argument(
        "--skip-tasks",
        type=str,
        default="",
        help="Comma-separated list of task IDs to skip (e.g. 'level1_TCPServer,level2_XorEncodedStrings')",
    )
    parser.add_argument(
        "--only-tasks",
        type=str,
        default="",
        help="Comma-separated list of task IDs to keep (skips everything else). Useful for parallel chunking.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show agent reasoning, tool calls, and outputs in real time",
    )

    args = parser.parse_args()

    # Logging is for errors only — all user-facing output goes through print()
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")

    # Determine default model per provider
    model_defaults = {
        "anthropic": "claude-opus-4-6",
        "openai": "gpt-4o",
        "gemini": "gemini-2.0-flash",
        "deepseek": "deepseek-chat",
        "glm": "glm-5.1",
        "moonshot": "kimi-k2.6",
    }
    model = args.model or model_defaults.get(args.provider, "claude-opus-4-6")

    project_root = Path(__file__).parent.resolve()

    config = BenchmarkConfig(
        project_root=project_root,
        workspace_dir=project_root / "binaries",
        ground_truths_dir=project_root / "ground_truths",
        model=model,
        provider=args.provider,
        api_key=args.api_key,
        max_tool_calls=args.max_tool_calls,
        max_tokens=args.max_tokens,
        use_docker=not args.no_docker,
        inter_task_sleep_seconds=args.inter_task_sleep,
        results_dir=Path(args.report) if args.report else None,
        verbose=args.verbose,
    )

    # Validate
    if not config.workspace_dir.exists():
        print(
            f"Error: binaries directory not found at {config.workspace_dir}\n"
            f"Run ./build_binaries.sh first to compile the samples.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not config.ground_truths_dir.exists():
        print(
            f"Error: ground truths directory not found at {config.ground_truths_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    task_filter = args.task if args.task else None
    skip_tasks = [t.strip() for t in args.skip_tasks.split(",") if t.strip()] or None
    only_tasks = [t.strip() for t in args.only_tasks.split(",") if t.strip()] or None

    try:
        aggregate, task_metrics, score_results = run_benchmark(
            config, task_filter, skip_tasks, only_tasks
        )
    except Exception as e:
        logging.getLogger(__name__).error("Benchmark failed: %s", e, exc_info=True)
        sys.exit(1)

    print(f"\nTotal score: {aggregate.total_score:.4f}")
    print(f"Tasks completed: {aggregate.tasks_with_answer}/{aggregate.tasks_run}")
    print(f"Total wall time: {aggregate.total_wall_time:.1f}s")
    print(f"Total tokens: {aggregate.total_tokens}")


if __name__ == "__main__":
    main()
