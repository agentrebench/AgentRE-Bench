<h1 align="center">AgentRE-Bench</h1>
<p align="center"><em>Reverse-engineering intelligence, measured.</em></p>

<p align="center">
<a href="https://github.com/agentrebench/AgentRE-Bench/stargazers"><img src="https://img.shields.io/github/stars/agentrebench/AgentRE-Bench?style=flat&color=6366f1" alt="Stars"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-00d4aa.svg" alt="MIT"></a>
<a href="https://agentre-bench.ai"><img src="https://img.shields.io/badge/site-agentre--bench.ai-6366f1.svg" alt="Website"></a>
<a href="docs/results-current.md"><img src="https://img.shields.io/badge/results-v3.1%20PE%20·%20Nov%202026-blue.svg" alt="Current v3.1 results"></a>
</p>

## Abstract

AgentRE-Bench evaluates whether AI agents can reverse engineer compiled binaries. It gives an agent an unfamiliar ELF or PE binary, a fixed static-analysis toolset, and a budget of 25 tool calls. A deterministic scorer compares the agent's structured findings to fixed ground truth. The benchmark has 23 levels: 13 Linux ELF x86-64 binaries and 10 Windows PE32+ programs. Each PE level is evaluated as a stripped and unstripped pair. The levels cover reverse shells, covert channels, encryption, process injection, direct syscall resolution, reflective loading, and control-flow obfuscation. The current Windows evaluation covers six models and 600 attempts. The highest mean score is 87.37/100. No attempt received full credit.

## Why this benchmark exists

Most AI coding benchmarks start with readable code and a clear task. Security teams usually start with neither. They get a compiled program, no context, and one question: what does this program do?

AgentRE-Bench asks LLM agents that question. Each task is a purpose-built ELF or Windows PE binary compiled from known source. The agent receives the binary and a fixed set of static-analysis tools. It does not receive the source, a description, or a meaningful filename. The agent must choose which tools to run, read hex dumps and disassembly, follow references across tool calls, and submit a structured answer. A deterministic scorer compares the answer to ground truth.

The benchmark separates reverse engineering from pattern recognition. A model that knows the term "process hollowing" must still find the technique in 18 KB of stripped machine code.

## Results

The current results use the V3 Windows PE suite: ten programs, from DLL injection to a synthetic ransomware worm. Each program is evaluated unstripped and stripped. Six models ran all 20 artifacts five times, with a budget of 25 tool calls per attempt. This gives 100 attempts per model and 600 in total. The v3.1 report was updated on November 5, 2026.

![AgentRE-Bench v3.1 leaderboard: Overall out of 100, with 90% Main and 10% Bonus contributions and fixed-suite confidence intervals](docs/leaderboard-v3.svg)

<!-- CURRENT_RESULTS_START -->
| Rank | Model | Overall /100 | Main /100 | Bonus /100 | Valid answers | Access |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Muse Wonder | **87.37** | 87.37 | 87.37 | 100/100 | API |
| 2 | GPT-6 Astra | **87.04** | 86.40 | 92.82 | 100/100 | API |
| 3 | Grok 4.7 | **79.62** | 81.02 | 67.04 | 96/100 | API |
| 4 | DeepSeek V4.1 Flash | **78.31** | 78.43 | 77.25 | 98/100 | API |
| 5 | Claude Opus 5.5 | **69.66** | 68.84 | 77.03 | 78/100 | API |
| 6 | Gemini 4 Argon | **31.20** | 29.53 | 46.23 | 36/100 | API |
<!-- CURRENT_RESULTS_END -->

Main is the mean over the 18 Level 14 to 22 artifacts. Bonus is the mean over the two Level 23 artifacts. Overall is 90% Main plus 10% Bonus, reported out of 100. Each artifact score averages five attempts. Refusals and budget exhaustion count as zero. Valid answers meet the submission format; they can still contain errors.

Findings from the run:

- Muse Wonder scored 87.37 and GPT-6 Astra scored 87.04. Their 0.32-point difference is smaller than the uncertainty in the comparison: the adjusted 95% interval spans −3.82 to +4.47 points.
- GPT-6 Astra recovered the algorithms and keys for all 130 required encryption components across its 100 attempts. Muse Wonder recovered 128 sets of key bytes; 125 received full key credit after accounting for the algorithm description.
- Claude Opus 5.5 refused 22 of 100 attempts. Gemini 4 Argon refused 64. These refusals lower their overall scores alongside errors in the answers they submitted.
- None of the 600 attempts earned full credit under the scoring rubric.

