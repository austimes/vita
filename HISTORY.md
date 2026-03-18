# VedaLang History

Chronological record of the current repository state.

## 2026-03-18

- Updated the `vita init` starter `AGENTS.md` bootstrap so agents install Vita
  skills into the project-local `.codex/skills/` directory, force-refresh
  stale copies before install, and report installed skill names, paths, and
  visible in-session availability back to the user.
- Removed the VedaLang LSP and bundled VS Code/Cursor extension. The project
  is now explicitly CLI-first for model authoring and validation, and Viz owns
  the standalone visualization/viewing workflow.
- Bumped the shipped repo/tool version to `0.4.1` across the Python package
  and both CLI version markers.
- Bumped the shipped repo/tool version to `0.3.1` across the Python package,
  LSP server, and VS Code extension metadata.
- Made `vita update` version-aware: it now compares the installed tool package
  to GitHub `main`, reports when you are already current, and only refreshes
  when `main` is newer.
- Added `vita update` to refresh the installed `vita`/`vedalang` tool package
  from GitHub `main` via `uv tool install --force`.
- Repository hygiene audit (`vedalang-tidn`): fixed broken pytest venv shim,
  resolved 29 ruff lint violations, added `runs/` to `.gitignore`, fixed
  README clone URL from `austimes/vedalang` to `austimes/vita`.
- Removed `docs/project-status/STATUS.md`, `tools/sync_status.py`, and
  `tests/test_sync_status.py` — STATUS.md duplicated `bd list` and was
  perpetually out of sync. bd is now the sole source of truth for issue
  tracking. Cleaned all references in AGENTS.md, skills, and docs.

## 2026-03-17

- Completed the vita/vedalang CLI surface split (`vedalang-yda` epic).
- Removed deprecated `vedalang-dev` run/analyze subcommands: `pipeline`,
  `run-times`, `times-results`, `sankey`.
- Created the `vita` CLI as the dedicated run/results/sankey/diff surface.
- Tests rewritten to enforce vita-only run/analyze CLI paths.
- Docs swept for split command drift and wording mismatches; user-facing role
  boundaries aligned between skills and docs.
- Created post-split hygiene audit (`vedalang-50e`) to track remaining cleanup.

## 2026-03-12

- Simplified the RES viewer Object explorer attribute presentation again so
  nested attributes now render as plain indented `field: value` lines without
  column alignment bars or array-count labels like `items (2)` / `outputs (1)`,
  and verified the live browser view against the agriculture example.
- Continued the browser-verified Object explorer layout pass so nested flat
  attribute arrays now read like the supplied inspector mockup: array items no
  longer add a second bordered sub-pane, deeper rows bias more strongly toward
  values, and the default inspector width now matches the live expanded layout.

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
- Flattened Object explorer attribute rendering further so nested non-object
  structures are always visible as indented field trees instead of disclosure
  widgets, matching the simpler transition-attribute presentation while
  keeping source excerpts collapsible.
- Tuned the Object explorer tree styling again so nested non-object attributes
  use tighter key/value columns and cleaner indentation rails, aligning more
  closely with the supplied inspector mockup without changing the object-card
  hierarchy.
- Used live browser verification against the standalone RES viewer to fix the
  inspector pane width preference bug and adjust nested Object explorer
  attribute rows so deeper structures stack instead of collapsing into
  character-by-character value columns.
- Reworked RES graph visualization so ledger emissions are now rendered as
  node-level process annotations with emission state metadata, legends, and
  gas markers instead of pseudo-flow edges, while material carbon flows remain
  normal topology.
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
