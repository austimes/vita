# VedaLang Design Agent Documentation

This documentation is for the AI agent that **designs and evolves VedaLang** — the DSL, compiler, schemas, and tooling.

## Purpose

The VedaLang Design Agent iteratively improves VedaLang through:
- Schema extensions for new constructs
- Compiler improvements
- Pattern discovery through experimentation
- Validation against xl2times (the oracle)

## Primary Reference

The main instructions for the Design Agent are in the repository root: **`AGENTS.md`**

This directory contains supporting documentation:

## Documentation Index

| Document | Purpose |
|----------|---------|
| [`skills/vedalang-design-exploration/SKILL.md`](../../skills/vedalang-design-exploration/SKILL.md) | Canonical exploration protocol skill |
| [exploration_prompt.md](exploration_prompt.md) | Compatibility pointer to the exploration skill |
| [schema_evolution.md](schema_evolution.md) | Rules for evolving the VedaLang schema |
| [canonical_form.md](canonical_form.md) | Canonical table form and semantics |
| [pcg_investigation.md](pcg_investigation.md) | PCG research notes |

### Subdirectories

- `design/` — Internal design documents (e.g., `veda-table-schemas.md`)
- `issues/` — Design epics and task specifications

## Key Workflows

### Design Iteration Loop

```
1. Prototype at TableIR level
2. Emit Excel via vedalang-dev emit-excel
3. Validate with xl2times
4. If valid → lift pattern to VedaLang syntax
5. If invalid → fix and retry
```

### Schema Changes

1. Update `vedalang/schema/vedalang.schema.json`
2. Update compiler, docs, and examples in the same change set
3. Run `uv run pytest tests/test_vedalang_schema.py tests/test_schema_compatibility.py`
4. Add or refresh regression tests for the new contract

Current migration stance:
- Prototype hard cut; backward-compatibility shims are not retained by default
- Canonical public target is the v0.2 PRD in `docs/prds/20260307-vedalang-v0.2.prd.txt`

## What This Documentation Does NOT Cover

- How to use VedaLang to author models (see `docs/vedalang-user/`)
- End-user CLI usage
- Model authoring patterns (from a user perspective)
