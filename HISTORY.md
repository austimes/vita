# VedaLang History

Chronological record of the current v0.2-era repository state.

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
