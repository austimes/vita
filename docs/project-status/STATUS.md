# VedaLang Project Status

**Last updated:** 2026-03-09

## Summary

VedaLang now runs as a v0.2-only repository. The package/run/CSIR/CPIR rollout,
backend parity, diagnostics, tooling, supported example catalog, and strict
cleanup pass are all landed.

Current `bd` state: rollout and cleanup issues are closed; one low-priority
formatting task remains open.

## Current Focus

- Maintain the v0.2 package/run/CSIR/CPIR surface and backend parity through
  Excel, xl2times, and TIMES.
- Keep examples, docs, prompts, and tooling aligned with the active schema.

## Open Work

- `vedalang-4ov` — clean up checked-in example `.veda.yaml` formatting drift so
  documented `uv run vedalang fmt --check ...` examples on repo paths pass
  cleanly

## Recently Completed

- `vedalang-ndd` — updated the v0.2 RES role-granularity viewer so
  opportunity-backed groups expose their opportunity provenance in node labels
  and no longer collide with role-instance-backed groups
- `vedalang-ky3` — rewrote `toy_agriculture.veda.yaml` with coherent `farm_*`
  naming, explicit retrofit transitions for agricultural production, and a
  separate land-carbon management role where soil carbon and reforestation
  consume `material:farm_land` and provide `service:carbon_removal`
- `vedalang-8o6` — updated the README Quick Start and development command
  snippets to use `uv run vedalang fmt --check ...` instead of `bun run
  format:veda:check`
- `vedalang-5o0` — documented enum-backed README/tutorial fields and clarified
  that scenario categories are currently a runtime convention rather than a
  `vedalang.schema.json` enum
- `vedalang-bzb` — clarified that `region_partitions` group underlying spatial
  members into compile-time model regions in the minimal example docs
- `vedalang-d4l` — aligned the README filename guidance with current compiler
  output and normalized referenced scenario workbook naming to lowercase `scen_*`
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
