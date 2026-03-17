# Repository Hygiene Audit — 2026-03-17

## Summary

Comprehensive audit of the vedalang repository covering dead code, stale tests,
documentation drift, code quality, fixture hygiene, agent-first readiness, and
build/issue tracker hygiene. 760 tests collected, 6 failures found, 0 open bd
issues, and several stale artifacts identified.

## Findings by Category

### 1. Dead Code & Unused Modules

- **tests/agent_design/**: Empty directory with only `__pycache__` — no source
  files tracked in git. Residual from Phase 1 design work.
- **No orphaned Python modules detected** in `vedalang/` or `tools/`.

### 2. Stale / Failing Tests (6 failures)

- **test_llm_unit_check.py** (5 failures): `test_cmd_llm_lint_units_json_success`,
  `test_cmd_llm_lint_units_needs_review_exit_code`,
  `test_cmd_llm_lint_units_unknown_component_returns_error`,
  `test_cmd_llm_lint_units_text_prints_fix_suggestions`,
  `test_cmd_llm_lint_units_propagates_runtime_flags`. CLI output contract has
  drifted from test expectations (KeyError on `critical`, `diagnostics` keys;
  exit code 2 instead of 0).
- **test_llm_assessment.py** (1 failure):
  `test_lint_default_is_offline` — `vedalang lint` returns exit code 2 instead
  of expected 0 or 1.
- **test_minisystem_fixtures.py** (8 skips): parametrized for minisystem5-8 but
  only minisystem8 exists; 5/6/7 fixtures are missing.
- **test_vedalang_dev_cli.py** (2 skips): `veda_patterns` module import fails
  despite directory existing at `tools/veda_patterns/`.

### 3. Example Compilation Failures

- **ka11_fleet_distribution_base.veda.yaml** — E009: fleet distribution weight
  measure rollup error (issue vedalang-50e.4 was closed but regression persists
  for `vedalang compile` without `--run`).
- **ka11_fleet_distribution_stress.veda.yaml** — same E009.
- **ka14_run_selection_multi_run.veda.yaml** — E002: multiple runs, needs `--run`.
- **toy_industry*.veda.yaml** (3 files) — E002: multiple runs, needs `--run`.

Note: ka14 and toy_industry multi-run failures are expected (require `--run`
flag). ka11 E009 is a genuine regression when compiling standalone.

### 4. Documentation Drift

- **STATUS.md** lists `vedalang-50e` subtasks as open, but **all are closed** in
  bd. Open Work section is stale.
- **0 open bd issues** but STATUS.md shows 6 open items.

### 5. Code Quality

- **Ruff**: All checks passed ✓
- **No TODO/FIXME/HACK comments** in production code.
- **Bare `except Exception:`**: 8 occurrences across `vedalang/` and `tools/`.
  Most are in error-resilient paths (LSP, viz, CLI) — acceptable but worth
  reviewing.
- **Large files** (>500 lines): `cli.py` (2455), `server.py` (1498),
  `runner.py` (1426), `inspector.py` (1221), `compiler.py` (1172),
  `graph.py` (1147). cli.py is notably large.
- **Commented-out code blocks**: 2 found (`compiler.py:129` 12 lines,
  `runner.py:13` 5 lines).

### 6. Fixture & Example Hygiene

- **output/** (224K), **tmp/** (138M): stale build artifacts present but
  gitignored — not tracked.
- **output_invalid/**: empty directory.
- **fixtures/MiniVEDA2/**: actively used by integration tests ✓

### 7. Build & Configuration Hygiene

- **uv.lock**: up to date ✓
- **.DS_Store files**: 16 on disk but none tracked in git ✓
- **No hardcoded absolute paths** in Python source ✓
- **.gitignore**: covers all generated artifacts ✓

### 8. Issue Tracker Hygiene

- **0 open issues**, **260 closed issues** — tracker is clean.
- All `vedalang-50e` subtasks are closed but STATUS.md was not updated.

## Agent-First Scorecard

| Criterion | Score | Notes |
|-----------|-------|-------|
| Discoverability | 5/5 | AGENTS.md is comprehensive, directory structure is clear |
| Self-documenting | 4/5 | Schemas and types are well-defined; some large files could use splitting |
| Feedback loops | 4/5 | validate/pytest/ruff work well; 6 test failures reduce signal |
| Minimal ambiguity | 4/5 | Three-CLI split is clear; some naming edge cases |
| Clean boundaries | 4/5 | Good separation; cli.py at 2455 lines blurs concerns |
| Onboarding speed | 5/5 | Skills + AGENTS.md enable fast productive sessions |
| **Overall** | **4.3/5** | |

## Recommendation

Top 3 highest-impact improvements:
1. Fix 6 failing tests (llm_unit_check + llm_assessment) to restore green CI
2. Sync STATUS.md with bd state (all 50e issues are closed)
3. Clean up stale artifacts (tests/agent_design, commented-out code blocks)
