# Known-Answer Solver Suite Catalog

This catalog is the modeler-facing reference for solver-backed known-answer
tests. It tracks what each fixture validates and shows the authored VedaLang to
VEDA/TIMES mapping used by solved assertions.

Status values below reflect current `bd` state as of 2026-03-15.

## Current Implemented Tests

| KA ID | Test | Fixture(s) | Validated behavior | Solved-output assertion | Current status |
|---|---|---|---|---|---|
| KA01 | `test_ka01_base_activity_is_stable` | `ka01_gas_supply_base.veda.yaml` | Baseline gas-supply activity from authored stock in a single-region run | `VAR_ACT` level for process containing `GAS_SUPPLY` at `year=2020` is `3.1536` (`pytest.approx`) and `>= 3.0` | Implemented (`vedalang-rh9.2.1` closed) |
| KA02 | `test_ka02_double_capacity_doubles_supply_activity` | `ka01_gas_supply_base.veda.yaml` + `ka02_gas_supply_double.veda.yaml` | Doubling gas-supply stock doubles solved supply activity | KA02 variant `VAR_ACT` level for `GAS_SUPPLY` is `6.3072` (`pytest.approx`), and `(KA02 / KA01) == 2.0` | Implemented (`vedalang-rh9.2.1` + `vedalang-rh9.2.3` closed) |
| KA03 | `test_ka03_emissions_fixture_preserves_supply_activity` | `ka03_emissions_factor.veda.yaml` | Emission-factor authoring survives lowering while the fixture still produces deterministic solved activity and solved flow observability | Solved `VAR_ACT(GAS_SUPPLY,2020)` remains `3.1536`; solved natural-gas flow/activity ratio is `1.0` (flow source `VAR_FLO` or `PAR_FLO`); implied emissions from solved flow match `activity * 0.056`; compiled `~FI_T` `ENV_ACT` remains `0.056` | Implemented (`vedalang-rh9.2.2`, upgraded by `vedalang-wvu.2`) |
| KA04 | `test_ka04_merit_order_prefers_zero_cost_supply` | `ka04_merit_order_dispatch.veda.yaml` | Costed fallback gas supply is suppressed while zero-cost supply carries dispatch | `GAS_CHEAP` activity `>= 3.0`; `GAS_EXP` is near zero; cheap share across `{GAS_CHEAP, GAS_EXP}` is `>= 0.99` | Implemented (`vedalang-rh9.2.2`) |
| KA05 | `test_ka02_double_capacity_doubles_supply_activity` | `ka01_gas_supply_base.veda.yaml` + `ka02_gas_supply_double.veda.yaml` | Parameter-flip directional behavior is validated through the KA01/KA02 paired fixture delta (no standalone KA05 fixture file) | `(KA02 / KA01) == 2.0` on solved `VAR_ACT(GAS_SUPPLY)` confirms deterministic flip magnitude | Implemented (`vedalang-rh9.2.3` closed; traceability is carried by the KA02 paired-variant test) |
| KA06 | `test_ka06_stock_sufficient_keeps_new_capacity_near_zero` | `ka06_stock_sufficient.veda.yaml` | Stock-sufficient supply case meets the authored demand-proxy activity level without investment expansion | `VAR_ACT(FSUP,2020)` and `VAR_ACT(FDEM,2020)` are `0.8` (`>= 0.79`) and `VAR_NCAP(FSUP,2020)` remains near zero | Implemented (`vedalang-rh9.3.1`) |
| KA07 | `test_ka07_demand_spike_triggers_positive_new_capacity` | `ka06_stock_sufficient.veda.yaml` + `ka07_demand_spike.veda.yaml` | Demand-spike variant increases solved activity and triggers positive solved new capacity on the same supply process | `VAR_ACT(FSUP,2020)` rises from `0.8` to `1.2` (`1.5x`), and spike-case `VAR_NCAP(FSUP,2020)` is `8.0517503805175` (`>= 8.0`) | Implemented (`vedalang-rh9.3.1`) |
| KA08 | `test_ka08_build_limit_tight_suppresses_backup_build` | `ka08_build_limit_loose.veda.yaml` + `ka08_build_limit_tight.veda.yaml` | Tight fallback build limit suppresses backup activity/build versus loose-limit case | Loose case has `IFB` activity (`8.0`) with `VAR_NCAP(IFB)` around `153.678`; tight case keeps `IFB` near zero with `VAR_NCAP ~= 0` | Implemented (`vedalang-rh9.3.2`) |
| KA09 | `test_ka09_zone_opportunity_shift_changes_active_process_class` | `ka09_zone_opportunity_loose.veda.yaml` + `ka09_zone_opportunity_tight.veda.yaml` | Zone-opportunity toggle shifts solved activity between zone-opportunity and role-instance process classes | Loose case activates `ZONE_OPPORTUNITY` (`8.0`) while tight case activates `ROLE_INSTANCE_FS_R1_IFB` (`8.0`) | Implemented (`vedalang-rh9.3.2`) |
| KA10 | `test_ka10_network_transfer_flip_shifts_active_region` | `ka10_network_transfer_open.veda.yaml` + `ka10_network_transfer_constrained.veda.yaml` | Two-region network transfer direction controls which region supplies solved gas activity | Open variant dispatch is region `B` (`B_G_B_GB`) and constrained variant flips dispatch to region `A` (`A_G_A_GA`), each at `6.3072` with opposite region near zero | Implemented (`vedalang-rh9.4.1`) |
| KA11 | `test_ka11_fleet_distribution_respects_weighted_allocation` | `ka11_fleet_distribution_base.veda.yaml` + `ka11_fleet_distribution_stress.veda.yaml` | Weighted fleet allocation remains directional across two regions and under stress stock scaling | Region-scoped `VAR_ACT` keeps a `~3:1` (`NTH:STH`) ratio in both variants, north share stays `>= 0.74`, and stress levels are `>1.9x` baseline in both regions | Implemented (`vedalang-rh9.4.2`) |
| KA12 | `test_ka12_temporal_growth_scales_supply_activity` | `ka12_temporal_growth_annual.veda.yaml` | Annual-growth base-year adjustment scales solved activity over a ten-year run shift | `VAR_ACT(GAS_SUPPLY, 2030)` is `8.17962622217` and `(KA12 / KA01-2020 baseline)` equals `1.1^10` | Implemented (`vedalang-rh9.4.3`) |
| KA13 | `test_ka13_constraint_edge_exposes_actionable_solver_diagnostics` | `ka08_build_limit_tight.veda.yaml` (stressed bound fixture) | Tight build-limit edge case now verifies solver diagnostics artifacts are populated and bound metadata is visible when constraints are active | Asserts `summary.ok`, model/solve status codes, `gams_command`/`lst_file`/diagnostics path presence, compiled `NCAP_BND(IFB)=0`, and near-zero solved `IFB` activity | Implemented (`vedalang-rh9.3.3`) |
| KA14 | `test_ka14_run_selection_changes_solved_activity` | `ka14_run_selection_multi_run.veda.yaml` | Selecting different run IDs from one multi-run source yields deterministic solved-output differences | `run=reg1_2020` gives `3.1536`, `run=reg1_2030` gives `6.3072`, and ratio is exactly `2.0` | Implemented (`vedalang-rh9.4.3`) |
| KA15 | `test_vita_run_respects_value_flow_reporting_toggle` | `ka15_value_flow_reporting_toggle.veda.yaml` | Run-scoped `reporting.value_flows` controls whether `SysSettings.xlsx` emits `~TFM_INS` `RPT_OPT(FLO,3)=1`, and whether the solver scaffold mirrors that into the selected run | Default run solves with `RPT_OPT(FLO,1)=1` and `RPT_OPT(FLO,3)=1` visible in the solved GDX; reporting-off run leaves `RPT_OPT` unset | Implemented (`vedalang-2ckt`) |

