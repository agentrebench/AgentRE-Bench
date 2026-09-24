<h1 align="center">AgentRE-Bench</h1>
<p align="center"><em>Reverse-engineering intelligence, measured.</em></p>

<p align="center">
<a href="https://github.com/agentrebench/AgentRE-Bench/stargazers"><img src="https://img.shields.io/github/stars/agentrebench/AgentRE-Bench?style=flat&color=6366f1" alt="Stars"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-00d4aa.svg" alt="MIT"></a>
<a href="https://agentre-bench.ai"><img src="https://img.shields.io/badge/site-agentre--bench.ai-6366f1.svg" alt="Website"></a>
<a href="version3/ANALYSIS.md"><img src="https://img.shields.io/badge/results-V3%20PE%20·%20Aug%202026-blue.svg" alt="V3 results"></a>
</p>

## Abstract

Use of AI agents in cybersecurity is growing. No widely adopted public benchmark measures whether these agents can reverse engineer compiled binaries. Existing evaluations test question answering or recall of vulnerability knowledge, or they use an LLM as the judge. AgentRE-Bench gives an agent an unfamiliar ELF or PE binary, a fixed static-analysis toolset, and a budget of 25 tool calls. A deterministic scorer compares the agent's structured findings to fixed ground truth. The benchmark has 23 levels: 13 Linux ELF x86-64 binaries and 10 Windows PE32+ binaries. Each PE level is evaluated as a stripped and unstripped pair. The levels cover reverse shells, covert channels, encryption, process injection, direct syscall resolution, reflective loading, and control-flow obfuscation. In the V3 Windows evaluation (August 2026), the best of six frontier models scored 1.3618 of 2.0. No model recovered the bonus-level C2 endpoint. Stripping reduced the mean score by 6.47% relative across 46 matched pairs.

## Why this benchmark exists

Most AI coding benchmarks start with readable code and a clear task. Security teams usually start with neither. They get a compiled program, no context, and one question: what does this program do?

AgentRE-Bench asks LLM agents that question. Each task is a purpose-built ELF or Windows PE binary compiled from known source. The agent receives the binary and a fixed set of static-analysis tools. It does not receive the source, a description, or a meaningful filename. The agent must choose which tools to run, read hex dumps and disassembly, follow references across tool calls, and submit a structured answer. A deterministic scorer compares the answer to ground truth.

The benchmark separates reverse engineering from pattern recognition. A model that knows the term "process hollowing" must still find the technique in 18 KB of stripped machine code.

## Results

The current generation is V3, Windows PE, run in August 2026. It contains ten programs, from DLL injection to a synthetic ransomware worm. Each program is evaluated unstripped and stripped. Six frontier models ran all 20 artifacts with a budget of 25 tool calls and 16,000 output tokens per artifact.

![AgentRE-Bench V3 leaderboard, Total = Main + Bonus](docs/leaderboard-v3.svg)

| Rank | Model | Main /1.0 | Bonus /1.0 | Total /2.0 | Valid answers |
|-----:|-------|----------:|-----------:|-----------:|--------------:|
| 1 | **Kimi K3** | **0.6757** | **0.6861** | **1.3618** | **20/20** |
| 2 | Claude Opus 5 | 0.6147 | 0.6638 | 1.2785 | 18/20 |
| 3 | GPT-5.6 Sol | 0.5859 | 0.6298 | 1.2157 | 18/20 |
| 4 | DeepSeek V4 Flash | 0.5125 | 0.6782 | 1.1906 | 19/20 |
| 5 | Gemini 3.6 Flash | 0.5400 | 0.5653 | 1.1052 | 20/20 |
| 6 | Claude Fable 5 | 0.0000 | 0.0000 | 0.0000 | 0/20 |

Main is the mean over the 18 Level 14 to 22 artifacts. Bonus is the mean over the two Level 23 artifacts. Total is Main plus Bonus. Refusals and budget exhaustion count as zero.

Findings from the run:

- File type and encoded-string presence were easy. Every model that answered scored near 1.0 on both fields. No model recovered the exact Native API chains, the keys, or the Level 23 endpoint (`192.0.2.100:8443`).
- Stripping reduced the mean score by 0.0416 points across 46 complete pairs. Stripped binaries kept their imports, constants, and code shape.
- GPT-5.6 Sol made zero unsupported technique claims and recorded the best single-artifact score (0.9272). DeepSeek V4 Flash claimed `manual_getprocaddress` ten times where the ground truth did not contain it.
- Claude Fable 5 refused all 20 artifacts before its first tool call and scored 0.0. This is a coverage result, not a capability estimate.

The full report is in [`version3/ANALYSIS.md`](version3/ANALYSIS.md). It contains per-artifact scores, stripped-versus-unstripped results by level, hallucination tables, and the audit that reproduced all 120 score rows. The Linux ELF generation is in [`version2/ANALYSIS.md`](version2/ANALYSIS.md).

## Adoption

![GitHub star history for agentrebench/AgentRE-Bench](docs/star-history.svg)

