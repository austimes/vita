# Toy Industry Vita Experiment Notes

This note captures the reproducible `vita run` + `vita diff` loop for the current
`toy_industry` extension experiment and records the interpretation tied to generated
artifacts.

## Commands Executed

```bash
mkdir -p runs/toy_industry/{baseline,co2_cap_loose,co2_cap_mid,co2_cap_tight,high_gas_price,high_gas_price_co2_cap_mid,high_h2_price_co2_cap_mid,diffs}

uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/baseline --json | tee runs/toy_industry/baseline/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_co2_cap_loose.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/co2_cap_loose --json | tee runs/toy_industry/co2_cap_loose/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_co2_cap_mid.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/co2_cap_mid --json | tee runs/toy_industry/co2_cap_mid/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_co2_cap_tight.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/co2_cap_tight --json | tee runs/toy_industry/co2_cap_tight/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_gas_price.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_gas_price --json | tee runs/toy_industry/high_gas_price/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_gas_price_co2_cap_mid.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_gas_price_co2_cap_mid --json | tee runs/toy_industry/high_gas_price_co2_cap_mid/run.json >/dev/null
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_h2_price_co2_cap_mid.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_h2_price_co2_cap_mid --json | tee runs/toy_industry/high_h2_price_co2_cap_mid/run.json >/dev/null

uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap_loose --json > runs/toy_industry/diffs/baseline_vs_co2_cap_loose.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap_mid --json > runs/toy_industry/diffs/baseline_vs_co2_cap_mid.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap_tight --json > runs/toy_industry/diffs/baseline_vs_co2_cap_tight.json
uv run vita diff runs/toy_industry/co2_cap_loose runs/toy_industry/co2_cap_mid --json > runs/toy_industry/diffs/co2_cap_loose_vs_co2_cap_mid.json
uv run vita diff runs/toy_industry/co2_cap_mid runs/toy_industry/co2_cap_tight --json > runs/toy_industry/diffs/co2_cap_mid_vs_co2_cap_tight.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_gas_price --json > runs/toy_industry/diffs/baseline_vs_high_gas_price.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_gas_price_co2_cap_mid --json > runs/toy_industry/diffs/baseline_vs_high_gas_price_co2_cap_mid.json
uv run vita diff runs/toy_industry/co2_cap_mid runs/toy_industry/high_gas_price_co2_cap_mid --json > runs/toy_industry/diffs/co2_cap_mid_vs_high_gas_price_co2_cap_mid.json
uv run vita diff runs/toy_industry/co2_cap_mid runs/toy_industry/high_h2_price_co2_cap_mid --json > runs/toy_industry/diffs/co2_cap_mid_vs_high_h2_price_co2_cap_mid.json
```

## Run Summary

| Run | Objective | Solver Status | Artifact Directory |
|---|---:|---|---|
| baseline (`single_2025`) | 195.5915 | optimal | `runs/toy_industry/baseline` |
| co2_cap_loose | 211.0330 | optimal | `runs/toy_industry/co2_cap_loose` |
| co2_cap_mid | 234.1951 | optimal | `runs/toy_industry/co2_cap_mid` |
| co2_cap_tight | 257.3573 | optimal | `runs/toy_industry/co2_cap_tight` |
| high_gas_price | 452.9488 | optimal | `runs/toy_industry/high_gas_price` |
| high_gas_price_co2_cap_mid | 362.8737 | optimal | `runs/toy_industry/high_gas_price_co2_cap_mid` |
| high_h2_price_co2_cap_mid | 280.5194 | optimal | `runs/toy_industry/high_h2_price_co2_cap_mid` |

## Objective Delta Summary

| Diff | Δ Objective | % Δ Objective |
|---|---:|---:|
| baseline vs co2_cap_loose | +15.4414 | +7.89% |
| baseline vs co2_cap_mid | +38.6036 | +19.74% |
| baseline vs co2_cap_tight | +61.7657 | +31.58% |
| co2_cap_loose vs co2_cap_mid | +23.1622 | +10.98% |
| co2_cap_mid vs co2_cap_tight | +23.1622 | +9.89% |
| baseline vs high_gas_price | +257.3573 | +131.58% |
| baseline vs high_gas_price_co2_cap_mid | +167.2822 | +85.53% |
| co2_cap_mid vs high_gas_price_co2_cap_mid | +128.6786 | +54.95% |
| co2_cap_mid vs high_h2_price_co2_cap_mid | +46.3243 | +19.78% |

## Extension Checks

| Extension Focus | Check | Result |
|---|---|---|
| A: Cap ladder | Monotonic objective increase from `co2_cap_loose -> co2_cap_mid -> co2_cap_tight` | Pass |
| B: Driver attribution | `baseline_vs_high_gas_price` objective delta exceeds `baseline_vs_co2_cap_mid` | Pass |
| B: Interaction | Combined case (`high_gas_price_co2_cap_mid`) remains below pure high gas price stress | Pass |
| C: Hydrogen marginal | `co2_cap_mid_vs_high_h2_price_co2_cap_mid` is non-zero and isolates H2 stress under binding policy proxy | Pass |

## Extracted Switching Tables

| Run | `var_act` rows | `var_ncap` rows | `var_cap` rows | `var_flo` rows | `var_flo_source` |
|---|---:|---:|---:|---:|---|
| baseline | 3 | 2 | 2 | 3 | `PAR_FLOM` |
| co2_cap_loose | 3 | 3 | 3 | 3 | `PAR_FLOM` |
| co2_cap_mid | 3 | 3 | 3 | 3 | `PAR_FLOM` |
| co2_cap_tight | 3 | 3 | 3 | 3 | `PAR_FLOM` |
| high_gas_price | 3 | 2 | 2 | 3 | `PAR_FLOM` |
| high_gas_price_co2_cap_mid | 3 | 3 | 3 | 3 | `PAR_FLOM` |
| high_h2_price_co2_cap_mid | 3 | 3 | 3 | 3 | `PAR_FLOM` |

## Diff Interpretation

| Diff | Switching-Level Reading |
|---|---|
| baseline vs co2_cap_mid | `var_ncap`/`var_cap` each add one row (`GAS_BOIL`, baseline 0 → variant 50). |
| baseline vs high_gas_price | Objective rises with no row-level changes across switching tables. |
| co2_cap_mid vs high_h2_price_co2_cap_mid | Objective rises with no row-level `var_ncap`/`var_cap` deltas in current extraction payload. |

All objective movement in the current extraction payload appears under
`objective_breakdown.OBJINV`.

## Capacity Delta Detail (baseline vs co2_cap_mid)

```text
Metric: var_ncap
  process: PRC_FLT_HEAT_SUP_FLEET_GAS_BOIL
  baseline_level: 0.0
  variant_level: 50.0
  delta_level: +50.0

Metric: var_cap
  process: PRC_FLT_HEAT_SUP_FLEET_GAS_BOIL
  baseline_level: 0.0
  variant_level: 50.0
  delta_level: +50.0
```

## Current Limitation

Direct ACT_BND policy authoring is not yet exposed on the current public VedaLang
surface. The extension ladder uses canonical `.veda.yaml` policy proxies (residual gas
stock clamp + near-zero gas new build). Switching extraction remains mostly parameter-
level (`PAR_FLOM`) in this toy setup, so objective movement is currently the most stable
signal for extension ranking.
