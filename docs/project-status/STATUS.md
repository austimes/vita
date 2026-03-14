# VedaLang Project Status

**Last updated:** 2026-03-15

## Summary

VedaLang now runs as a v0.3 repository. The package/run/CSIR/CPIR rollout,
backend parity, diagnostics, tooling, and supported example catalog remain
landed, and the commodity identity reset has now removed authored namespace
prefixes in favor of bare IDs plus explicit commodity typing.

Current `bd` state: the solver-backed known-answer CI program has now fully
landed. Harness/canonicalization, core primitive, capacity/constraint,
spatial/run, and CI reliability epics are all closed, with one targeted
follow-up task open for KA03 solved emissions-flow observability.
The modeler-facing known-answer catalog is now published at
`docs/vedalang-user/known_answer_catalog.md`.
Capacity suite KA06/KA07/KA08/KA09 plus KA13 diagnostics coverage and
spatial/run KA10/KA11/KA12/KA14 solved known-answer coverage are implemented,
with fast/full solver-tier CI wiring in place.

## Current Focus

- Maintain the v0.3 package/run/CSIR/CPIR surface and backend parity through
  Excel, xl2times, and TIMES.
- Keep examples, docs, prompts, and tooling aligned with the active schema.

## Open Work

- `vedalang-bit` — require authored descriptions for RES object-explorer types
  so facilities, fleets, zone opportunities, technology roles, and
  technologies all carry user-facing explanatory copy in the viewer
- `vedalang-wvu` — close the KA03 solved emissions-flow observability gap so
  known-answer coverage can assert emissions-flow behavior from extracted solved
  outputs instead of compile-only coefficients

## Recently Completed

- `vedalang-rh9` — completed the known-answer end-to-end solver CI program
  with all epics closed (`rh9.1` through `rh9.5`)
- `vedalang-rh9.5` — completed CI orchestration/reliability for solve tests
  with marker tiering, workflow wiring, artifact capture, and determinism
  guidance
- `vedalang-rh9.5.3` — published solver tolerance/determinism policy and
  contributor guidance in `docs/vedalang-design-agent/known_answer_tests.md`
- `vedalang-rh9.5.2` — added `.github/workflows/solver-known-answer.yml`
  with PR fast tier, scheduled/manual full tier, solver preflight checks, and
  failure artifact uploads
- `vedalang-rh9.5.1` — implemented pytest solve-tier taxonomy
  (`solver_fast`/`solver_full`), test classification, and marker guardrails
- `vedalang-rh9.3` — completed capacity/constraint known-answer epic
  (KA06/KA07/KA08/KA09 + KA13 diagnostics)
- `vedalang-rh9.3.3` — added KA13 constraint-edge diagnostics coverage with
  artifact-path assertions for actionable solver-failure debugging
- `vedalang-rh9.1` — delivered solver-test foundation with reusable harness,
  robust times-results extraction, semantic assertion helpers, and reference
  documentation/tests
- `vedalang-rh9.2.1` — added KA01/KA02 known-answer solver fixtures and
  deterministic activity assertions in `tests/test_known_answer_core.py`
- `vedalang-rh9.2.3` — added paired-variant parameter-delta behavior assertion
  (2x gas-supply activity) over the KA01/KA02 fixtures
- `vedalang-rh9.2` — completed core primitive known-answer suite coverage (KA01-KA05) with solver-backed deterministic assertions
- `vedalang-rh9.2.2` — added KA03 emissions-factor mapping and KA04 merit-order dispatch known-answer fixtures/tests with deterministic solver-backed assertions
- `vedalang-rh9.3.1` — added KA06/KA07 stock-sufficient and demand-spike known-answer fixtures/tests with deterministic activity-delta plus solved `VAR_NCAP` trigger assertions
- `vedalang-rh9.3.2` — added KA08/KA09 build-limit and zone-opportunity known-answer fixture pairs with solved backup-suppression and process-class-shift assertions
- `vedalang-rh9.4.1` — added KA10 two-region network transfer-direction known-answer fixture pair with solved regional dispatch-flip assertions
- `vedalang-rh9.4.2` — added KA11 fleet weighted-distribution baseline/stress known-answer fixtures/tests with solved regional ratio/share assertions and stress-directional checks
- `vedalang-rh9.4.3` — added KA12 temporal-growth and KA14 run-selection known-answer fixtures/tests with deterministic cross-run solved-output ratio/difference assertions
- `vedalang-rh9.4` — completed the spatial/run known-answer epic with KA10/KA11/KA12/KA14 solver-backed coverage and integrated suite validation
- `vedalang-bq3` — removed the remaining active `v0_2` naming from the public
  0.3 frontend by renaming compiler/viz modules and exports, flattening the
  versioned example paths into the current catalog, updating tests and active
  docs/help text, and bumping active package/LSP version markers to `0.3.0`