The [full report](docs/results-current.md) contains per-artifact results, scoring details, model settings, and confidence intervals. The [interactive report](https://www.agentre-bench.ai/results/v3-1/) includes field-level findings. Downloads: [JSON results and provenance](docs/results/v3-1/scores.json), [CSV results](docs/results/v3-1/scores.csv), and [per-artifact scores](docs/results/v3-1/artifact-scores.csv).

The [August V3 report](version3/ANALYSIS.md) used one attempt per artifact and an earlier scoring protocol. It is not directly comparable with these results. The Linux ELF evaluation is in the [V2 report](version2/ANALYSIS.md).

## Adoption

![GitHub star history for agentrebench/AgentRE-Bench](docs/star-history.svg)

agentrebench created the repository on 12 February 2026. As of 5 November 2026 it has 138 stars and 14 forks.

## The benchmark

The benchmark has 23 levels and 33 binary artifacts. Levels 1 to 13 are Linux ELF x86-64. They start with a plaintext TCP reverse shell and end with a metamorphic dropper that uses 18 distinct techniques. Levels 14 to 23 are Windows PE32+. They form an injection ladder that ends with an advanced evasion loader and a synthetic worm. Each PE level is a stripped and unstripped pair with the same anonymized filename.

<details><summary><strong>Linux ELF, Levels 1 to 13</strong></summary>

| Level | Task | Techniques | Difficulty |
|------:|------|------------|------------|
| 1 | TCP Reverse Shell | Plaintext C2, socket connect, dup2, execve | Trivial |
| 2 | XOR Encoded Strings | XOR encoding, string obfuscation | Easy |
| 3 | Anti-Debugging Shell | ptrace detection, timing checks | Easy |
| 4 | Polymorphic Shell | Self-modifying code, runtime decryption | Medium |
| 5 | Multistage Shell | Staged payload delivery | Medium |
| 6 | ICMP Covert Channel | ICMP protocol C2, covert channel | Medium |
| 7 | DNS Tunnel Shell | DNS-based C2 tunneling | Medium |
| 8 | Process Hollowing | Process injection, memory manipulation | Hard |
| 9 | Shared Object Injection | .so injection, dlopen/dlsym | Hard |
| 10 | AES Encrypted Shell | AES encryption, key recovery | Hard |
| 11 | Fork Bomb Shell | Process evasion, fork techniques | Hard |
| 12 | JIT Compiled Shellcode | Runtime code generation, JIT | Very Hard |
| 13 | Metamorphic Dropper | RC4 encryption, anti-analysis, metamorphic code | Bonus |

</details>

<details><summary><strong>Windows PE, Levels 14 to 23</strong></summary>

| Level | Task | Core behavior |
|------:|------|---------------|
| 14 | DLL Injection | Manual API resolution, PEB anti-debug, CreateRemoteThread |
| 15 | APC Injection | RC4 payload, NtQueueApcThread, Native API calls |
| 16 | Code Cave Injection | PE section scanning, CPUID check, XOR payload and auxiliary S-box/XOR transform |
| 17 | Process Hollowing | Suspended process, image replacement, thread-context repair |
| 18 | Hell's Gate | Dynamic syscall resolution and anti-hooking checks |
| 19 | Reflective DLL Injection | Manual PE mapping, relocations, imports, DllMain |
| 20 | Remote PE Execution | Remote mapping, relocations, Native API writes |
| 21 | Ghost Process Hollowing | Sectionless native process creation, remote allocation and thread creation |
| 22 | Advanced Evasion Loader | Custom S-box/XOR cipher, C++ dispatch, PEB walk and anti-debug checks |
| 23 | Synthetic Ransomware Worm | File rewriting, TEST-NET port scanning, service creation and anti-analysis (bonus) |

</details>

### Tools

The current protocol exposes nine static-analysis tools plus `final_answer`, with a budget of 25 tool attempts per episode. Rejected calls and the final submission consume budget; the harness also limits an attempt to 64 model turns.

| Tool | Output |
|------|--------|
| `file` | File type |
| `strings` | Printable strings (configurable minimum length, UTF-16LE for PE) |
| `readelf` | ELF headers, sections, symbols, program headers |
| `objdump` | Disassembly, symbol tables, section contents |
| `nm` | Symbol list |
| `hexdump` / `xxd` | Hex and ASCII dumps at a given offset |
| `entropy` | Shannon entropy per sliding window |
| `pe_info` | PE headers, sections, imports, exports, data directories |
| `final_answer` | Structured submission. Ends the episode. |

Agents work in isolated workspaces without source code. The harness never executes the target binary. Model settings are included in the result download.

### Scoring

The current Windows scorer compares structured claims with rubric v3.4. PE technique and anti-analysis fields use fact-level F1, `2 × matched / (2 × matched + unsupported + missing)`, with exact aliases and bounded semantic rules. Generic findings do not imply specific APIs. Mixed claims retain their unsupported parts. Unknown wording requires review.

Encryption algorithms and key bytes are scored separately for every required component. Correct key bytes paired with an incomplete or incorrect algorithm can receive reduced or zero key credit. Explicit decoded bytes must match exactly. Applicable field weights are renormalized; nonanswers retain zero. [The scoring contract](docs/scoring.md) explains the fields, penalties, and interpretation limits.

| PE field | Base weight |
| --- | ---: |
| Techniques | 0.25 |
| Injection details | 0.20 |
| Decoded C2, encryption key, decoded strings, anti-analysis | 0.10 each |
| Encryption algorithm, C2 protocol | 0.05 each |
| File type | 0.03 |
| Encoded strings | 0.02 |

```text
Artifact score = mean(all five planned attempts)
Main           = mean(18 artifact scores, Levels 14–22)
Bonus          = mean(2 artifact scores, Level 23)
Overall        = 0.9 × Main + 0.1 × Bonus
Website/table  = Overall × 100
```

The reported scores use rubric v3.4 and scorer `6.2.0+exact-claim-review-20261105`, including post-hoc review of claim wording. The [full report](docs/results-current.md) documents those decisions and their effect on scores.

### Telemetry

The evaluation records structured answers, outcomes, field scores, tool activity, timing, and token usage. The public [episode records](docs/results/v3-1/reviewed-episodes.json) contain scores, answer hashes, outcomes, and field breakdowns for all 600 attempts. Raw answers and complete provider logs are not included in that download.

## Reproduce the public tables and graphics

```bash
python3 -m pip install -r scripts/requirements-site.txt
python3 scripts/build_site_results.py
python3 scripts/build_github_results.py
```

These commands rebuild the website, README table, and SVG graphics from the published scores.

<details><summary><strong>Legacy runner setup and CLI reference</strong></summary>

The commands below use the repository's earlier runner and scorer. The current report also depends on the claim review described in the [methodology](docs/results-current.md).

## Quick start

Provider environment variables can be placed in `.env`, exported in the shell, or supplied with `--api-key`.

| Provider | Environment variable |
|----------|----------------------|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Moonshot / Kimi | `MOONSHOT_API_KEY` |
| GLM | `GLM_API_KEY` |

```bash
git clone https://github.com/agentrebench/AgentRE-Bench.git && cd AgentRE-Bench
cp .env.example .env            # add at least one provider key
python run_benchmark.py --task level1_TCPServer --provider anthropic -v
```

## Setup

Prerequisites: Python 3.10 or later, and Docker for the sandboxed tools (required on macOS). Local builds need gcc and binutils on Linux x86-64, and MinGW-w64 (`x86_64-w64-mingw32-gcc`) for PE.

```bash
# 1. Build the sandboxed tool image
docker build --platform linux/amd64 -t agentre-bench-tools:latest -f Dockerfile.tools .

# 2. Optional development builds only; use a separate checkout.
# Rebuilding replaces artifact bytes and invalidates the frozen hashes.
./build_binaries.sh                      # Linux ELF, levels 1-13
./version3/build_windows_binaries.sh     # Windows PE, levels 14-23, unstripped + stripped

# 3. Run
python run_benchmark.py --all                                        # Linux suite
python run_benchmark.py --all --manifest version3/tasks_v3.json \
  --max-tool-calls 25 --max-tokens 16000 \
  --provider openai --model gpt-5.6-sol --reasoning-effort xhigh     # V3 PE suite
python run_benchmark.py --all --report results/opus_run1/            # custom output dir
```

Agents do not receive or compile source code during evaluation. On Apple Silicon the build scripts cross-compile through Docker with `--platform linux/amd64`.

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--all` | | Run every task in the selected manifest |
| `--task ID` | | Run one task by ID |
| `--manifest PATH` | `tasks.json` | Linux manifest, or `version3/tasks_v3.json` for PE |
| `--provider` | `anthropic` | `anthropic`, `openai`, `gemini`, `deepseek`, `moonshot` |
| `--model` | per-provider | Model name |
| `--api-key` | from `.env` | API key override |
| `--report DIR` | `results/` | Output directory |
| `--max-tool-calls` | `25` | Tool-call budget per task |
| `--max-tokens` | `4096` | Maximum tokens per LLM response |
| `--reasoning-effort` | provider default | OpenAI-compatible reasoning effort |
| `--resume` | | Keep terminal episodes, rescore stored answers, retry provider errors |
| `--no-docker` | | Run tools as a local subprocess |
| `-v` | | Print agent reasoning and tool I/O as they happen |

### Output

```text
results/
  agent_outputs/          Raw agent JSON answers, one per task
  transcripts/            Per-task scoring, metrics, full message logs
  benchmark_report.json   Aggregate report with all metrics and scores
```

### Standalone scorer

```bash
python scorer.py -g ground_truths/level1_TCPServer.json -a agent_outputs/level1_TCPServer.json
python scorer.py -G ground_truths/ -A agent_outputs/ -r report.json      # batch
```

## Architecture

```text
run_benchmark.py            CLI entry point
harness/
  config.py                 Configuration (dataclass, .env loading)
  runner.py                 Orchestrator: load tasks → run agent → score → report
  agent.py                  Provider-agnostic tool-calling loop
  tools.py                  Tool schemas + ToolExecutor dispatch
  sandbox.py                PathValidator + DockerRunner / SubprocessRunner
  metrics.py                TaskMetrics + AggregateMetrics
  providers/                anthropic · openai · gemini · deepseek · moonshot (raw HTTP, no SDKs)
scorer.py                   Deterministic scorer (standalone + used by harness)
tasks.json                  Linux ELF manifest (13 entries)
version3/                   Self-contained PE manifest, sources, binaries, results, build script, verify.py
build_binaries.sh           Linux build script
Dockerfile.tools            Sandboxed tool-execution image
```

The harness has no Python dependencies. Every provider call uses the standard library module `urllib.request`.

</details>

## Limits and next steps

- Static analysis only. There is no debugger, emulator, or sandboxed execution.
- Fixed tool set. The agent cannot use Ghidra or IDA, write scripts, or install tools.
- Synthetic samples. The binaries have controlled behaviors. They do not have the full complexity of packed production malware.
- Five attempts per artifact measure variability on a fixed suite of ten programs. The binaries are public and may appear in model training data.
- x86-64 only. The suite covers ELF and PE32+. It does not cover ARM or MIPS.
- Reasoning settings, token budgets, clients, and collection dates differ between models. The report lists each configuration.
- Scores measure agreement with the rubric. A correct observation outside the rubric can lose credit, so unmatched claims are not a direct measure of hallucination.
- Some binaries contain file and service operations or incomplete payload paths. Static analysis does not establish how they would behave when executed.

Planned work:

- Dynamic-analysis tools: strace, ltrace, and sandboxed execution.
- Packed and cross-architecture samples: ARM, MIPS, and realistic packers.
- Multi-turn hypothesis refinement.
- Held-out tasks, human grading checks, and runs with matched resource budgets.

## Links

| | |
|--|--|
| [Current Windows PE results](docs/results-current.md) | Six models, five attempts per artifact, 600 attempts |
| [August V3 report](version3/ANALYSIS.md) | One attempt per artifact with the earlier scorer |
| [V2 Linux ELF report](version2/ANALYSIS.md) | Frontier reasoning-model run on levels 1 to 13 |
| [Why AgentRE matters](version3/WHY_AGENTRE_MATTERS.md) | The defensive-security case for measuring RE capability |
| [agentre-bench.ai](https://agentre-bench.ai) | Website: results, history, blog |
| [AgentRE Challenge](https://agentre-bench.ai/challenge/) | Season 1. Submit your own binary challenge. |
| [Private evals](https://agentre-bench.ai/private-evals/) · [RL data](https://agentre-bench.ai/rl-data/) | Held-out evaluation and training data |

## Citation

```bibtex
@misc{agentrebench2026,
  title        = {AgentRE-Bench: Measuring Long-Horizon Reverse Engineering in LLM Agents},
  author       = {agentrebench},
  year         = {2026},
  howpublished = {\url{https://github.com/agentrebench/AgentRE-Bench}},
  note         = {v3.1 Windows PE report, updated November 5, 2026; six models, 600 episodes; rubric v3.4; scorer 6.2.0+exact-claim-review-20261105}
}
```

## License

[MIT](LICENSE) © 2026 agentrebench
