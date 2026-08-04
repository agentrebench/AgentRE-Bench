#!/usr/bin/env python3
"""Verify the published AgentRE-Bench V3 result snapshot."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


VERSION_DIR = Path(__file__).resolve().parent
ROOT = VERSION_DIR.parent
sys.path.insert(0, str(ROOT))

from scorer import score_sample  # noqa: E402


MODEL_DIRS = (
    "anthropic_claude-fable-5",
    "anthropic_claude-opus-5_retry",
    "deepseek_deepseek-v4-flash",
    "gemini_gemini-3.6-flash",
    "moonshot_kimi-k3",
    "openai_gpt-5.6-sol",
)


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left: float, right: float, places: int = 4) -> bool:
    return math.isclose(round(left, places), round(right, places), abs_tol=10 ** -places)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_artifacts(run_manifest: dict) -> None:
    for artifact in run_manifest["artifacts"]:
        binary = ROOT / artifact["binary"]
        ground_truth = ROOT / artifact["ground_truth"]
        source = ROOT / artifact["source"]
        require(binary.is_file(), f"missing binary: {binary}")
        require(ground_truth.is_file(), f"missing ground truth: {ground_truth}")
        require(source.is_file(), f"missing source: {source}")
        require(
            sha256(binary) == artifact["binary_sha256"],
            f"binary checksum mismatch: {artifact['task_id']}",
        )
        require(
            sha256(ground_truth) == artifact["ground_truth_sha256"],
            f"ground-truth checksum mismatch: {artifact['task_id']}",
        )
        require(
            sha256(source) == artifact["source_sha256"],
            f"source checksum mismatch: {artifact['task_id']}",
        )


def verify_results_ledger(run_manifest: dict) -> None:
    ledger = ROOT / run_manifest["publication"]["results_checksum_ledger"]
    require(ledger.is_file(), "missing raw-results checksum ledger")
    require(
        sha256(ledger) == run_manifest["publication"]["results_checksum_ledger_sha256"],
        "raw-results checksum-ledger mismatch",
    )
    entries = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        digest, relative_path = line.split("  ", 1)
        entries[relative_path] = digest
    expected_paths = {
        str(path.relative_to(ROOT))
        for path in (VERSION_DIR / "results").rglob("*")
        if path.is_file()
    }
    require(set(entries) == expected_paths, "raw-results checksum-ledger coverage mismatch")
    for relative_path, expected_hash in entries.items():
        require(
            sha256(ROOT / relative_path) == expected_hash,
            f"raw-results checksum mismatch: {relative_path}",
        )


def verify_model(model_dir: str, task_map: dict[str, dict]) -> tuple[float, float, float]:
    result_dir = VERSION_DIR / "results" / model_dir
    report = load_json(result_dir / "benchmark_report.json")
    metrics = {row["task_id"]: row for row in report["task_metrics"]}
    scores = {row["sample"]: row for row in report["score_results"]}
    expected_ids = set(task_map)

    require(len(report["task_metrics"]) == len(metrics) == 20, f"{model_dir}: task rows")
    require(len(report["score_results"]) == len(scores) == 20, f"{model_dir}: score rows")
    require(set(metrics) == expected_ids, f"{model_dir}: task coverage")
    require(set(scores) == expected_ids, f"{model_dir}: score coverage")

    for task_id, task in task_map.items():
        output_path = result_dir / "agent_outputs" / f"{task_id}.json"
        transcript = result_dir / "transcripts" / f"{task_id}_transcript.json"
        full_transcript = result_dir / "transcripts" / f"{task_id}_full_transcript.json"
        require(output_path.is_file(), f"{model_dir}: missing output {task_id}")
        require(transcript.is_file(), f"{model_dir}: missing transcript {task_id}")
        require(full_transcript.is_file(), f"{model_dir}: missing full transcript {task_id}")

        answer = load_json(output_path)
        ground_truth = load_json(ROOT / task["ground_truth"])
        independent = score_sample(ground_truth, answer)
        published = scores[task_id]
        metric = metrics[task_id]

        require(
            close(independent["final_score"], published["final_score"]),
            f"{model_dir}/{task_id}: independent score mismatch",
        )
        require(
            close(metric["score"], published["final_score"]),
            f"{model_dir}/{task_id}: report score mismatch",
        )
        require(
            independent["tier"] == published["tier"] == metric["tier"],
            f"{model_dir}/{task_id}: tier mismatch",
        )
        require(
            set(independent["field_scores"]) == set(published["field_scores"]),
            f"{model_dir}/{task_id}: field coverage mismatch",
        )
        for field, value in independent["field_scores"].items():
            require(
                close(value, published["field_scores"][field], places=8),
                f"{model_dir}/{task_id}: {field} mismatch",
            )

    main = sum(metrics[f"v3_l{level}_{variant}"]["score"] for level in range(14, 23) for variant in "us") / 18
    bonus = sum(metrics[f"v3_l23_{variant}"]["score"] for variant in "us") / 2
    total = main + bonus
    aggregate = report["aggregate_metrics"]
    require(close(main, aggregate["main_score"]), f"{model_dir}: Main mismatch")
    require(close(bonus, aggregate["bonus_score"]), f"{model_dir}: Bonus mismatch")
    require(close(total, aggregate["total_score"]), f"{model_dir}: Total mismatch")
    require(
        sum(row["has_valid_answer"] for row in metrics.values()) == aggregate["tasks_with_answer"],
        f"{model_dir}: valid-answer count mismatch",
    )
    require(
        sum(row["total_tokens"] for row in metrics.values()) == aggregate["total_tokens"],
        f"{model_dir}: token sum mismatch",
    )
    require(
        close(sum(row["wall_time_seconds"] for row in metrics.values()), aggregate["total_wall_time"], places=2),
        f"{model_dir}: wall-time sum mismatch",
    )
    return aggregate["main_score"], aggregate["bonus_score"], aggregate["total_score"]


def main() -> int:
    manifest = load_json(VERSION_DIR / "tasks_v3.json")
    task_map = {task["task_id"]: task for task in manifest["tasks"]}
    require(len(task_map) == 20, "task manifest must contain 20 unique IDs")

    run_manifest = load_json(VERSION_DIR / "RUN_MANIFEST.json")
    require(
        {row["task_id"] for row in run_manifest["artifacts"]} == set(task_map),
        "run-manifest artifact coverage mismatch",
    )
    require(
        sha256(VERSION_DIR / "tasks_v3.json") == run_manifest["tasks_manifest_sha256"],
        "publication task-manifest checksum mismatch",
    )
    for relative_path, expected_hash in run_manifest["code_checksums_sha256"].items():
        path = ROOT / relative_path
        require(path.is_file(), f"missing harness file: {relative_path}")
        require(sha256(path) == expected_hash, f"harness checksum mismatch: {relative_path}")
    verify_artifacts(run_manifest)
    verify_results_ledger(run_manifest)

    observed_models = {path.name for path in (VERSION_DIR / "results").iterdir() if path.is_dir()}
    require(observed_models == set(MODEL_DIRS), "published model-directory set mismatch")
    for model_dir in MODEL_DIRS:
        report_path = VERSION_DIR / "results" / model_dir / "benchmark_report.json"
        require(
            sha256(report_path) == run_manifest["report_checksums_sha256"][model_dir],
            f"report checksum mismatch: {model_dir}",
        )
        main_score, bonus_score, total_score = verify_model(model_dir, task_map)
        print(f"OK  {model_dir:41} Main {main_score:.4f}  Bonus {bonus_score:.4f}  Total {total_score:.4f}")

    print("OK  120/120 rows rescored; 366 raw files, binaries, sources, ground truths, harness, and aggregates verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
