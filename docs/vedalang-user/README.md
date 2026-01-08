# VedaLang User Documentation

This documentation is for AI agents and humans who **use VedaLang** to author energy system models.

## What is VedaLang?

VedaLang is a typed DSL that compiles to VEDA Excel tables. You write `.veda.yaml` files, and the compiler generates the Excel files that xl2times processes into TIMES models.

```
VedaLang Source (.veda.yaml)  →  VEDA Excel (.xlsx)  →  TIMES DD files
```

## Quick Start

1. Read [LLMS.md](LLMS.md) — the comprehensive LLM guide for authoring VedaLang
2. Study the examples in `vedalang/examples/`
3. Check the schema at `vedalang/schema/vedalang.schema.json`
4. Use patterns from `rules/patterns.yaml`

## Key Resources

| Resource | Description |
|----------|-------------|
| [LLMS.md](LLMS.md) | LLM guide for authoring VedaLang models |
| [attribute_mapping.md](attribute_mapping.md) | VedaLang → VEDA/TIMES attribute mapping |
| [heuristics.md](heuristics.md) | Heuristic checks that catch modeling mistakes |
| `vedalang/schema/vedalang.schema.json` | Formal language schema |
| `vedalang/examples/` | Example `.veda.yaml` models |
| `rules/patterns.yaml` | Pattern "standard library" |

## Validation

Always validate your models:

```bash
# Full validation (lint + compile + xl2times)
uv run vedalang validate your_model.veda.yaml

# Lint only (fast, checks heuristics)
uv run vedalang lint your_model.veda.yaml
```

## What This Documentation Does NOT Cover

- How to extend or modify VedaLang itself
- Compiler internals and schema evolution
- Design workflows and experimentation

For those topics, see `docs/vedalang-design-agent/`.
