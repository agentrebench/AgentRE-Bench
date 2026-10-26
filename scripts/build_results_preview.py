"""Export only public aggregate values for the local 6.2.0 website preview."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/v3_4-20261025-rescore-6_2_0"
OUT = ROOT / "docs/previews/results-6-2-0"
MODELS = [
    ("muse_wonder_high_native_cli", "muse-wonder-1.0", "Muse Wonder", "Muse", "MW", "High", "Coding plan"),
    ("codex_astra_xhigh_subscription", "gpt-6-astra", "GPT-6 Astra", "OpenAI", "AS", "Extra high", "Coding plan"),
    ("xai_grok47_high", "grok-4.7", "Grok 4.7", "xAI", "X", "High", "API"),
    ("claude_opus55_high_subscription", "claude-opus-5-5", "Claude Opus 5.5", "Anthropic", "CL", "High", "Coding plan"),
    ("gemini_argon4_high", "gemini-4-argon", "Gemini 4 Argon", "Google", "GE", "High", "API"),
]


def build_data():
    quality = json.loads((SOURCE / "ANSWER_QUALITY.json").read_text())
    qualities = {row["model"]: row for row in quality["models"]}
    models, hashes = [], {}
    for filename, model_id, name, provider, initials, reasoning, access in MODELS:
        path = SOURCE / (filename + ".json")
        report = json.loads(path.read_text())
        assert report["scorer_version"] == "6.2.0" and report["episodes"] == 100
        assert report["calibration"]["review_required_episodes"] == 0
        values = report["aggregate_metrics"]
        selected = qualities[model_id]
        assert abs(values["overall_score"] - (0.9 * values["main_score"] + 0.1 * values["bonus_score"])) < 1e-10
        models.append({"id": model_id, "name": name, "provider": provider, "initials": initials,
                       "reasoning": reasoning, "access": access,
                       "overall": values["overall_score"] * 100,
                       "main": values["main_score"] * 100, "bonus": values["bonus_score"] * 100,
                       "interval": [value * 100 for value in report["uncertainty"]["intervals"]["overall_score"]["confidence_interval"]],
                       "quality": selected["conditional_answer_quality"]["artifact_balanced_mean"] * 100,
                       "answered_artifacts": selected["conditional_answer_quality"]["answered_artifacts"],
                       "valid": selected["outcomes"]["valid_answer"]["count"],
                       "refusals": selected["outcomes"]["refusal"]["count"],
                       "budget": selected["outcomes"]["budget_exhaustion"]["count"]})
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    models.sort(key=lambda row: row["overall"], reverse=True)
    pair = json.loads((SOURCE / "PAIR_VERIFICATION.json").read_text())
    data = {"date": "2026-10-25", "suite": "v3.4", "scorer": "6.2.0",
            "evaluation_type": "saved_answer_rescore", "models": models,
            "artifacts": 20, "programs": 10, "attempts_per_artifact": 5, "episodes": 500,
            "pair": {"direction": "Muse minus Astra", "gap_pp": pair["mean_gap_pp"],
                     "interval_pp": pair["simultaneous_95_percent_interval_pp"],
                     "family_confidence": 0.95, "family_comparisons": 10,
                     "statistical_winner": None},
            "source_report_sha256": hashes,
            "notes": ["Five fresh attempts averaged per artifact; all 20 artifacts weighted equally.",
                      "Overall retains zero-valued refusals and budget exhaustion.",
                      "Conditional quality is artifact-balanced over submitted valid answers; model subsets differ.",
                      "Astra, Opus and Muse used coding plans; Gemini and Grok used APIs. Configurations differ.",
                      "Scoring was calibrated retrospectively against source/binary evidence. Public suite; no held-out generalization claim."]}
    return data


def build():
    data = build_data()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scores.json").write_text(json.dumps(data, indent=2) + "\n")
    (OUT / "scores.js").write_text("window.AGENTRE_RESULTS = " + json.dumps(data, ensure_ascii=False) + ";\n")
    shutil.copy2(ROOT / "docs/favicon.svg", OUT / "favicon.svg")
    print(f"Exported {len(data['models'])} models / {data['episodes']} episodes to {OUT}")


if __name__ == "__main__":
    build()
