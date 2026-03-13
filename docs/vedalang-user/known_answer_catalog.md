# Known-Answer Solver Suite Catalog

This is the modeler-facing catalog for solver-backed known-answer tests. It
lists each live test, what behavior it validates, current status, and how
VedaLang constructs map to VEDA/TIMES artifacts and solved GDX outputs.

## Current Test Matrix

| KA ID | Pytest Test | Fixture(s) | What It Validates | Solved Assertion | Status |
|---|---|---|---|---|---|
| KA01 | `test_ka01_base_activity_is_stable` | `ka01_gas_supply_base.veda.yaml` | Baseline stock-to-activity behavior for a gas-supply process | `VAR_ACT(GAS_SUPPLY, 2020)` is `3.1536` (and `>= 3.0`) | Implemented |
| KA02 | `test_ka02_double_capacity_doubles_supply_activity` | `ka01_gas_supply_base.veda.yaml`, `ka02_gas_supply_double.veda.yaml` | Deterministic directional response when observed stock is doubled | `VAR_ACT` doubles from `3.1536` to `6.3072` | Implemented |
| KA03 | `test_ka03_emissions_fixture_preserves_supply_activity` | `ka03_emissions_factor.veda.yaml` | Emission-enabled technology path still solves and preserves baseline activity without emission policy forcing | `VAR_ACT(GAS_SUPPLY, 2020)` remains `3.1536` | Implemented |
| KA04 | `test_ka04_merit_order_prefers_zero_cost_supply` | `ka04_merit_order_dispatch.veda.yaml` | Cost-priority dispatch in a two-technology supply role (zero-cost beats expensive fallback) | `GAS_CHEAP` is active, `GAS_EXP` is near zero, cheap share `>= 0.99` | Implemented |
| KA05 | `test_ka02_double_capacity_doubles_supply_activity` (paired-variant clause) | Same KA01/KA02 pair | Explicit paired-variant ratio check to guard directional semantics | `(KA02 activity / KA01 activity) == 2.0` | Implemented |

## Per-Test Mapping Details

### KA01 Baseline Stock Activity

| VedaLang Input | Compiled Artifact | Solved Output Used |
|---|---|---|
| `facilities[*].stock.items[*].metric: installed_capacity` on `gas_import` | `vt_*` `~TFM_INS` row with `attribute: PRC_RESID` | `VAR_ACT` for process containing `GAS_SUPPLY` |
| `technologies[*].performance` | `vt_*` `~FI_T` efficiency/process metadata | Activity level consistency in `VAR_ACT` |
| `runs[*]` (`base_year`, `region_partition`) | `syssettings.xlsx` run/year/region scope | `year=2020` slice in `VAR_ACT` |

### KA02 Doubled Stock Delta

| VedaLang Input | Compiled Artifact Delta | Solved Output Used |
|---|---|---|
| `observed.value` changed `100 MW -> 200 MW` | `PRC_RESID` magnitude doubles for same process/year | `VAR_ACT` doubles (`6.3072 / 3.1536 = 2.0`) |

### KA03 Emission-Enabled Fixture

| VedaLang Input | Compiled Artifact | Solved Output Used |
|---|---|---|
| `commodities[*].type: emission` (`co2`) | `~FI_COMM` emission commodity row (`csets: ENV`) | Same solved process activity remains stable |
| `technologies[*].emissions[*].factor` on `gas_import` | `~FI_T` emission attribute row (`ENV_ACT`) | `VAR_ACT` baseline-equivalent value under no emission policy |
| Shared stock/run setup from KA01 | Same `PRC_RESID` baseline path | `VAR_ACT(GAS_SUPPLY, 2020) == 3.1536` |

### KA04 Merit-Order Dispatch

| VedaLang Input | Compiled Artifact | Solved Output Used |
|---|---|---|
| `technology_roles[*].technologies: [gas_cheap, gas_exp]` | Two process rows in `~FI_PROCESS` | Two candidate process IDs in `VAR_ACT`/`PRC_RESID` |
| `variable_om` (`0` vs `10 MUSD24/PJ`) | Cost coefficients on process attributes (`ACT_COST`) | `GAS_CHEAP` activity high, `GAS_EXP` activity near zero |
| Shared stock availability for both technologies | Two `PRC_RESID` rows for the same role instance boundary | Process share assertion (`cheap >= 99%`) |

## Coverage Notes

1. The current KA03 assertion validates solved behavior for emission-enabled
   fixtures under neutral policy conditions.
2. A stricter emission-flow ratio assertion (activity-to-emission solved ratio)
   remains in scope for the continuing `vedalang-rh9.2.2` work.
3. Next epics extend this catalog to capacity/constraint and spatial/run suites
   (`vedalang-rh9.3`, `vedalang-rh9.4`, `vedalang-rh9.5`).

## Where To Find The Code

1. Core suite: `tests/test_known_answer_core.py`
2. Harness and assertions: `tests/helpers/solver_harness.py`, `tests/helpers/solver_assertions.py`
3. Fixture set: `vedalang/examples/known_answer/`
4. Harness contract doc: `docs/vedalang-design-agent/known_answer_tests.md`
