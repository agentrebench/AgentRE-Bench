# AgentRE-Bench V3 — Windows PE Results

V3 evaluates 10 Windows PE32+ binaries as matched unstripped/stripped pairs across six frontier models.

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

From the repository root, verify every published score row, aggregate, artifact hash, answer, and transcript:

```bash
python3 version3/verify.py
```

Build fresh PE pairs (this does not reproduce byte-identical hashes across toolchain versions):

```bash
./version3/build_windows_binaries.sh
```

Run the frozen V3 suite:

```bash
python3 run_benchmark.py --all --manifest version3/tasks_v3.json
```
