# Repository Hygiene Audit — 2026-03

## Summary

The v0.2 rollout and example-catalog migration are complete, but the runtime still carries several intentional compatibility surfaces for the pre-v0.2 authoring model. These are now the main source of architectural ambiguity: the public DSL is v0.2-only, while parts of the compiler, viz/query stack, LLM lint flows, docs, and regression fixtures still encode `model`/`roles`/`variants`/`providers` semantics.

This audit focuses on legacy support surfaces that should be removed or quarantined so the project can become operationally v0.2-only.

## Findings By Category

### Compiler and schema compatibility

- [vedalang/compiler/compiler.py](/Users/gre538/code/vedalang/vedalang/compiler/compiler.py) still routes between legacy and v0.2 schemas and keeps the legacy `compile_vedalang_to_tableir()` path alive.
- [vedalang/versioning.py](/Users/gre538/code/vedalang/vedalang/versioning.py) still advertises legacy top-level key detection as a first-class runtime concept.
- [vedalang/schema/vedalang.legacy.schema.json](/Users/gre538/code/vedalang/vedalang/schema/vedalang.legacy.schema.json) remains bundled into normal validation flows.

### RES query, viz, and export compatibility

- [vedalang/viz/query_engine.py](/Users/gre538/code/vedalang/vedalang/viz/query_engine.py) still branches between legacy graph builders and v0.2 artifact-backed builders.
- [vedalang/viz/graph_models.py](/Users/gre538/code/vedalang/vedalang/viz/graph_models.py) is a large legacy/provider-centric graph path.
- [vedalang/lint/res_export.py](/Users/gre538/code/vedalang/vedalang/lint/res_export.py) still preserves the legacy `roles`/`variants` export contract and v0.2 adapts into it.
- [vedalang/viz/static/app.js](/Users/gre538/code/vedalang/vedalang/viz/static/app.js) still exposes `provider`, `provider_variant`, and `provider_variant_mode` granularities in the UI.

### Legacy facility/provider lowering

- [vedalang/compiler/facilities.py](/Users/gre538/code/vedalang/vedalang/compiler/facilities.py) lowers facility primitives into legacy `providers`, `provider_parameters`, and generated `variants`.
- Legacy provider-centric reporting still leaks into compiler and graph details through this lowering layer.

### LLM lint and eval legacy assumptions

- [vedalang/lint/llm_unit_check.py](/Users/gre538/code/vedalang/vedalang/lint/llm_unit_check.py) still uses `roles`/`variants` component enumeration.
- [vedalang/lint/prompts/res-assessment/v1/system.txt](/Users/gre538/code/vedalang/vedalang/lint/prompts/res-assessment/v1/system.txt) and [vedalang/lint/prompts/res-assessment/v2/system.txt](/Users/gre538/code/vedalang/vedalang/lint/prompts/res-assessment/v2/system.txt) still instruct the model in terms of legacy role/variant graphs.
- Ground-truth eval fixtures under [tools/veda_dev/evals/fixtures/ground_truth](/Users/gre538/code/vedalang/tools/veda_dev/evals/fixtures/ground_truth) are still authored in the legacy surface.

### User-facing docs and LSP schema docs

- [docs/vedalang-user/attribute_mapping.md](/Users/gre538/code/vedalang/docs/vedalang-user/attribute_mapping.md) still documents P4 role/variant ownership as the active model.
- [tools/vedalang_lsp/server/schema_docs.py](/Users/gre538/code/vedalang/tools/vedalang_lsp/server/schema_docs.py) still contains hover/help text for legacy fields such as `variants.kind`, service `context`, and `timeslices`.
- Historical design/reference PRDs remain useful as archive material, but the active user/design doc entry points should no longer direct agents toward those removed surfaces.

### Test and fixture drag

- Large parts of [tests/test_vedalang_compiler.py](/Users/gre538/code/vedalang/tests/test_vedalang_compiler.py) still exercise legacy role/variant/provider behavior.
- Compatibility tests such as [tests/test_versioning.py](/Users/gre538/code/vedalang/tests/test_versioning.py) and the legacy-isolation portion of [tests/test_schema_compatibility.py](/Users/gre538/code/vedalang/tests/test_schema_compatibility.py) are still intentionally keeping the old runtime path alive.

## Recommendation

1. Remove legacy compiler/schema routing first so the runtime contract becomes unambiguous.
2. Collapse viz/query/export onto the v0.2 CSIR/CPIR path and delete provider-centric graph abstractions.
3. Rewrite LLM lint/eval prompts, fixtures, docs, and LSP help so every agent-facing surface teaches only the v0.2 model.
