# AgentRE-Bench V2 — Frontier Reasoning-Model Run

**Run date:** 2026-04-28 / expanded 2026-04-29
**Scope:** All 13 tasks (12 standard + 1 bonus), 25 tool-call budget per task, Docker-sandboxed static analysis tools, default 4096 max output tokens (raised to 16000 for Anthropic adaptive thinking).

This document is the exhaustive writeup for the V2 generation of frontier-model results. It supersedes the V1 leaderboard (Claude Opus 4.6 / DeepSeek V3.2 / GPT-5.2). All raw `benchmark_report.json`, `agent_outputs/`, and `transcripts/` are preserved under `version2/results/`.

**2026-04-29 update.** Three additional models tested (Gemini 3.1 Flash Lite Preview, GLM 5.1, Kimi K2.6) plus an attempt at Gemini 3.1 Pro Preview that was rate-limited out before scoring. Headline finding flipped: a *small non-thinking* model (Gemini Flash Lite) is the new bench leader, beating every frontier reasoning model in the field on Main score by a wide margin. The story is no longer "thinking depth wins" — it's "hallucination calibration wins, and small fast models are better calibrated."

---

## 1. Headline

| Rank | Model                              | Total ↑ | Main (L1–12) | Bonus (L13) | Answered | Halluc/task ↓ |
|-----:|------------------------------------|--------:|-------------:|------------:|---------:|--------------:|
| 1    | **Gemini 3.1 Flash Lite (no thinking)** | **0.667** | **0.562** | 0.105     | 13 / 13  | **1.92**      |
| 2    | DeepSeek V4 Pro (thinking)         | 0.648   | 0.377        | **0.271**   | 10 / 13  | 2.69          |
| 3    | Claude Opus 4.7 (thinking)         | 0.512   | 0.367        | 0.145       | 13 / 13  | 5.62          |
| 4    | Kimi K2.6 (reasoning)              | 0.497   | 0.497        | 0.000       | 9 / 13   | **2.08**      |
| 5    | DeepSeek V4 Flash                  | 0.449   | 0.449        | 0.000       | 13 / 13  | 3.38          |
| 6    | GPT-5.5 (reasoning)                | 0.255   | 0.255        | 0.000       | 12 / 13  | 6.31          |
| —    | GLM 5.1 (reasoning) ‡              | DNF     | 0.622 *     | —           | 4 / 13 *  | 3.00 *        |
| —    | Gemini 3.1 Pro Preview (thinking) † | DNF     | —            | —           | —        | —             |

`*` GLM 5.1's "0.622 main" is the **average over only the 4 levels that completed** (L1 0.80 · L2 0.70 · L3 0.45 · L9 0.54), not a 12-task Main score. Not directly comparable to other models. **Not ranked** in the leaderboard.
`†` Gemini Pro Preview's 2M TPM tier was insufficient for the bench's per-task token consumption; could not complete a single task before exhausting retry budget.
`‡` GLM 5.1's bench run is **DNF** for two distinct reasons: (a) initial run hit Z.AI's "insufficient balance" 429s on L4 onward (resolved by topping up); (b) post-top-up retry runs hit repeated **z.ai API connection hangs** — TCP connection established to the z.ai HTTPS endpoint but no data flowing for 30+ minutes per call, with urllib's per-recv timeout failing to catch it because z.ai apparently dripped enough TLS keepalive bytes to reset the timer. After L1, L2, L3 (and a bonus L9 from a chunk run), nine remaining tasks could not be completed.

**Best single-task scores:** L1 Kimi 0.875 · L2 Kimi 0.83 · L3 Flash Lite 0.61 · L6 Flash Lite 0.71 · L7 Flash Lite 0.54 · L11 Flash Lite 0.80 · L12 Flash Lite 0.76 · L13 V4 Pro 0.27. Flash Lite holds bench-best on **8 of 13 levels** (sole or tied).

**Levels nobody solved well:** L4 Polymorphic (max 0.40, none with valid answer), L10 AES-Encrypted (max 0.40 from Kimi but no valid answer), L13 Metamorphic (max 0.27).

---

## 2. Methodology

### Models tested (and configurations)

| Provider   | Model                              | Reasoning mode                                   | Notes |
|------------|------------------------------------|--------------------------------------------------|-------|
| Anthropic  | `claude-opus-4-7`                  | `thinking: {type: adaptive}` + `output_config: {effort: high}` | New API shape — old `thinking.type=enabled` rejected by 4.7 |
| OpenAI     | `gpt-5.5`                          | reasoning is automatic (reasoning model); `max_completion_tokens` required, not `max_tokens` | |
| DeepSeek   | `deepseek-v4-pro`                  | thinking on by default; returns `reasoning_content` separate from `content` | Server requires the trace echoed back on every subsequent turn |
| DeepSeek   | `deepseek-chat` (resolves to `deepseek-v4-flash`) | non-thinking | Used as a non-reasoning baseline |
| Google     | `gemini-3.1-flash-lite-preview`    | non-thinking | Endpoint: `https://generativelanguage.googleapis.com/v1beta/models`; minor TPM caps still bite on hard mid-bench tasks |
| Google     | `gemini-3.1-pro-preview`           | adaptive thinking | DNF — 2M tokens/min paid-tier cap insufficient for the bench; lost L1 to retry-exhausted 429s |
| Z.AI       | `glm-5.1`                          | reasoning (thinking) | Endpoint: `https://api.z.ai/api/paas/v4`; OpenAI-compatible; very tight rate limits — completed only L1–L3 |
| Moonshot   | `kimi-k2.6`                        | reasoning (thinking) | Endpoint: `https://api.moonshot.ai/v1`; OpenAI-compatible; lost 4 tasks to mid-conversation HTTP 400 errors (likely context format issues) |

