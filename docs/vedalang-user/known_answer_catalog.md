# Known-Answer Solver Suite Catalog

This catalog is the modeler-facing reference for solver-backed known-answer
tests. It tracks what each fixture validates and shows the authored VedaLang to
VEDA/TIMES mapping used by solved assertions.

Status values below reflect current `bd` state as of 2026-03-14.

## Current Implemented Tests

| KA ID | Test | Fixture(s) | Validated behavior | Solved-output assertion | Current status |
|---|---|---|---|---|---|
| KA01 | `test_ka01_base_activity_is_stable` | `ka01_gas_supply_base.veda.yaml` | Baseline gas-supply activity from authored stock in a single-region run | `VAR_ACT` level for process containing `GAS_SUPPLY` at `year=2020` is `3.1536` (`pytest.approx`) and `>= 3.0` | Implemented (`vedalang-rh9.2.1` closed) |
| KA02 | `test_ka02_double_capacity_doubles_supply_activity` | `ka01_gas_supply_base.veda.yaml` + `ka02_gas_supply_double.veda.yaml` | Doubling gas-supply stock doubles solved supply activity | KA02 variant `VAR_ACT` level for `GAS_SUPPLY` is `6.3072` (`pytest.approx`), and `(KA02 / KA01) == 2.0` | Implemented (`vedalang-rh9.2.1` + `vedalang-rh9.2.3` closed) |
| KA03 | `test_ka03_emissions_fixture_preserves_supply_activity` | `ka03_emissions_factor.veda.yaml` | Emission-factor authoring survives lowering while the fixture still produces deterministic solved activity | Solved `VAR_ACT` for `GAS_SUPPLY` remains `3.1536`; compiled `~FI_T` `ENV_ACT` coefficient for same process is `0.056` | Implemented (`vedalang-rh9.2.2`) |
| KA04 | `test_ka04_merit_order_prefers_zero_cost_supply` | `ka04_merit_order_dispatch.veda.yaml` | Costed fallback gas supply is suppressed while zero-cost supply carries dispatch | `GAS_CHEAP` activity `>= 3.0`; `GAS_EXP` is near zero; cheap share across `{GAS_CHEAP, GAS_EXP}` is `>= 0.99` | Implemented (`vedalang-rh9.2.2`) |
| KA06 | `test_ka06_stock_sufficient_keeps_new_capacity_near_zero` | `ka06_stock_sufficient.veda.yaml` | Stock-sufficient supply case solves above the authored demand-proxy threshold without investment expansion | `VAR_ACT(FSUP,2020)` is `0.94608` (`>= 0.8`) and `VAR_NCAP(FSUP,2020)` remains near zero | Implemented (`vedalang-rh9.3.1`) |
| KA07 | `test_ka07_demand_spike_preserves_shortfall_signal_without_new_build` | `ka06_stock_sufficient.veda.yaml` + `ka07_demand_spike.veda.yaml` | Low-stock demand-spike variant keeps a deterministic solved shortfall signal under the same demand proxy | `VAR_ACT(FSUP,2020)` drops from `0.94608` to `0.15768` (`6x` lower), remains `< 0.8`, and `VAR_NCAP` stays near zero | Implemented (`vedalang-rh9.3.1`) |
| KA08 | `test_ka08_build_limit_tight_suppresses_backup_build` | `ka08_build_limit_loose.veda.yaml` + `ka08_build_limit_tight.veda.yaml` | Tight fallback build limit suppresses backup activity/build versus loose-limit case | Loose case has `IFB` activity (`8.0`) with `VAR_NCAP(IFB)` around `153.678`; tight case keeps `IFB` near zero with `VAR_NCAP ~= 0` | Implemented (`vedalang-rh9.3.2`) |
| KA09 | `test_ka09_zone_opportunity_shift_changes_active_process_class` | `ka09_zone_opportunity_loose.veda.yaml` + `ka09_zone_opportunity_tight.veda.yaml` | Zone-opportunity toggle shifts solved activity between zone-opportunity and role-instance process classes | Loose case activates `ZONE_OPPORTUNITY` (`8.0`) while tight case activates `ROLE_INSTANCE_FS_R1_IFB` (`8.0`) | Implemented (`vedalang-rh9.3.2`) |
| KA10 | `test_ka10_network_transfer_flip_shifts_active_region` | `ka10_network_transfer_open.veda.yaml` + `ka10_network_transfer_constrained.veda.yaml` | Two-region network transfer direction controls which region supplies solved gas activity | Open variant dispatch is region `B` (`B_G_B_GB`) and constrained variant flips dispatch to region `A` (`A_G_A_GA`), each at `6.3072` with opposite region near zero | Implemented (`vedalang-rh9.4.1`) |
| KA11 | `test_ka11_fleet_distribution_respects_weighted_allocation` | `ka11_fleet_distribution_base.veda.yaml` + `ka11_fleet_distribution_stress.veda.yaml` | Weighted fleet allocation remains directional across two regions and under stress stock scaling | Region-scoped `VAR_ACT` keeps a `~3:1` (`NTH:STH`) ratio in both variants, north share stays `>= 0.74`, and stress levels are `>1.9x` baseline in both regions | Implemented (`vedalang-rh9.4.2`) |
| KA12 | `test_ka12_temporal_growth_scales_supply_activity` | `ka12_temporal_growth_annual.veda.yaml` | Annual-growth base-year adjustment scales solved activity over a ten-year run shift | `VAR_ACT(GAS_SUPPLY, 2030)` is `8.17962622217` and `(KA12 / KA01-2020 baseline)` equals `1.1^10` | Implemented (`vedalang-rh9.4.3`) |
| KA14 | `test_ka14_run_selection_changes_solved_activity` | `ka14_run_selection_multi_run.veda.yaml` | Selecting different run IDs from one multi-run source yields deterministic solved-output differences | `run=reg1_2020` gives `3.1536`, `run=reg1_2030` gives `6.3072`, and ratio is exactly `2.0` | Implemented (`vedalang-rh9.4.3`) |

