# AgentRE-Bench current Windows PE results

Six models analyzed ten Windows programs, each supplied as a stripped and unstripped binary. Each model made five attempts per artifact with a budget of 25 tool calls: 100 attempts per model, 600 in total. Analysis was static; the target binaries were never executed.

Updated November 5, 2026. Report v3.1; rubric v3.4; scorer `6.2.0+exact-claim-review-20261105`.

![Current six-model leaderboard with 90/10 Main/Bonus contributions and individual confidence intervals](leaderboard-v3.svg)

## Scores and coverage

All scores below are out of 100. Overall averages five attempts per artifact and weights the 20 artifacts equally: 90% Main (Levels 14–22) and 10% Bonus (Level 23). Refusals and budget exhaustion count as zero.

| Model | Overall | Individual 95% interval | Main | Bonus | Valid answers | Access |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Muse Wonder | **87.3681** | 85.18–89.56 | 87.3677 | 87.3720 | 100/100 | API |
| GPT-6 Astra | **87.0438** | 85.80–88.29 | 86.4016 | 92.8240 | 100/100 | API |
| Grok 4.7 | **79.6204** | 76.59–82.65 | 81.0181 | 67.0410 | 96/100 | API |
| DeepSeek V4.1 Flash | **78.3077** | 75.01–81.60 | 78.4254 | 77.2480 | 98/100 | API |
| Claude Opus 5.5 | **69.6560** | 62.57–76.74 | 68.8363 | 77.0330 | 78/100 | API |
| Gemini 4 Argon | **31.1994** | 13.30–49.10 | 29.5297 | 46.2270 | 36/100 | API |

Scores measure credit under the rubric. A valid answer meets the submission format but can still contain errors. None of the 600 attempts received full credit.

The intervals use Student t across the five complete-suite repetition means. They describe variability on this fixed set of ten programs. Model settings and token limits differ; the [results download](results/v3-1/scores.json) lists each configuration and the pairwise comparisons.

| Model | Conditional answer quality /100 | Artifacts answered | Refusals / blocks | Budget exits | Thinking |
| --- | ---: | ---: | ---: | ---: | --- |
| Muse Wonder | 87.3681 | 20/20 | 0 | 0 | High |
| GPT-6 Astra | 87.0438 | 20/20 | 0 | 0 | Extra high |
| Grok 4.7 | 82.9673 | 20/20 | 0 | 4 | High |
| DeepSeek V4.1 Flash | 80.0294 | 20/20 | 0 | 2 | Max |
| Claude Opus 5.5 | 89.3982 | 19/20 | 22 | 0 | High |
| Gemini 4 Argon | 85.3845 | 18/20 | 64 | 0 | High |

Conditional quality averages valid answers within each answered artifact, then gives those artifacts equal weight. Models answered different subsets, so these means cannot be compared as a separate ranking. Across all models, 508 attempts produced valid answers, 86 ended in refusals or blocks, and six exhausted the budget.

## Findings from the binaries

Models generally recovered the main injection sequence: the target process, memory allocation, payload writes, and execution method. Average injection-detail scores ranged from 95.3 to 99.6/100 among submitted answers where that field applied. Every submitted answer identified the PE file type correctly. Errors became more apparent in the cipher parameters, callback registration, anti-analysis behavior, and decoded strings.

| Model | Injection details | Techniques | Algorithms | Key credit | Anti-analysis | Decoded strings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Muse Wonder | 96.2 | 87.1 | 97.0 | 97.0 | 69.2 | 80.0 |
| GPT-6 Astra | 99.6 | 72.2 | 100.0 | 100.0 | 84.2 | 100.0 |
| Grok 4.7 | 98.1 | 70.4 | 86.2 | 83.6 | 88.7 | 88.2 |
| DeepSeek V4.1 Flash | 95.3 | 82.2 | 89.3 | 87.8 | 59.9 | 40.0 |
| Claude Opus 5.5 | 99.4 | 84.9 | 100.0 | 100.0 | 62.9 | 100.0 |
| Gemini 4 Argon | 99.4 | 72.4 | 89.6 | 89.6 | 95.8 | 55.6 |

Each cell is a mean out of 100 over valid answers where the field applies. Refusals and budget exits are excluded from this table. Models answered different subsets. Key credit depends on the associated algorithm description; it is not the percentage of key bytes recovered. Field denominators and the answer examples below are in the [findings data](results/v3-1/findings.json).

### Encryption parameters

Levels 16, 19, 22, and 23 contain custom S-box/XOR transforms. They use AES-related names and constants but do not implement standard AES. Levels 16, 19, and 23 use ten rounds; Level 22 uses fourteen. Recovering these routines requires describing the operations and their parameters.

Muse made a specific error on the unstripped Level 23 binary in attempt 1: it reported the round-dependent XOR value as `round × 18`. The implementation uses `round × 27` (`0x1B`). The answer identified the custom transform but gave the wrong constant.