- `vedalang-xga` — browser-verified the live RES viewer inspector, fixed the
  broken missing-width preference path that was forcing narrow panes, grouped
  inspector header actions coherently, and reworked nested Object explorer
  attribute rows so deeper structures stack instead of collapsing values into
  unreadable slivers
- `vedalang-7r8` — browser-verified the follow-up Object explorer layout pass,
  removed redundant nested array-item rails, widened the deepest key/value
  rows, and aligned flat attribute arrays like `stock.items` more closely with
  the supplied line-based inspector mockup
- `vedalang-sx5` — replaced the remaining Object explorer column layout with
  a plain indented `field: value` tree, removed array-count labels like
  `items (n)` / `outputs (n)`, and browser-verified the agriculture inspector
  against the simplified mockup direction
- `vedalang-g0l` — refined the Object explorer nested attribute layout toward
  the line-based mockup, tightening key/value columns and indentation rails so
  non-object attribute trees read like a continuous outline inside each object
  card
- `vedalang-n0a` — flattened Object explorer attribute rendering so nested
  non-object data like stock, distribution, performance, emissions, and nested
  cost fields now render as always-visible indented attribute trees instead of
  nested disclosure blocks, while leaving object cards and source expanders
  unchanged
- `vedalang-fng` — cleaned up the RES viewer Object explorer card taxonomy so
  only authored objects render as cards, added compact presentation metadata
  plus a `Show all attributes` inspector toggle, and restyled nested attribute
  groups so relationship fields no longer compete visually with true object
  cards
- `vedalang-vyz` — surfaced retrofit/changeover semantics in the RES viewer so
  system-lens role and instance nodes expose transition badges on the graph and
  a dedicated `Transitions` inspector section, while leaving fleet
  `new_build_limits` and `zone_opportunity` nodes unmarked unless explicit role
  transitions exist
- `vedalang-j2p` — improved RES viewer contrast so inspector object-type badges
  now use stronger, kind-specific pill colors and process overlay secondary and
  meta label text reads clearly against the dark graph background
- `vedalang-suz` — removed ledger-emission pseudo-flow edges from the RES
  graph/Mermaid surfaces, added node-level `ledger_emissions` metadata and
  process annotations for emit/remove/mixed states, kept physical material CO2
  as normal topology, and versioned the structural RES assessment prompt to
  match the new contract
- `vedalang-eiu` — removed redundant `id` rows from Object explorer cards,
  moved built-in object-type explainer text behind the type badge hover/click
  affordance, and flattened simple list rendering so outputs, stock entries,
  and similar fields no longer expand into unnecessary nested cards
- `vedalang-84d` — removed generic `opportunities` from the public DSL,
  replaced them with explicit `zone_opportunities`, tightened zone-only
  resolution and provenance through CSIR/CPIR/viewer surfaces, and migrated
  the example/test corpus to fleet/facility `new_build_limits` unless the
  build class is genuinely zone-bound
- `vedalang-6ov` — hard-cut the public DSL to v0.3 commodity identity: removed
  authored commodity prefixes, split commodity semantics into explicit
  `type`/`energy_form`, lowered commodities to canonical backend namespaces,
  updated diagnostics and the LSP to type-based messaging, and migrated the
  example/test corpus to bare commodity references
- `vedalang-p0w` — reworked the RES viewer inspector `Object explorer` into a
  nested authored-object tree, removed redundant type wording, hid `ok`
  section/query status text in the UI, and replaced raw object-explorer JSON
  blobs with recursive expandable field groups
- `vedalang-8n3` — restored the historical `llm.units.component_quorum` and
  `llm.structure.res_assessment` prompt bundle texts to the snapshots implied
  by their checked-in manifests, so prompt-registry verification and the LLM
  unit-check tests pass again without mutating historical manifest hashes
- `vedalang-4ov` — reformatted the checked-in example catalog, fixed the
  `vedalang fmt --check` canonicalization bug so check mode now agrees with
  write mode after Prettier normalization, and cleaned the remaining repo-wide
  Prettier drift in the eval fixture corpus
- `vedalang-8j7` — replaced stale deprecated beads guidance in `AGENTS.md`
  and the checked-in `.beads` docs with the current `bd onboard` / `bd prime`
  / `bd dolt push` workflow
- `vedalang-6y5` — replaced the RES viewer's `DSL attributes` pane with an
  `Object explorer`, fixed missing asset-backed facility cards in process-node
  inspectors, added built-in kind explainer text and per-item YAML source
  expanders with line gutters, and switched inspector source snippets from
  processed JSON excerpts to exact authored `.veda.yaml` blocks
- `vedalang-3qd` — added direct fleet distribution and asset-scoped
  `new_build_limits`, reserved `zone_opportunities` for explicitly zone-bound
  build classes,
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
  zone-opportunity-backed groups expose their provenance in node labels and no
  longer collide with role-instance-backed groups
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
