# Eval Extra-Flag Calibration (2026-02-27)

Run artifact:
- `tmp/evals/eval-calibration-ci-20260227.json`
- command: `uv run vedalang-dev eval run --profile ci --no-judge --progress --max-concurrency 4 --no-cache --cache tmp/evals/cache-calibration-ci.json --out tmp/evals/eval-calibration-ci-20260227.json`

## Extra-code frequency (CI profile)

- `UNIT_OTHER`: 28
- `UNIT_INVESTMENT_COST_DENOM_MISMATCH`: 9
- `STR_FUEL_PATHWAY_ROLE`: 5
- `UNIT_BASIS_MISSING`: 4
- `STR_AMBIGUOUS_VARIANT_NAMING`: 1
- `UNIT_CAPACITY_DENOM_MISMATCH`: 1

## Adjudication

### Fixture/label gaps (updated)

- `s03` emitted `STR_FUEL_PATHWAY_ROLE` repeatedly.
  - Fixture contains fuel-pathway role split (`provide_heat_from_power`, `provide_heat_from_gas`), so this is a real additional structural issue in that case.
  - Action: add `STR_FUEL_PATHWAY_ROLE` as expected-present label for `s03`.

- `u05` (`heat_bad_capacity_denom_1`) repeatedly emitted `UNIT_INVESTMENT_COST_DENOM_MISMATCH`.
  - Fixture value is `investment_cost: "40 MAUD24/Bvkm/yr"` with role capacity `GW`; this is an investment-cost denominator mismatch.
  - Action: relabel expected-present from `UNIT_CAPACITY_DENOM_MISMATCH` to `UNIT_INVESTMENT_COST_DENOM_MISMATCH` and add `UNIT_CAPACITY_DENOM_MISMATCH` as expected-absent control.

- `u15` (`steam_bad_capacity_denom_1`) has the same pattern in deep profile.
  - Action: relabel expected-present to `UNIT_INVESTMENT_COST_DENOM_MISMATCH` and add `UNIT_CAPACITY_DENOM_MISMATCH` expected-absent control.

- `s02` had one `STR_AMBIGUOUS_VARIANT_NAMING` extra from `phantom_heater` naming.
  - Action: rename variant id to `heat_service_device` to avoid accidental naming ambiguity confound in zero-input test.

### Likely linter over-flagging (not fixture defects)

- `UNIT_OTHER` findings in `u01/u02/u03/u04/u05/u06` are mostly advisory/speculative:
  - cap-to-activity reminders,
  - "possible" HHV/LHV caveats despite explicit basis,
  - absolute `lhv_mj_per_unit/hhv_mj_per_unit` interpretation inconsistent with current modeling guidance (ratio-focused use).
- These should not dominate benchmark accuracy/cost signal.
- Tracked by: `vedalang-3a5`.

### Ambiguous case needing benchmark policy decision

- `u06` (`mobility_clean_1`) recurrent extras argue missing explicit PJ<->Bvkm coefficient anchor.
- Benchmark policy is unclear: should efficiency-only be accepted for energy->service mappings, or should coefficient anchors be required?
- Tracked by: `vedalang-9zk`.

### Scoring caveat discovered

- Component-scoped units cases currently use a source-level deterministic parity signal, which can be unrelated to the target component and distort deterministic score.
- Tracked by: `vedalang-cts`.

### Runtime caveat discovered

- Severe latency outliers correlate with large output/reasoning token volumes, especially on high effort.
- Tracked by: `vedalang-91p`.