## VedaLang To VEDA/TIMES Mapping

The suite validates model semantics through the full path:

`VedaLang source -> CSIR/CPIR -> TableIR/Excel -> xl2times DD -> TIMES solve -> GDX symbols`

| VedaLang object/type | Compiled VEDA/TIMES artifacts in KA fixtures | Solved symbols used by assertions |
|---|---|---|
| `commodities[*]` with `type` + `energy_form` | `SysSettings.xlsx` `~FI_COMM` rows with canonical `csets` membership (`NRG`, `DEM`, `ENV`) | `VAR_ACT` activity rows for process behavior, plus compiled-table checks for `ENV_ACT` where applicable |
| `technology_roles[*]` + `technologies[*]` | `VT_<veda_book_name>_ALL_V1.xlsx` `~FI_PROCESS` process definitions and `~FI_T` conversion rows (`commodity-in`, `commodity-out`, `eff`, `ncap_tlife`, `act_cost`) | `VAR_ACT` for dispatched process activity and share calculations |
| `technologies[*].emissions[*].factor` | `~FI_T` rows with `attribute: ENV_ACT` and emission commodity symbol | KA03 asserts solved natural-gas flow/activity behavior (with `VAR_FLO`/`PAR_FLO` fallback), checks implied solved emissions consistency, and verifies emitted `ENV_ACT` coefficient value |
| `fleets[*].distribution` with `method: proportional` + `weight_by` | Region-specific `~TFM_INS` `PRC_RESID` rows for allocated fleet stock | KA11 asserts region-scoped `VAR_ACT` ratio/share and stress-directional scaling |
| `facilities[*].stock.items[*]` with `metric: installed_capacity` | `VT_<veda_book_name>_ALL_V1.xlsx` `~TFM_INS` rows with `attribute: PRC_RESID` at run base-year after adjustment | `VAR_ACT` behavior under deterministic known-answer fixture conditions |
| `facilities[*].new_build_limits[*].max_new_capacity` | `VT_<veda_book_name>_ALL_V1.xlsx` `~TFM_INS` rows with `attribute: NCAP_BND` on the instantiated supply process | KA06 validates no-build (`VAR_NCAP ~= 0`), KA07 validates positive-build trigger (`VAR_NCAP > 0`) under demand spike, and KA08/KA13 validate tight-bound suppression and diagnostics traceability |
| `facilities[*].stock.items[*]` with `metric: annual_activity` on demand devices | Demand-proxy stock lowered through `PRC_RESID` on the demand-side process | KA06/KA07 compare deterministic solved supply/demand activity anchors (`0.8` baseline vs `1.2` spike) and the resulting new-capacity trigger direction |
| `zone_opportunities[*].max_new_capacity` | Zone-opportunity process rows lowered with opportunity-bound capacity constraints | KA09 checks class-shift behavior via solved activity on `ZONE_OPPORTUNITY` versus role-instance fallback processes |
| `networks[*].links[*]` directional transfer links | `suppxls/trades` `~TRADELINKS` topology plus generated trade processes in solved GDX | KA10 asserts region-scoped `VAR_ACT` supplier dominance flips between open and constrained network directions |
| `facilities[*].stock.adjust_to_base_year.series` with `time_series` index refs | Run-specific adjusted stock in CSIR/CPIR lowered to `PRC_RESID` for the selected start year | KA12 solved activity ratio check against `1.1^10` baseline scaling |
| `time_series[*]` (`kind: index`) + selected run year set | Index-ratio adjustment of stock before lowering for selected run (`reg1_2020` vs `reg1_2030`) | KA14 solved-level delta and ratio assertions across selected run IDs |
| `year_sets[*]` + `runs[*]` (`year_set`, `veda_book_name`, `region_partition`, `reporting.value_flows`) | `SysSettings.xlsx` run/year context (`~STARTYEAR`, `~MILESTONEYEARS`, `~BOOKREGIONS_MAP`) plus reporting controls (`~TFM_INS` `RPT_OPT(FLO,3)=1`) and a human-readable `Reporting` tab, with the solver scaffold mirroring emitted `RPT_OPT` rows as RUN-file assignments | Year/region slices in `VAR_ACT` rows and run-scoped reporting control in solved artifacts |

