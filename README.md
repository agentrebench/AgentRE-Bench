# AgentRE-Bench

A benchmark for evaluating LLM agents on **long-horizon reverse engineering tasks** with deterministic scoring.

> **Platforms:** Linux/Unix (ELF x86-64) and Windows (PE32+ x86-64).

AgentRE-Bench gives an LLM agent a compiled binary and a platform-appropriate static-analysis toolset, then measures how well it can identify C2 infrastructure, encoding schemes, anti-analysis techniques, process-injection behavior, and communication protocols — all without human guidance or source code.

The [V3 Windows PE results](version3/ANALYSIS.md) evaluate 10 binaries twice—once unstripped and once stripped—across six frontier models. Raw answers, transcripts, reports, and reproduction metadata are preserved under [`version3/`](version3/).

## Why This Benchmark?

### Why Synthetic?

All 23 levels are compiled from purpose-built C/C++ sources with known ground truths. This gives us:

- **Deterministic judging** — every field has an exact expected answer, no ambiguity
- **Controlled difficulty progression** — from plaintext TCP shells to PE injection, direct syscalls, advanced evasion, and a synthetic ransomware worm
- **Reproducibility** — anyone can compile identical binaries and verify scores

Real malware would require subjective expert judgment and introduce licensing, ethics, and reproducibility issues. Synthetic samples eliminate all of that while testing the same analytical capabilities.

### Why Agentic?

Traditional RE benchmarks ask a model a question and check the answer. AgentRE-Bench requires the agent to:

- **Plan** which tools to use and in what order
- **Interpret** raw tool output (hex dumps, disassembly, symbol tables)
- **Synthesize** findings across multiple tool calls into a structured analysis
- **Manage a budget** of 25 tool calls — wasting calls on redundant queries means running out before finding the answer

This tests reasoning, tool selection, and information synthesis — not just pattern matching.

### Why Long-Horizon?

Simple RE questions ("What architecture is this binary?") don't differentiate models. The hard problems require chains of 10-25 tool calls where each call's output informs the next decision. Level 13 requires the agent to:

1. Identify encrypted strings via entropy analysis
2. Locate the encryption key in the binary
3. Determine the key storage mechanism (XOR mask)
4. Decode the actual C2 URL
5. Identify 18 distinct techniques across anti-debugging, process injection, and network evasion

This is where agent capability differences become visible.

### Why Deterministic Judging?

Every agent answer is scored against a fixed ground truth with weighted fields and Jaccard overlap for set comparisons. There is no LLM-as-judge, no subjective rubric, no human grader variance. The same answer always produces the same score.

Hallucinations are penalized: claiming a technique not present in the binary costs -0.05 per false claim. This means models can't game scores by guessing everything.

## Linux Task Difficulty Progression

| Level | Task | Techniques | Difficulty |
|-------|------|-----------|------------|
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

Levels 1-12 are **standard tasks** (averaged to 1.0 pt max). Level 13 is a **bonus task** with a deeper rubric (1.0 pt max). **Total possible: 2.0 points.**

## Windows PE V3 Task Ladder

| Level | Task | Core behavior |
|-------|------|---------------|
| 14 | DLL Injection | Manual API resolution, PEB anti-debug, CreateRemoteThread |
| 15 | APC Injection | RC4 payload, NtQueueApcThread, Native API calls |
| 16 | Code Cave Injection | PE section scanning, anti-VM, code-cave execution |
| 17 | Process Hollowing | Suspended process, image replacement, thread-context repair |
| 18 | Hell’s Gate | Dynamic syscall resolution and anti-hooking checks |
| 19 | Reflective DLL Injection | Manual PE mapping, relocations, imports, DllMain |
| 20 | Remote PE Execution | Remote mapping, relocations, Native API writes |
| 21 | Ghost Process Hollowing | Empty process creation and manual image mapping |
| 22 | Advanced Evasion Loader | AES-256, TLS callbacks, PEB walk, multi-stage implant |
| 23 | Synthetic Ransomware Worm | File encryption, propagation, persistence, anti-analysis (bonus) |

Every V3 level is evaluated as an anonymized **unstripped/stripped pair**. Main is the mean over the 18 Level 14-22 artifacts; Bonus is the mean over the two Level 23 artifacts; Total is Main + Bonus (2.0 maximum).

## Scoring Model

### Standard Levels (1-12)

Each task is scored across 5 weighted fields:

| Field | Weight | Scoring |
|-------|--------|---------|
| `decoded_c2` | 0.40 | Exact match = 1.0, host-only match = 0.5 |
| `techniques` | 0.30 | Jaccard overlap between predicted and ground truth sets |
| `file_type` | 0.10 | Exact match (case-insensitive) |
| `encoded_strings` | 0.10 | Exact match (boolean) |
| `c2_protocol` | 0.10 | Exact match (case-insensitive) |

