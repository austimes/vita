# Toy Industry Vita Experiment Notes

This note captures the reproducible `vita run` + `vita diff` loop for the current
`toy_industry` example and records the interpretation tied to generated artifacts.

## Commands Executed

```bash
mkdir -p runs/toy_industry/{baseline,co2_cap,high_gas_capex,high_h2_capex,diffs}

uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/baseline --json | tee runs/toy_industry/baseline/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run s25_co2_cap --no-sankey --out runs/toy_industry/co2_cap --json | tee runs/toy_industry/co2_cap/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_gas_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_gas_capex --json | tee runs/toy_industry/high_gas_capex/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_h2_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_h2_capex --json | tee runs/toy_industry/high_h2_capex/run.json >/dev/null

uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap --json > runs/toy_industry/diffs/baseline_vs_co2_cap.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_gas_capex --json > runs/toy_industry/diffs/baseline_vs_high_gas_capex.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_h2_capex --json > runs/toy_industry/diffs/baseline_vs_high_h2_capex.json
```

## Run Summary

| Run | Objective | Solver Status | Artifact Directory |
|---|---:|---|---|
| baseline (`single_2025`) | 195.5915 | optimal | `runs/toy_industry/baseline` |
| co2_cap (`s25_co2_cap`) | 195.5915 | optimal | `runs/toy_industry/co2_cap` |
| high_gas_capex | 452.9488 | optimal | `runs/toy_industry/high_gas_capex` |
| high_h2_capex | 241.9158 | optimal | `runs/toy_industry/high_h2_capex` |

## Extracted Switching Tables

| Run | `var_act` rows | `var_ncap` rows | `var_cap` rows | `var_flo` rows | `var_flo_source` |
|---|---:|---:|---:|---:|---|
| baseline | 3 | 2 | 2 | 3 | `PAR_FLOM` |
| co2_cap | 3 | 2 | 2 | 3 | `PAR_FLOM` |
| high_gas_capex | 3 | 2 | 2 | 3 | `PAR_FLOM` |
| high_h2_capex | 3 | 2 | 2 | 3 | `PAR_FLOM` |

## Diff Interpretation

| Diff | Δ Objective | % Δ Objective | Switching-Level Reading |
|---|---:|---:|---|
| baseline vs co2_cap | +0.0000 | +0.00% | No row-level changes across `var_act`/`var_ncap`/`var_cap`/`var_flo`. |
| baseline vs high_gas_capex | +257.3573 | +131.58% | Objective rises with no switching-table row deltas in current toy shape. |
| baseline vs high_h2_capex | +46.3243 | +23.68% | `var_ncap` and `var_cap` each show one changed row (`H2_BOIL`) with `+180 MW` (100 → 280, +180%). |

All objective movement in the current extraction payload appears under
`objective_breakdown.OBJINV`.

## Capacity Delta Detail (baseline vs high_h2_capex)

```text
Metric: var_ncap
  process: PRC_P_ROLE_INSTANCE_HEAT_SUP_FLEET_SINGLE_H2_BOIL_1CE78447
  baseline_level: 100.0
  variant_level: 280.0
  delta_level: +180.0

Metric: var_cap
  process: PRC_P_ROLE_INSTANCE_HEAT_SUP_FLEET_SINGLE_H2_BOIL_1CE78447
  baseline_level: 100.0
  variant_level: 280.0
  delta_level: +180.0
```

## Current Limitation

Switching extraction is now populated, but this toy setup still produces identical
`var_act` and `var_flo` tables across all three baseline-vs-variant diffs. The
strongest switching signal in this run set is capacity scaling (`var_ncap`/`var_cap`)
for the high-H2-capex case.
