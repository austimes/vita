# VedaLang Project Status

**Last updated:** 2026-03-10

## Summary

VedaLang now runs as a v0.2-only repository. The package/run/CSIR/CPIR rollout,
backend parity, diagnostics, tooling, supported example catalog, and strict
cleanup pass are all landed.

Current `bd` state: rollout and cleanup issues are closed; one follow-up issue
remains open.

## Current Focus

- Maintain the v0.2 package/run/CSIR/CPIR surface and backend parity through
  Excel, xl2times, and TIMES.
- Keep examples, docs, prompts, and tooling aligned with the active schema.

## Open Work

- `vedalang-bit` — require authored descriptions for RES object-explorer types
  so facilities, fleets, opportunities, technology roles, and technologies all
  carry user-facing explanatory copy in the viewer

## Recently Completed

- `vedalang-8j7` — replaced stale deprecated beads guidance in `AGENTS.md`
  and the checked-in `.beads` docs with the current `bd onboard` / `bd prime`
  / `bd dolt push` workflow
- `vedalang-6y5` — replaced the RES viewer's `DSL attributes` pane with an
  `Object explorer`, fixed missing asset-backed facility cards in process-node
  inspectors, added built-in kind explainer text and per-item YAML source
  expanders with line gutters, and switched inspector source snippets from
  processed JSON excerpts to exact authored `.veda.yaml` blocks
- `vedalang-3qd` — added direct fleet distribution and asset-scoped
  `new_build_limits`, reserved `opportunities` for place-bound build classes,
  split viewer provenance labels into facility-vs-fleet instances, and
  migrated the toy-sector examples and tutorial to fleet-first single-region
  authoring
- `vedalang-532` — fixed the browser RES viewer's duplicate VEDA tray shell by
  making the hidden tray and hidden collapsed-bar actually leave layout, so the
  tray now collapses to a single reopen handle instead of leaving an inert
  middle container behind
- `vedalang-b72` — trimmed the browser RES inspector so it only renders
  DSL, resolved semantic, and lowered IR sections, added a real collapsible
  bottom VEDA tray handle so the tray can reopen without toggling tables off,
  and tightened process label box padding and dimensions
- `vedalang-61i` — fixed the RES viewer follow-up where the bottom VEDA tray
  needed to collapse independently of the global `Show VEDA tables` toggle,
  tray open/close was still causing page-level viewport jumps, and process
  overlay labels were not scaling coherently with graph zoom
- `vedalang-1vn` — reworked the browser RES viewer shell so the graph is now
  the dominant surface, moved controls into left `Files`/`View`/`Filters`
  tabs, made the inspector collapsible and resizable on the right, added a
  header `Reset View` action plus auto-fit on window resize, and enlarged the
  process node/overlay sizing so labels stay contained more reliably
- `vedalang-xxw` — removed region text from system-lens RES viewer labels,
  made region filtering affect graph construction, aggregated multi-region
  system nodes and edges across the selected regions, and surfaced normalized
  scope/provenance/aggregation details in the viewer inspector
- `vedalang-hcc` — updated the Mermaid multi-run RES viewer regression to
  assert the current stacked, region-free role labels instead of the old
  `space_heat_supply@QLD` substring
- `vedalang-7lw` — fixed the RES viewer follow-up where the VEDA tables tray
  could appear inert because the graph/details region was allowed to grow and
  push the tray out of view; the top pane is now height-bounded, diagnostics
  scroll internally, and tray rendering is triggered directly on eligible node
  clicks
- `vedalang-wdu` — replaced the RES viewer's right-pane `VEDA/TIMES`
  inspector section with a toggle-controlled bottom tray that renders the
  actual emitted VEDA tables for selected system-lens process and commodity
  nodes, backed by stable per-table inspector row identities
- `vedalang-apz` — added a layered RES viewer inspector with collapsible
  `DSL attributes`, `Resolved semantic model`, `Lowered IR`, and `VEDA/TIMES`
  sections for process and commodity nodes, including collapsed-commodity
  membership tracking and query-engine regression coverage
- `vedalang-20i` — switched the browser RES viewer to an overlay label layer
  for process nodes so semantic top lines render stronger and provenance lines
  render lighter
- `vedalang-4r4` — adopted stacked multiline labels for v0.2 RES role and
  instance nodes so semantic role or technology stays on the first line and
  provenance moves to lower lines
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