## VedaLang To VEDA/TIMES Mapping

The suite validates model semantics through the full path:

`VedaLang source -> CSIR/CPIR -> TableIR/Excel -> xl2times DD -> TIMES solve -> GDX symbols`

| VedaLang object/type | Compiled VEDA/TIMES artifacts in KA fixtures | Solved symbols used by assertions |
|---|---|---|
| `commodities[*]` with `type` + `energy_form` | `syssettings.xlsx` `~FI_COMM` rows with canonical `csets` membership (`NRG`, `DEM`, `ENV`) | `VAR_ACT` activity rows for process behavior, plus compiled-table checks for `ENV_ACT` where applicable |
| `technology_roles[*]` + `technologies[*]` | `vt_*` `~FI_PROCESS` process definitions and `~FI_T` conversion rows (`commodity-in`, `commodity-out`, `eff`, `ncap_tlife`, `act_cost`) | `VAR_ACT` for dispatched process activity and share calculations |
| `technologies[*].emissions[*].factor` | `~FI_T` rows with `attribute: ENV_ACT` and emission commodity symbol | KA03 asserts the emitted `ENV_ACT` coefficient value and a non-zero solved activity on the same process |
| `fleets[*].distribution` with `method: proportional` + `weight_by` | Region-specific `~TFM_INS` `PRC_RESID` rows for allocated fleet stock | KA11 asserts region-scoped `VAR_ACT` ratio/share and stress-directional scaling |
| `facilities[*].stock.items[*]` with `metric: installed_capacity` | `vt_*` `~TFM_INS` rows with `attribute: PRC_RESID` at run base-year after adjustment | `VAR_ACT` behavior under deterministic known-answer fixture conditions |
| `facilities[*].new_build_limits[*].max_new_capacity` | `vt_*` `~TFM_INS` rows with `attribute: NCAP_BND` on the instantiated supply process | Near-zero `VAR_NCAP` checks in KA06/KA07 confirm explicit no-build solved behavior in the current fixture envelope |
| `facilities[*].stock.items[*]` with `metric: annual_activity` on demand devices | Demand-proxy stock lowered through `PRC_RESID` on the demand-side process | KA06/KA07 compare solved supply-side `VAR_ACT` against the authored `0.80 PJ/year` proxy threshold |
| `zone_opportunities[*].max_new_capacity` | Zone-opportunity process rows lowered with opportunity-bound capacity constraints | KA09 checks class-shift behavior via solved activity on `ZONE_OPPORTUNITY` versus role-instance fallback processes |
| `networks[*].links[*]` directional transfer links | `suppxls/trades` `~TRADELINKS` topology plus generated trade processes in solved GDX | KA10 asserts region-scoped `VAR_ACT` supplier dominance flips between open and constrained network directions |
| `facilities[*].stock.adjust_to_base_year.using` with `annual_growth` | Run-specific adjusted stock in CSIR/CPIR lowered to `PRC_RESID` for selected base year | KA12 solved activity ratio check against `1.1^10` baseline scaling |
| `temporal_index_series[*]` + run-specific base year | Index-ratio adjustment of stock before lowering for selected run (`reg1_2020` vs `reg1_2030`) | KA14 solved-level delta and ratio assertions across selected run IDs |
| `runs[*]` (`base_year`, `region_partition`) | `syssettings.xlsx` run/year context (`~STARTYEAR`, `~BOOKREGIONS_MAP`) and region-scoped DD generation | Year/region slices in `VAR_ACT` rows used by assertions |

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
3. Test asserts the emitted `ENV_ACT` coefficient equals the authored factor while solved gas-supply activity remains non-zero and deterministic.

