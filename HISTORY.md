# VedaLang History

Chronological record of the current repository state.

## 2026-03-11

- Hard-cut the public DSL from v0.2 to v0.3.
- Removed authored commodity namespace prefixes so commodity definitions and
  references now use bare IDs.
- Split commodity semantics into explicit `type` and `energy_form` fields, with
  `primary` / `secondary` / `resource` retained only as internal lowered energy
  namespaces.
- Updated schema, compiler, diagnostics, lint, LSP, examples, and regression
  coverage so backend consumers receive canonical namespaced commodity IDs while
  author-facing tooling shows bare commodity labels plus type metadata.
- Simplified the RES viewer Object explorer by hiding redundant `id` rows,
  moving built-in type descriptions behind the type badge, and compacting
  simple list rendering to avoid unnecessary nested cards.
- Tightened the RES viewer Object explorer card taxonomy so only authored
  semantic objects render as cards, added presentation metadata for compact
  attribute hiding, introduced a `Show all attributes` toggle, and restyled
  nested attribute groups to read as fields instead of nested cards.
- Removed generic `opportunities` from the public DSL in favor of explicit
  `zone_opportunities`, migrated example rollouts to fleet/facility
  `new_build_limits`, and rewrote the toy agriculture model to use fleet-first
  stock and rollout boundaries.

## 2026-03-08

- Continued the hard cut to a v0.2-only repository.
- Removed residual compiler schema-routing helpers and deleted the dead
  scenario/trade/constraint lowering block from
  `vedalang/compiler/compiler.py`.
- Simplified source-shape detection to positive v0.2 recognition only in
  `vedalang/versioning.py`.
- Rewrote formatter regressions to use v0.2 examples only.
- Started the follow-up repository sweep to delete superseded design docs and
  rewrite active guidance around the supported v0.2 DSL.
- Completed the strict post-hard-cut cleanup sweep: removed dead diagnostic and
  compatibility helpers, deleted superseded PRDs/design docs, and scrubbed the
  remaining repo-visible pre-v0.2 wording outside the explicit
  unsupported-syntax diagnostic path.
- Normalized project and LSP version markers to `0.2.0`.
- Removed the explicit old-syntax preflight from compiler and tooling entry
  points, so unsupported sources now fail through normal YAML/schema
  validation rather than a custom legacy-format diagnostic.

## 2026-03-07

- Completed the v0.2 rollout around the package/run/CSIR/CPIR architecture.
- Landed the v0.2 schema, typed AST, resolution layer, canonical IRs,
  provenance artifacts, backend lowering, diagnostics, CLI updates, and
  regression matrix.
- Ported the supported example catalog to v0.2 and made the public CLI and
  tooling run-scoped.

## 2026-02-25

- Confirmed prototype governance for the repository:
  breaking changes are acceptable, examples are updated in place, and git
  history plus this file are the changelog during the pre-1.0 phase.
