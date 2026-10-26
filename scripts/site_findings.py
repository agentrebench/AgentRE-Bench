"""Explain the frozen v3.1 results without changing their scores.

Field means use valid answers where the field applies. Point losses use all
100 planned attempts per model, so they reconcile to the published Overall.
"""
import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from statistics import mean

from build_results_preview import MODELS, ROOT, SOURCE

MANIFEST = ROOT / "version3/v3_4/tasks_v3_4_scorer6_2_0.json"
SCORER = ROOT / "version3/v3_4/scorer_6_2_0/scorer.py"
TLS_EVIDENCE = ROOT / "reviews/claims-20261025/runtime_tls_all_levels.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_findings():
    # Read the frozen constants without importing the evolving scorer package.
    weights = {}
    for node in ast.parse(SCORER.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", "")
            if name in ("PE_INJECTION_WEIGHTS", "BONUS_WEIGHTS"):
                weights[name] = ast.literal_eval(node.value)
    tasks = {t["task_id"]: t for t in json.loads(MANIFEST.read_text())["tasks"]}
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in (MANIFEST, SCORER, TLS_EVIDENCE)}
    truths = {}
    for task_id, task in tasks.items():
        path = ROOT / task["ground_truth"]
        assert digest(path) == task["ground_truth_sha256"]
        truths[task_id] = json.loads(path.read_text())
        for key in ("ground_truth", "source_file"):
            path = ROOT / task[key]
            hashes[str(path.relative_to(ROOT))] = digest(path)

    models, examples = [], []
    selected = {
        ("muse-wonder-1.0", "v3_l23_u", "trial-01"): "wrong_round_constant",
        ("muse-wonder-1.0", "v3_l22_u", "trial-01"): "unregistered_tls_routine",
        ("grok-4.7", "v3_l23_u", "trial-01"): "algorithm_detail_in_key_storage",
        ("gpt-6-astra", "v3_l18_u", "trial-01"): "stub_check_wording",
    }
    for filename, model_id, name, *_ in MODELS:
        path = SOURCE / (filename + ".json")
        hashes[str(path.relative_to(ROOT))] = digest(path)
        report = json.loads(path.read_text())
        assert report["scorer_version"] == "6.2.0" and report["run_status"] == "complete"
        episodes = report["episode_changes"]
        assert len(episodes) == 100
        assert Counter(e["task_id"] for e in episodes) == Counter({t: 5 for t in tasks})
        assert len({(e["task_id"], e["trial"]) for e in episodes}) == 100
        sources = {Path(s["report"]).parent.name: Path(s["report"]).parent for s in report["sources"]}
        fields, losses = defaultdict(list), Counter()
        missing, unmatched, components, reasons = Counter(), Counter(), defaultdict(list), Counter()
        outcomes = Counter(e["status"] for e in episodes)
        encoded_errors, tls_flags = [], []
        for episode in episodes:
            score = episode["new_score"]
            if episode["status"] != "valid_answer":
                assert score["final_score"] == 0
                continue
            task_id = episode["task_id"]
            answer_path = sources[episode["trial"]] / "agent_outputs" / (task_id + ".json")
            assert digest(answer_path) == episode["answer_sha256"]
            answer = json.loads(answer_path.read_text())
            base = weights["BONUS_WEIGHTS" if score["tier"] == "bonus" else "PE_INJECTION_WEIGHTS"]
            total = sum(base[f] for f in score["field_scores"])
            weighted = 0
            for field, value in score["field_scores"].items():
                fields[field].append(value)
                weighted += base[field] / total * value
                losses[field] += base[field] / total * (1 - value)
            assert round(weighted, 4) == score["weighted_score"]
            penalty = score["spurious_penalty"] + score["hallucination_penalty"]
            assert round(max(0, weighted - penalty), 4) == score["final_score"]
            losses["extra_field_penalty"] += score["spurious_penalty"]
            losses["extra_technique_penalty"] += score["hallucination_penalty"]
            missing.update(score["missing_techniques"])
            unmatched.update(score.get("unsupported_techniques", []))
            for component in score["encryption_component_scores"]["components"]:
                assert component["required"] and component["key_required"]
                components[component["expected_algorithm"]].append(component)
                if component["algorithm_score"] < 1:
                    reasons[component["algorithm_match_reason"]] += 1
            if score["field_scores"]["encoded_strings"] == 0:
                # These are encrypted-payload/encoded-string distinctions, not
                # evidence that the model failed to recover the payload cipher.
                assert answer["encoded_strings"] is True
                assert truths[task_id]["encoded_strings"] is False
                encoded_errors.append({"task_id": task_id, "trial": episode["trial"]})
            rejected = set(score.get("unsupported_techniques", []) + score.get("contradicted_anti_analysis", []))
            if task_id.startswith("v3_l22_") and "tls_callback" in rejected:
                tls_flags.append({"task_id": task_id, "trial": episode["trial"]})
            example_id = selected.get((model_id, task_id, episode["trial"]))
            if example_id:
                examples.append({
                    "id": example_id, "model": model_id, "task_id": task_id,
                    "trial": episode["trial"], "episode_id": episode["episode_id"],
                    "answer_path": str(answer_path.relative_to(ROOT)),
                    "answer_sha256": episode["answer_sha256"],
                    "answer_fields": {k: answer.get(k) for k in
                                      ("encryption_components", "techniques", "anti_analysis")},
                    "scored_components": score["encryption_component_scores"],
                    "anti_analysis_matches": score.get("anti_analysis_matches", []),
                    "source_file": tasks[task_id]["source_file"],
                })
        overall = mean(e["new_score"]["final_score"] for e in episodes) * 100
        assert abs(overall - report["aggregate_metrics"]["overall_score"] * 100) < 1e-9
        # 100 attempts make a sum of unit-scale per-episode losses numerically
        # equal to points lost from a 100-point Overall score.
        losses["unanswered_attempts"] = 100 - outcomes["valid_answer"]
        losses["rounding_adjustment"] = 100 - overall - sum(losses.values())
        assert abs(losses["rounding_adjustment"]) < .005
        all_components = [c for values in components.values() for c in values]
        models.append({
            "id": model_id, "name": name, "overall": overall, "outcomes": dict(outcomes),
            "fields": {f: {"mean_score": mean(v) * 100, "answers": len(v),
                            "full_credit_answers": sum(x == 1 for x in v)} for f, v in fields.items()},
            "losses_overall_points": dict(losses),
            "missing_technique_counts": dict(missing),
            "unmatched_technique_counts": dict(unmatched),
            "encryption": {
                "required_components": len(all_components),
                "correct_key_bytes": sum(c["key_matches_component"] for c in all_components),
                "fully_scored_keys": sum(c["key_score"] == 1 for c in all_components),
                "partial_algorithm_reasons": dict(reasons),
                "by_algorithm": {a: {"components": len(v),
                                     "full_algorithm_credit": sum(c["algorithm_score"] == 1 for c in v),
                                     "correct_key_bytes": sum(c["key_matches_component"] for c in v)}
                                 for a, v in components.items()},
            },
            "encoded_strings_false_positives": encoded_errors,
            "level22_tls_flags": tls_flags,
        })
    muse, astra = models[:2]
    for model in models:
        rc4 = model["encryption"]["by_algorithm"]["RC4"]
        assert rc4["full_algorithm_credit"] == rc4["correct_key_bytes"] == rc4["components"]
    assert muse["fields"]["encryption_algorithm"]["full_credit_answers"] == 96
    assert muse["fields"]["encryption_key"]["full_credit_answers"] == 96
    assert astra["fields"]["encryption_algorithm"]["full_credit_answers"] == 100
    assert astra["fields"]["encryption_key"]["full_credit_answers"] == 100
    difference = {f: astra["losses_overall_points"].get(f, 0) - muse["losses_overall_points"].get(f, 0)
                  for f in set(muse["losses_overall_points"]) | set(astra["losses_overall_points"])}
    assert abs(sum(difference.values()) - (muse["overall"] - astra["overall"])) < 1e-9
    assert len(examples) == len(selected)
    return {
        "date": "2026-10-25", "release": "v3.1", "scorer": "6.2.0", "rubric": "v3.4",
        "episodes": 500, "valid_answers": sum(m["outcomes"]["valid_answer"] for m in models),
        "definitions": {
            "field_means": "Mean field score across valid answers where that field is scored; not a new ranking. Models answered different subsets.",
            "losses": "Points lost from 100 across all 100 planned attempts; field losses, penalties, nonanswers and rounding sum to 100 minus Overall.",
            "correct_key_bytes": "Required component has the correct key bytes, independent of its algorithm score. Component counts differ from answer counts.",
            "unsupported": "Scorer-rejected claims include incomplete, misplaced and unrecognized wording; these are not a verified hallucination rate.",
            "examples": "Selected saved-answer examples checked against source or existing static binary evidence, not a new audit of every claim.",
        },
        "models": models, "muse_minus_astra_points_by_field": difference,
        "examples": examples, "source_sha256": hashes,
    }


