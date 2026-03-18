# Toy Sector Examples

Compact sector-focused examples designed to prove the VedaLang pipeline
end-to-end. Accuracy of numbers is secondary; the goal is getting models
running in days.

Notes:
- The historical `2ts` and `4ts` electricity examples now use two-node and
  four-node region partitions instead of the removed public timeslice surface.
- The remaining files are direct public-surface examples using `technology_roles`,
  `facilities`, `fleets`, and `networks`.

## Running Toy Examples With Vita

Use `vita` for toy execution/diff loops and keep `vedalang` for
author/lint/validate work.

```bash
# Run any toy model (pick a run id defined in that file's `runs:` block)
uv run vita run vedalang/examples/toy_sectors/<toy_model>.veda.yaml --run <run_id> --no-sankey --out runs/<study>/<case> --json

# Compare two run artifact directories
uv run vita diff runs/<study>/baseline runs/<study>/<variant> --json
```

For toy-sector workflows, keep `--no-sankey` by default unless Sankey support
is explicitly confirmed for your run path.

---

## Toy Model Questions

Each toy model is built to answer a specific question via experiments.

### 1. Electricity & Energy (`toy_electricity_2ts` / `toy_electricity_4ts`)

**Question:** "Given an exogenous +X TWh demand uplift by 2035 and an emissions
cap, what least-cost generation + firming build is required?"

- **Type:** Endogenous optimisation
- **Experiment:** The model selects the cheapest mix of solar, wind, storage,
  gas peakers, and interconnectors to meet demand uplift from other sectors
  under a CO₂ cap.
- **Key sensitivities:** Demand uplift magnitude, emissions cap stringency,
  battery vs gas peaker cost.
- **Hints:** `COM: ELC, CO2` · `PRC: SOLAR, WIND, BATT, CCGT, OCGT` ·
  `UC: CO2_CAP` · `OUT: ΔTWh, Δpeak MW, ΔMtCO2, $/MWh`
- **Extensions:**
  - A: As the CO₂ cap tightens stepwise, which firming/build option enters
    first, and what technology is displaced first?
  - B: Which is the bigger driver of total system cost and buildout: demand
    uplift magnitude or CO₂ cap stringency?
  - C: What is the ordered marginal contribution of renewables, firming, and
    interconnection to meeting the 2035 target?

### 2. Transport (`toy_transport`)

**Question:** "If EVs reach Y% of light-vehicle km by 2035, what is ΔTWh,
Δpeak MW, and ΔMtCO2 vs baseline?"

- **Type:** Exogenous share experiment
- **Experiment:** Define an EV uptake S-curve, convert fleet-km to electricity
  demand (kWh/km), and displace petrol. Apply a charging profile to determine
  peak MW impact.
- **Key sensitivities:** EV share trajectory, kWh/km efficiency, charging
  profile (flat vs peak-biased), petrol displacement factor.
- **Hints:** `COM: ELC, PETROL, CO2` · `PRC: ICE_CAR, EV_CAR` ·
  `DM: PASS_KM` · `OUT: ΔTWh, Δpeak MW, ΔMtCO2`
- **Extensions:**
  - A: Under a CO₂ constraint, does the model reduce emissions first through
    EV uptake, efficiency, or charging-shape changes?
  - B: Is EV share or charging profile the bigger driver of Δpeak MW?
  - C: What is the ordered marginal contribution of EV uptake, vehicle
    efficiency, and smart charging to ΔTWh, Δpeak MW, and ΔMtCO2?

### 3. Built Environment (`toy_buildings`)

**Question:** "Replace Z% of gas heating with heat pumps; include one
efficiency lever. What is ΔTWh, Δpeak MW, ΔMtCO2, implied $/t?"

- **Type:** Mixed (exogenous share + endogenous efficiency)
- **Experiment:** Switch gas water/space heating to heat pumps while allowing
  an endogenous efficiency lever (e.g., building shell retrofit) to reduce
  total demand. Must capture winter peak impact.
- **Key sensitivities:** Heat pump COP, switchover rate, building efficiency
  improvement, winter peak profile shape.
- **Hints:** `COM: ELC, GAS, CO2` · `PRC: GAS_HEAT, HEAT_PUMP, RETROFIT` ·
  `DM: HEAT_PJ` · `OUT: ΔTWh, Δpeak MW, ΔMtCO2, $/t`
- **Extensions:**
  - A: When emissions tighten, which lever moves first: shell efficiency
    retrofit or gas-to-heat-pump switching?
  - B: Is carbon price or heat-pump performance the bigger driver of emissions
    reduction and cost?
  - C: What is the ordered marginal contribution of retrofit, heat pumps, and
    peak-shaping to winter peak reduction?

### 4. Industry (`toy_industry`)