The keys are embedded in the binaries. Recovery requires locating their bytes and associating them with the correct component. Astra recovered all 130 required component keys and received full algorithm credit. Muse recovered 128 of 130 keys; 125 received full key credit after accounting for the algorithm descriptions. DeepSeek recovered 111 of 128 keys, with 108 receiving full key credit.

Grok recovered 120 of 124 keys but often omitted the round count from the algorithm field. In one Level 23 answer, it put the correct ten-round description under key storage instead. That answer lost credit because the scorer reads the algorithm field. Gemini recovered all 51 required keys in its submitted answers, but only 43 received full key credit after the algorithm scores were applied. A reduced key score can therefore reflect an incomplete algorithm description even when the key bytes are correct.

### TLS callback registration

Level 22 contains a custom TLS routine that is not registered in the shipped binary's active callback array. The registered callbacks belong to the compiler runtime. Muse's first unstripped answer claimed that the custom callback would execute before `WinMain`. Grok and Opus also described it running on process attach.

Finding the routine establishes that its code is present. Establishing TLS execution requires following the binary's TLS directory and callback array to that routine. These answers asserted execution without the required registration. A function name or source comment cannot establish that path in the compiled artifact.

### Encoded strings and exact decoding

The benchmark distinguishes encrypted payload bytes from encoded strings. Muse marked encoded strings as present in 74 answers where the ground truth specified otherwise; Astra did so in 75. Those errors reduced their Overall scores by 1.97 and 2.00 points, respectively. Recovering an encrypted payload does not establish that the program's strings are encoded.

Exact string recovery also varied. Across the 20 applicable answers from each model, Astra received full decoded-string credit in all 20, Muse in 16, and DeepSeek in eight. DeepSeek's injection-detail mean was 95.3/100, while its decoded-string mean was 40.0/100. It often recovered the main execution sequence without supplying all the required decoded values. Grok received full decoded-string credit in 15 of 17 applicable answers; Gemini did so in five of nine.

### Technique and anti-analysis findings

Muse scored 87.1/100 for technique identification, compared with Astra's 72.2, despite Astra's stronger encryption and string recovery. Both models submitted all 100 answers. The technique field received full credit in six of Muse's answers and one of Astra's.

Anti-analysis was a weaker field for DeepSeek, Opus, and Muse, with means of 59.9, 62.9, and 69.2/100. Opus received full algorithm and key credit in all 78 submitted answers, but full anti-analysis credit in only nine. DeepSeek received full anti-analysis credit in ten of 98 answers; Muse did so in 31 of 100. The TLS example shows one concrete error in this area: attributing behavior to code that is not registered to run as claimed.

These field scores combine missing expected facts with unsupported claims. They also include wording and field-placement effects. Correct observations outside the rubric can lose credit, so the aggregate deductions should not be reported as a count of factual errors or hallucinations.

### Refusals and budget exhaustion

Opus refused or was blocked on 22 attempts; Gemini on 64. Their Overall scores include those zero-valued attempts. Opus recovered all required algorithms and keys in the answers it submitted, so its lower overall result cannot be explained by encryption analysis alone. Gemini's high injection and anti-analysis means cover only the subset it answered.

Grok exhausted the tool budget on four attempts and DeepSeek on two. These also count as zero. Coverage and field scores describe different failures: whether a model submitted an answer, and what it recovered when it did.

## Downloads and reproduction

- [Interactive report](https://www.agentre-bench.ai/results/v3-1/)
- [JSON results, configurations, intervals, and provenance hashes](results/v3-1/scores.json)
- [Summary CSV](results/v3-1/scores.csv) and [artifact CSV](results/v3-1/artifact-scores.csv)
- [Public numeric records for all 600 episodes](results/v3-1/reviewed-episodes.json)
- [Field scores, component counts, and answer examples](results/v3-1/findings.json)
- [Preserved October five-model results](results/v3-1/archive/20261025/scores.json)
- [Scoring contract and review history](scoring.md)

From the repository root:

```bash
python3 -m pip install -r scripts/requirements-site.txt
python3 scripts/build_site_results.py
python3 scripts/build_github_results.py
```

These commands rebuild the tables, graphics, and website from the published numeric records. They do not regrade raw answers. The [scoring documentation](scoring.md) records the grading rules and retrospective corrections used for this report.

## Earlier results

The [August V3 report](../version3/ANALYSIS.md) uses one attempt per artifact and the older Main-plus-Bonus total. Those results, including Kimi K3, are not directly comparable with this five-attempt evaluation. Incomplete campaigns are excluded from the current table.

The suite consists of synthetic, public programs. These results describe static analysis of those artifacts; they do not establish performance on unseen malware or successful execution of the behaviors described.