### What was instrumented

`benchmark_report.json` per run captures, per task and aggregate:

- `score`, `field_scores`, `tier`
- `tool_calls_total`, `tool_calls_by_type`, `redundant_tool_calls`, `invalid_tool_calls`, `invalid_json_attempts`
- `hallucinated_techniques`, `hallucination_count`, `missing_techniques`
- `wall_time_seconds`, **`llm_seconds`** (new — sum of provider call latency)
- `input_tokens`, `output_tokens`, **`reasoning_tokens`** (new — OpenAI/DeepSeek thinking models), `total_tokens`
- `has_valid_answer`, `max_steps_hit`

Aggregate adds `total_llm_seconds`, `avg_llm_seconds_per_task`, `total_reasoning_tokens`.

### Harness changes required to land these runs

Documented here so the next run is plug-and-play:

1. **`harness/providers/anthropic.py`** — Opus 4.7 rejects the old extended-thinking shape (`thinking.type=enabled` + `budget_tokens`). New shape is `thinking: {type: "adaptive"}` plus `output_config: {effort: "high"}`. Thinking content is server-side: response blocks of type `thinking` come back with empty `thinking` text and a `signature` field. The signed block must be echoed back verbatim on subsequent turns (alongside `text` / `tool_use` blocks) or the model loses context.
2. **`harness/providers/openai_provider.py`** — extracts `usage.completion_tokens_details.reasoning_tokens` and the optional `message.reasoning_content`. Default `_token_param` is `max_completion_tokens` (gpt-5.5 rejects `max_tokens`).
3. **`harness/providers/deepseek.py`** — DeepSeek thinking models return `message.reasoning_content`. **The API rejects subsequent turns (HTTP 400 "The `reasoning_content` in the thinking mode must be passed back to the API")** if the assistant's prior `reasoning_content` is dropped. This bit us hard on the first v4-pro run — every task error'd at the second turn until the harness was patched.
4. **`harness/providers/base.py`** — `ProviderResponse` adds `reasoning_tokens`, `reasoning_content`, `thinking_blocks`.
5. **`harness/agent.py`** — accumulates `llm_seconds` per call; assembles assistant message blocks in the order Anthropic requires (`thinking` → `text` → `tool_use`), and preserves DeepSeek `reasoning_content` as a `{"type":"reasoning"}` block re-emitted by the OpenAI-compatible provider's `_convert_message`.
6. **`harness/metrics.py`** — `TaskMetrics` and `AggregateMetrics` persist the new fields.

### Operational gotchas encountered

