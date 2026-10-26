"""Static, accessible defaults and downloads for the v3.1 result explorer."""
import csv
import hashlib
import io
import json
from html import escape

from build_results_preview import ROOT, SOURCE

TERMS = {
    "episodes": ("Episodes", "One episode is one complete attempt by one model on one binary, including its tool calls and final outcome. Twenty binaries × five attempts × five models = 500 episodes."),
    "overall": ("Overall", "The average of all 20 binary scores. Each binary score averages five attempts. Main contributes 90% and Bonus 10%. Refusals and budget exits count as zero. All scores are out of 100."),
    "main": ("Main", "The average across 18 binaries from Levels 14–22. These binaries account for 90% of Overall."),
    "bonus": ("Bonus", "The average across the two Level 23 binaries. Together they account for 10% of Overall, the same weight as any other program’s two variants."),
    "valid": ("Valid answers", "Answers that passed the required format checks. Valid does not mean correct. Each model had 100 attempts; the score measures what those answers recovered."),
    "quality": ("Answer quality", "Average valid-answer scores within each answered binary, then average those binaries equally. Nonanswers are excluded here. Models answered different subsets, so compare this number alongside coverage."),
}
CITATION = ("AgentRE-Bench. 2026. AgentRE-Bench v3.1: Windows PE Results. "
            "October 25, 2026. Scorer 6.2.0; rubric v3.4. "
            "https://www.agentre-bench.ai/results/v3-1/")
FIELDS = (("techniques", "Techniques"), ("injection_details", "Injection details"),
          ("encryption_algorithm", "Algorithms"), ("encryption_key", "Keys"),
          ("anti_analysis", "Anti-analysis"))


def mobile_rows(models, quality=False):
    rows = []
    for rank, m in enumerate(models, 1):
        primary = m["quality"] if quality else m["overall"]
        label = "Answer quality" if quality else "Overall"
        details = [("Main · 90%", f'{m["main"]:.2f}'), ("Bonus · 10%", f'{m["bonus"]:.2f}'),
                   ("Overall 95% interval", f'{m["interval"][0]:.2f}–{m["interval"][1]:.2f}')]
        if quality:
            details = [("Artifacts answered", f'{m["answered_artifacts"]}/20'),
                       ("Refusals / blocks", str(m["refusals"])), ("Budget exits", str(m["budget"]))]
        details += [("Thinking", m["reasoning"])]
        rows.append(f'''<details class="mobile-model" data-model="{m['id']}">
          <summary><span class="mobile-rank">{rank:02d}</span><span class="mobile-name">{escape(m['name'])}<small>{m['valid']}/100 valid answers</small></span><span class="mobile-value"><strong>{primary:.2f}</strong><small>{label}</small><span class="mobile-expand" aria-hidden="true">Details ↓</span></span></summary>
          <dl>{''.join('<div><dt>'+escape(k)+'</dt><dd>'+escape(v)+'</dd></div>' for k, v in details)}</dl>
        </details>''')
    return '\n'.join(rows)


def bar(value, note):
    return (f'<span class="compare-value">{value:.2f}</span><span class="model-meta">{escape(note)}</span>'
            f'<span class="compare-track" aria-hidden="true"><span style="width:{value:.4f}%"></span></span>')


def comparison_rows(left, right, fields=False):
    rows = []
    for key, label in FIELDS if fields else (("overall", "Overall"), ("main", "Main"), ("bonus", "Bonus")):
        cells = '<th scope="row">' + label + '</th>'
        for m in (left, right):
            if fields:
                f = m["fields"][key]
                value, note = f["mean_score"], f'{f["answers"]} valid answers'
            else:
                value, note = m[key], {"overall": "100 attempts", "main": "90 attempts", "bonus": "10 attempts"}[key]
            cells += '<td>' + bar(value, note) + '</td>'
        rows.append('<tr>' + cells + '</tr>')
    if fields:
        rows.append('<tr><th scope="row">Correct key bytes</th>' + ''.join(
            f'<td><span class="compare-value">{m["key_bytes"]["correct"]}/{m["key_bytes"]["total"]}</span><span class="model-meta">required components</span></td>'
            for m in (left, right)) + '</tr>')
    return '\n'.join(rows)


