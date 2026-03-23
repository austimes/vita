---
name: vedalang
description: >-
  Operational skill for authoring VedaLang models and running the CLI pipeline
  (lint/compile/validate). Use when writing, editing, or validating .veda.yaml
  files.
---

# VedaLang (Skill)

This is the canonical agent skill for day-to-day VedaLang authoring and
pipeline operation.

## Read Order

1. [`references/dsl-cli-pipeline.md`](references/dsl-cli-pipeline.md) — CLI
   commands, source priority, and reliability rules
2. [`references/modeling-conventions.md`](references/modeling-conventions.md) —
   conventions for commodities, technologies, roles, stock placement, and naming

## Quick Start

```bash
vedalang fmt <model>.veda.yaml --agent-mode
vedalang lint <model>.veda.yaml --agent-mode --json
vedalang validate <model>.veda.yaml --run <run_id> --agent-mode --json
vedalang compile <model>.veda.yaml --run <run_id> --out <dir> --agent-mode --json
```

## Command Inventory

| Command    | Purpose                                              |
|------------|------------------------------------------------------|
| `fmt`      | Normalize YAML formatting                            |
| `lint`     | Fast structural / heuristic checks                   |
| `llm-lint` | Advisory LLM-powered lint by category                |
| `compile`  | Compile VedaLang to Excel                            |
| `validate` | Compile and validate with xl2times                   |
| `res`      | Query RES graph views (agent-first JSON API)         |
| `viz`      | Visualize the Reference Energy System                |

## CLI Boundary

- Use `vedalang` for author/lint/compile/validate actions on `.veda.yaml`.
- Use `vita` for run execution, solver outputs, experiment diffs, and result
  narratives — see the `vita` skill.

## Hard Rules

- Always pass `--agent-mode` to `vedalang` and `vita`.
- Add `--json` whenever the command supports structured output and you intend
  to parse the result.
- Treat schema as authoritative for valid syntax.
- Use canonical modeling conventions from
  `references/modeling-conventions.md`.
- When in doubt, trust `vedalang validate` diagnostics over assumptions.

## Public Object Families

The current public schema surface:

`imports`, `commodities`, `technologies`, `technology_roles`,
`stock_characterizations`, `spatial_layers`, `spatial_measure_sets`,
`temporal_index_series`, `policies`, `region_partitions`, `zone_overlays`,
`sites`, `facilities`, `fleets`, `zone_opportunities`, `networks`, `runs`

## Scope

This skill covers **using** VedaLang to author and validate models.
It does not cover changing the schema, compiler, or language design — for that,
see `docs/vedalang-design-agent/SKILL.md` (internal/dev only).
