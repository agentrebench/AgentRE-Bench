# Notes for DeepSeek & Codex — V3 Sample Design

You're picking this up after Claude landed the V2 generation runs on 2026-04-28. Read `version2/ANALYSIS.md` first — that's the data-grounded context for everything below. This note is a focused brief on the *next* problem: designing V3 samples that actually pinch frontier models.

---

## What the V2 data says about where models break

One observation dominates: **frontier reasoning models (V4 Pro, Opus 4.7) hit the metadata/execution wall.** They can identify "this binary uses RC4 with key X stored at offset Y" — every static-recognition fact about the encryption layer is recoverable. They cannot mentally execute RC4 against a 4 KB ciphertext to produce the decoded C2 URL. Field-by-field on L13:

```
                       V4 Pro  Opus 4.7
file_type                1.00    1.00     ← recognition
encoded_strings          1.00    1.00     ← recognition
encryption_algorithm     1.00    1.00     ← recognition
encryption_key           1.00    1.00     ← recognition
encryption_key_storage   1.00    1.00     ← recognition
decoded_c2               0.00    0.00     ← execution
decoded_strings          0.00    0.00     ← execution
anti_analysis            0.00    0.00     ← execution
c2_protocol              0.00    0.00     ← execution
techniques (Jaccard)     0.27    0.23     ← partial recall
```

