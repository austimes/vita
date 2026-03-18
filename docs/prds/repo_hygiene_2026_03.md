# Repository Hygiene Audit — 2026-03-18

## Summary

The repo is in good shape after the recent v0.3 stabilization. All 885 tests pass, no orphaned modules, and examples compile. The main issues are: (1) a broken pytest shim requiring `python -m pytest` workaround, (2) 29 ruff lint violations across vita/ and tests/, (3) `runs/` directory with solver artifacts not gitignored, (4) the `test_experiment_validation.py` F821 undefined name `ExperimentManifest`, and (5) .DS_Store files in the working tree.

## Findings by Category

### 1. Dead Code & Unused Modules
- **No orphaned modules found.** All Python files are referenced.
- `vita/experiment_validation.py`: 3 unused local variables (`step_map`, `design_variant_ids`, `design_comp_ids`) — F841
- `vita/experiment_validation.py`: 1 unused import (`Collection`) — F401
- `tests/test_experiment_validation.py`: unused `pytest` import — F401
- `tests/test_vita_project_init.py`: unused `pytest` import — F401

### 2. Stale Tests
- **All 885 tests pass**, 29 skipped (expected: missing GDX/minisystem fixtures).
- `tests/test_experiment_validation.py:68` — F821: `ExperimentManifest` used as quoted return type but never imported. Should import from `vita.experiment_manifest`.
- **Pytest shim broken**: `uv run pytest` fails with `ModuleNotFoundError: No module named 'yaml'` while `uv run python -m pytest` works fine. The `.venv/bin/pytest` shim is stale and doesn't resolve pyyaml.

### 3. Stale Experiments
- **No `experiments/` directory exists.** Clean.

### 4. Documentation Drift
- `STATUS.md` says "No open issues. All 274 bd issues are closed" but bd actually has 1 open issue (`vedalang-q2x`).
- `README.md` references `git clone https://github.com/austimes/vedalang.git` but the repo is now `austimes/vita`.

### 5. Code Quality — Ruff Violations
- **22 errors in vita/ + tools/**, **7 errors in tests/** (29 total)
- Breakdown: 15× E501 (line too long), 4× F841 (unused variable), 3× F401 (unused import), 2× I001 (unsorted imports), 1× F821 (undefined name), 1× UP037 (quoted annotation)
- 6 auto-fixable with `--fix`.

### 6. Fixture & Example Hygiene
- `vedalang validate` passes for quickstart example.
- `output/` directory contains stale CSV artifacts (gitignored, harmless).
- `runs/` directory contains solver output artifacts (GDX, LST) — **not gitignored**, untracked but could accidentally be committed.

### 7. Agent-First Repository Assessment

| Criterion | Score | Notes |
|-----------|-------|-------|
| Discoverability | 5/5 | AGENTS.md is comprehensive, CLI tools well-documented |
| Self-documenting | 5/5 | Schema-first design, clear naming |
| Feedback loops | 4/5 | Pytest shim broken; workaround needed |
| Minimal ambiguity | 4/5 | Clean after v0.3 reset |
| Clean boundaries | 5/5 | vedalang/vita/tools well-separated |
| Onboarding speed | 4/5 | Would be 5/5 if pytest shim worked |

### 8. Configuration & Build Hygiene
- `.DS_Store` files present in working tree (gitignored, not tracked — cosmetic).
- `runs/` not in `.gitignore` — risk of accidental commit of large GDX files.
- `uv.lock` is up to date.
- No hardcoded absolute paths found.

### 9. Issue Tracker Hygiene
- bd database had to be rebuilt (dolt database directory was empty). Recovered from JSONL backup.
- STATUS.md out of sync with bd (claims 0 open, actually 1 open).

## Recommendation

1. **Fix pytest shim** — `uv sync --reinstall` or rebuild the venv
2. **Fix ruff violations** — auto-fix 6, manually fix remaining 23
3. **Add `runs/` to .gitignore** — prevent accidental commit of solver artifacts
4. **Fix test_experiment_validation.py** — add missing `ExperimentManifest` import
5. **Remove STATUS.md** — duplicates `bd list`, perpetually drifts; bd is the sole source of truth