def interaction_parts(data, findings):
    lookup = {m["id"]: m for m in findings["models"]}
    models = []
    for m in data["models"]:
        public = {k: m[k] for k in ("id", "name", "overall", "main", "bonus", "valid", "refusals", "budget", "reasoning")}
        public["fields"] = lookup[m["id"]]["fields"]
        enc = lookup[m["id"]]["encryption"]
        public["key_bytes"] = {"correct": enc["correct_key_bytes"], "total": enc["required_components"]}
        models.append(public)
    pairs_path = SOURCE / "COMPARISON.json"
    comparison = json.loads(pairs_path.read_text())
    pairs = []
    for pair in comparison["pairwise_comparisons"]:
        assert pair["status"] == "estimated"
        pairs.append({"left": pair["left"], "right": pair["right"],
                      "difference": pair["difference"] * 100,
                      "interval": [v * 100 for v in pair["simultaneous_interval"]]})
    assert len(pairs) == 10
    for pair in pairs:
        by_id = {m["id"]: m for m in models}
        assert abs(by_id[pair["left"]]["overall"] - by_id[pair["right"]]["overall"] - pair["difference"]) < 1e-8
    triggers, popovers = [], []
    for key, (title, explanation) in TERMS.items():
        triggers.append(f'<button type="button" class="metric-trigger" popovertarget="term-{key}">{title}<span aria-hidden="true">?</span></button>')
        popovers.append(f'<aside class="metric-popover" id="term-{key}" popover role="dialog" aria-labelledby="term-{key}-title" aria-describedby="term-{key}-text"><h3 id="term-{key}-title">{title}</h3><p id="term-{key}-text">{escape(explanation)}</p><button type="button" class="text-button" popovertarget="term-{key}" popovertargetaction="hide" autofocus>Close</button></aside>')
    left, right = models[:2]
    options = lambda selected: ''.join(f'<option value="{m["id"]}"'+(' selected' if m['id']==selected else '')+'>'+escape(m['name'])+'</option>' for m in models)
    pair = next(p for p in pairs if {p["left"], p["right"]} == {left["id"], right["id"]})
    lo, hi = pair['interval'] if pair['left'] == left['id'] else [-pair['interval'][1], -pair['interval'][0]]
    return {
        "MOBILE_OVERALL": mobile_rows(data["models"]), "MOBILE_QUALITY": mobile_rows(data["models"], True),
        "METRIC_HELP": ''.join(triggers), "METRIC_POPOVERS": '\n'.join(popovers),
        "COMPARE_LEFT_OPTIONS": options(left["id"]), "COMPARE_RIGHT_OPTIONS": options(right["id"]),
        "COMPARE_LEFT_NAME": escape(left["name"]), "COMPARE_RIGHT_NAME": escape(right["name"]),
        "COMPARE_SCORE_ROWS": comparison_rows(left, right), "COMPARE_FIELD_ROWS": comparison_rows(left, right, True),
        "COMPARE_INTERVAL": f'{left["name"]} minus {right["name"]}: {left["overall"]-right["overall"]:+.4f} points. Simultaneous 95% interval: {lo:+.4f} to {hi:+.4f}.',
        "INTERACTIVE_DATA": json.dumps({"models": models, "pairs": pairs, "comparison_sha256": hashlib.sha256(pairs_path.read_bytes()).hexdigest()}, separators=(',', ':')).replace('<', '\\u003c'),
        "CITATION": escape(CITATION),
    }


def csv_downloads(data):
    summary = io.StringIO(newline='')
    writer = csv.writer(summary)
    writer.writerow(['release', 'date', 'model', 'overall_100', 'main_100', 'bonus_100',
                     'valid_answers', 'planned_attempts', 'refusals', 'budget_exits',
                     'conditional_quality_100', 'answered_artifacts', 'access', 'thinking', 'scorer', 'rubric'])
    artifacts = io.StringIO(newline='')
    aw = csv.writer(artifacts)
    aw.writerow(['release', 'model', 'artifact', 'variant', 'mean_score_100', 'valid_answers', 'planned_attempts', 'scorer', 'rubric'])
    for m in data['models']:
        writer.writerow(['v3.1', data['date'], m['name'], m['overall'], m['main'], m['bonus'], m['valid'], 100,
                         m['refusals'], m['budget'], m['quality'], m['answered_artifacts'], m['access'], m['reasoning'], data['scorer'], data['rubric']])
        for a in m['artifacts']:
            aw.writerow(['v3.1', m['name'], a['task_id'], 'stripped' if a['task_id'].endswith('_s') else 'unstripped',
                         a['mean'], a['valid'], a['attempts'], data['scorer'], data['rubric']])
    return {"scores.csv": summary.getvalue(), "artifact-scores.csv": artifacts.getvalue()}
