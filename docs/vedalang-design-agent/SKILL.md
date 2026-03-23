---
name: vedalang-dev
description: >-
  Design-agent skill for iterative VedaLang primitive exploration, schema-gap
  detection, and structured handoff records. Internal/dev only — not for model
  authors or end users.
---

# VedaLang Design Agent (Skill — Internal)

**Audience:** VedaLang language designers and compiler developers only.
This skill is NOT bootstrapped by `vita init` and should not be referenced
from public-facing skills or starter templates.

For authoring models using VedaLang, see `skills/vedalang/SKILL.md` instead.

## Purpose

Guide an AI agent to iteratively extend VedaLang by exploring energy system
primitives, validating against the xl2times oracle, and proposing minimal
schema changes when existing constructs are insufficient.

## Primary References

| Document | Purpose |
|----------|---------|
| [`exploration-protocol.md`](exploration-protocol.md) | Step-by-step primitive exploration loop |
| [`schema_evolution.md`](schema_evolution.md) | Rules for evolving the VedaLang schema |
| [`canonical_form.md`](canonical_form.md) | Canonical table form and semantics |
| [`known_answer_tests.md`](known_answer_tests.md) | Solver-backed known-answer harness |

## Design Iteration Loop

```
1. Prototype at TableIR level
2. Emit Excel via vedalang-dev emit-excel
3. Validate with xl2times
4. If valid → lift pattern to VedaLang syntax
5. If invalid → fix and retry
```

## Execution Contract

1. Explore one primitive at a time.
2. Prefer minimal examples and existing schema/patterns first.
3. Validate with `vedalang validate ... --agent-mode --json`.
4. Record structured handoff outcomes before moving to next primitive.
5. Propose schema changes only after repeated, evidence-backed failures.

## Agent Rules

- Always pass `--agent-mode` to `vedalang` and `vita`.
- Add `--json` whenever the command supports structured output and you intend
  to parse it.