**Question:** "Apply an emissions constraint to stylised industrial heat
demand; allow gas, e-heat, and H₂. What technology is selected and what is
ΔTWh and implied $/t?"

- **Type:** Endogenous optimisation
- **Experiment:** Represent a single subsector with fixed PJ demand. The model
  chooses between gas boiler, electric resistance/heat pump, or green hydrogen
  boiler under a tightening CO₂ constraint.
- **Model note:** The current run IDs are `single_2025` (baseline) and
  `s25_co2_cap` (policy-hook control). The strongest objective deltas come from
  cost-variant model files
  (`toy_industry_high_gas_capex.veda.yaml`,
  `toy_industry_high_h2_capex.veda.yaml`) diffed against the baseline run.
  Switching-table extraction is now populated for this loop (`var_act`,
  `var_ncap`, `var_cap`, `var_flo`): in current artifacts, only the
  high-H2-capex variant shows row-level switching deltas (+180 MW for H2 boiler
  in `var_ncap` and `var_cap`).
- **Key sensitivities:** H₂ delivered cost, electricity price, CO₂ constraint
  stringency, heat pump temperature grade applicability.
- **Hints:** `COM: ELC, GAS, H2, CO2` · `PRC: GAS_BOIL, E_HEAT, H2_BOIL` ·
  `UC: CO2_CAP` · `OUT: ΔTWh, ΔMtCO2, $/t`
- **Extensions:**
  - A: What happens when you add a CO₂ constraint? Which technology switches
    first?
  - B: Is the carbon price or the clean-heat target the bigger driver?
  - C: What is the ordered marginal contribution of e-heat, hydrogen, and
    heat-demand reduction to ΔTWh, ΔMtCO2, and implied $/t?

Declarative experiment manifest:

```bash
vita experiment vedalang/examples/toy_sectors/experiments/toy_industry_core.experiment.yaml
```

Current reproducible Vita loop:

```bash
uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/baseline --json
uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run s25_co2_cap --no-sankey --out runs/toy_industry/co2_cap --json
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_gas_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_gas_capex --json
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_h2_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_h2_capex --json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap --json > runs/toy_industry/diffs/baseline_vs_co2_cap.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_gas_capex --json > runs/toy_industry/diffs/baseline_vs_high_gas_capex.json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_h2_capex --json > runs/toy_industry/diffs/baseline_vs_high_h2_capex.json
```

### 5. Resources (`toy_resources`)

**Question:** "Electrify X% of mining energy demand OR allow optimisation under
carbon constraint. Compare ΔTWh and implied $/t."

- **Type:** Paired (exogenous + endogenous variant)
- **Experiment:** Variant A forces X% electrification of diesel haul/load.
  Variant B allows the model to choose between diesel, electric, and biodiesel
  under a CO₂ constraint.
- **Key sensitivities:** Diesel vs electricity cost ratio, electric equipment
  capex, mine-site load profile, CO₂ constraint level.
- **Hints:** `COM: ELC, DSL, BIO_DSL, CO2` · `PRC: DSL_HAUL, E_HAUL, BIO_HAUL` ·
  `UC: CO2_CAP (variant B)` · `OUT: ΔTWh, ΔMtCO2, $/t`
- **Extensions:**
  - A: As the CO₂ constraint tightens, which option enters first:
    electrification or biodiesel substitution?
  - B: Is the diesel-electricity price gap or the CO₂ policy the bigger driver
    of technology choice?
  - C: What is the ordered marginal contribution of electric haul, biodiesel
    substitution, and equipment conversion limits to ΔTWh and implied $/t?

### 6. Agriculture & Land (`toy_agriculture`)

**Question:** "Represent a simple methane abatement supply curve +
sequestration under an economy-wide cap. What is ΔMtCO2 and implied $/t?"

- **Type:** Endogenous abatement supply curve
- **Experiment:** Model 3–4 options (feed additives, manure management, soil
  carbon, reforestation) with costs and potentials. The model stacks them under
  a CO₂e cap to find the marginal abatement cost.
- **Key sensitivities:** Abatement costs, potential caps, sequestration
  permanence discount, economy-wide cap level.
- **Hints:** `COM: CH4, CO2, OFFSETS` · `PRC: FEED_ADD, MANURE, SOIL_C, REFOREST` ·
  `UC: CO2E_CAP` · `OUT: ΔMtCO2e, $/t`
- **Extensions:**
  - A: As the CO₂e cap tightens, which abatement option is selected first,
    and which is the marginal last option?
  - B: Is abatement cost or land availability the bigger constraint on total
    mitigation?
  - C: What is the ordered marginal contribution of feed additives, manure
    management, soil carbon, and reforestation to ΔMtCO2e and implied $/t?
