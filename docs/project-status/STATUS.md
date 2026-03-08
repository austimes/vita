# VedaLang Project Status

**Last updated:** 2026-03-08

## Summary

VedaLang now runs as a v0.2-only repository. The package/run/CSIR/CPIR rollout,
backend parity, diagnostics, tooling, supported example catalog, and strict
cleanup pass are all landed.

Current `bd` state: all rollout and cleanup issues are closed.

## Current Focus

- Maintain the v0.2 package/run/CSIR/CPIR surface and backend parity through
  Excel, xl2times, and TIMES.
- Keep examples, docs, prompts, and tooling aligned with the active schema.

## Open Work

- No open transition work.

## Recently Completed

- `vedalang-b4r` — added concise block-level guidance to the README, tutorial,
  and quickstart example docs for the minimal model structure
- `vedalang-bc8` — removed residual compiler/CLI schema-routing helpers and the
  dead scenario/trade/constraint lowering block
- `vedalang-icc` — purged superseded wording from active user, LSP, status, and
  changelog docs
- `vedalang-1hb` — deleted superseded design and reference documents
- `vedalang-vbw` — removed residual diagnostic helper wrappers from the
  compiler and eval runner
- `vedalang-99l` — removed final transition residue from docs, prompts,
  comments, and namespace lint
- `vedalang-vyr` — removed the explicit old-syntax preflight so unsupported
  sources now fail through normal schema validation
- `vedalang-y0a` — completed the strict post-hard-cut cleanup sweep
- `vedalang-txa` — completed the v0.2 rollout across schema, resolution, IR,
  backend, diagnostics, tooling, docs, and regressions

## Validation Baseline

- `uv run pytest`
- `uv run ruff check .`
- `uv run vedalang validate <model>.veda.yaml --run <run_id>`