### KA04 Merit-Order Dispatch Suppression

1. KA04 defines two gas-supply technologies in one role: `gas_cheap` (`variable_om: 0`) and `gas_exp` (`variable_om: 10`).
2. Both are present in fixture stock, but the costed fallback is dominated by the zero-cost option in solve results.
3. Test asserts cheap activity, expensive near-zero activity, and a `>= 99%` cheap dispatch share.

### KA06 Stock-Sufficient No-Build

1. KA06 defines a two-process chain (`FSUP` supply, `FDEM` demand-proxy) with `FSUP` stock at `30 MW` and demand-proxy set at `0.80 PJ/year`.
2. `new_build_limits` remains present on `FSUP`, but the solved activity signal (`0.94608`) already exceeds the demand-proxy threshold.
3. Solver assertions verify `VAR_ACT(FSUP,2020) >= 0.8` and near-zero `VAR_NCAP` on the same process.

### KA07 Demand-Spike Shortfall Signal

1. KA07 reuses KA06 structure but lowers `FSUP` stock to `5 MW` while keeping the same `0.80 PJ/year` demand proxy.
2. The solved supply activity drops to `0.15768`, producing a stable shortfall signal relative to the proxy threshold.
3. Solver assertions verify the `6x` activity drop from KA06 and maintain near-zero `VAR_NCAP` under the current backend semantics.

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

### KA12 Annual-Growth Temporal Scaling

1. KA12 applies `adjust_to_base_year.using.kind: annual_growth` with `rate: 10 %/year` to both supply and conversion stocks observed in 2020.
2. Run selection at `base_year=2030` scales stock by `1.1^10`, then lowers to 2030 `PRC_RESID` values.
3. Solver assertion checks both absolute 2030 `VAR_ACT` and ratio consistency versus the KA01 2020 baseline.

### KA14 Multi-Run Selection Semantics

1. KA14 defines one source file with two runs (`reg1_2020`, `reg1_2030`) and one `temporal_index_series` (`2020: 1.0`, `2030: 2.0`).
2. Each run selection applies a different stock adjustment ratio before lowering to VEDA tables.
3. Solver assertions verify run-specific solved outputs and a deterministic `2x` ratio between selected runs.

## Current Caveat

1. A strict solved emissions-flow ratio check for KA03 remains blocked by solved-symbol extraction limits (`VAR_FLO` coverage) and is tracked as follow-on known-answer work.

## Where To Find The Code

1. Core known-answer tests: `tests/test_known_answer_core.py`
2. Harness contract/reference smoke: `docs/vedalang-design-agent/known_answer_tests.md` and `tests/test_known_answer_reference.py`
3. Fixture files: `vedalang/examples/known_answer/`
4. Cross-reference mapping guidance: `docs/vedalang-user/attribute_mapping.md`
