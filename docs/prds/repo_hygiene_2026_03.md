# Repository Hygiene Audit — 2026-03

## Summary

This audit found six actionable hygiene items across documentation drift,
code quality, and boundary clarity. Core feedback loops are mostly healthy
(`pytest --collect-only` succeeds; `uv lock --check` passes), but current
drift in status reporting and a few residual code/documentation smells reduce
agent-first reliability.

## Findings By Category

### Dead Code & Unused Modules

- `tools/veda_run_times/cli.py` appears to be a residual CLI surface after the
  vita split. It is not wired through `pyproject.toml` scripts and has no
  inbound references from repository code.

### Stale Tests

- `uv run pytest --collect-only -q` succeeds (760 tests collected).
- No untracked unconditional `skip`/`xfail` markers were found; current skips
  are environment-gated (`skipif`) and appear intentional.

### Stale Experiments

- `experiments/` directory is absent in this checkout; this category is
  currently not applicable.

### Documentation Drift

- `docs/project-status/STATUS.md` still reports `vedalang-uet` items as open,
  while `bd list` reports zero open issues.
- `docs/vedalang-user/tutorial.md` and
  `docs/vedalang-design-agent/known_answer_tests.md` contain hardcoded
  machine-local absolute paths (`/Users/gre538/...`).

### Code Quality

- `uv run ruff check . --exclude xl2times --exclude times` fails with
  `F821 Undefined name RunContext` in `vedalang/compiler/backend.py`.
- `tools/veda_dev/sankey.py` and `tools/veda_dev/times_results.py` duplicate
  `find_gdxdump` and `dump_symbol_csv` helper logic.

### Fixture & Example Hygiene

- A naive compile sweep (`vedalang compile <file> --out ...`) reports failures
  for multi-run examples because they require explicit `--run` selection.
  The examples compile successfully when iterated per declared run id.

### Agent-First Assessment

| Criterion | Score | Notes |
|-----------|-------|-------|
| Discoverability | 4/5 | Repo shape and top-level docs are clear, but status drift hurts trust. |
| Self-documenting | 4/5 | Schema and examples are strong; absolute local links reduce portability. |
| Feedback loops | 4/5 | Collect-only and lock checks are clean; Ruff regression weakens baseline. |
| Minimal ambiguity | 3/5 | Multi-run compile expectations are not explicit in hygiene scripts. |
| Clean boundaries | 3/5 | Residual `veda_run_times` CLI module blurs post-split ownership. |
| Onboarding speed | 4/5 | Good command ergonomics, with some drift in status/docs. |

Overall: **3.7 / 5**

## Recommendation

Prioritize the following in order:

1. Restore quality baseline by fixing the Ruff `RunContext` regression.
2. Re-sync `STATUS.md` with `bd` and remove hardcoded local paths from docs.
3. Clean split residue by resolving/removing dead `veda_run_times` CLI surface
   and deduplicating shared GDX helper utilities.
