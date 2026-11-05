"""Build the November extension from public, allowlisted numeric records.

Install scripts/requirements-site.txt, then run python3 scripts/build_site_results.py. This computes publication statistics only; it does
not regrade answers. Frozen source report hashes accompany the numeric export.
"""
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from math import sqrt
from pathlib import Path
from statistics import mean, variance

from scipy.stats import t

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/results/v3-1'
INPUT = OUT / 'reviewed-episodes.json'
MAIN = dict(techniques=.25, injection_details=.20, decoded_c2=.10,
            encryption_key=.10, decoded_strings=.10, anti_analysis=.10,
            encryption_algorithm=.05, c2_protocol=.05, file_type=.03, encoded_strings=.02)
BONUS = dict(decoded_c2=.15, encryption_algorithm=.10, encryption_key=.20,
             encryption_key_storage=.05, techniques=.15, decoded_strings=.15,
             anti_analysis=.10, file_type=.03, encoded_strings=.02, c2_protocol=.05)


def interval(values):
    center = mean(values)
    half = t.ppf(.975, len(values) - 1) * sqrt(variance(values) / len(values))
    return [float(center - half), float(center + half)]


def build_reviewed_data():
    source = json.loads(INPUT.read_text())
    old = json.loads((OUT / 'archive/20261025/scores.json').read_text())
    findings = json.loads((OUT / 'archive/20261025/findings.json').read_text())
    old_models = {m['id']: m for m in old['models']}
    old_findings = {m['id']: m for m in findings['models']}
    models, summaries, repetitions = [], [], {}
    for raw in source['models']:
        episodes = raw['episodes']
        assert len(episodes) == len({(e['trial'], e['task_id']) for e in episodes}) == 100
        assert Counter(e['task_id'] for e in episodes) == Counter({f'v3_l{n}_{s}': 5 for n in range(14, 24) for s in ('s', 'u')})
        assert all(e['status'] == 'valid_answer' or e['final_score'] == 0 for e in episodes)
        model = {k: v for k, v in raw.items() if k not in ('episodes', 'audited_overall', 'audited_interval')}
        outcomes = Counter(e['status'] for e in episodes)
        valid = [e for e in episodes if e['status'] == 'valid_answer']
        artifacts = []
        quality = []
        for level in range(14, 24):
            for suffix in ('u', 's'):
                task = f'v3_l{level}_{suffix}'
                group = [e for e in episodes if e['task_id'] == task]
                answered = [e['final_score'] * 100 for e in group if e['status'] == 'valid_answer']
                artifacts.append(dict(task_id=task, mean=mean(e['final_score'] for e in group) * 100,
                                      attempts=5, valid=len(answered)))
                if answered:
                    quality.append(mean(answered))
        trials = sorted({e['trial'] for e in episodes})
        repeats = [mean(e['final_score'] for e in episodes if e['trial'] == trial) * 100 for trial in trials]
        repetitions[model['id']] = repeats
        overall = mean(a['mean'] for a in artifacts)
        assert abs(overall - raw['audited_overall'] * 100) < 1e-10
        ci = interval(repeats)
        assert all(abs(a - b * 100) < 1e-8 for a, b in zip(ci, raw['audited_interval']))
        model.update(overall=overall, main=mean(a['mean'] for a in artifacts[:18]),
                     bonus=mean(a['mean'] for a in artifacts[18:]), interval=ci,
                     quality=mean(quality), answered_artifacts=len(quality),
                     valid=outcomes['valid_answer'], refusals=outcomes['refusal'],
                     budget=outcomes['budget_exhaustion'], full_credit_episodes=sum(e['final_score'] == 1 for e in episodes),
                     full_credit_rate=sum(e['final_score'] == 1 for e in episodes) / 100,
                     artifacts=artifacts, trial_means=repeats,
                     baseline_overall=mean(e['baseline_score'] for e in episodes) * 100)
        paired, complete = [], []
        lookup = {(e['trial'], e['task_id']): e for e in episodes}
        for trial in trials:
            deltas = []
            for level in range(14, 24):
                s, u = (lookup[(trial, f'v3_l{level}_{suffix}')] for suffix in ('s', 'u'))
                delta = (s['final_score'] - u['final_score']) * 100
                deltas.append(delta)
                if s['status'] == u['status'] == 'valid_answer':
                    complete.append(delta)
            paired.append(mean(deltas))
        model['stripping'] = dict(direction='stripped_minus_unstripped', all_pairs=50,
                                  all_delta_pp=mean(paired), interval_pp=interval(paired),
                                  valid_pairs=len(complete), valid_delta_pp=mean(complete))
        assert abs(overall - (.9 * model['main'] + .1 * model['bonus'])) < 1e-9
        if model['id'] in old_models:
            previous = old_models[model['id']]
            for key in ('overall', 'main', 'bonus', 'quality', 'valid', 'refusals', 'budget'):
                assert abs(model[key] - previous[key]) < 1e-8, (model['id'], key)
        models.append(model)
        fields, losses, components = defaultdict(list), Counter(), defaultdict(list)
        for e in valid:
            weights = BONUS if e['task_id'].startswith('v3_l23_') else MAIN
            denominator = sum(weights[f] for f in e['field_scores'])
            for field, value in e['field_scores'].items():
                fields[field].append(value)
                losses[field] += weights[field] / denominator * (1 - value)
            losses['extra_field_penalty'] += e['spurious_penalty']
            losses['extra_technique_penalty'] += e['hallucination_penalty']
            for c in e['encryption_components']:
                components[c['expected_algorithm']].append(c)
        losses['unanswered_attempts'] = 100 - len(valid)
        losses['rounding_adjustment'] = 100 - overall - sum(losses.values())
        assert abs(losses['rounding_adjustment']) < .005
        all_components = [c for group in components.values() for c in group]
        summary = dict(old_findings.get(model['id'], {}))
        summary.update(id=model['id'], name=model['name'], overall=overall, outcomes=dict(outcomes),
                       fields={f: dict(mean_score=mean(values) * 100, answers=len(values),
                                       full_credit_answers=sum(v == 1 for v in values)) for f, values in fields.items()},
                       losses_overall_points=dict(losses), encryption={
                           'required_components': len(all_components),
                           'correct_key_bytes': sum(c['key_matches_component'] for c in all_components),
                           'fully_scored_keys': sum(c['key_score'] == 1 for c in all_components),
                           'partial_algorithm_reasons': dict(Counter(c['algorithm_match_reason'] for c in all_components if c['algorithm_score'] < 1)),
                           'by_algorithm': {algorithm: dict(components=len(group),
                               full_algorithm_credit=sum(c['algorithm_score'] == 1 for c in group),
                               correct_key_bytes=sum(c['key_matches_component'] for c in group)) for algorithm, group in components.items()}})
        if model['id'] in old_findings:
            for field, stats in summary['fields'].items():
                assert abs(stats['mean_score'] - old_findings[model['id']]['fields'][field]['mean_score']) < 1e-8
        summaries.append(summary)
    models.sort(key=lambda m: m['overall'], reverse=True)
    summaries.sort(key=lambda m: m['overall'], reverse=True)
    pairs = []
    for left, right in combinations(sorted(repetitions), 2):
        a, b = repetitions[left], repetitions[right]
        va, vb = variance(a) / len(a), variance(b) / len(b)
        df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
        half = float(t.ppf(1 - .05 / (2 * 15), df) * sqrt(va + vb))
        diff = mean(a) - mean(b)
        pairs.append(dict(left=left, right=right, difference=diff, interval=[diff - half, diff + half],
                          degrees_of_freedom=df, family_comparisons=15))
    assert len(pairs) == 15
    focus = next(p for p in pairs if p['left'] == 'gpt-6-astra' and p['right'] == 'muse-wonder-1.0')
    hashes = dict(source['source_report_sha256'])
    hashes['reviewed-episodes.json'] = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    data = dict(date=source['date'], suite='v3.4', scorer=source['scorer'], base_scorer='6.2.0',
                evaluation_type='saved_answer_semantic_review', models=models, artifacts=20, programs=10,
                attempts_per_artifact=5, episodes=600, source_report_sha256=hashes, release='v3.1',
                rubric='v3.4', score_scale=100, aggregation='artifact_mean_v1', main_weight=.9, bonus_weight=.1,
                pair=dict(direction='Muse minus Astra', gap_pp=-focus['difference'],
                          interval_pp=[-focus['interval'][1], -focus['interval'][0]],
                          family_confidence=.95, family_comparisons=15, statistical_winner=None),
                pairs=pairs, ledger_sha256=source['ledger_sha256'], adapter_sha256=source['adapter_sha256'],
                uncertainty=dict(individual_intervals='95% Student t intervals across five full-suite repetition means',
                                 pair_interval='Welch interval with Bonferroni protection across all 15 model pairs',
                                 scope='Repeat performance on the fixed public artifact suite'),
                notes=[source['review_method'], source['model_conditions_note'],
                       'Scores measure fixed-rubric credit, not pure factual accuracy. Correct observations outside allowed facts or placed in another field can lose credit.',
                       'Independent assistant audit reproduced all 600 baseline and reviewed score records; no independent human validation is claimed.',
                       'Previous 500 episode scores are numerically unchanged. DeepSeek baseline 75.9084/100 becomes 78.3077/100 under the versioned exact-claim review.',
                       'DeepSeek: 98 valid answers, two zero-score budget exits; two recovered URLError requests, no terminal infrastructure failures. No failed episodes were dropped.',
                       'All six models have zero full-credit episodes under this rubric; valid submission is not task success.',
                       'New DeepSeek collection completed November 5 UTC (November 4 US Central). Prior five models retain their original collection dates.',
                       'Historical five-model episodes were previously rescored from v3.2/scorer 5.0 to v3.4/scorer 6.2.0. This extension uses unchanged v3.4 artifacts and ground truths.',
                       'Kimi and GLM incomplete campaigns are excluded. No new inference was used for semantic review.',
                       'Public suite with post-hoc calibration; no claim of held-out generalization or controlled compute comparison.'])
    findings.update(date=source['date'], scorer=source['scorer'], episodes=600,
                    valid_answers=sum(m['valid'] for m in models), models=summaries)
    findings['source_sha256'].update(hashes)
    findings['definitions']['review'] = source['review_method']
    return data, findings
