---
name: vedalang-design-exploration
description: >-
  Design-agent skill for iterative VedaLang primitive exploration, schema-gap
  detection, and structured handoff records.
---

# VedaLang Design Exploration (Skill)

Use this skill when extending VedaLang capabilities through exploration
experiments.

Primary protocol:
- [`references/exploration-protocol.md`](references/exploration-protocol.md)

Execution contract:
1. Explore one primitive at a time.
2. Prefer minimal examples and existing schema/patterns first.
3. Validate with `uv run vedalang validate ... --agent-mode --json`.
4. Record structured handoff outcomes before moving to next primitive.
5. Propose schema changes only after repeated, evidence-backed failures.

Agent rule:
- Always pass `--agent-mode` to `vedalang` and `vita`.
- Add `--json` whenever the command supports structured output and you intend
  to parse it.

This skill is the canonical home of the exploration protocol. The legacy doc at
`docs/vedalang-design-agent/exploration_prompt.md` is a pointer shim.