agentrebench created the repository on 12 February 2026. As of 24 September 2026 it has 119 stars and 14 forks.

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
| 16 | Code Cave Injection | PE section scanning, anti-VM, code-cave execution |
| 17 | Process Hollowing | Suspended process, image replacement, thread-context repair |
| 18 | Hell's Gate | Dynamic syscall resolution and anti-hooking checks |
| 19 | Reflective DLL Injection | Manual PE mapping, relocations, imports, DllMain |
| 20 | Remote PE Execution | Remote mapping, relocations, Native API writes |
| 21 | Ghost Process Hollowing | Empty process creation and manual image mapping |
| 22 | Advanced Evasion Loader | AES-256, TLS callbacks, PEB walk, multi-stage implant |
| 23 | Synthetic Ransomware Worm | File encryption, propagation, persistence, anti-analysis (bonus) |

</details>

### Tools

The agent has nine tools and a budget of 25 calls per episode.

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

All tools run inside Docker with `--network=none`, `--read-only`, and `--memory=512m`. The workspace is mounted read-only. The harness makes provider API calls outside the agent workspace.

### Scoring

The scorer compares each answer to ground truth field by field. Scalar fields use exact match. Technique sets use Jaccard overlap. Each technique that the agent claims but the binary does not contain costs 0.05 points, or 0.03 on bonus levels. A non-null claim for a null ground-truth field costs the same. No LLM judges the answer. The same answer always receives the same score.

<details><summary><strong>Field weights</strong></summary>

Linux standard levels (1 to 12):

| Field | Weight | Rule |
|-------|-------:|------|
| `decoded_c2` | 0.40 | Exact match = 1.0, host-only match = 0.5 |
| `techniques` | 0.30 | Jaccard overlap between predicted and ground-truth sets |
| `file_type` | 0.10 | Exact match, case-insensitive |
| `encoded_strings` | 0.10 | Exact match, boolean |
| `c2_protocol` | 0.10 | Exact match, case-insensitive |

Windows PE levels (14 to 22). Weights for fields absent from a ground truth are removed. The remaining weights are renormalized.

| PE field | Base weight |
|----------|------------:|
| Techniques | 0.25 |
| Injection details | 0.20 |
| Decoded C2 | 0.10 |
| Encryption key | 0.10 |
| Decoded strings | 0.10 |
| Anti-analysis | 0.10 |
| Encryption algorithm | 0.05 |
| C2 protocol | 0.05 |
| File type | 0.03 |
| Encoded strings | 0.02 |

Bonus levels (13 and 23) weight key recovery at 0.20. Decoded C2, techniques, and decoded strings are 0.15 each. Algorithm and anti-analysis are 0.10 each. Key storage and protocol are 0.05 each. File type is 0.03 and encoded strings is 0.02.

```text
Main  = mean(standard levels)   # Linux: L1-12 · PE: 18 Level 14-22 artifacts   → 0.0-1.0
Bonus = mean(bonus level)       # Linux: L13   · PE: 2 Level 23 artifacts        → 0.0-1.0
Total = Main + Bonus                                                            → 0.0-2.0
```

</details>

### Telemetry

Each episode records these fields in addition to the score: `field_scores`, `tool_calls_total`, `tool_calls_by_type`, `redundant_tool_calls`, `invalid_tool_calls`, `invalid_json_attempts`, `hallucinated_techniques`, `missing_techniques`, `steps_to_answer`, `max_steps_hit`, `wall_time_seconds`, `input_tokens`, and `output_tokens`. The aggregate report adds `success_rate`, `avg_tool_calls_per_task`, `avg_hallucination_rate`, `episode_length_*`, `tool_usage_distribution`, and `max_steps_hit_count`.

These fields support a failure taxonomy with six classes: byte-level reasoning failure, control-flow misinterpretation, API hallucination, tool misuse, early termination, and JSON format violation.

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

# 2. Optional: rebuild binaries from source. Precompiled artifacts are checked in.
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

## Limits and next steps

- Static analysis only. There is no debugger, emulator, or sandboxed execution.
- Fixed tool set. The agent cannot use Ghidra or IDA, write scripts, or install tools.
- Synthetic samples. The binaries have controlled behaviors. They do not have the full complexity of packed production malware.
- One trial per model and task. The paired stripped and unstripped results are descriptive. They do not estimate variance.
- x86-64 only. The suite covers ELF and PE32+. It does not cover ARM or MIPS.
- Token cost. A frontier run uses millions of provider-reported tokens.

Planned work:

- Dynamic-analysis tools: strace, ltrace, and sandboxed execution.
- Packed and cross-architecture samples: ARM, MIPS, and realistic packers.
- Multi-turn hypothesis refinement.
- Repeated trials with confidence intervals for model and stripping effects.

## Links

| | |
|--|--|
| [V3 Windows PE report](version3/ANALYSIS.md) | Leaderboard, matched stripped analysis, per-artifact scores, verification audit |
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
  note         = {V3 Windows PE results, August 2026}
}
```

## License

[MIT](LICENSE) © 2026 agentrebench
