"""Regenerate the existing README graphics and table from public result data."""
import json
import math
import re
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INK = '#7a7f87'
PURPLE = '#6366f1'
GREEN = '#0fa88a'


def svg_open(height, title, description):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 {height}" width="880" height="{height}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>']


def text(x, y, value, size=12, anchor='start', color=INK, weight='normal'):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-weight="{weight}">{escape(str(value))}</text>'


def leaderboard(data):
    rows = svg_open(376, 'AgentRE-Bench v3.1 Windows PE results — November 2026',
                    'Six models, 600 episodes. Overall is 90% Main plus 10% Bonus, out of 100. Whiskers show individual 95% intervals across five full-suite repetitions. Valid answers are format-valid submissions, not full-task successes.')
    rows += [text(190, 18, 'V3.1 WINDOWS PE · OVERALL /100 · NOVEMBER 2026', weight='600'),
             '<rect x="190" y="32" width="10" height="10" rx="2" fill="'+PURPLE+'"/>',
             text(206, 42, '90% Main · 18 artifacts', 11),
             '<rect x="370" y="32" width="10" height="10" rx="2" fill="'+GREEN+'"/>',
             text(386, 42, '10% Bonus · 2 artifacts', 11), text(790, 42, 'Valid answers', 11, 'middle')]
    left, width = 190, 480
    for value in range(0, 101, 25):
        x = left + width * value / 100
        rows += [f'<line x1="{x}" x2="{x}" y1="56" y2="320" stroke="{INK}" stroke-opacity="0.25"/>',
                 text(x, 338, value, 11, 'middle')]
    for index, model in enumerate(data['models']):
        y = 69 + index * 43
        main, bonus = .9 * model['main'], .1 * model['bonus']
        assert abs(main + bonus - model['overall']) < 1e-9
        x_mid = left + width * main / 100
        low, high = [left + width * v / 100 for v in model['interval']]
        rows += [f'<g data-model="{model["id"]}" data-overall="{model["overall"]:.4f}" data-main-contribution="{main:.8f}" data-bonus-contribution="{bonus:.8f}">',
                 text(178, y + 12, model['name'], 13, 'end'),
                 f'<rect x="{left}" y="{y}" width="{width * main / 100:.6f}" height="16" fill="{PURPLE}"/>',
                 f'<rect x="{x_mid:.6f}" y="{y}" width="{width * bonus / 100:.6f}" height="16" fill="{GREEN}"/>',
                 text(716, y + 12, f'{model["overall"]:.2f}', 13, 'end', weight='600'),
                 text(790, y + 12, f'{model["valid"]}/100', 12, 'middle'),
                 f'<line x1="{low:.6f}" x2="{high:.6f}" y1="{y+24}" y2="{y+24}" stroke="{INK}" stroke-width="1.5"/>',
                 f'<path d="M{low:.6f},{y+20}v8 M{high:.6f},{y+20}v8" stroke="{INK}" stroke-width="1.5"/>', '</g>']
    rows += [text(190, 363, '20 artifacts × 5 attempts per model · failures retained at zero · whiskers: fixed-suite 95% CI', 11), '</svg>']
    return '\n'.join(rows) + '\n'


def stars(data):
    start = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')).date()
    end = datetime.fromisoformat(data['as_of']).date()
    days = sorted(datetime.fromisoformat(v.replace('Z', '+00:00')).date() for v in data['starred_at'])
    assert len(days) == data['stargazers_count']
    maximum = math.ceil(max(len(days), 1) / 40) * 40
    points, total = [], 0
    date = start
    while date <= end:
        while total < len(days) and days[total] <= date:
            total += 1
        points.append((52 + 788 * (date-start).days/(end-start).days, 256 - 228 * total/maximum))
        date += timedelta(days=1)
    rows = svg_open(300, 'GitHub stars over time — agentrebench/AgentRE-Bench',
                    f'{len(days)} current GitHub stargazers by star date, updated {data["as_of"]}. Source: GitHub API. Historical counts exclude users who have since unstarred.')
    rows += [text(52, 16, 'GITHUB STARS · CUMULATIVE · 2026', weight='600'),
             text(840, 16, f'GitHub API · {data["as_of"]}', 11, 'end')]
    for i in range(5):
        n = maximum * i / 4
        y = 256 - 228 * i / 4
        rows += [f'<line x1="52" x2="840" y1="{y}" y2="{y}" stroke="{INK}" stroke-opacity="0.25"/>', text(44, y+4, f'{n:g}', 11, 'end')]
    date = start.replace(day=1)
    while date <= end:
        if date >= start:
            x = 52 + 788 * (date-start).days/(end-start).days
            rows.append(text(x, 276, date.strftime('%b'), 11, 'middle'))
        date = date.replace(year=date.year+(date.month==12), month=date.month%12+1)
    xy = ' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
    path = 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x,y in points)
    rows += [f'<path d="{path} L840,256 L52,256 Z" fill="{PURPLE}" fill-opacity="0.10"/>',
             f'<polyline points="{xy}" fill="none" stroke="{PURPLE}" stroke-width="2" stroke-linejoin="round"/>',
             f'<circle cx="840" cy="{points[-1][1]:.2f}" r="4.5" fill="{PURPLE}"/>',
             text(830, points[-1][1]-10, f'{len(days)} stars', 13, 'end', PURPLE, '600'), '</svg>']
    return '\n'.join(rows) + '\n'


def table(data):
    rows = ['| Rank | Model | Overall /100 | Main /100 | Bonus /100 | Valid answers | Access |',
            '| ---: | --- | ---: | ---: | ---: | ---: | --- |']
    rows += [f'| {i} | {m["name"]} | **{m["overall"]:.2f}** | {m["main"]:.2f} | {m["bonus"]:.2f} | {m["valid"]}/100 | {m["access"]} |' for i,m in enumerate(data['models'], 1)]
    return '\n'.join(rows)


def build():
    data = json.loads((ROOT/'docs/results/v3-1/scores.json').read_text())
    adoption = json.loads((ROOT/'docs/assets/github-stars.json').read_text())
    (ROOT/'docs/leaderboard-v3.svg').write_text(leaderboard(data))
    (ROOT/'docs/star-history.svg').write_text(stars(adoption))
    readme = ROOT/'README.md'
    source, count = re.subn(r'<!-- CURRENT_RESULTS_START -->.*?<!-- CURRENT_RESULTS_END -->',
                           '<!-- CURRENT_RESULTS_START -->\n'+table(data)+'\n<!-- CURRENT_RESULTS_END -->', readme.read_text(), flags=re.S)
    assert count == 1
    readme.write_text(source)
    print(f'Updated README table and both existing SVG graphics: {len(data["models"])} models / {data["episodes"]} episodes.')


if __name__ == '__main__':
    build()