## Per-Test Mapping Notes

### KA01 Baseline Gas Supply Activity

1. Authored source sets `reg1_gas_supply` stock to `100 MW` on `gas_import`.
2. Compiler lowers this to `~TFM_INS` with `attribute: PRC_RESID` for 2020.
3. Solver assertion verifies stable non-zero `VAR_ACT` on the resulting gas-supply process.

### KA02 Doubled Capacity Directionality

1. KA02 changes only gas-supply observed stock from `100 MW` to `200 MW`.
2. Compiled delta is the same process/year `PRC_RESID` level.
3. Solver assertions verify both absolute doubled activity and the `2x` ratio.

### KA03 Emissions Factor Mapping

1. KA03 adds `co2` as an `emission` commodity and an authored `emissions.factor` on `gas_import`.
2. Compiler lowers this into `~FI_T` as `ENV_ACT` for the gas-supply process.
3. Test extracts solved flows (`include_flows=True`) and asserts natural-gas flow/activity ratio consistency on the same solved process.
4. Test accepts deterministic `VAR_FLO`/`PAR_FLO` flow-source fallback, then confirms implied solved emissions (`flow * ENV_ACT`) match activity-scaled expectations while emitted `ENV_ACT` remains exactly authored.

### KA04 Merit-Order Dispatch Suppression

1. KA04 defines two gas-supply technologies in one role: `gas_cheap` (`variable_om: 0`) and `gas_exp` (`variable_om: 10`).
2. Both are present in fixture stock, but the costed fallback is dominated by the zero-cost option in solve results.
3. Test asserts cheap activity, expensive near-zero activity, and a `>= 99%` cheap dispatch share.

### KA05 Parameter-Flip Directionality Traceability

1. `vedalang-rh9.2.3` intentionally reuses the KA01/KA02 fixture pair rather than introducing a third standalone fixture file.
2. The KA02 stock delta (`100 MW -> 200 MW`) is the authored parameter flip under test.
3. `test_ka02_double_capacity_doubles_supply_activity` carries the KA05 directional acceptance check with a solved `2x` activity ratio assertion.