**Hallucination penalty**: -0.05 per technique claimed but not in ground truth.

### Bonus Level (13)

10 weighted fields including encryption algorithm, key, key storage mechanism, decoded strings, and anti-analysis techniques. Lighter hallucination penalty (-0.03) given the larger technique set.

### Aggregate Scoring

```
Main Score  = average(level_1_score, ..., level_12_score)    # 0.0 - 1.0
Bonus Score = level_13_score                                  # 0.0 - 1.0
Total Score = Main Score + Bonus Score                        # 0.0 - 2.0
```

## Benchmark Metrics

Beyond correctness, AgentRE-Bench records research-grade metrics for every task:

**Per-Task Metrics:**

| Metric | Description |
|--------|-------------|
| `score` | Final weighted score after hallucination penalty |
| `field_scores` | Per-field breakdown (decoded_c2, techniques, etc.) |
| `tool_calls_total` | Number of tool calls used |
| `tool_calls_by_type` | Distribution across tool types |
| `redundant_tool_calls` | Identical tool calls repeated (same name + args) |
| `invalid_tool_calls` | Tool calls that returned errors |
| `invalid_json_attempts` | Times the agent responded with text instead of a tool call |
| `hallucinated_techniques` | Techniques claimed but not in ground truth |
| `missing_techniques` | Ground truth techniques the agent failed to identify |
| `steps_to_answer` | Tool calls before submitting final answer |
| `max_steps_hit` | Whether the agent exhausted its 25-call budget |
| `wall_time_seconds` | End-to-end wall clock time |
| `input_tokens` / `output_tokens` | Token consumption |

**Aggregate Metrics:**

| Metric | Description |
|--------|-------------|
| `success_rate` | Fraction of tasks with a valid submitted answer |
| `avg_tool_calls_per_task` | Mean tool calls across all tasks |
| `avg_tool_calls_per_success` | Mean tool calls for tasks that got an answer |
| `avg_hallucination_rate` | Mean hallucinated technique count per task |
| `episode_length_*` | Wall time distribution (min/max/mean/median) |
| `tool_usage_distribution` | Which tools models prefer across all tasks |
| `max_steps_hit_count` | How often agents exhaust their budget |

These metrics enable **failure taxonomy** — categorizing failures into:
- Byte-level reasoning failure
- Control-flow misinterpretation
- API hallucination
- Tool misuse
- Early termination
- JSON format violation

## Architecture

```
run_benchmark.py              CLI entry point
  |
  v
harness/
  config.py                   Configuration (dataclass, .env loading)
  runner.py                   Orchestrator (load tasks, run agent, score, report)
  agent.py                    Provider-agnostic agent loop (tool calling)
  tools.py                    Tool schemas + ToolExecutor dispatch
  sandbox.py                  PathValidator + DockerRunner / SubprocessRunner
  metrics.py                  TaskMetrics + AggregateMetrics collection
  providers/
    base.py                   Abstract AgentProvider + ProviderResponse
    anthropic.py              Claude (raw HTTP to Messages API)
    openai_provider.py        GPT (raw HTTP to Chat Completions API)
    gemini.py                 Gemini (raw HTTP to GenerativeAI API)
    deepseek.py               DeepSeek (extends OpenAI-compatible provider)
    moonshot.py               Kimi (OpenAI-compatible provider)

scorer.py                     Deterministic scorer (standalone + used by harness)
tasks.json                    Linux ELF manifest (13 entries)
version3/                     Self-contained PE manifest, sources, binaries, results, and build script
build_binaries.sh             Linux build script
Dockerfile.tools              Sandboxed tool execution image
```

**Zero Python dependencies.** All LLM provider calls use Python's built-in `urllib.request`. No SDKs required.

### Tool Sandbox

All tools execute inside Docker containers with strict isolation:

```
docker run --rm --platform linux/amd64 \
  --network=none --read-only --memory=512m --cpus=1 \
  -v binaries:/workspace:ro \
  agentre-bench-tools:latest <command>
```

- `--network=none` — no network access
- `--read-only` — immutable filesystem
- `--memory=512m` — memory cap
- Workspace mounted read-only

### Available Tools

| Tool | Description |
|------|-------------|
| `file` | File type identification |
| `strings` | Extract printable strings (configurable min length) |
| `readelf` | ELF headers, sections, symbols, program headers |
| `objdump` | Disassembly, symbol tables, section contents |
| `nm` | Symbol listing |
| `hexdump` | Hex + ASCII dump at specific offsets |
| `xxd` | Hex dump (alternative format) |
| `entropy` | Shannon entropy per sliding window (detects encrypted/compressed data) |
| `pe_info` | PE headers, sections, imports, exports, and data directories |

