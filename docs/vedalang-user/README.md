# VedaLang User Documentation

This documentation is for AI agents and humans who **use VedaLang** to author energy system models.

## What is VedaLang?

VedaLang is a typed DSL that compiles to VEDA Excel tables. You write `.veda.yaml` files, and the compiler generates the Excel files that xl2times processes into TIMES models.

```
VedaLang Source (.veda.yaml)  →  VEDA Excel (.xlsx)  →  TIMES DD files
```

## Quick Start

1. Read [`skills/vedalang-dsl-cli/SKILL.md`](../../skills/vedalang-dsl-cli/SKILL.md) — canonical DSL + CLI operational skill
2. Study the examples in `vedalang/examples/`
3. Check the schema at `vedalang/schema/vedalang.schema.json`
4. Use patterns from `rules/patterns.yaml`

## Key Resources

| Resource | Description |
|----------|-------------|
| [tutorial.md](tutorial.md) | Your first VedaLang model |
| [`skills/vedalang-dsl-cli/SKILL.md`](../../skills/vedalang-dsl-cli/SKILL.md) | LLM skill for authoring + CLI pipeline |
| [attribute_mapping.md](attribute_mapping.md) | VedaLang → VEDA/TIMES mapping + explicit supported unit strings and capacity/activity rules |
| [heuristics.md](heuristics.md) | Heuristic checks that catch modeling mistakes |
| `vedalang/schema/vedalang.schema.json` | Formal language schema |
| `vedalang/examples/` | Example `.veda.yaml` models |
| `rules/patterns.yaml` | Pattern "standard library" |

For structural modeling conventions guidance, see
`skills/vedalang-modeling-conventions/SKILL.md`.

For the full LLM-facing docs ownership map (what each doc is for), see
`docs/LLM_DOCS.md`.

## Validation

Always validate your models:

```bash
# Formatting only (blank lines/indent/layout)
uv run vedalang fmt your_model.veda.yaml

# Non-mutating formatting gate
uv run vedalang fmt --check your_model.veda.yaml

# Full validation (lint + compile + xl2times)
uv run vedalang validate your_model.veda.yaml

# Validate only selected case(s)
uv run vedalang validate your_model.veda.yaml --case baseline
uv run vedalang validate your_model.veda.yaml --case baseline --case policy

# Compile only selected case(s)
uv run vedalang compile your_model.veda.yaml --out out/ --case policy

# Lint all deterministic categories
uv run vedalang lint your_model.veda.yaml

# Deterministic lint categories (repeat --category as needed)
uv run vedalang lint your_model.veda.yaml --category feasibility
uv run vedalang lint your_model.veda.yaml --category core --category identity

# LLM lint (advisory checks; critical findings fail by default)
uv run vedalang llm-lint your_model.veda.yaml --category structure
uv run vedalang llm-lint your_model.veda.yaml --category units

# LLM lint runtime controls
uv run vedalang llm-lint your_model.veda.yaml --category structure --model gpt-5-nano --reasoning-effort low --prompt-version v1
uv run vedalang llm-lint your_model.veda.yaml --category units --model gpt-5-mini --model gpt-5-nano --reasoning-effort low --request-timeout-sec 180

# Eval harness (model/effort leaderboard)
uv run vedalang-dev eval catalog
uv run vedalang-dev eval run --profile ci --prompt-version all
uv run vedalang-dev eval compare tmp/evals/run_a.json tmp/evals/run_b.json
uv run vedalang-dev eval report tmp/evals/run_b.json
```

Command responsibilities:

- `fmt`: formatting only (style/layout)
- `lint`: semantic/modeling checks
- `compile`: VedaLang to Excel/TableIR emission
- `validate`: full pipeline validation through xl2times

## Lint Taxonomy

VedaLang linting uses one shared category taxonomy across deterministic and LLM
engines:

- `core` — parse/schema/cross-reference integrity
- `identity` — naming/ID convention checks
- `structure` — RES architecture and stage/role/variant consistency
- `units` — units, basis, coefficients, and denominator plausibility
- `emissions` — emission namespace/type/factor checks
- `feasibility` — pre-solve heuristic risk checks

Deterministic `lint` behavior:

- default runs all deterministic categories
- use `--category` to narrow to specific categories

Use `uv run vedalang lint --list-categories` and
`uv run vedalang lint --list-checks` to inspect available coverage.

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
