# Known-Answer Solver Test Harness

This document defines the contract for solver-backed known-answer tests.

For the modeler-facing catalog (KA coverage/status plus VedaLang → VEDA/TIMES
mapping validated by solved outputs), see
[`docs/vedalang-user/known_answer_catalog.md`](file:///Users/gre538/code/vedalang/docs/vedalang-user/known_answer_catalog.md).

## Fixture Convention

1. Place known-answer fixtures under `vedalang/examples/known_answer/` as this suite grows.
2. Keep fixtures intentionally small and deterministic.
3. Prefer clean arithmetic (for example, `0.5`, `2.0`) and large cost gaps to avoid tie-driven flakiness.

## Harness API

1. Use [`tests/helpers/solver_harness.py`](file:///Users/gre538/code/vedalang/tests/helpers/solver_harness.py) for full pipeline execution and stable artifact discovery.
2. Use `detect_solver_prerequisites()` to decide whether to skip solver-backed tests when prerequisites are unavailable.
3. Use `run_solver_pipeline_fixture()` to run `.veda.yaml` sources through the full solver path and retrieve GDX/diagnostics artifacts.

## Results Extraction

1. Use [`tools/veda_dev/times_results.py`](file:///Users/gre538/code/vedalang/tools/veda_dev/times_results.py) for GDX extraction.
2. Pass `limit=0` to disable truncation for deterministic test assertions.
3. Use `include_flows=True` when tests assert efficiency or commodity-ratio behavior.

## Semantic Assertions

1. Use [`tests/helpers/solver_assertions.py`](file:///Users/gre538/code/vedalang/tests/helpers/solver_assertions.py) instead of ad-hoc numeric checks.
2. Available helpers include activity thresholds, near-zero checks, flow ratios, and process-share checks.
3. Assertion failures are expected to include process/year/region context.

## Reference Test

1. [`tests/test_known_answer_reference.py`](file:///Users/gre538/code/vedalang/tests/test_known_answer_reference.py) demonstrates harness -> extraction -> semantic assertion in one smoke test.

## Test Catalog

See [`docs/vedalang-user/known_answer_catalog.md`](file:///Users/gre538/code/vedalang/docs/vedalang-user/known_answer_catalog.md) for the per-test catalog with VedaLang→VEDA/TIMES mapping details, assertion summaries, and status tracking.
