"""Build the v3.1 website release from public reviewed numeric episode records.

The website release name does not rename the underlying rubric or artifacts.
Only explicitly selected aggregate fields are exported; no transcripts or secrets.
"""
import hashlib
import json
import re
from html import escape
from pathlib import Path

from build_results_preview import ROOT
from site_findings import findings_html, home_findings_html
from site_interactions import interaction_parts, csv_downloads

OUT = ROOT / "docs/results/v3-1"
TEMPLATE = ROOT / "scripts/site_templates/results-v3-1.html"
LEVELS = {
    14: "DLL injection", 15: "APC injection", 16: "Code cave injection",
    17: "Process hollowing", 18: "Hell’s Gate", 19: "Reflective DLL loading",
    20: "Remote PE injection", 21: "Ghost hollowing", 22: "Advanced evasion",
    23: "Synthetic worm",
}


def signed(value, digits=2):
    return f"{value:+.{digits}f}".replace("-", "−")


def cell(label, content, cls="num"):
    return f'<td class="{cls}" data-label="{escape(label)}">{content}</td>'


def build():
    from reviewed_site_data import build_reviewed_data
    data, findings = build_reviewed_data()
    rows, home_rows, quality_rows, stripping_rows, settings_rows = [], [], [], [], []
    for rank, model in enumerate(data["models"], 1):
        name = escape(model["name"])
        identity = (f'<td class="rank" data-label="Rank">{rank:02d}</td>'
                    f'<th scope="row" class="model-name">{name}'
                    f'<span class="model-meta">{escape(model["reasoning"])} thinking</span></th>')
        low, high = model["interval"]
        rows.append(f'<tr data-model="{model["id"]}">{identity}'
                    + cell("Overall", f'<strong class="overall-score">{model["overall"]:.2f}</strong>'
                           f'<span class="score-interval">95% CI {low:.2f}–{high:.2f}</span>')
                    + cell("Main · 90%", f'{model["main"]:.2f}')
                    + cell("Bonus · 10%", f'{model["bonus"]:.2f}')
                    + cell("Valid answers", f'{model["valid"]}/100') + '</tr>')
        leading = ' class="leading-model"' if rank == 1 else ''
        home_rows.append(f'<tr{leading}><td class="rank">{rank:02d}</td><th scope="row">{name}</th>'
                         f'<td class="numeric total">{model["overall"]:.2f}</td>'
                         f'<td class="numeric">{model["main"]:.2f}</td>'
                         f'<td class="numeric">{model["bonus"]:.2f}</td>'
                         f'<td class="numeric">{model["valid"]}/100</td></tr>')
        quality_rows.append(f'<tr data-model="{model["id"]}">{identity}'
                            + cell("Answer quality", f'{model["quality"]:.2f}')
                            + cell("Valid answers", f'{model["valid"]}/100')
                            + cell("Artifacts answered", f'{model["answered_artifacts"]}/20')
                            + cell("Refusals / blocks", str(model["refusals"]))
                            + cell("Budget exits", str(model["budget"])) + '</tr>')
        s = model["stripping"]
        lo, hi = s["interval_pp"]
        stripping_rows.append(f'<tr><th scope="row">{name}</th>'
                              + cell("All attempts · Δ", signed(s["all_delta_pp"]))
                              + cell("95% CI", f'{signed(lo)} to {signed(hi)}')
                              + cell("Complete pairs", f'{s["valid_pairs"]}/50')
                              + cell("Valid pairs · Δ", signed(s["valid_delta_pp"])) + '</tr>')
        settings = model["settings"]
        settings_rows.append(f'<tr><th scope="row">{name}</th>'
                             + cell("Thinking", model["reasoning"], "")
                             + cell("Tool calls", str(settings["max_tool_calls"])) + '</tr>')

    artifact_rows = []
    lookup = {m["id"]: {a["task_id"]: a for a in m["artifacts"]} for m in data["models"]}
    for level, label in LEVELS.items():
        for suffix, variant in (("u", "Unstripped"), ("s", "Stripped")):
            task_id = f"v3_l{level}_{suffix}"
            cells = f'<th scope="row">L{level} · {label}<span class="model-meta">{variant}</span></th>'
            for m in data["models"]:
                a = lookup[m["id"]][task_id]
                cells += (f'<td class="num heat-cell" data-label="{escape(m["name"])}" '
                          f'style="--heat:{a["mean"] * .3:.4f}%">{a["mean"]:.2f}'
                          f'<span class="score-interval">{a["valid"]}/5 valid</span></td>')
            artifact_rows.append(f'<tr data-variant="{suffix}" data-artifact="{task_id}">{cells}</tr>')

    mini_rows = '\n'.join(
        f'<div class="mini-row" style="--score-width:{m["overall"]:.2f}%"><span>{i:02d}</span>'
        f'<strong>{escape(m["name"])}</strong><span>{m["overall"]:.2f}</span></div>'
        for i, m in enumerate(data["models"][:3], 1))
    home_path = ROOT / "docs/index.html"
    home = home_path.read_text()
    nav = re.search(r'<header class="site-header".*?</header>', home, re.S).group()
    nav = nav.replace('href="#', 'href="/#')
    nav = nav.replace('href="/results/v3-1/"', 'href="/results/v3-1/" aria-current="page"', 1)
    footer = re.search(r'<footer\b[^>]*>.*?</footer>', home, re.S).group()
    page = TEMPLATE.read_text()
    interactive = interaction_parts(data, findings)
    replacements = {
        "NAV": nav, "FOOTER": footer, "MINI_ROWS": mini_rows,
        "SCORE_ROWS": '\n'.join(rows), "QUALITY_ROWS": '\n'.join(quality_rows),
        "STRIPPING_ROWS": '\n'.join(stripping_rows), "SETTINGS_ROWS": '\n'.join(settings_rows),
        "ARTIFACT_HEADINGS": ''.join(f'<th scope="col" class="num">{escape(m["name"])}</th>' for m in data["models"]),
        "PAIR_LOW": f'{data["pair"]["interval_pp"][0]:+.4f}',
        "PAIR_HIGH": f'{data["pair"]["interval_pp"][1]:+.4f}',
        "ARTIFACT_ROWS": '\n'.join(artifact_rows),
        "FINDINGS": findings_html(findings),
        **interactive,
    }
    for key, value in replacements.items():
        page = page.replace(f'@@{key}@@', value)
    assert '@@' not in page, 'Unfilled template field'
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page)
    (OUT / "scores.json").write_text(json.dumps(data, indent=2) + '\n')
    (OUT / "findings.json").write_text(json.dumps(findings, indent=2, sort_keys=True) + '\n')
    for name, content in csv_downloads(data).items():
        (OUT / name).write_text(content)
    home = re.sub(r'<!-- CURRENT_RESULTS_START -->.*?<!-- CURRENT_RESULTS_END -->',
                  '<!-- CURRENT_RESULTS_START -->\n' + '\n'.join(home_rows) + '\n<!-- CURRENT_RESULTS_END -->', home, flags=re.S)
    home, count = re.subn(r'(<section\b[^>]*id="findings".*?)(<ul class="findings-list">.*?</ul>)',
                         lambda match: match[1] + home_findings_html(), home, count=1, flags=re.S)
    assert count == 1
    for marker, key in (("HOME_MOBILE_RESULTS", "MOBILE_OVERALL"), ("HOME_METRIC_HELP", "METRIC_HELP"), ("HOME_POPOVERS", "METRIC_POPOVERS")):
        home, count = re.subn(f'<!-- {marker}_START -->.*?<!-- {marker}_END -->',
                             lambda _: f'<!-- {marker}_START -->\n' + interactive[key] + f'\n<!-- {marker}_END -->',
                             home, count=1, flags=re.S)
        assert count == 1, marker
    home_path.write_text(home)
    print(f'Built {OUT.relative_to(ROOT)}: v3.1, {len(data["models"])} models, {data["episodes"]} episodes.')


if __name__ == "__main__":
    build()
