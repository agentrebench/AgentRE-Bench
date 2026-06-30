#!/usr/bin/env python3
"""
AgentRE-Bench Scorer

Scoring model:
  - Levels 1-12 (standard):  each scored 0–1, averaged → 1.0 pt max
  - Level 13    (bonus):     granular rubric           → 1.0 pt max
  - Total possible:                                      2.0 pts

Usage:
    # Single sample
    python scorer.py -g ground_truths/level1_TCPServer.json \
                     -a agent_outputs/level1_TCPServer.json

    # Full benchmark (batch)
    python scorer.py -G ground_truths/ -A agent_outputs/ -r results.json
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("scorer")

# ===================================================================
# Standard weights (levels 1-12) — must sum to 1.0
# ===================================================================
STANDARD_WEIGHTS = {
    "decoded_c2":      0.40,
    "techniques":      0.30,
    "file_type":       0.10,
    "encoded_strings": 0.10,
    "c2_protocol":     0.10,
}

# ===================================================================
# Bonus weights (level 13) — must sum to 1.0
#
#   The bonus level has crypto recovery, string decryption, and
#   anti-analysis identification on top of the standard fields,
#   so it gets its own deeper rubric.
# ===================================================================
BONUS_WEIGHTS = {
    "decoded_c2":              0.15,   # C2 URL
    "encryption_algorithm":    0.10,   # "RC4"
    "encryption_key":          0.15,   # "gh0st_k3y_2024"
    "encryption_key_storage":  0.05,   # XOR mask 0xa5
    "techniques":              0.15,   # 18 techniques, Jaccard
    "decoded_strings":         0.15,   # 13 encrypted strings recovered
    "anti_analysis":           0.10,   # 5 anti-analysis entries
    "file_type":               0.03,   # ELF64
    "encoded_strings":         0.02,   # true
    "c2_protocol":             0.05,   # HTTP
}

HALLUCINATION_PENALTY = 0.05   # per extra technique claim
BONUS_HALLUCINATION_PENALTY = 0.03   # lighter per-claim (more techniques)

BONUS_SAMPLE_PATTERN = re.compile(r"level(?:13|23)", re.IGNORECASE)


# ===================================================================
# Shared helpers
# ===================================================================
def normalize_c2(value):
    if value is None:
        return None
    return str(value).strip().lower().rstrip("/")


def score_decoded_c2(gt_val, agent_val):
    gt_norm = normalize_c2(gt_val)
    agent_norm = normalize_c2(agent_val)

    if gt_norm == agent_norm:
        return 1.0
    if gt_norm is None and agent_norm is None:
        return 1.0
    if gt_norm is None or agent_norm is None:
        return 0.0

    # Partial: host/IP matches but port/path differs
    gt_host = gt_norm.split("://")[-1].split("/")[0].split(":")[0]
    agent_host = agent_norm.split("://")[-1].split("/")[0].split(":")[0]
    if gt_host == agent_host:
        return 0.5

    return 0.0


def score_set_overlap(gt_items, agent_items):
    """Jaccard overlap.  Returns (credit, extra_count)."""
    gt_set = set(gt_items or [])
    agent_set = set(agent_items or [])
    if not gt_set and not agent_set:
        return 1.0, 0
    if not gt_set:
        return 0.0, len(agent_set)
    union = gt_set | agent_set
    inter = gt_set & agent_set
    extra = agent_set - gt_set
    return (len(inter) / len(union) if union else 1.0), len(extra)


def score_exact(gt_val, agent_val):
    if gt_val is None and agent_val is None:
        return 1.0
    if isinstance(gt_val, str) and isinstance(agent_val, str):
        return 1.0 if gt_val.strip().lower() == agent_val.strip().lower() else 0.0
    return 1.0 if gt_val == agent_val else 0.0


def score_fuzzy_string(gt_val, agent_val):
    """Case-insensitive substring / contains check for partial credit."""
    if gt_val is None and agent_val is None:
        return 1.0
    if gt_val is None or agent_val is None:
        return 0.0
    g = str(gt_val).strip().lower()
    a = str(agent_val).strip().lower()
    if g == a:
        return 1.0
    if g in a or a in g:
        return 0.5
    return 0.0


def is_bonus(ground_truth, gt_path=""):
    """Detect whether a sample is a bonus level (13 or 23)."""
    name = ground_truth.get("sample", "") or Path(gt_path).stem
    return bool(BONUS_SAMPLE_PATTERN.search(name))


# ===================================================================
# Standard scoring (levels 1-12)
# ===================================================================
def score_standard(gt, agent):
    result = {
        "tier": "standard",
        "field_scores": {},
        "hallucinated_techniques": [],
        "missing_techniques": [],
        "hallucination_penalty": 0.0,
        "weighted_score": 0.0,
        "final_score": 0.0,
    }

    # decoded_c2
    result["field_scores"]["decoded_c2"] = score_decoded_c2(
        gt.get("decoded_c2"), agent.get("decoded_c2"),
    )

    # techniques
    tech_credit, halluc_count = score_set_overlap(
        gt.get("techniques"), agent.get("techniques"),
    )
    result["field_scores"]["techniques"] = tech_credit
    gt_t = set(gt.get("techniques", []))
    ag_t = set(agent.get("techniques", []))
    result["hallucinated_techniques"] = sorted(ag_t - gt_t)
    result["missing_techniques"] = sorted(gt_t - ag_t)

    # file_type
    result["field_scores"]["file_type"] = score_exact(
        gt.get("file_type"), agent.get("file_type"),
    )

    # encoded_strings
    result["field_scores"]["encoded_strings"] = score_exact(
        gt.get("encoded_strings"), agent.get("encoded_strings"),
    )

    # c2_protocol
    result["field_scores"]["c2_protocol"] = score_exact(
        gt.get("c2_protocol"), agent.get("c2_protocol"),
    )

    # Weighted sum
    weighted = sum(
        result["field_scores"].get(f, 0.0) * w
        for f, w in STANDARD_WEIGHTS.items()
    )
    result["weighted_score"] = round(weighted, 4)

    penalty = HALLUCINATION_PENALTY * halluc_count
    result["hallucination_penalty"] = round(penalty, 4)
    result["final_score"] = round(max(0.0, weighted - penalty), 4)

    return result


# ===================================================================
# Bonus scoring (levels 13, 23, etc.) — 1.0 point rubric
# ===================================================================
def _get_nested(d, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d


def score_bonus(gt, agent):
    result = {
        "tier": "bonus",
        "field_scores": {},
        "hallucinated_techniques": [],
        "missing_techniques": [],
        "hallucination_penalty": 0.0,
        "weighted_score": 0.0,
        "final_score": 0.0,
    }

    # --- decoded_c2 (0.15) ---
    result["field_scores"]["decoded_c2"] = score_decoded_c2(
        gt.get("decoded_c2"), agent.get("decoded_c2"),
    )

    # --- encryption_algorithm (0.10) ---
    gt_algo = _get_nested(gt, "encryption_details", "algorithm", default="")
    ag_algo = _get_nested(agent, "encryption_details", "algorithm", default="")
    result["field_scores"]["encryption_algorithm"] = score_exact(gt_algo, ag_algo)

    # --- encryption_key (0.15) ---
    gt_key = _get_nested(gt, "encryption_details", "key", default="")
    ag_key = _get_nested(agent, "encryption_details", "key", default="")
    result["field_scores"]["encryption_key"] = score_exact(gt_key, ag_key)

    # --- encryption_key_storage (0.05) ---
    #   Partial credit: agent mentions "xor" → 0.5, mentions "0xa5" → 0.5
    gt_ks = str(_get_nested(gt, "encryption_details", "key_storage", default="")).lower()
    ag_ks = str(_get_nested(agent, "encryption_details", "key_storage", default="")).lower()
    ks_score = 0.0
    if gt_ks and ag_ks:
        if "xor" in ag_ks:
            ks_score += 0.5
        if "0xa5" in ag_ks or "a5" in ag_ks:
            ks_score += 0.5
    elif not gt_ks and not ag_ks:
        ks_score = 1.0
    result["field_scores"]["encryption_key_storage"] = min(ks_score, 1.0)

    # --- techniques (0.15) ---
    tech_credit, halluc_count = score_set_overlap(
        gt.get("techniques"), agent.get("techniques"),
    )
    result["field_scores"]["techniques"] = tech_credit
    gt_t = set(gt.get("techniques", []))
    ag_t = set(agent.get("techniques", []))
    result["hallucinated_techniques"] = sorted(ag_t - gt_t)
    result["missing_techniques"] = sorted(gt_t - ag_t)

    # --- decoded_strings (0.15) ---
    #   Compare the decoded_strings dict; credit = fraction matched
    gt_ds = _get_nested(gt, "decoded_strings", default={})
    ag_ds = _get_nested(agent, "decoded_strings", default={})
    if gt_ds:
        matched = 0
        for key, gt_val in gt_ds.items():
            ag_val = ag_ds.get(key)
            if ag_val is not None and str(ag_val).strip() == str(gt_val).strip():
                matched += 1
        result["field_scores"]["decoded_strings"] = matched / len(gt_ds)
    else:
        result["field_scores"]["decoded_strings"] = 1.0 if not ag_ds else 0.0

    # --- anti_analysis (0.10) ---
    gt_aa = gt.get("anti_analysis", [])
    ag_aa = agent.get("anti_analysis", [])
    aa_credit, _ = score_set_overlap(gt_aa, ag_aa)
    result["field_scores"]["anti_analysis"] = aa_credit

    # --- file_type (0.03) ---
    result["field_scores"]["file_type"] = score_exact(
        gt.get("file_type"), agent.get("file_type"),
    )

    # --- encoded_strings (0.02) ---
    result["field_scores"]["encoded_strings"] = score_exact(
        gt.get("encoded_strings"), agent.get("encoded_strings"),
    )

    # --- c2_protocol (0.05) ---
    result["field_scores"]["c2_protocol"] = score_exact(
        gt.get("c2_protocol"), agent.get("c2_protocol"),
    )

    # Weighted sum
    weighted = sum(
        result["field_scores"].get(f, 0.0) * w
        for f, w in BONUS_WEIGHTS.items()
    )
    result["weighted_score"] = round(weighted, 4)

    penalty = BONUS_HALLUCINATION_PENALTY * halluc_count
    result["hallucination_penalty"] = round(penalty, 4)
    result["final_score"] = round(max(0.0, weighted - penalty), 4)

    return result


# ===================================================================
# Dispatch: pick standard or bonus scorer
# ===================================================================
def score_sample(gt, agent, gt_path=""):
    if is_bonus(gt, gt_path):
        return score_bonus(gt, agent)
    return score_standard(gt, agent)


# ===================================================================
# I/O helpers
# ===================================================================
def load_json(path):
    with open(path) as f:
        return json.load(f)


def score_single(gt_path, agent_path):
    gt = load_json(gt_path)
    agent = load_json(agent_path)

    sample_name = gt.get("sample", Path(gt_path).stem)
    result = score_sample(gt, agent, gt_path)
    result["sample"] = sample_name

    log.info("Sample: %s [%s]", sample_name, result["tier"])
    for field, val in result["field_scores"].items():
        log.info("  %-28s %.4f", field, val)
    log.info("  Weighted score:            %.4f", result["weighted_score"])
    log.info("  Hallucination penalty:     %.4f", result["hallucination_penalty"])
    log.info("  Final score:               %.4f", result["final_score"])

    if result["hallucinated_techniques"]:
        log.warning("  Hallucinated: %s", result["hallucinated_techniques"])
    if result["missing_techniques"]:
        log.info("  Missing:      %s", result["missing_techniques"])

    return result


def score_batch(gt_dir, agent_dir):
    gt_dir = Path(gt_dir)
    agent_dir = Path(agent_dir)

    results = []
    gt_files = sorted(gt_dir.glob("*.json"))

    if not gt_files:
        log.error("No ground truth JSON files found in %s", gt_dir)
        return results

    for gt_file in gt_files:
        agent_file = agent_dir / gt_file.name
        if not agent_file.exists():
            log.warning("No agent output for %s, skipping", gt_file.name)
            continue
        results.append(score_single(str(gt_file), str(agent_file)))

    return results


# ===================================================================
# Summary output
# ===================================================================
def print_summary(results):
    if not results:
        log.info("No results to summarize.")
        return

    standard = [r for r in results if r.get("tier") == "standard"]
    bonus    = [r for r in results if r.get("tier") == "bonus"]

    # --- Standard table ---
    if standard:
        print("\n" + "=" * 76)
        print("  STANDARD LEVELS (1-12)   each 0–1, averaged → 1.0 pt max")
        print("=" * 76)
        print(f"  {'Sample':<40} {'Raw':>7} {'Penalty':>8} {'Final':>7}")
        print("  " + "-" * 72)

        for r in standard:
            name = r["sample"][:39]
            print(
                f"  {name:<40} {r['weighted_score']:>7.4f}"
                f" {r['hallucination_penalty']:>8.4f}"
                f" {r['final_score']:>7.4f}"
            )

        avg = (
            sum(r["final_score"] for r in standard) / len(standard)
            if standard else 0.0
        )
        print("  " + "-" * 72)
        print(f"  {'MAIN SCORE  (avg of ' + str(len(standard)) + ' levels)':<40}"
              f" {'':>7} {'':>8} {avg:>7.4f}")
        print(f"  {'Max possible':<40} {'':>7} {'':>8} {'1.0000':>7}")
        print("=" * 76)
    else:
        avg = 0.0

    # --- Bonus table ---
    bonus_score = 0.0
    if bonus:
        print("\n" + "=" * 76)
        print("  BONUS LEVEL          granular rubric → 1.0 pt max")
        print("=" * 76)
        for r in bonus:
            print(f"  Sample: {r['sample']}")
            print(f"  {'Field':<32} {'Score':>7}")
            print("  " + "-" * 42)
            for field, val in r["field_scores"].items():
                w = BONUS_WEIGHTS.get(field, 0)
                print(f"  {field:<32} {val:>7.4f}  (x{w:.2f})")
            print("  " + "-" * 42)
            print(f"  {'Weighted score':<32} {r['weighted_score']:>7.4f}")
            print(f"  {'Hallucination penalty':<32} {r['hallucination_penalty']:>7.4f}")
            print(f"  {'BONUS SCORE':<32} {r['final_score']:>7.4f}")
            print(f"  {'Max possible':<32} {'1.0000':>7}")
            bonus_score = r["final_score"]
        print("=" * 76)

    # --- Grand total ---
    total = avg + bonus_score
    max_total = (1.0 if standard else 0.0) + (1.0 if bonus else 0.0)

    print("\n" + "=" * 76)
    print("  GRAND TOTAL")
    print("=" * 76)
    if standard:
        print(f"    Main score  (levels 1-12):  {avg:>7.4f} / 1.0")
    if bonus:
        print(f"    Bonus score (level 13):     {bonus_score:>7.4f} / 1.0")
    print(f"    ─────────────────────────────────────")
    print(f"    TOTAL:                      {total:>7.4f} / {max_total:.1f}")
    print("=" * 76 + "\n")


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="AgentRE-Bench Scorer: compare agent RE output against ground truth"
    )
    parser.add_argument(
        "--ground-truth", "-g",
        help="Path to a single ground truth JSON file",
    )
    parser.add_argument(
        "--agent-output", "-a",
        help="Path to a single agent output JSON file",
    )
    parser.add_argument(
        "--ground-truth-dir", "-G",
        help="Directory of ground truth JSON files (batch mode)",
    )
    parser.add_argument(
        "--agent-output-dir", "-A",
        help="Directory of agent output JSON files (batch mode)",
    )
    parser.add_argument(
        "--report", "-r",
        help="Write JSON report to this path",
    )

    args = parser.parse_args()

    if args.ground_truth and args.agent_output:
        result = score_single(args.ground_truth, args.agent_output)
        results = [result]
    elif args.ground_truth_dir and args.agent_output_dir:
        results = score_batch(args.ground_truth_dir, args.agent_output_dir)
    else:
        parser.error(
            "Provide either --ground-truth + --agent-output "
            "or --ground-truth-dir + --agent-output-dir"
        )
        return

    print_summary(results)

    if args.report:
        standard = [r for r in results if r.get("tier") == "standard"]
        bonus    = [r for r in results if r.get("tier") == "bonus"]
        main_score = (
            sum(r["final_score"] for r in standard) / len(standard)
            if standard else 0.0
        )
        bonus_score = bonus[0]["final_score"] if bonus else 0.0

        report = {
            "results": results,
            "summary": {
                "standard_samples": len(standard),
                "main_score": round(main_score, 4),
                "main_max": 1.0,
                "bonus_score": round(bonus_score, 4),
                "bonus_max": 1.0,
                "total_score": round(main_score + bonus_score, 4),
                "total_max": (1.0 if standard else 0.0) + (1.0 if bonus else 0.0),
                "standard_weights": STANDARD_WEIGHTS,
                "bonus_weights": BONUS_WEIGHTS,
                "hallucination_penalty_standard": HALLUCINATION_PENALTY,
                "hallucination_penalty_bonus": BONUS_HALLUCINATION_PENALTY,
            },
        }
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
        log.info("Report written to %s", args.report)


if __name__ == "__main__":
    main()