Plus `final_answer` — a structured submission tool the agent calls when done.

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
python run_benchmark.py --task level1_TCPServer --provider anthropic -v
```

## Setup

### Prerequisites

- Python 3.10+
- **Linux x86-64**: gcc, binutils, file, xxd, python3 (for local builds and `--no-docker` mode)
- **Windows PE builds**: MinGW-w64 (`x86_64-w64-mingw32-gcc` / `g++`)
- **macOS**: Docker (for cross-compilation and sandboxed tool execution)

### 1. Clone and Configure

```bash
git clone https://github.com/agentrebench/AgentRE-Bench.git
cd AgentRE-Bench

# Create .env with your API key(s)
cp .env.example .env
# Edit .env — add at least one provider key
```

### 2. Build Binaries (optional)

```bash
chmod +x build_binaries.sh version3/build_windows_binaries.sh
./build_binaries.sh
./version3/build_windows_binaries.sh
```

The benchmark accepts precompiled artifacts; agents never receive or compile source code during evaluation. On **Linux x86-64**, the ELF build uses local gcc. The PE build uses MinGW-w64 and produces both `version3/binaries/windows/` and `version3/binaries/windows_stripped/`.

On **macOS / Apple Silicon**: uses Docker with `--platform linux/amd64` to cross-compile.

### 3. Build Tools Image

```bash
docker build --platform linux/amd64 -t agentre-bench-tools:latest -f Dockerfile.tools .
```

### 4. Run

```bash
# Single task with verbose output
python run_benchmark.py --task level1_TCPServer -v

# Full benchmark
python run_benchmark.py --all

# V3 Windows PE suite (10 unstripped + 10 stripped artifacts)
python run_benchmark.py --all --manifest version3/tasks_v3.json \
  --max-tool-calls 25 --max-tokens 16000 \
  --provider openai --model gpt-5.6-sol --reasoning-effort xhigh

# Different providers
python run_benchmark.py --all --provider anthropic --model claude-opus-4-6
python run_benchmark.py --all --provider openai --model gpt-4o
python run_benchmark.py --all --provider gemini --model gemini-2.0-flash
python run_benchmark.py --all --provider deepseek --model deepseek-chat

# Custom output directory
python run_benchmark.py --all --report results/opus_run1/
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--all` | | Run every task in the selected manifest |
| `--task ID` | | Run a single task by ID |
| `--manifest PATH` | `tasks.json` | Select the Linux or V3 PE task manifest |
| `--provider` | `anthropic` | `anthropic`, `openai`, `gemini`, `deepseek`, `moonshot` |
| `--model` | per-provider | Model name |
| `--api-key` | from .env | API key override |
| `--report DIR` | `results/` | Output directory |
| `--max-tool-calls` | `25` | Tool call budget per task |
| `--max-tokens` | `4096` | Max tokens per LLM response |
| `--reasoning-effort` | provider default | OpenAI-compatible reasoning effort |
| `--resume` | | Preserve terminal episodes, rescore stored answers, and retry provider errors |
| `--no-docker` | | Run tools via local subprocess |
| `-v` | | Verbose: show agent reasoning + tool I/O live |

## Output

```
results/
  agent_outputs/              Raw agent JSON answers (one per task)
  transcripts/                Per-task scoring, metrics, and full message logs
  benchmark_report.json       Aggregate report with all metrics and scores
```

## Standalone Scorer

The scorer works independently of the agent harness:

```bash
# Single sample
python scorer.py -g ground_truths/level1_TCPServer.json \
                 -a agent_outputs/level1_TCPServer.json

# Batch
python scorer.py -G ground_truths/ -A agent_outputs/ -r report.json
```

## Known Limitations

- **Static analysis only** — no dynamic execution, debugging, or sandboxed runtime. Tests static RE reasoning specifically.
- **Synthetic samples** — designed to test real RE skills, but production malware has additional complexity (packers, anti-VM, polymorphism at scale) not fully represented.
- **Fixed tool set** — agents can't install tools, write scripts, or use Ghidra/IDA. Standardizes evaluation but limits agent creativity.
- **Single-agent** — no multi-agent collaboration or human-in-the-loop.
- **Single trial per model/task** — paired stripped/unstripped results reveal useful patterns but do not estimate run-to-run variance.
- **Architecture scope** — current public binaries are x86-64 ELF and PE32+; ARM and MIPS are not yet covered.
- **Token cost** — frontier runs can consume millions of provider-reported tokens. Budget accordingly.

## Roadmap

- **Dynamic analysis tools** — strace, ltrace, sandboxed execution
- **Packed and cross-architecture samples** — ARM, MIPS, and realistic packers
- **Multi-turn refinement** — tasks requiring iterative hypothesis refinement
- **Repeated trials** — confidence intervals for model and stripping effects

## License

MIT
