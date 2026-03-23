# VedaLang User Documentation

This documentation is for AI agents and humans who **use VedaLang** to author energy system models.

## What is VedaLang?

VedaLang is a typed DSL that compiles to VEDA Excel tables. You write `.veda.yaml` files, and the compiler generates the Excel files that xl2times processes into TIMES models.

```
VedaLang Source (.veda.yaml)  →  VEDA Excel (.xlsx)  →  TIMES DD files
```

## Quick Start

```bash
# Install the latest CLI tools from GitHub
uv tool install git+https://github.com/austimes/vita

# Start a workspace with a runnable starter model
vita init my-experiment
cd my-experiment

# Validate or run the starter model
vedalang validate models/example.veda.yaml --run demo_2025
vita run models/example.veda.yaml --run demo_2025 --no-solver --json
```

Refresh the installed `vita` and `vedalang` commands later with `vita update`.
It only reinstalls when GitHub `main` is newer than your current tool version.

Read [`skills/vedalang/SKILL.md`](../../skills/vedalang/SKILL.md), study `vedalang/examples/`, check `vedalang/schema/vedalang.schema.json`, and use patterns from `rules/patterns.yaml` when you want the full repository content locally.

## Key Resources

| Resource | Description |
|----------|-------------|
| [tutorial.md](tutorial.md) | Your first VedaLang model |
| [`skills/vedalang/SKILL.md`](../../skills/vedalang/SKILL.md) | LLM skill for authoring + CLI pipeline |
| [attribute_mapping.md](attribute_mapping.md) | VedaLang → VEDA/TIMES mapping + explicit supported unit strings and capacity/activity rules |
| [known_answer_catalog.md](known_answer_catalog.md) | Solver-backed known-answer suite catalog with KA-by-KA status and solved-output mappings |
| [heuristics.md](heuristics.md) | Heuristic checks that catch modeling mistakes |
| `vedalang/schema/vedalang.schema.json` | Formal language schema |
| `vedalang/examples/` | Example `.veda.yaml` models |
| `rules/patterns.yaml` | Pattern "standard library" |

For structural modeling conventions guidance, see
[`skills/vedalang/references/modeling-conventions.md`](../../skills/vedalang/references/modeling-conventions.md).

For the full LLM-facing docs ownership map (what each doc is for), see
`docs/LLM_DOCS.md`.

## Validation

Always validate your models:

```bash
# Formatting only (blank lines/indent/layout)
vedalang fmt your_model.veda.yaml

# Non-mutating formatting gate
vedalang fmt --check your_model.veda.yaml

# Full validation (lint + compile + xl2times)
vedalang validate your_model.veda.yaml --run your_run_id

# Compile only
vedalang compile your_model.veda.yaml --run your_run_id --out out/

# Execute/solve a run and write machine-readable artifacts
vita run your_model.veda.yaml --run your_run_id --json

# Compare two completed run artifacts
vita diff runs/<study>/baseline runs/<study>/variant --json

# Lint all deterministic categories
vedalang lint your_model.veda.yaml

# Deterministic lint categories (repeat --category as needed)
vedalang lint your_model.veda.yaml --category feasibility
vedalang lint your_model.veda.yaml --category core --category identity

# LLM lint (advisory checks; critical findings fail by default)
vedalang llm-lint your_model.veda.yaml --category structure
vedalang llm-lint your_model.veda.yaml --category units

# LLM lint runtime controls
vedalang llm-lint your_model.veda.yaml --category structure --model gpt-5-nano --reasoning-effort low --prompt-version v1
vedalang llm-lint your_model.veda.yaml --category units --model gpt-5-mini --model gpt-5-nano --reasoning-effort low --request-timeout-sec 180
```

`vedalang-dev eval ...` is design-agent R&D tooling and intentionally excluded
from user-authoring workflows.

Command responsibilities:

- `fmt`: formatting only (style/layout)
- `lint`: semantic/modeling checks
- `compile`: v0.3 run-scoped artifact, TableIR, and Excel emission
- `validate`: compile + xl2times validation for the selected run
- `vita run`: solver execution + run artifact generation for analysis
- `vita diff`: baseline-vs-variant delta comparison across run artifacts

For toy-sector examples (`vedalang/examples/toy_sectors/*.veda.yaml`), keep
`--no-sankey` on `vita run` unless Sankey support is explicitly confirmed.

## Lint Taxonomy

VedaLang linting uses one shared category taxonomy across deterministic and LLM
engines:

- `core` — parse/schema/cross-reference integrity
- `identity` — naming/ID convention checks
- `structure` — RES architecture and stage/role/technology consistency
- `units` — units, basis, coefficients, and denominator plausibility
- `emissions` — emission namespace/type/factor checks
- `feasibility` — pre-solve heuristic risk checks

Deterministic `lint` behavior:

- default runs all deterministic categories
- use `--category` to narrow to specific categories

Use `vedalang lint --list-categories` and
`vedalang lint --list-checks` to inspect available coverage.

LLM lint behavior:

- `llm-lint` uses the same categories
- currently implemented: `structure`, `units`
- currently unsupported (reported as skipped): `core`, `identity`, `emissions`, `feasibility`
- default exit behavior: critical findings return exit code `2`
- use `--advisory` to avoid critical findings causing exit code `2`
- default runtime target: `gpt-5-nano` at `low` reasoning effort
- runtime controls:
  - `--reasoning-effort none|low|medium|high|xhigh`
  - `--prompt-version <version|all>`
  - `--request-timeout-sec <seconds>`

## What This Documentation Does NOT Cover

- How to extend or modify VedaLang itself
- Compiler internals and schema evolution
- Design workflows and experimentation

For those topics, see `docs/vedalang-design-agent/`.
