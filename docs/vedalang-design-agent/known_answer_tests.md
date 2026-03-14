# Known-Answer Solver Test Harness

This document defines the contract for solver-backed known-answer tests.

For the modeler-facing catalog (KA coverage/status plus VedaLang → VEDA/TIMES
mapping validated by solved outputs), see
[`docs/vedalang-user/known_answer_catalog.md`](file:///Users/gre538/code/vedalang/docs/vedalang-user/known_answer_catalog.md).

## Fixture Convention

1. Place known-answer fixtures under `vedalang/examples/known_answer/` as this suite grows.
2. Keep fixtures intentionally small and deterministic.
3. Prefer clean arithmetic (for example, `0.5`, `2.0`) and large cost gaps to avoid tie-driven flakiness.
4. For run-selection coverage, prefer one fixture with multiple `runs` entries and deterministic expected deltas between run IDs.

## Harness API

1. Use [`tests/helpers/solver_harness.py`](file:///Users/gre538/code/vedalang/tests/helpers/solver_harness.py) for full pipeline execution and stable artifact discovery.
2. Use `detect_solver_prerequisites()` to decide whether to skip solver-backed tests when prerequisites are unavailable.
3. Use `run_solver_pipeline_fixture()` to run `.veda.yaml` sources through the full solver path and retrieve GDX/diagnostics artifacts.
4. For fleet-weighting coverage, pass deterministic compile-time `measure_weights`/`custom_weights` through `run_solver_pipeline_fixture()` instead of writing ad-hoc compile wrappers inside tests.
5. For CI artifact bundles, set `VEDALANG_SOLVER_ARTIFACTS_DIR` so the harness copies each pipeline `work_dir` plus `summary.json`/`pipeline_result.json` into a stable upload path.

## Pytest Tiering

1. All solver-backed tests carry `@pytest.mark.solver` and `@pytest.mark.solver_full`.
2. PR-fast tests add `@pytest.mark.solver_fast` on top of `solver_full`.
3. Fast tier command: `uv run pytest -m "solver and solver_fast" tests/test_known_answer_core.py tests/test_known_answer_reference.py tests/test_solver_harness.py`.
4. Full tier command: `uv run pytest -m "solver and solver_full" tests/test_known_answer_core.py tests/test_known_answer_reference.py tests/test_solver_harness.py`.
5. Collection guardrails in [`tests/conftest.py`](file:///Users/gre538/code/vedalang/tests/conftest.py) enforce that every `solver` test is at least `solver_full` classified.

## Results Extraction

1. Use [`tools/veda_dev/times_results.py`](file:///Users/gre538/code/vedalang/tools/veda_dev/times_results.py) for GDX extraction.
2. Pass `limit=0` to disable truncation for deterministic test assertions.
3. Use `include_flows=True` when tests assert efficiency or commodity-ratio behavior.

## Semantic Assertions

1. Use [`tests/helpers/solver_assertions.py`](file:///Users/gre538/code/vedalang/tests/helpers/solver_assertions.py) instead of ad-hoc numeric checks.
2. Available helpers include activity/new-capacity thresholds, near-zero checks, flow ratios, and process-share checks.
3. Assertion failures are expected to include process/year/region context.
4. For temporal-growth and run-selection tests, assert solved-level ratios/deltas directly from extracted `VAR_ACT` values.
5. Keep KA03 emissions-flow ratio caveats documented when `VAR_FLO` extraction limitations block strict solved-flow assertions.
6. For network-direction known-answer tests (KA10), use region-scoped process assertions so directional dispatch flips are validated from solved `VAR_ACT` rows.
7. For constraint-edge diagnostics tests, include artifact references (`diagnostics_json`, `lst_file`, `work_dir`) in assertion context so failures are actionable in CI logs.

## Tolerance And Determinism Policy

1. Prefer directional solved-behavior assertions (ratios, dominance flips, near-zero suppression) over objective-value equality checks.
2. Use strict `pytest.approx` checks only for intentionally deterministic known-answer anchor values (for example KA01/KA02/KA12/KA14 activity anchors).
3. Keep near-zero checks explicit (`assert_activity_near_zero`, `assert_new_capacity_near_zero`) with small absolute tolerances (`1e-6` unless model semantics require looser bounds).
4. Avoid fragile assertions on symbols known to be extraction-limited (`VAR_FLO` caveat for KA03 emissions ratio).
5. When adding fixtures, keep arithmetic simple and cost deltas large to avoid tie-driven nondeterminism.
6. When solver runs fail, rely on captured diagnostics artifacts (`*_gams_diagnostics.json`, `.lst`, pipeline result JSON) before changing tolerances.

## Reference Test

1. [`tests/test_known_answer_reference.py`](file:///Users/gre538/code/vedalang/tests/test_known_answer_reference.py) demonstrates harness -> extraction -> semantic assertion in one smoke test.

## Test Catalog

See [`docs/vedalang-user/known_answer_catalog.md`](file:///Users/gre538/code/vedalang/docs/vedalang-user/known_answer_catalog.md) for the per-test catalog with VedaLang→VEDA/TIMES mapping details, assertion summaries, and status tracking.
