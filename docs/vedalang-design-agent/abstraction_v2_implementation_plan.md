# VedaLang Core Abstraction v2 Implementation Plan

Date: 2026-03-06  
PRD: `docs/prds/20260305-vedalang-core-abstraction-role-variant-mode-provider-scope-v1.prd.txt`  
Epic: `vedalang-cgl`

## Locked Decisions

1. Hard cut during prototype phase (no backward-compatibility guarantees).
2. Process symbols are sanitized for compiler output.
3. Top-level primitives are `roles` and `variants` (process semantics).
4. Provider-based reporting outputs are part of this rollout.
5. Roles are process abstractions (not commodities).

## Target Semantic Model

- Type axis: `role -> variant -> mode`
- Object axis: `provider` (`facility` or `fleet`, single-role for now)
- Commodity axis: `scope` is commodity-only (market partition), not process/type identity

## Rollout Phases

### Phase 1: Schema + IR Core (`vedalang-hh4`, `vedalang-3gm`, `vedalang-ezz`)

- Add schema primitives:
  - `variants[*].modes[*]`
  - `providers[*]`
  - `provider_parameters[*]`
- Refactor IR expansion from `availability`-centric to provider-centric:
  - build providers
  - expand `provider x variant x mode x region x scope` instances
- Emit canonical provider-aware process symbols:
  - `{FAC|FLT}::{provider_id}::ROLE::{role_id}::VAR::{variant_id}::MODE::{mode_id}`
- Keep metadata parseable for diagnostics/query grouping.

Acceptance:
- Compiler emits stable symbols and metadata fields for provider, role, variant, mode.
- Provider validation errors are deterministic (unknown refs, role mismatch, mode mismatch).

### Phase 2: Facilities/Fleets Lowering (`vedalang-4y6`, `vedalang-ihm`)

- Rework facility lowering to provider-native objects.
- Retire synthetic variant leakage in reporting semantics.
- Add provider-aware selector semantics for parameter and case overlays.

Acceptance:
- Facilities and fleets share one provider abstraction in compiler metadata.
- Selector application can target provider + variant + mode deterministically.

### Phase 3: Query/Viz/LSP Surface (`vedalang-dmn`, `vedalang-8k9`)

- Grouping levels:
  - `role`
  - `provider`
  - `provider_variant`
  - `provider_variant_mode`
  - `instance`
- Decouple commodity aggregation from grouping:
  - `scoped`
  - `collapse_scope`
- Update query contract, web UI controls, and LSP schema docs.

Acceptance:
- Grouping and commodity aggregation are independent controls.
- Collapsed commodity nodes preserve provenance for explainability.

### Phase 4: Lint/Identity + Test Matrix (`vedalang-dy4`, `vedalang-2gz`)

- Add deterministic lint rules for:
  - role->variant->mode containment
  - provider single-role constraint
  - provider/type identifiers free of scope leakage
- Expand regression tests for schema/compiler/query/viz/LSP/provider reporting.

Acceptance:
- New abstraction invariants fail fast with explicit diagnostics.
- Full test matrix passes with provider-heavy and fleet-heavy fixtures.

### Phase 5: Docs + Examples + Governance (`vedalang-22a`, `vedalang-4vt`)

- Rewrite user/design docs and examples to teach:
  - what a role is
  - what a variant is
  - what a mode is
  - what a provider is
  - why scope is commodity-only
- Update status/governance docs and decision history.

Acceptance:
- Docs lead with v2 abstraction and provider mental model.
- Example set demonstrates facility and fleet providers with mode switching.

## Execution Notes

- During migration, use automated codemods for examples/tests where possible.
- Keep all transformation logic deterministic and test-first.
- Track every subtask in `bd` and keep `STATUS.md` synced.
