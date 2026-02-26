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
# Full validation (lint + compile + xl2times)
uv run vedalang validate your_model.veda.yaml

# Validate only selected case(s)
uv run vedalang validate your_model.veda.yaml --case baseline
uv run vedalang validate your_model.veda.yaml --case baseline --case policy

# Compile only selected case(s)
uv run vedalang compile your_model.veda.yaml --out out/ --case policy

# Lint only (fast, checks heuristics)
uv run vedalang lint your_model.veda.yaml
```

## What This Documentation Does NOT Cover

- How to extend or modify VedaLang itself
- Compiler internals and schema evolution
- Design workflows and experimentation

For those topics, see `docs/vedalang-design-agent/`.
