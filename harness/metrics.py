from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskMetrics:
    task_id: str
    score: float                    # final_score from scorer
    tier: str                       # "standard" or "bonus"
    field_scores: dict[str, float] = field(default_factory=dict)

    tool_calls_total: int = 0
    tool_calls_by_type: dict[str, int] = field(default_factory=dict)
    redundant_tool_calls: int = 0
    invalid_tool_calls: int = 0
    invalid_json_attempts: int = 0
    steps_to_answer: int = 0
    max_steps_hit: bool = False
    has_valid_answer: bool = False

    hallucinated_techniques: list[str] = field(default_factory=list)
    hallucination_count: int = 0
    missing_techniques: list[str] = field(default_factory=list)

    wall_time_seconds: float = 0.0
    llm_seconds: float = 0.0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "score": self.score,
            "tier": self.tier,
            "field_scores": self.field_scores,
            "tool_calls_total": self.tool_calls_total,
            "tool_calls_by_type": self.tool_calls_by_type,
            "redundant_tool_calls": self.redundant_tool_calls,
            "invalid_tool_calls": self.invalid_tool_calls,
            "invalid_json_attempts": self.invalid_json_attempts,
            "steps_to_answer": self.steps_to_answer,
            "max_steps_hit": self.max_steps_hit,
            "has_valid_answer": self.has_valid_answer,
            "hallucinated_techniques": self.hallucinated_techniques,
            "hallucination_count": self.hallucination_count,
            "missing_techniques": self.missing_techniques,
            "wall_time_seconds": self.wall_time_seconds,
            "llm_seconds": self.llm_seconds,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


@dataclass
class AggregateMetrics:
    success_rate: float = 0.0       # fraction with has_valid_answer
    main_score: float = 0.0         # avg of standard (1-12)
    bonus_score: float = 0.0        # level 13 score
    total_score: float = 0.0        # main + bonus

    avg_tool_calls_per_task: float = 0.0
    avg_tool_calls_per_success: float = 0.0
    tool_usage_distribution: dict[str, int] = field(default_factory=dict)
    avg_hallucination_rate: float = 0.0

    episode_length_min: float = 0.0
    episode_length_max: float = 0.0
    episode_length_mean: float = 0.0
    episode_length_median: float = 0.0

    total_wall_time: float = 0.0
    total_llm_seconds: float = 0.0
    avg_llm_seconds_per_task: float = 0.0
    total_tokens: int = 0
    total_reasoning_tokens: int = 0
    max_steps_hit_count: int = 0

    tasks_run: int = 0
    tasks_with_answer: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_rate": round(self.success_rate, 4),
            "main_score": round(self.main_score, 4),
            "bonus_score": round(self.bonus_score, 4),
            "total_score": round(self.total_score, 4),
            "avg_tool_calls_per_task": round(self.avg_tool_calls_per_task, 2),
            "avg_tool_calls_per_success": round(self.avg_tool_calls_per_success, 2),
            "tool_usage_distribution": self.tool_usage_distribution,
            "avg_hallucination_rate": round(self.avg_hallucination_rate, 4),
            "episode_length_min": round(self.episode_length_min, 2),
            "episode_length_max": round(self.episode_length_max, 2),
            "episode_length_mean": round(self.episode_length_mean, 2),
            "episode_length_median": round(self.episode_length_median, 2),
            "total_wall_time": round(self.total_wall_time, 2),
            "total_llm_seconds": round(self.total_llm_seconds, 2),
            "avg_llm_seconds_per_task": round(self.avg_llm_seconds_per_task, 2),
            "total_tokens": self.total_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "max_steps_hit_count": self.max_steps_hit_count,
            "tasks_run": self.tasks_run,
            "tasks_with_answer": self.tasks_with_answer,
        }