- **Stale shell env keys override `.env`.** The harness loader (`config._load_dotenv`) intentionally does not overwrite shell env vars (CLI > shell > .env). When a previous shell session left `ANTHROPIC_API_KEY` etc. exported, the harness sees the stale (invalid) key and 401s instantly with no tokens consumed. Workaround: run with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u DEEPSEEK_API_KEY -u GOOGLE_API_KEY python3 run_benchmark.py …`. This explains every "0 tokens / 0.1s wall time" report in the prior `results/`.
- **OpenAI per-minute TPM rate limits.** Running 4 models in parallel competing for the same OpenAI key burns the per-minute TPM budget after ~5 tasks. Run OpenAI serially or stagger.
- **OpenAI `insufficient_quota`** is account-level, not a temporary rate limit. A retry returns 429 immediately; the user has to top up the account.
- **Mid-run provider timeouts** (`urlopen error [Errno 60] Operation timed out`) abort the entire task in the current loop — no retry. V4 Pro lost L3, L4, L5 to this. Adding 1–2 retries with backoff on transient `urlopen` errors would meaningfully improve the answered-task count for thinking models on hard tasks.

---

## 3. Per-model deep dive

### 3.1 DeepSeek V4 Pro (thinking) — winner

```
total: 0.648  main: 0.377  bonus: 0.271  answered: 10/13  halluc/task: 2.69
total wall: 3,338s   total tokens: 10.25M   avg tools/task: 12.4
episode_length_max: 1,303.7s (L10)   episode_length_median: 142.7s
```

**Strengths.** Best calibration of any model — only **2.69** hallucinated techniques per task. The thinking trace clearly translates into more conservative claims; V4 Pro lists fewer techniques per answer and is less likely to invent ones the binary doesn't show. It is the only model that scored above zero on L13's bonus rubric (`0.27`), and it's the only model in the field with a non-trivial L4 Polymorphic score (0.40 — but it never submitted a final answer there; the score reflects partial credit from the scorer's defaults, see §3.1 caveat).

**Weaknesses.** Very expensive in wall time (3,338s — 2× any other model). L10 alone burned **22 minutes / 22 tool calls / 2.3M tokens** for a 0.05 score. Did not survive provider-side timeouts on L3, L4, L5; the loop hard-aborts on any `urlopen` error. The score on those three (0.0 / 0.4 / 0.0) is whatever default the scorer produces from an empty answer, not a real result.

**Caveat on `llm_seconds`.** This run started before the latency-instrumentation patch landed; only `wall_time_seconds` is available. The "256.8s avg LLM time/task" figure on the website is `total_wall_time / 13`, not measured per-call.

### 3.2 Claude Opus 4.7 (thinking) — most consistent

```
total: 0.512  main: 0.367  bonus: 0.145  answered: 13/13  halluc/task: 5.62
total wall: 1,433s   total LLM time: 1,413s (98.6% of wall)   total tokens: 7.67M   avg tools/task: 8.5
total_reasoning_tokens: 0 (Anthropic adaptive thinking returns signature only, no chain-of-thought text)
```

**Strengths.** Submitted a valid answer on every task. Highest score on L2 (0.75) and L8 (0.54). Lowest avg tool calls per task (8.5) — most economical when it does answer. `llm_seconds / wall_time` ratio of 98.6% means tool execution overhead is negligible; nearly all wall time is the model thinking + generating.

**Weaknesses.** Hallucinations rose vs. V4 Pro (5.6 vs 2.7/task). On L3 the model claimed 9 techniques but only 2 were correct. Adaptive-thinking-at-high-effort appears to over-analyze on simple binaries: L1 scored only 0.43 even though every other model in the field cleared 0.49+. Bonus level barely engaged (0.145).

**Surprising observation.** A non-thinking baseline run of `claude-opus-4-7` (no `thinking` config) scored **0.7138** total — *higher* than the thinking-enabled run's 0.512. Possible explanations:
- Single-trial variance on a 13-task benchmark with stochastic decoding;
- Adaptive thinking + high effort surfaces more "techniques" candidates, increasing the Jaccard-overlap denominator AND the hallucination penalty count;
- Without thinking, Opus 4.7 is more conservative about what it claims.

This deserves a multi-trial follow-up before concluding which mode is "better" — it's a one-shot data point, not a robust comparison.

### 3.3 DeepSeek V4 Flash — best non-thinking baseline

```
total: 0.449  main: 0.449  bonus: 0.000  answered: 13/13  halluc/task: 3.38
total wall: 636s   total tokens: 14.72M   avg tools/task: 15.1
```

**Strengths.** **Best Main score** (0.449 — beats both thinking models on standard levels). Highest single-task scores on L1 (0.72), L11 (0.71). Only 49s avg per task — 5× faster than V4 Pro for ⅔ the main score. Scored 0.69 on L5 Multistage where V4 Pro completely whiffed (0.00 due to timeout).

**Weaknesses.** No engagement with the bonus task — submitted `{}` on L13. The non-thinking model can't sustain the multi-step reasoning the bonus rubric requires. L4 Polymorphic (0.14) and L10 AES-Encrypted (0.10) also weak.

**Surprising observation.** **Non-thinking V4 Flash scores HIGHER on Main than thinking V4 Pro** (0.449 vs 0.377). The thinking model's Main suffers from the lost L3/L4/L5 tasks (provider timeouts) — if those held up, V4 Pro would likely lead Main as well. Re-running the failed tasks is the highest-value next action.

### 3.4 GPT-5.5 (reasoning) — last place

```
total: 0.255  main: 0.255  bonus: 0.000  answered: 12/13  halluc/task: 6.31
total wall: 1,971s   total LLM time: 1,947s   total tokens: 6.58M   avg tools/task: 10.5
total_reasoning_tokens: 96,564
```

**Strengths.** Reasoning tokens are exposed and measurable — 96.6K reasoning tokens total across 13 tasks, with **per-task reasoning ranging 256–72,493 tokens.** Most efficient on simple tasks (L1: 282 reasoning tokens, 13.3s).

**Weaknesses.** Highest hallucination rate (6.31/task — invents techniques on every task). Burned **22 minutes and 72,493 reasoning tokens** on L13 for a 0 (final answer was never submitted — L13 was the one task it failed to complete). Generally weakest scores on hard tasks (L8, L12). Highest token consumption per dollar of score gained.

**Failure mode of note.** L13 hits `max_tool_calls` after the model loops on partial decryption attempts. The reasoning trace appears to attempt RC4 decryption symbolically and gets lost; meanwhile the wall clock runs and the loop never converges to a `final_answer` call. This is a clear "reasoning runaway" pattern unique to GPT-5.5 in this run.

### 3.5 Gemini 3.1 Flash Lite Preview (no thinking) — bench leader

```
total: 0.667  main: 0.562  bonus: 0.105  answered: 13/13  halluc/task: 1.92
total wall: 525s   total LLM time: 487s (92.7% of wall)   total tokens: 30.5M   avg tools/task: 14.3
total_reasoning_tokens: 0  (no thinking trace exposed)
```

**Strengths.** **Bench-best on 8 of 13 levels** (sole or tied): L1 0.80 · L3 0.61 · L6 0.71 · L7 0.54 · L8 0.54 · L10 0.15 · L11 0.80 · L12 0.76. **Lowest hallucination rate of any model** (1.92/task — half of Opus 4.7's 5.62). Only model to crack L7 DNS Tunnel above 0.33. Beats V4 Flash's previous bench-best Main score (0.449 → **0.562**) by 25%. Fast — 525s wall total, 5–60s per task.

**Weaknesses.** L4 Polymorphic remains a flat 0.05 (every model fails). Bonus L13 only 0.105 — the metadata-vs-execution wall still applies to non-thinking models, just at a lower ceiling than thinking models reach. Token consumption is high (30.5M total — second only to Kimi) because there's no reasoning compaction; the model re-reads tool outputs in full each turn.

**Surprising observation — the central V2.5 finding.** Flash Lite is *categorically* a smaller model than every model below it on the leaderboard, and it has *no* thinking trace. Yet it leads. The hypothesis: hallucination calibration matters more on this bench than reasoning depth. Flash Lite makes confident, focused tool calls, returns short technique lists, and doesn't over-claim. Frontier reasoning models surface large candidate technique sets via thinking — and pay the –0.05/technique hallucination penalty for each one that's not in the ground truth. The bench rewards "look at the right things, don't claim what you didn't verify" over "explore the possibility space."

### 3.6 Kimi K2.6 (reasoning) — strongest L1/L2, fragile mid-bench

```
total: 0.497  main: 0.497  bonus: 0.000  answered: 9/13  halluc/task: 2.08
total wall: 12,004s (200 min)   total LLM time: 11,958s (99.6% of wall)   total tokens: 22.9M   avg tools/task: 15.9
total_reasoning_tokens: 0  (Moonshot doesn't expose them in usage even with thinking enabled)
```

**Strengths.** **Bench-best L1 (0.875) and L2 (0.83)** by a clear margin (V2 prior best on L2 was Opus 4.7 at 0.75). Second-best calibration in the field (2.08 halluc/task — only Flash Lite is lower). Strong on L11 (0.71) and L12 (0.64). Never claimed a technique it didn't have evidence for — even on tasks it failed to complete, the hallucination_count is 0.

**Weaknesses.** **Lost 4 tasks to mid-conversation HTTP 400 errors** (L4, L8, L10, L13). The 400s appear to fire after a 429 retry reconstruction — the assistant message format that round-trips through retry sometimes triggers a server-side validation failure. Worth investigating whether Moonshot is rejecting some specific block type ordering. Slowest model in the field — **920s avg LLM time per task**, 200-minute total run. L10 alone took **112 minutes** before the final 400 (but scored 0.40 on partial credit before the error).

**Surprising observation.** L10 AES-Encrypted: **Kimi scored 0.40, the bench-best** (next is Flash Lite at 0.15). Kimi's 24-call deep dive into the binary appears to have peeled enough of the AES-misdirection layer to recover real fields — even without submitting a valid final answer. Re-running L10 with retry logic that survives Moonshot 400s would likely yield a clean 0.40+ result with valid_answer=True.

### 3.7 GLM 5.1 (reasoning) — DNF after multiple retry attempts

```
4/13 valid attempts (L1, L2, L3, L9). Aggregate over those 4: 0.622 average.
NOT ranked in the leaderboard — sample size too small and not directly comparable.

Per-level (valid attempts only):
  L1  TCP Reverse Shell        0.800   1 hallucination
  L2  XOR Encoded              0.700   2
  L3  Anti-Debug               0.446   6
  L9  SO Injection             0.540   3
```

**What happened.** Two distinct failure modes hit this run:

1. **Insufficient balance (resolved):** Initial run on 2026-04-28 ran L1–L3 cleanly, then on L4 the z.ai account ran out of pre-paid balance. The API returned HTTP 429 with code `1113 - Insufficient balance` (which we initially mis-categorized as a rate limit because the HTTP status is the same). L4 cycled in retry cascades for 7.8 hours; L5–L13 returned pure 0.0 with 0 successful tool calls. The user topped up the account after the initial run finished.
2. **z.ai HTTPS connection hangs (unresolved):** Post-top-up re-run attempts (sequential and chunked-parallel) made some progress — L9 completed cleanly at 0.54 from a chunk run — but most tasks hit a different failure: the urllib HTTPS connection to `api.z.ai` would establish, the request would be sent, and **no response data flowed for 30+ minutes**. Python's `timeout=300` per-`recv()` setting did not catch this because z.ai apparently dripped enough TLS keepalive frames to keep resetting the read timer. We observed this on L4 (1+ hour hang) and L10 (56-minute hang) before manually killing each run.

**Where GLM did run.** L1 0.80 ties Flash Lite for bench-best on L1. L2 0.70 is mid-pack. L3 0.45 mid-pack. L9 0.54 mid-pack. Average over the 4 valid attempts is **0.622**, which is **competitive** but not directly comparable to other models' Main scores (which are averaged over all 12 standard levels including the difficult ones).

**Hallucination rate** of 3.0/task across 4 valid attempts is mid-pack; the small sample is not load-bearing.

**Recommendation.** A future run needs (a) a higher z.ai tier with sustainable rate budget, AND (b) a hard wall-clock timeout on urlopen via thread-wrapped or signal-based cutoff, since urllib's built-in timeout is per-recv only. **Until both are fixed, GLM 5.1's actual benchmark position is unknown.** The 4 datapoints we have suggest it would be in the middle of the pack — likely between V4 Flash and Kimi K2.6 — but we cannot confirm.

### 3.8 Gemini 3.1 Pro Preview — DNF, rate-limited before scoring

Did not complete a single task. Started before Flash Lite was tried, exhausted the 4-retry budget on L1 with HTTP 429s, then on L2 same outcome despite the inter-task sleep. The Gemini paid-tier 2M tokens/min cap is incompatible with this bench's per-task token consumption (each task can spike 1–2M tokens in 60s due to re-sent conversation history). Switching to Flash Lite (smaller model, less per-turn input compounding) avoided the wall entirely.

This is a useful negative result: it tells us that **even paid-tier API quotas can be a hard ceiling on running this bench**, independent of model capability. For comparable evaluation across providers, all keys need to be on tiers that can sustain ~5M tokens/min sustained for 30+ minutes. Anyone reproducing the bench needs to budget for this.

---

## 4. Per-level analysis

Bold = bench best. Bench best is sole-best unless followed by `(=)` for ties.

| L  | Task                | Flash Lite | V4 Pro | Opus 4.7 | Kimi K2.6 | V4 Flash | GPT-5.5 | GLM 5.1 |
|---:|---------------------|----------:|-------:|---------:|----------:|---------:|--------:|--------:|
| 1  | TCP Reverse Shell   | 0.80(=) | 0.66   | 0.43     | **0.88**  | 0.72     | 0.49    | 0.80(=) |
| 2  | XOR Encoded         | 0.59     | 0.65   | 0.75     | **0.83**  | 0.30     | 0.58    | 0.70    |
| 3  | Anti-Debug          | **0.61**  | (fail) | 0.27     | 0.53      | 0.58     | 0.32    | 0.45    |
| 4  | Polymorphic         | 0.05     | 0.40* | 0.00     | 0.40*     | 0.14     | 0.00    | (DNF)   |
| 5  | Multistage          | 0.70     | (fail) | 0.57     | 0.63      | **0.69**  | 0.32    | (DNF)   |
| 6  | ICMP Covert         | **0.71**  | 0.64   | 0.38     | 0.58      | 0.59     | 0.38    | (DNF)   |
| 7  | DNS Tunnel          | **0.54**  | 0.03   | 0.07     | 0.00      | 0.33     | 0.00    | (DNF)   |
| 8  | Process Hollow      | 0.54(=) | 0.38   | 0.54(=)| 0.00*     | 0.30     | 0.14    | (DNF)   |
| 9  | SO Injection        | 0.48     | 0.46   | 0.43     | 0.38      | 0.40     | 0.22    | 0.54    |
| 10 | AES Encrypted       | 0.15     | 0.05   | 0.00     | **0.40**\* | 0.10    | 0.00    | (DNF)   |
| 11 | Fork Bomb           | **0.80**  | 0.62   | 0.50     | 0.71      | 0.71     | 0.45    | (DNF)   |
| 12 | JIT Shellcode       | **0.76**  | 0.64   | 0.48     | 0.64      | 0.53     | 0.17    | (DNF)   |
| 13 | Metamorphic (bonus) | 0.11     | **0.27** | 0.15  | 0.00*     | 0.00     | 0.00    | (DNF)   |

`*` Score landed without a valid `final_answer` (provider-error abort or HTTP 400 mid-conversation); reflects scorer's partial-credit default, not model output.
`(DNF)` GLM did not complete this task — z.ai connection hangs (no data flowing for 30+ min) on retry attempts after balance top-up. Initial run had `Insufficient balance` 429s on L4–L13 before account recharge.

**Patterns:**
- **Flash Lite dominates the standard tasks.** Best on L3, L6, L7, L11, L12; tied-best on L1 and L8. The breadth is the surprise — it's not just one or two flukes.
- **Kimi K2.6 dominates the easiest two levels** (L1 0.88, L2 0.83) with significant margin. Suggests thinking helps when the answer is reachable in 5–10 calls but the agent has to be very precise about which fields to populate.
- **Thinking models are still essential for L13** — Flash Lite's bonus 0.11 is meaningfully below V4 Pro's 0.27. The bonus task gates on encryption-algorithm recognition, which Flash Lite without thinking doesn't sustain.
- **L4 Polymorphic remains the universal blind spot.** Best valid attempt is Flash Lite at 0.05. The 0.40 partial-credit zeros are scorer artifacts — no model produced a valid L4 answer.
- **L10 AES Encrypted now has Kimi at 0.40** (partial-credit, no valid answer) and Flash Lite at 0.15 (valid). Flash Lite's 0.15 is the highest *legitimate* L10 score in the bench. Kimi's 0.40 suggests a thinking model could plausibly hit 0.50+ if the harness survived its 400 errors.
- **L7 DNS Tunnel** went from "everyone gets ~0" to "Flash Lite 0.54." Stateful protocol reasoning is now within reach of small fast models.

---

## 5. The metadata-vs-execution wall (the L13 finding)

This is the most important qualitative observation in this run.

L13's bonus rubric scores 10 fields. Both thinking models (V4 Pro and Opus 4.7) produced **identical perfect scores on the metadata fields**:

| Field                     | V4 Pro | Opus 4.7 | Flash Lite | V4 Flash | GPT-5.5 | Kimi |
|---------------------------|-------:|---------:|-----------:|---------:|--------:|-----:|
| `file_type`               | 1.00   | 1.00     | 1.00       | 0.00     | 0.00    | 0.00 |
| `encoded_strings`         | 1.00   | 1.00     | 1.00       | 0.00     | 0.00    | 0.00 |
| `encryption_algorithm`    | 1.00   | 1.00     | 0.00       | 0.00     | 0.00    | 0.00 |
| `encryption_key`          | 1.00   | 1.00     | 0.00       | 0.00     | 0.00    | 0.00 |
| `encryption_key_storage`  | 1.00   | 1.00     | 0.00       | 0.00     | 0.00    | 0.00 |
| **`decoded_c2`**          | **0.00** | **0.00** | **0.00** | 0.00     | 0.00    | 0.00 |
| **`decoded_strings`**     | **0.00** | **0.00** | **0.00** | 0.00     | 0.00    | 0.00 |
| **`anti_analysis`**       | **0.00** | **0.00** | **0.00** | 0.00     | 0.00    | 0.00 |
| **`c2_protocol`**         | **0.00** | **0.00** | **0.00** | 0.00     | 0.00    | 0.00 |
| `techniques` (Jaccard)    | 0.27   | 0.23     | 0.16       | 0.00     | 0.00    | 0.00 |

**The pattern.** Frontier reasoning models can identify *the existence of* RC4, locate the key bytes in the binary, and explain the key-storage scheme — every static-analysis fact about the encryption layer is recoverable. **What they cannot do** is run RC4 against a 4 KB ciphertext in their head to actually produce the decoded C2 URL or the plaintext string table. The execution step — symbolic interpretation of a stream cipher across thousands of bytes — is the wall.

**Flash Lite cracks the recognition layer without thinking** — it gets `file_type` and `encoded_strings` right at 1.0 each, but doesn't reach the encryption-algorithm-recognition layer (no thinking budget). It then makes a respectable Jaccard-overlap stab at the techniques set. Net: 0.105 on the bonus task — meaningfully below the thinking models but well above the non-thinking baselines. This refines the V2 finding: the bonus task has a *recognition* tier and an *execution* tier, with the recognition tier accessible via deep static-analysis reasoning (which Flash Lite can do without thinking) and the execution tier blocked by symbolic-execution incapability across all models.

**The flat-zero models (V4 Flash, GPT-5.5, Kimi)** never submitted a valid L13 answer — `agent_outputs/level13_*.json` is `{}` or empty for all three. V4 Flash's non-thinking nature aborted before constructing a full bonus-rubric answer; GPT-5.5 burned its tool-call budget loop-thrashing on partial decryption attempts; Kimi hit an HTTP 400 on the final turn before its answer would have been submitted (but partial credit still landed). All three failed for *different* reasons, which is itself a finding — the bonus task is the bench's most varied failure-mode generator.

**Why this matters for V3.** L13 currently leaks 50% of its weight to fields that don't actually require reverse engineering — they require recognition. A future bench should weight execution-output fields heavily and recognition fields lightly, so the score gradient lives where the models actually struggle.

---

## 6. Reasoning time

`llm_seconds` is the time the agent loop spent inside `provider.create_message(...)` (waiting for the model). It's the precise "thinking time" metric distinct from tool execution and harness overhead.

| Model           | Total LLM time | Avg / task | Wall time | LLM/Wall ratio |
|-----------------|---------------:|-----------:|----------:|---------------:|
| Opus 4.7        | 1,413s         | 108.7s     | 1,433s    | **98.6%**      |
| V4 Flash        | (proxy)        | (~49s)     | 636s      | n/a            |
| V4 Pro          | (proxy)        | (~257s)    | 3,338s    | n/a            |
| GPT-5.5         | 1,947s         | 149.8s     | 1,971s    | **98.8%**      |

V4 Pro and V4 Flash do not have measured `llm_seconds` because their runs began before the latency-instrumentation patch landed; the displayed numbers are `wall_time / 13`. Opus 4.7 and GPT-5.5 were re-run on the patched harness and have ground-truth measurements.

**Per-task tail-distribution observations** (mean is misleading on these workloads — single hard tasks dominate):

- Opus 4.7: episode_length_min 17.1s · median 57.9s · max 443.0s (L10) — long-tail driven by L10 + L13 + L8.
- V4 Pro: episode_length_min 18.1s · median 142.7s · max 1,303.7s (L10) — the median alone is more than the *total* run length of some other models.
- GPT-5.5: per-task LLM time scales with `reasoning_tokens` — L13 alone consumed 1,324s and 72,493 reasoning tokens (75% of the entire run's reasoning budget).

**Reasoning-token discipline.** GPT-5.5's L13 reasoning spend (72k tokens, 22 minutes, 0 score) is a textbook "reasoning runaway" — the model symbolic-execute itself out of the tool-call budget. V4 Pro on the same task: 24 tool calls in 309s for a 0.27. V4 Pro's thinking is more grounded in the tool-result trace; GPT-5.5's reasoning appears more autonomous and less anchored.

---

## 7. Hallucination patterns

Per-task averages (lower is better — every fabricated technique is a –0.05 penalty on standard, –0.03 on bonus):

```
GLM 5.1     0.69    ← only 3 valid attempts; sample too small to be load-bearing
Flash Lite  1.92    ← lowest in field with full 13-task coverage
Kimi K2.6   2.08    ← second-best calibration; only valid 9 tasks
V4 Pro      2.69    ← thinking + grounding
V4 Flash    3.38    ← non-thinking but careful
Opus 4.7    5.62    ← high-effort thinking surfaces too many candidates
GPT-5.5     6.31    ← worst: invents techniques on nearly every task
```

**The ordering by hallucination is nearly identical to the ordering by score.** This is the central finding of V2.5. Models that don't over-claim score better. The –0.05/technique penalty is the dominant lever, not raw thinking budget.

**Specific patterns observed:**

1. **Flash Lite's calibration is genuinely impressive.** 1.92 hallucinations/task across 13 successful attempts; on L11 it claimed 0 hallucinated techniques while scoring 0.80. This is what good RE looks like in real life — confident on what's verifiable, silent on what's not.
2. **Kimi K2.6 hallucinates even less *per attempted task*** (2.08), but answered only 9/13. The reasoning trace appears to make Kimi *very* conservative — when it doesn't have evidence, it returns shorter lists. The cost is occasional 400 errors that wipe out partial work.
3. **GPT-5.5 invents technique names that look plausible but aren't in the ground truth** (e.g., on L8: 10 hallucinated techniques in one task). The reasoning trace appears to brainstorm possibilities and surface them all.
4. **Opus 4.7 with thinking surfaces broader candidate lists.** On L3 it claimed 9 techniques, most rejected by scorer. Thinking-at-high-effort overshoots.
5. **V4 Pro is conservative — but pays for it on technique Jaccard.** When unsure it returns shorter technique lists, which keeps hallucinations low but caps `techniques` field score.

**Cost of hallucinations:**
- GPT-5.5's penalty across 13 tasks: ~6.3 × 13 × 0.05 = **4.10 point penalty**.
- Opus 4.7's penalty: **3.64 points**.
- V4 Flash penalty: **2.20 points**.
- Flash Lite penalty: **1.25 points**.

If you scored only on raw weighted score (no penalty), Opus 4.7 (raw 0.62 vs final 0.51) and GPT-5.5 (raw 0.46 vs final 0.26) would close some of the gap to Flash Lite — but Flash Lite's raw score is also higher than its final, so it would still lead. The ordering is robust to penalty intensity.

---

## 8. Failure-mode taxonomy observed in this run

| Mode                       | Models affected         | Example                             |
|----------------------------|-------------------------|-------------------------------------|
| Provider HTTP timeout      | V4 Pro                  | L3, L4, L5 — `urlopen [Errno 60]`   |
| Per-minute TPM cap saturated | Gemini Pro Preview, GLM 5.1 | DNF or 9+ pure-zero tasks |
| Mid-conversation HTTP 400  | Kimi K2.6               | L4, L8, L10, L13 — context format issue |
| Reasoning runaway          | GPT-5.5                 | L13 — 22 min, never submits answer  |
| Empty bonus submission     | V4 Flash, GPT-5.5, Kimi | L13 `agent_outputs` is `{}` or partial |
| Over-claiming techniques   | Opus 4.7, GPT-5.5       | hallucination rate 5.6+ / task    |
| Missed metadata layer      | Flash Lite, V4 Flash, GPT-5.5, Kimi | L13 encryption_algorithm = 0 |
| Decryption execution       | All seven               | L13 `decoded_c2` / `decoded_strings` = 0 universally |
| Nested misdirection        | All seven               | L10 (claims AES, is XOR) — max valid 0.15 |

The harness handles transient 4xx/5xx with retry-with-backoff (added 2026-04-29). Non-transient 400s and account-tier rate caps still abort cleanly. A V3 evaluation could distinguish "no answer" (loop aborted, never submitted) from "wrong answer" (submitted but failed scoring) — they're different failure stories.

---

## 9. What got better vs. V1

| Metric                    | V1 leader (Claude 4.6) | V2 leader (V4 Pro) | Δ |
|---------------------------|-----------------------:|--------------------:|---|
| Total score               | 0.487                  | **0.648**          | **+33%** |
| Bonus L13                 | 0.000                  | **0.271**          | first non-zero |
| Hallucinations / task     | 3.31 (Claude 4.6)      | **2.69**           | –19% |

L13 transitioning from "nobody scores" to "thinking models score" is the most important V1→V2 change. The metadata layer is now solvable by the field; only the execution layer still pinches.

**What didn't change:** L4, L7, L10 are still flat. Polymorphic shellcode generation, DNS tunneling logic, and inline-assembly XOR-disguised-as-AES are not yielding to thinking budgets.

---

## 10. Recommendations for AgentRE-Bench V3 (making it tougher)

Ordered roughly by ROI. Each is a lever you can pull without a full bench rewrite.

### A. Cheap (no new samples)

1. **Re-weight the bonus rubric so execution-output fields dominate.**
   Current L13 lets a model bank 50%+ of available points on metadata recognition (file_type, encoded_strings, encryption_algorithm, encryption_key, encryption_key_storage). Push those down to ~20% combined and put 50%+ on `decoded_c2` + `decoded_strings`. Models would have to actually *run* the decryption in their head — which is exactly the wall observed in §5. Even more importantly given the V2.5 finding: this would cleanly distinguish "small models that recognize" from "thinking models that execute," which is currently muddled.

2. **Tighten the hallucination penalty.**
   Standard penalty is –0.05 per fabricated technique. The V2.5 leaderboard is already largely a hallucination-calibration ranking (§7) — raising to –0.10 would amplify the existing signal and make the bench an even sharper test of "claim only what you can defend."

3. **Add a "no answer" tier in scoring.** Distinguish `submitted-and-failed` from `never-submitted`. Currently both are 0 — but they tell very different stories about the agent loop. Especially relevant after V2.5: Kimi's 4 NO_ANS tasks would be visually distinguished from real failures.

4. **Retry-with-backoff (LANDED 2026-04-29).** Now in `harness/agent.py`. Honors `Retry-After` header, parses Gemini's `retryDelay` field, exponential backoff fallback (30 / 60 / 120s), max 3 retries, only on 408/425/429/5xx + connection timeouts. Saved Gemini Flash Lite from losing tasks to L4/L5/L10 transient 429s.

5. **Inter-task pause (LANDED 2026-04-29).** `--inter-task-sleep N` flag in `run_benchmark.py`. Pauses N seconds between tasks to let provider rate-limit windows reset. Used 90s for Gemini; insufficient for Pro Preview tier, fine for Flash Lite.

6. **A `python_eval` sandbox tool (NEW V3 PROPOSAL).** Static-analysis humans use Python REPLs all the time. Add a tool that takes a Python script + bytes, executes in a sandboxed subprocess (no fs, no net, no subprocess), returns stdout. Removes the in-head-arithmetic ceiling on L13 RC4 execution while preserving the static-analysis frame ("don't run the malware itself"). Expected to split the L13 leaderboard between "recognized RC4" (current ceiling) and "recognized + ran RC4" (real gradient). See discussion in `NOTES_FOR_AGENTS.md`.

### B. Medium (new sample types, modest authoring)

5. **Multi-binary correlation.**
   Loader binary that drops + executes a payload binary. Both binaries are in `binaries/`; the agent must analyze both and link the loader's RC4 key to the payload's encrypted body. Tests cross-artifact reasoning — a capability current bench doesn't probe.

6. **Larger ciphertexts at higher difficulty.**
   Today's L13 has a small encrypted string table. A V3 sample with a 64 KB encrypted blob using a bespoke stream cipher would force a model to either (a) symbolically execute correctly, (b) recognize they need to ask the harness for a "decrypt this with key X" tool (a future tool), or (c) admit defeat. All three are useful signals.

7. **Negative-control samples.**
   A binary that *looks* like malware (suspicious strings, suspicious imports) but is actually benign. Hallucination rate then becomes a first-class scored metric — currently it's only a penalty, not a positive test.

8. **Network-protocol-only RE.**
   Drop a `.pcap` next to a binary; the agent must reverse-engineer the C2 protocol from the wire alongside the binary. New tool: `tcpdump-style` reader. Tests synthesis across artifacts.

### C. Heavy (new sample types, significant authoring)

9. **VM-protected control flow.**
   Bytecode-VM-style protection (think VMProtect-lite) where the actual logic is encoded as opcodes for a custom interpreter compiled into the binary. Models must reverse-engineer the VM, then the bytecode. No model in this run would touch it.

10. **Anti-disassembly via overlapping instructions.**
    x86 instruction-stream tricks where the same bytes decode differently depending on entry point. Defeats `objdump` linear sweep. Would force the agent to build a control-flow graph manually from `hexdump` + reasoning.

11. **Position-independent shellcode-only samples.**
    No ELF wrapper at all — just raw shellcode in a buffer. Forces the agent to identify entry semantics with no metadata crutches.

12. **Cross-platform: Windows PE / ARM.**
    Already in the V1 README roadmap. Worth pursuing — it doubles the bench's coverage and exposes any Linux-x86-64-specific blind spots in the models' training data.

13. **Dynamic-analysis tier (separate scoring).**
    Add `strace`, `ltrace`, sandboxed `chroot` execution as opt-in tools. Score correctness AND tool-selection wisdom — a model that runs `strace` to confirm a syscall pattern should score better than one that infers it (wrongly) from disassembly.

### Most-bang-for-buck single change

**Re-weight L13** (recommendation 1) — zero authoring, immediately reopens the leaderboard between models and exposes the execution wall as a scored quantity. Pair with recommendation 4 (retry on transient errors) and you'd have a much sharper V2 leaderboard from the same data.

---

## 11. Open questions / things to validate next session

1. **Multi-trial variance.** Every number here is single-trial. How much does V4 Pro's bonus 0.27 jitter across 5 trials? If σ > 0.1, single-run rankings are noise.
2. **Opus 4.7 with vs. without thinking.** The non-thinking 0.71 vs thinking 0.51 gap is large enough to investigate. Run both modes 3× each at the same seed-ish settings and compare.
3. **Thinking budget effort knob for Opus 4.7.** Try `effort: medium` and `effort: low`. If `medium` produces fewer hallucinations on simple tasks while keeping bonus engagement, it's the right default.
4. **V4 Pro's lost tasks.** Re-run L3/L4/L5 in isolation with retry-on-timeout. Likely +0.05–0.10 on Main.
5. **Reasoning-token accounting for Anthropic.** Current Anthropic provider estimates `reasoning_tokens` as `len(thinking_text) // 4`. Adaptive-thinking returns empty `thinking` text with only a signature, so this estimate is always 0 on Opus 4.7. To get actual thinking-token counts we'd need to inspect `usage.cache_*` deltas or a yet-undocumented field — neither verified.
6. **Did Flash actually outperform V4 Pro on Main?** If V4 Pro's lost tasks are recovered, Flash's Main lead disappears. The "non-thinking baseline beats thinking sibling on standard tasks" finding is fragile.

---

## 12. Reproducing this run

```bash
cd /Users/marqbritt/workspace/AgentRE-Bench

# .env must contain working keys for any provider you run
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u DEEPSEEK_API_KEY -u GOOGLE_API_KEY \
  -u GLM_API_KEY -u MOONSHOT_API_KEY \
  python3 run_benchmark.py --all --provider anthropic --model claude-opus-4-7

# OpenAI
env -u ... python3 run_benchmark.py --all --provider openai --model gpt-5.5

# DeepSeek (thinking + non-thinking)
env -u ... python3 run_benchmark.py --all --provider deepseek --model deepseek-v4-pro
env -u ... python3 run_benchmark.py --all --provider deepseek --model deepseek-chat

# Gemini Flash Lite (Pro Preview is rate-limited out on standard paid tier)
env -u ... python3 run_benchmark.py --all --provider gemini --model gemini-3.1-flash-lite-preview --inter-task-sleep 90

# Z.AI GLM (note: tight rate limits; needs higher tier or aggressive pacing)
env -u ... python3 run_benchmark.py --all --provider glm --model glm-5.1

# Moonshot Kimi
env -u ... python3 run_benchmark.py --all --provider moonshot --model kimi-k2.6
```

Sequential execution recommended for OpenAI and Gemini to avoid TPM rate limits. Anthropic + DeepSeek + GLM + Moonshot can run in parallel safely (different accounts).

**Approximate runtimes** (patched harness, post-2026-04-29 retry+pause additions):
- V4 Flash: ~11 min
- Flash Lite: ~9 min
- Opus 4.7: ~25 min
- V4 Pro: ~55 min
- GPT-5.5: ~33 min
- GLM 5.1 (DNF on tight tier): >8 hr (do not reproduce on this tier)
- Kimi K2.6: ~200 min
- Gemini Pro Preview: ~30 min if it runs at all (this account couldn't)

**~330 minutes total** to reproduce all viable runs sequentially. Parallel execution across providers brings this down to the slowest (Kimi at ~200 min).

## 13. Files in this snapshot

```
version2/
├── ANALYSIS.md                                  (this file — updated 2026-04-29)
├── NOTES_FOR_AGENTS.md                          (V3 sample-design brief for DeepSeek/Codex)
└── results/
    ├── anthropic_claude-opus-4-7/               ← Opus 4.7 thinking, 13/13
    ├── deepseek_deepseek-v4-pro/                ← V4 Pro thinking, 10/13
    ├── deepseek_deepseek-chat/                  ← V4 Flash, 13/13
    ├── openai_gpt-5.5/                          ← gpt-5.5 reasoning, 12/13
    ├── gemini_gemini-3.1-flash-lite-preview/    ← Flash Lite (bench leader), 13/13
    ├── gemini_gemini-3.1-pro-preview/           ← Pro Preview (DNF, rate-limited)
    ├── glm_glm-5.1/                             ← GLM 5.1 (DNF, rate-limited from L4)
    └── moonshot_kimi-k2.6/                      ← Kimi K2.6, 9/13

each results/<provider_model>/ contains:
    benchmark_report.json     ← aggregate + per-task metrics
    agent_outputs/            ← final answer JSON per task
    transcripts/              ← per-task scoring + full conversation
```

The original `results/` directory in the repo root continues to be the working area; this `version2/` is a frozen snapshot for the V2 generation analysis. The 2026-04-29 expansion added Flash Lite, Pro Preview (DNF), GLM (DNF), and Kimi to the original four-model set.