def findings_html(data):
    muse, astra, grok, opus, gemini = data["models"]
    def score(model, field):
        return f'{model["fields"][field]["mean_score"]:.1f}'
    columns = (("injection_details", "Injection"), ("techniques", "Techniques"),
               ("encryption_algorithm", "Algorithms"), ("encryption_key", "Keys"),
               ("anti_analysis", "Anti-analysis"))
    rows = []
    for model in data["models"]:
        cells = f'<th scope="row">{escape(model["name"])}<span class="model-meta">{model["outcomes"]["valid_answer"]} valid answers</span></th>'
        for field, label in columns:
            value = model["fields"][field]
            cells += (f'<td class="num" data-label="{label}">{value["mean_score"]:.1f}'
                      f'<span class="score-interval">{value["answers"]} answers</span></td>')
        rows.append('<tr>' + cells + '</tr>')
    advantage = data["muse_minus_astra_points_by_field"]["techniques"]
    gkeys, mkeys = grok["encryption"], gemini["encryption"]
    writeup = (ROOT / "scripts/site_templates/findings-v3-1.html").read_text()
    assert len(re.sub(r'<[^>]+>', ' ', writeup).split()) == 500
    return f'''
  {writeup}
  <details class="compact-details" id="detailed-findings"><summary>Field scores and specific errors</summary><div class="details-content">
  <div class="findings-report">
    <h3>Why the scores were high</h3>
    <p>Among submitted answers, average injection-detail scores ranged from {score(muse, "injection_details")} to {score(astra, "injection_details")}/100. Models usually identified the target process, memory writes, and execution method. Every submitted answer also received full credit for identifying the PE file type, though that field carries little weight. All five models recovered the RC4 algorithm and key in every submitted answer that required them.</p>
    <div class="table-wrap"><table class="results-table responsive-results secondary-table" id="field-scores">
      <caption>Average field scores /100 · submitted answers only</caption>
      <thead><tr><th scope="col">Model</th>{''.join(f'<th scope="col" class="num">{label}</th>' for _, label in columns)}</tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    <p class="results-note">Each cell averages valid answers where that field applies. Refusals and budget exits are excluded here. Models answered different subsets, so this table explains their scores; it is not another leaderboard.</p>

    <h3>Where Muse gained its lead</h3>
    <p>Muse earned {score(muse, "techniques")}/100 for technique identification, compared with Astra’s {score(astra, "techniques")}. That gave Muse {advantage:.2f} points toward the Overall comparison. Astra recovered ground through more complete injection details, encryption recovery, and anti-analysis answers, leaving Muse ahead by 0.32 points. Both answered all 100 attempts.</p>
    <p>Astra received full algorithm and key credit in all 100 answers. Muse did so in 96. Astra also recovered every required decoded string; Muse did so in 16 of the 20 answers where strings were scored. Muse’s technique advantage decided the recorded ranking.</p>

    <h3>Encryption: finding the key was usually easier than describing the cipher</h3>
    <p>The binaries store keys as constants, so recovery mainly tests finding those bytes and connecting them to the right routine. Levels 16, 19, 22, and 23 contain a custom S-box/XOR transform. Its round count matters: ten rounds in Levels 16, 19, and 23; fourteen in Level 22. It is not standard AES, despite the names used in the sample code. Level 23 also has a separate XOR string component; its truncated RSA blob is not a working encryption component.</p>
    <p>Grok recovered {gkeys["correct_key_bytes"]} of {gkeys["required_components"]} required component keys. Most of its cipher deductions came from naming the family without giving the round count in the algorithm field. In one bonus answer, it put the correct ten-round description under key storage instead. The scorer reads the algorithm field, so that answer received partial credit. Gemini recovered all {mkeys["correct_key_bytes"]} required keys in its submitted answers, but also lost algorithm credit. Key credit depends on the associated algorithm, so a reduced key score does not always mean wrong key bytes.</p>
    <p>Muse made a concrete cipher error in Level 23, unstripped, attempt 1: it reported <code>round × 18</code>. The code uses <code>round × 27</code>. Astra and Opus earned full credit on these components in every submitted answer that required them.</p>

    <h3>Hallucinations: claiming code runs when it does not</h3>
    <p>A clear example is Level 22’s custom TLS routine. Muse’s first unstripped answer claimed “TLS callback execution before WinMain.” Grok and Opus also described it running on process attach. The shipped binary does not register that routine in its active callback array; the registered callbacks belong to the compiler runtime.</p>
    <p>Missing a technique is a different error. Broad labels and descriptions placed in another answer field can also lose credit. Unmatched claims therefore cannot be reported as a hallucination rate. The scores include those wording and field-placement effects.</p>

    <h3>Two other reasons models lost points</h3>
    <p><strong>Encrypted payloads were confused with encoded strings.</strong> Muse marked strings as encoded in {len(muse["encoded_strings_false_positives"])} answers where the rubric says they were not; Astra did so in {len(astra["encoded_strings_false_positives"])}. This cost them {muse["losses_overall_points"]["encoded_strings"]:.2f} and {astra["losses_overall_points"]["encoded_strings"]:.2f} Overall points. Recovering an encrypted payload does not make the separate string flag true.</p>
    <p><strong>Some models did not submit an answer.</strong> Opus had 22 refusals or blocks, Gemini 64, and Grok four budget exits. Those attempts receive zero in Overall. Opus still recovered every required algorithm and key in its 78 submitted answers. Its lower Overall score therefore includes a completion problem, not just analysis errors.</p>
    <p class="results-note">Figures use the 500 saved score records. The <a href="findings.json" download="agentre-v3.1-findings.json">findings data</a> contains field counts, point losses, and the cited answer examples. <a href="#comparison">Muse–Astra uncertainty</a> remains in the method.</p>
  </div></div></details>'''


def home_findings_html():
    return '''<ul class="findings-list">
        <li><strong>Muse Wonder wins v3.1.</strong> It scored 87.37/100 to Astra’s 87.04, earning more credit for technique identification.</li>
        <li><strong>Astra was stronger on encryption.</strong> It received full algorithm and key credit in all 100 answers. Muse did so in 96.</li>
        <li><strong>The errors went beyond missing keys.</strong> Models omitted cipher details, confused encrypted payloads with encoded strings, and sometimes claimed code would run when it would not.</li>
      </ul>'''