def collect_task_metrics(
    task_id: str,
    agent_result: dict[str, Any],
    score_result: dict[str, Any],
) -> TaskMetrics:
    hallucinated = score_result.get("hallucinated_techniques", [])

    return TaskMetrics(
        task_id=task_id,
        score=score_result.get("final_score", 0.0),
        tier=score_result.get("tier", "standard"),
        field_scores=score_result.get("field_scores", {}),
        tool_calls_total=agent_result.get("tool_call_count", 0),
        tool_calls_by_type=agent_result.get("tool_calls_by_type", {}),
        redundant_tool_calls=agent_result.get("redundant_tool_calls", 0),
        invalid_tool_calls=agent_result.get("invalid_tool_calls", 0),
        invalid_json_attempts=agent_result.get("invalid_json_attempts", 0),
        steps_to_answer=agent_result.get("tool_call_count", 0),
        max_steps_hit=agent_result.get("max_steps_hit", False),
        has_valid_answer=agent_result.get("has_valid_answer", False),
        hallucinated_techniques=hallucinated,
        hallucination_count=len(hallucinated),
        missing_techniques=score_result.get("missing_techniques", []),
        wall_time_seconds=agent_result.get("wall_time_seconds", 0.0),
        llm_seconds=agent_result.get("llm_seconds", 0.0),
        total_tokens=agent_result.get("total_tokens", 0),
        input_tokens=agent_result.get("input_tokens", 0),
        output_tokens=agent_result.get("output_tokens", 0),
        reasoning_tokens=agent_result.get("reasoning_tokens", 0),
    )


def compute_aggregate(task_metrics: list[TaskMetrics]) -> AggregateMetrics:
    if not task_metrics:
        return AggregateMetrics()

    agg = AggregateMetrics()
    agg.tasks_run = len(task_metrics)

    # Separate standard vs bonus
    standard = [m for m in task_metrics if m.tier == "standard"]
    bonus = [m for m in task_metrics if m.tier == "bonus"]

    agg.tasks_with_answer = sum(1 for m in task_metrics if m.has_valid_answer)
    agg.success_rate = agg.tasks_with_answer / agg.tasks_run if agg.tasks_run else 0.0

    agg.main_score = (
        sum(m.score for m in standard) / len(standard) if standard else 0.0
    )
    agg.bonus_score = bonus[0].score if bonus else 0.0
    agg.total_score = agg.main_score + agg.bonus_score

    # Tool call stats
    all_calls = [m.tool_calls_total for m in task_metrics]
    agg.avg_tool_calls_per_task = (
        sum(all_calls) / len(all_calls) if all_calls else 0.0
    )

    success_calls = [m.tool_calls_total for m in task_metrics if m.has_valid_answer]
    agg.avg_tool_calls_per_success = (
        sum(success_calls) / len(success_calls) if success_calls else 0.0
    )

    # Tool usage distribution
    dist: dict[str, int] = {}
    for m in task_metrics:
        for tool, count in m.tool_calls_by_type.items():
            dist[tool] = dist.get(tool, 0) + count
    agg.tool_usage_distribution = dist

    # Hallucination rate
    halluc_counts = [m.hallucination_count for m in task_metrics]
    agg.avg_hallucination_rate = (
        sum(halluc_counts) / len(halluc_counts) if halluc_counts else 0.0
    )

    # Episode lengths (wall time)
    times = [m.wall_time_seconds for m in task_metrics]
    agg.episode_length_min = min(times)
    agg.episode_length_max = max(times)
    agg.episode_length_mean = statistics.mean(times)
    agg.episode_length_median = statistics.median(times)

    agg.total_wall_time = sum(times)
    llm_times = [m.llm_seconds for m in task_metrics]
    agg.total_llm_seconds = sum(llm_times)
    agg.avg_llm_seconds_per_task = (
        agg.total_llm_seconds / len(llm_times) if llm_times else 0.0
    )
    agg.total_tokens = sum(m.total_tokens for m in task_metrics)
    agg.total_reasoning_tokens = sum(m.reasoning_tokens for m in task_metrics)
    agg.max_steps_hit_count = sum(1 for m in task_metrics if m.max_steps_hit)

    return agg