### KA06 Stock-Sufficient No-Build

1. KA06 defines a two-process chain (`FSUP` supply, `FDEM` demand-proxy) with `FSUP` stock at `30 MW` and demand-proxy set at `0.80 PJ/year`.
2. The solved baseline remains deterministic at `0.8` activity for both `FSUP` and `FDEM` in 2020.
3. Solver assertions verify this baseline anchor and keep `VAR_NCAP(FSUP,2020)` near zero.

### KA07 Demand-Spike Positive-Build Trigger

1. KA07 reuses KA06 structure but increases solved demand pressure so the spike variant lifts both `FSUP` and `FDEM` activity to `1.2` in 2020.
2. Relative to KA06's `0.8` baseline, this is a deterministic `1.5x` solved activity increase.
3. Solver assertions verify the activity ratio and a positive new-capacity decision on `FSUP` (`VAR_NCAP = 8.0517503805175`).

### KA08 Build-Limit Tight vs Loose

1. KA08 keeps the same demand-chain structure but changes fallback `new_build_limits` (`1 MW` loose vs `0 MW` tight).
2. In the loose variant, fallback process `IFB` is active and receives positive solved new capacity.
3. In the tight variant, fallback `IFB` remains near zero and solved `VAR_NCAP` is suppressed.

### KA09 Zone-Opportunity Class Shift

1. KA09 compares a loose fixture with explicit `zone_opportunities` against a tight fixture without that opportunity path.
2. Loose case routes solved activity through `PRC_P_ZONE_OPPORTUNITY_*` process class.
3. Tight case shifts solved activity to the role-instance fallback process (`PRC_P_ROLE_INSTANCE_FS_R1_IFB_*`).

### KA10 Network Transfer Directional Flip

1. KA10 open and constrained variants keep the same two-region gas-supply assets but reverse transfer-link direction (`B -> A` vs `A -> B`).
2. The open fixture dispatches solved gas supply through region `B` (`B_G_B_GB`) while suppressing region `A` (`A_G_A_GA`).
3. The constrained fixture flips solved dispatch dominance to region `A`, with region `B` near zero in the same run year.

### KA11 Fleet Weighted Allocation (Baseline + Stress)

1. KA11 uses a `fleet` with `distribution.method: proportional` and `weight_by: ka11_pop` over `NTH` and `STH` run regions.
2. The shared solver harness injects deterministic measure weights (`NTH=3.0`, `STH=1.0`) during compile so stock allocation is explicit and repeatable.
3. Solver assertions verify region-scoped activity keeps the expected directional split (`~3:1`, north share `>= 0.74`) and that stress-stock activity increases in both regions without ratio drift.

### KA12 Canonical Time-Series Scaling

1. KA12 applies `adjust_to_base_year.series: { series: ka12_growth }` to both supply and conversion stocks observed in 2020.
2. `time_series.ka12_growth` encodes the same 2020->2030 index ratio (`1.0 -> 2.5937424601`, equivalent to `1.1^10`) before lowering to 2030 `PRC_RESID` values.
3. Solver assertion checks both absolute 2030 `VAR_ACT` and ratio consistency versus the KA01 2020 baseline.

### KA13 Constraint-Edge Diagnostics Coverage

1. KA13 diagnostics coverage runs on the intentionally tight KA08 bound fixture (`NCAP_BND(IFB)=0`) to exercise constraint-edge behavior.
2. Assertions validate both solved behavior (near-zero `IFB` activity) and diagnostics observability (`gams_command`, `.lst`, diagnostics JSON, model/solve status codes).
3. Failure messages include artifact-path context so CI failures are debuggable without rerunning blind.

### KA14 Multi-Run Selection Semantics

1. KA14 defines one source file with two runs (`reg1_2020`, `reg1_2030`) and one canonical `time_series` index (`2020: 1.0`, `2030: 2.0`).
2. Each run selection applies a different stock adjustment ratio before lowering to VEDA tables.
3. Solver assertions verify run-specific solved outputs and a deterministic `2x` ratio between selected runs.

## Current Caveat

1. No open KA03 solved-emissions observability caveat remains; flow extraction variability is handled in-test via explicit `VAR_FLO`/`PAR_FLO` source acceptance and solved-ratio assertions.

## Where To Find The Code

1. Core known-answer tests: `tests/test_known_answer_core.py`
2. Harness contract/reference smoke: `docs/vedalang-design-agent/known_answer_tests.md`, `tests/test_known_answer_reference.py`, and `tests/test_solver_harness.py`
3. Fixture files: `vedalang/examples/known_answer/`
4. CI tiering/workflow: `.github/workflows/solver-known-answer.yml`
5. Cross-reference mapping guidance: `docs/vedalang-user/attribute_mapping.md`
