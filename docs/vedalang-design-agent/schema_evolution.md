# VedaLang Schema Evolution Policy

This document defines how to evolve `vedalang.schema.json` during the current
prototype phase.

## Guiding Principle

**Design correctness is more important than backward compatibility.** VedaLang
is still pre-1.0, so schema changes may be breaking when they improve the DSL
design or align the implementation with the active PRD.

## Allowed Changes

These changes are acceptable during the prototype phase:

| Change Type | Example | Why Acceptable |
|-------------|---------|----------------|
| Add optional properties | Add `runs` metadata | Expands expressiveness without ambiguity |
| Add new `$defs` types | Add `technology_role` | Required for new DSL primitives |
| Rename properties | `processes` → `roles` | Clarifies the public contract |
| Remove obsolete properties | Remove `processes` from the public CLI | Prevents stale competing syntax |
| Narrow or replace enums | Replace old commodity vocabulary | Keeps semantics coherent |
| Change required fields | Make `technology_role` explicit | Enforces better structure |

## Required Process for Schema Changes

1. Update the active PRD or decision record if the change alters public meaning.
2. Update `vedalang/schema/vedalang.schema.json`.
3. Update compiler, CLI, docs, and examples in the same change set.
4. Add or update regression tests for the intended new contract.
5. Run focused schema/compiler tests plus broader validation before commit.

## Guardrails

- Do not keep dual public schemas unless an external release explicitly
  requires one.
- Do not keep compatibility aliases once the new design lands.
- Prefer deterministic rejection with good diagnostics over silent acceptance of
  stale syntax.
- Keep `tests/test_schema_compatibility.py` as a drift alarm for whatever the
  current schema contract is; it is not a promise of long-term backward
  compatibility.

## Recommended Validation Commands

```bash
uv run pytest tests/test_vedalang_schema.py tests/test_schema_compatibility.py -v
uv run pytest tests/test_vedalang_compiler.py -v
uv run ruff check .
```

## Current Versioning Context

- Active public design target: **VedaLang v0.3**
- Canonical PRD: `docs/VEDA2_NL_to_VEDA_PRD_v0_3.txt`
- Migration stance: **hard cut** under prototype rules
