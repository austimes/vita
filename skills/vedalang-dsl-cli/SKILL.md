---
name: vedalang-dsl-cli
description: >-
  Operational skill for authoring VedaLang models and running the CLI pipeline
  (lint/compile/validate). Use this instead of LLMS.md.
---

# VedaLang DSL + CLI (Skill)

This is the canonical agent skill for day-to-day VedaLang authoring and
pipeline operation.

Read first:
- [`references/dsl-cli-pipeline.md`](references/dsl-cli-pipeline.md)

Then execute with this order:
1. Author/edit model YAML (`.veda.yaml`)
2. Format: `uv run vedalang fmt <model>.veda.yaml`
3. Lint quickly: `uv run vedalang lint <model>.veda.yaml`
4. Full validation: `uv run vedalang validate <model>.veda.yaml --run <run_id>`
5. If needed, compile only: `uv run vedalang compile <model>.veda.yaml --run <run_id> --out <dir>`

Hard rules:
- Treat schema as authoritative for valid syntax.
- Use canonical modeling conventions from
  `skills/vedalang-modeling-conventions/references/modeling-conventions.md`.
- When in doubt, trust `vedalang validate` diagnostics over assumptions.
- Prefer the v0.2 object families: `commodities`, `technologies`,
  `technology_roles`, `sites`, `facilities`, `fleets`, `opportunities`,
  `networks`, and `runs`.
