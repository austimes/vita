---
name: llm-lint-eval-evolution
description: >-
  Calibrate llm-lint by converting undesirable or missing findings into benchmark
  eval cases and prompt updates. Use when llm-lint flags something you disagree
  with, misses an expected issue, or shows unstable extras across
  model/reasoning candidates and you need to update eval fixtures plus
  versioned prompts.
---

# LLM Lint Eval Evolution (Skill)

Use this skill to turn one-off llm-lint disagreements into durable benchmark
coverage and prompt improvements.

Primary workflow:
- [`references/calibration-loop.md`](references/calibration-loop.md)

Execution contract:
1. Track work in `bd` and keep the calibration thread linked with `discovered-from` deps when follow-ups are found.
2. Reproduce with eval artifacts first; do not patch prompts from a single anecdotal run.
3. Keep benchmark labels tied only to intentionally seeded signals; treat all other detections as `additional`.
4. Keep prompt versions append-only (`vN`); never edit historical prompt directories in place.
5. Re-run eval (`smoke` first, then `ci`) and verify quality, label match, extras, latency, and cost before closing.
