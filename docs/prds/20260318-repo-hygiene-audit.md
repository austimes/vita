# Repository Hygiene Audit — 2026-03-18

## Summary

Comprehensive audit of the vedalang repository. Core health is strong: 762 tests
collected, 733 pass, 29 skip (all legitimate — GDX/patterns unavailability),
0 failures. Ruff clean. All 53 examples compile. No orphaned Python modules.
`uv.lock` in sync. `sync_conventions --check` passes. 0 open bd issues.

Seven actionable findings across documentation drift, stale artifacts, code
quality, and build hygiene.

## Findings by Category

### 1. Dead Code & Unused Modules

- **No orphaned Python modules.** All source files in `vedalang/` and `tools/`
  have inbound references.
- **`tools/veda_run_times/`** — the runner module is still used by
  `veda_dev/pipeline.py`, test helpers, and solver tests. It is NOT dead code,
  but has no standalone CLI entry point. Acceptable as-is.

### 2. Stale Tests

- **No failures.** 733 passed, 29 skipped.
- All `skipif` decorators are conditional on external resources (GDX files,
  `veda_patterns` module, output artifacts), not stale feature flags.
- **No `@pytest.mark.xfail` decorators** in the test suite.

### 3. Stale Experiments

- **`experiments/` directory does not exist** — previously cleaned up.

### 4. Documentation Drift ⚠️

- **STATUS.md Open Work is stale (F1).** Lists `vedalang-xp5` and 6 subtasks as
  open, but all 274 bd issues are closed. Open Work should be empty.
- **7 untracked PRD files in `docs/prds/` (F2).** Five AEMO MVP drafts
  (v1–v5), two earlier hygiene audits, and one generic hygiene PRD are untracked
  by git. Should be committed or removed.
- **2 untracked docs in `docs/vedalang-user/` (F3).**
  `toy_industry_experiment_notes.md` and `toy_industry_vita_explainer.html`
  (8 KB) are not committed.
- **Machine-local paths (F4).** Mentioned in prior audit PRD as unresolved.
  Only one remaining reference found in `docs/prds/repo_hygiene_2026_03.md`
  (self-referential).

### 5. Code Quality

- **Ruff passes.** Zero violations.
- **No TODO/FIXME/HACK/XXX comments** in production code.
- **7 bare `except Exception:` blocks (F5).** These swallow errors silently in:
  `llm_unit_check.py:76`, `ledger_emissions.py:189`, `cli.py:981`,
  `source_maps.py:287`, `evals/runner.py:143`, `gdx_utils.py:32`,
  `pipeline.py:636`.
- **Large files.** `cli.py` is 2,455 lines. Previously triaged and accepted —
  no action needed this round.

### 6. Fixture & Example Hygiene

- **All 53 example files compile successfully** (57 runs checked, 0 failures).
- **`output/` contains stale xl2times CSV artifacts (F6).** 20+ CSV files from a
  prior run sit in `output/`. Gitignored but should be cleaned.
- **`output_invalid/` is empty.** No action.
- **`runs/` directory has untracked solver artifacts (F6).** `mini_test/` and
  `toy_industry/` with GDX/lst files, manifests, results. Gitignored but
  present locally.

### 7. Build & Configuration Hygiene

- **17 `.DS_Store` files on disk (F7).** None tracked by git (`.gitignore`
  covers them), but they clutter `find` results.
- **`uv.lock` in sync.** `uv lock --check` passes.
- **No hardcoded absolute paths** in source code.

### 8. Issue Tracker Hygiene

- **All 274 issues are closed.** No stale or orphaned issues.
- **STATUS.md is the only drift point** (covered in F1).

## Agent-First Scorecard

| Criterion | Score | Notes |
|-----------|-------|-------|
| Discoverability | 5/5 | AGENTS.md comprehensive, skills well-organized |
| Self-documenting | 5/5 | Schema-first, clear naming, typed |
| Feedback loops | 5/5 | `validate`, `pytest`, `ruff` all give clear output |
| Minimal ambiguity | 4/5 | STATUS.md drift is the main ambiguity source |
| Clean boundaries | 4/5 | `veda_run_times` boundary slightly blurry |
| Onboarding speed | 5/5 | Skills system + AGENTS.md make cold-start fast |

**Overall: 4.7/5** — very healthy repository.

## Recommendations

1. **Sync STATUS.md** — highest impact, low effort
2. **Commit or remove untracked PRDs/docs** — decide what to keep
3. **Clean local stale artifacts** — `output/`, `runs/`, `.DS_Store`