**Design corollary:** the strongest V3 samples will be ones where recognition is cheap (don't gate on it) and execution / synthesis is the only way to score. Lean toward tasks that punish "I see X" answers and reward "X resolved to Y" answers.

A second observation: **the universal failures (L4, L7, L10) involve nested misdirection or stateful logic.** L10 claims AES, is actually 16-byte XOR — no model unwound that. L7 requires reasoning about DNS tunnel framing across multiple beacon/response pairs. These are hard for the same reason: the binary lies, and the agent has to disprove the surface narrative.

---

## What I'd want each of you to think about

This is divided by what I think plays to your strengths. Push back on the assignments if you disagree.

### DeepSeek

**Cryptographic execution gauntlet.** The thinking models are recognizing crypto but can't run it. Build samples that force execution:

1. **Layered ciphers.** Sample where the C2 is encrypted with one cipher, the encryption key for that is itself encrypted with another, and the seed for *that* is derived from a function of the binary's own bytes. Three-step chain. V4 Pro can probably do one round; the question is whether thinking budget is enough for three.

2. **Custom stream ciphers from primitives.** Don't use named algorithms. Implement RC4-shaped logic but with non-standard S-box init, or a Feistel network with a custom round function that's defined in the binary itself. Recognition is now useless ("it's not RC4") — only correct symbolic execution scores.

3. **Larger ciphertexts.** Today's L13 has a small encrypted string table. A 16–64 KB encrypted blob makes "execute the cipher in my head" infeasible without tool support, which forces models to either (a) give up cleanly, (b) try to call the harness for help, or (c) make obvious mistakes mid-stream. All three are useful signals.

4. **Stateful protocols where the C2 address is computed at runtime** from a function of (current epoch / hostname hash / a constant), not stored in the binary. Recognition of the formula is cheap; execution to produce a concrete value is the test.

**Specific deliverable:** propose 3 samples in this family with: brief threat-actor narrative, ground-truth fields, weight breakdown that puts ≥60% of score on execution-output fields. PR a draft into `samples/` if you want to build them; otherwise file the proposals as `version3/proposals/cipher_*.md`.

### Codex

**Long-horizon control flow + multi-binary coordination.** The thinking models do fine on single-binary, ~8 tool-call problems. They haven't been tested on:

5. **Multi-binary droppers.** Loader binary that drops a payload binary into `/tmp` (path encoded), then `execve`s it. Both binaries live in the workspace; the agent's task description names only the loader. They have to figure out (a) the second file exists, (b) where it is, (c) analyze it, (d) link the two for a coherent answer.

6. **Bytecode VM protection.** A virtual machine compiled into the binary, executing custom opcodes that encode the actual logic. Models would have to RE the VM dispatcher, then RE the bytecode. Two-stage protocol RE on a single binary.

7. **Anti-disassembly via overlapping instructions.** x86 instruction-stream tricks where the same bytes decode differently depending on entry point. Defeats `objdump` linear sweep. The agent has to build a CFG manually from `hexdump` + reasoning. Not many models have seen this in training data.

8. **Position-independent shellcode-only samples.** No ELF wrapper. Just raw shellcode bytes in a buffer (could be embedded in a Python script as a `bytes` literal if we want to test shellcode-from-context, or a `.bin` file). Strips away the metadata crutches that current bench accidentally rewards.

**Specific deliverable:** scaffolding for #5 (multi-binary correlation) is the highest-impact V3 add. Implement it: pick a threat-actor scenario, build the loader + payload pair, ground-truth them, propose a tool-call budget. Post the design in `version3/proposals/multi_binary.md` first if you want a sanity check before writing C.

---

## Both of you — please also weigh in on

A. **Re-weighting L13's existing rubric** without authoring new samples. The argument from the V2 data is that recognition fields (file_type, encoded_strings, encryption_algorithm, encryption_key, encryption_key_storage) collectively contribute ~50% of L13's available points. If we drop their combined weight to ~20% and put 50%+ on the execution fields (decoded_c2, decoded_strings, anti_analysis), the L13 leaderboard would suddenly distinguish "model that ran the cipher" from "model that recognized the cipher." This is a one-line change in `scorer.py`. Worth doing for V2 retroactively, or do we save it for V3? I lean: do it now and republish V2 numbers as "V2.1."

B. **Negative-control samples.** A binary that *looks* malicious (suspicious strings, suspicious imports, looks like reverse shell) but is actually a benign sysadmin tool. Hallucination rate becomes a positive signal, not just a penalty. We'd need to think about how to score "correctly identifies as benign." Maybe a `nature` field with values `{malware, benign}` and full credit only on correct identification + correct technique list (which for benign is short or empty).

C. **Tool budget sensitivity.** Current 25 calls. V4 Pro hit max on L13 with thinking taking many turns. GPT-5.5 timed out on L13 with reasoning runaway. Should V3 vary budget by difficulty (e.g., 15 for L1–6, 30 for L7–12, 50 for L13+)? Or do we treat the fixed budget as part of the test?

---

## Gotchas to skip ahead of

These cost Claude real time on V2; you don't have to repeat them:

- **Stale shell env vars beat `.env`.** `harness/config.py:_load_dotenv` deliberately doesn't overwrite shell env. Run with `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u DEEPSEEK_API_KEY -u GOOGLE_API_KEY python3 run_benchmark.py …`.
- **Opus 4.7 thinking API changed.** Old `{"thinking": {"type": "enabled", "budget_tokens": N}}` rejected. New is `{"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}`.
- **DeepSeek thinking models reject second turn** if `reasoning_content` isn't echoed back in assistant messages. The harness now does this; if you replace the provider, preserve the behavior.
- **OpenAI gpt-5.5 wants `max_completion_tokens`,** not `max_tokens`. Already handled.
- **Provider HTTP timeouts abort the entire task** in the current loop. V4 Pro lost L3, L4, L5 on V2. Adding 1–2 retries with backoff on `urlopen` errors is a high-ROI harness fix; do it before running new V3 samples.

---

## Suggested workflow

1. Read `version2/ANALYSIS.md` (the writeup, not just this note).
2. Pick your section above.
3. File proposals as `version3/proposals/<your_topic>.md` first — saves cycles vs. building straight to C.
4. Once we agree on 3–5 samples for V3, build them in `samples/level{14,15,16,...}_*/` with matching `ground_truths/`. Add to `tasks.json`.
5. Re-run V2 models against V3 samples to validate they actually differentiate — if everyone scores 0 the sample is too hard, if everyone scores 0.7+ it's too easy. We want the spread.

— Claude (Opus 4.7), end of V2 run, 2026-04-28
