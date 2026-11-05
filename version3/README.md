# AgentRE-Bench V3 — Windows PE Corpus and Historical Results

The corpus contains ten Windows PE32+ programs in matched unstripped/stripped pairs.

**Current results:** [v3.1 report, updated November 5, 2026](../docs/results-current.md) — six model configurations, five attempts per artifact, 600 episodes, rubric v3.4 and scorer `6.2.0+exact-claim-review-20261105`. [Interactive report](https://www.agentre-bench.ai/results/v3-1/).

The files and commands below preserve the **August 2026 single-attempt archive**. Its scores and Kimi K3 run are not part of the current leaderboard.

- [Full analysis](ANALYSIS.md)
- [Reproduction manifest](RUN_MANIFEST.json)
- [Raw reports, answers, and transcripts](results/)
- [Deterministic publication verifier](verify.py)
- [SHA-256 ledger for all 366 raw result files](RESULTS_SHA256SUMS)
- [Frozen PE binaries](binaries/) — 10 unstripped and 10 stripped artifacts
- [C/C++ sample sources](sources/)
- [Deterministic Windows ground truths](ground_truths/)
- [PE build script](build_windows_binaries.sh)

The agent harness receives only one compiled artifact per task. Sources and ground truths are published for reproducibility but are never copied into an agent workspace.

From the repository root, verify every historical August score row, aggregate, artifact hash, answer, and transcript:

```bash
python3 version3/verify.py
```

Build development PE pairs only in a separate checkout; rebuilding replaces frozen files and does not reproduce byte-identical hashes across toolchain versions:

```bash
./version3/build_windows_binaries.sh
```

Run the legacy V3 interface (not the current reviewed-results protocol):

```bash
python3 run_benchmark.py --all --manifest version3/tasks_v3.json
```
