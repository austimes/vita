# Repository Hygiene Audit — 2026-03-17 (Post Vita/VedaLang Split)

## Summary

Following the Vita/VedaLang CLI surface split (`vedalang-yda` epic), this audit
identified 10 actionable findings across docs drift, code structure, broken
examples, stale artifacts, and build hygiene. The split removed deprecated
`vedalang-dev` run/analyze commands but left several residual issues: handler
functions still live in `tools/veda_dev/cli.py` instead of `vita/`, STATUS.md
references a closed issue as open, the README directory tree uses the old
package name, 6 examples fail compilation, and a stale `v0_2` cache directory
sits in examples.

## Findings

### 1. Vita handler functions still in `tools/veda_dev/cli.py` (code-quality)
The split removed CLI subcommands from `vedalang-dev` but the actual handler
functions (`run_pipeline_command`, `run_times_results_command`,
`run_sankey_command`, `run_diff_command`) remain in `tools/veda_dev/cli.py`.
`vita/cli.py` imports them across the boundary. These should move to `vita/` or
a shared `tools/` module so vita doesn't depend on vedalang-dev internals.

### 2. STATUS.md shows vedalang-bit as open, but bd says closed (docs-drift)
STATUS.md "Open Work" section lists `vedalang-bit` as open, but all child
issues are closed in bd. STATUS.md needs sync.

### 3. README directory tree uses `veda-devtools/` root name (docs-drift)
The README project structure section shows `veda-devtools/` as the root
directory. The repo is `vedalang/`. The tree also omits `vita/`, `skills/`,
`vedalang/heuristics/`, `vedalang/identity/`, `vedalang/lint/`, and
`vedalang/viz/` directories.

### 4. Six examples fail compilation (fixture-hygiene)
- `ka11_fleet_distribution_base.veda.yaml` — E009 fleet distribution error
- `ka11_fleet_distribution_stress.veda.yaml` — same
- `ka14_run_selection_multi_run.veda.yaml` — needs `--run` flag
- `toy_industry.veda.yaml` — needs `--run` flag
- `toy_industry_high_gas_capex.veda.yaml` — needs `--run` flag
- `toy_industry_high_h2_capex.veda.yaml` — needs `--run` flag

The ka14/toy_industry failures are "needs --run" (multi-run models), so the
test harness may need updating. The ka11 failures look like genuine
regressions from the fleet distribution weight measure change.

### 5. Failing test: `test_vedalang_fixture_compiles[ka11_fleet_distribution_base]` (stale-tests)
One test fails in the suite (116 passed, 1 failed). This is the ka11 fleet
distribution regression from finding #4.

### 6. Stale `vedalang/examples/v0_2/.cache/` directory (fixture-hygiene)
The `vedalang/examples/v0_2/` directory contains only a `.cache/` folder with
RES viewer artifacts containing absolute paths from a local dev machine. Not
tracked by git but should be cleaned up and the directory removed.

### 7. Stale `veda_devtools-0.2.0.dist-info` in venv (build-hygiene)
A broken dist-info for version 0.2.0 persists in the venv alongside the
correct 0.3.0 dist-info. Causes a warning on every `uv` run. Fix:
`rm -rf .venv/lib/python3.12/site-packages/veda_devtools-0.2.0.dist-info/`

### 8. 43 ruff E501 line-too-long violations (code-quality)
All in test files. Not blocking but worth a cleanup pass.

### 9. HISTORY.md missing post-split entry (docs-drift)
The vita/vedalang split is a significant architectural change but HISTORY.md
has no entry for it. The last entry is 2026-03-08.

### 10. Large files over 500 lines (code-quality, informational)
- `vedalang/cli.py` — 2455 lines
- `tools/vedalang_lsp/server/server.py` — 1498 lines
- `tools/veda_dev/evals/runner.py` — 1426 lines
- `vedalang/viz/inspector.py` — 1221 lines
- `vedalang/compiler/compiler.py` — 1172 lines

Not actionable now but worth noting for future refactoring passes.

## Agent-First Score Card

| Criterion | Score | Notes |
|-----------|-------|-------|
| Discoverability | 4/5 | AGENTS.md and LLM_DOCS.md are comprehensive |
| Self-documenting | 4/5 | Schema-first design with good naming |
| Feedback loops | 4/5 | Clear compile/validate/test cycle |
| Minimal ambiguity | 3/5 | Vita handlers in veda_dev, README tree stale |
| Clean boundaries | 3/5 | Vita still imports from veda_dev internals |
| Onboarding speed | 4/5 | Skills and LLM_DOCS.md provide fast entry |
