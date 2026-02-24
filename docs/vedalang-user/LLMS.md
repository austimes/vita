# VedaLang LLM Guide

> AI agent guidance for generating VedaLang source files.

For service-oriented RES structure conventions
(`role=service`, `variant=pathway`, physical-only modeling, diagnostics
boundaries), see the companion skill guide:
`.agents/skills/vedalang-modeling-conventions/SKILL.md`.

## Purpose & Scope

**VedaLang** is a typed DSL that compiles to VEDA Excel tables for the TIMES energy model. You write VedaLang YAML; the compiler emits Excel; xl2times validates the output.

```
VedaLang (.veda.yaml) → Compiler → VEDA Excel (.xlsx) → xl2times → TIMES DD files
```

### Terminology

VedaLang uses precise terminology to avoid ambiguity:

| Term | Definition |
|------|------------|
| **Scenario Parameter** | An atomic time-series or value assumption (e.g., CO2 price, demand projection) |
| **Category** | Logical grouping: `demands`, `prices`, `policies`, `technology_assumptions`, `resource_availability`, `global_settings` |
| **Case** | A named combination of scenario parameters for a model run (e.g., `baseline`, `ambitious`) |
| **Study** | A collection of cases for comparison |

**File organization:**
- **Model architecture** (VT_* files): processes, commodities, topology
- **Scenario instantiation** (Scen_{case}_{category}.xlsx): demands, prices, policies

### Sources of Truth (Priority Order)

1. **`vedalang/schema/vedalang.schema.json`** — What syntax is valid
2. **`vedalang/schema/attribute-master.json`** — Canonical TIMES attribute names (use ONLY these, never aliases)
3. **`rules/constraints.yaml`** — Valid tag/file/field combinations
4. **`rules/patterns.yaml`** — Reusable modeling patterns

### Golden Rules

1. **Use canonical attribute names only** — never aliases (e.g., `ACT_COST` not `VAROM`)
2. **Every process needs `primary_commodity_group`** — no exceptions
3. **Interpolation is required for time-series** — always specify `interpolation` for `values` maps
4. **Commodities must exist before reference** — define before using in processes
5. **Validate via `vedalang validate`** — xl2times is the oracle, not your assumptions
6. **Schema-first** — if the schema doesn't allow it, you can't do it
7. **Fail fast, learn** — when xl2times rejects output, capture the pattern

---

## Mental Model & Workflow

### When to Use VedaLang vs TableIR

| Use Case | Tool |
|----------|------|
| New model from scratch | VedaLang |
| Quick pattern experiment | TableIR + `vedalang-dev emit-excel` |
| Production model authoring | VedaLang |
| Debugging VEDA structure | TableIR (lower friction) |

### Standard Workflow

```bash
# Validate (lint + compile + xl2times)
uv run vedalang validate mymodel.veda.yaml

# Validate only selected case(s)
uv run vedalang validate mymodel.veda.yaml --case baseline --case policy

# Lint for heuristic issues only
uv run vedalang lint mymodel.veda.yaml

# Or step by step:
uv run vedalang compile mymodel.veda.yaml --out output/
uv run vedalang compile mymodel.veda.yaml --out output/ --case policy
uv run xl2times output/ --diagnostics-json diag.json
```

---

## VedaLang Syntax & Structure

### Terminology: VedaLang Fields vs TIMES Attributes vs VEDA Aliases

VedaLang uses **ergonomic field names** that compile to **canonical TIMES attributes**:

| Layer | Example | Description |
|-------|---------|-------------|
| **VedaLang field** | `varom`, `invcost`, `efficiency` | Human-readable DSL syntax |
| **TIMES attribute** | `ACT_COST`, `NCAP_COST`, `EFF` | Canonical names (source of truth) |
| **VEDA alias** | `VAROM`, `INVCOST` | Legacy shortcuts — **NEVER use** |

**Key insight:** VedaLang fields are NOT aliases. They're a clean abstraction layer that deterministically compiles to canonical TIMES attributes. When debugging compiled Excel or xl2times output, you'll see the canonical TIMES names (like `ACT_COST`), not the VedaLang names (like `varom`).

### Required Top-Level Structure

```yaml
model:
  name: <string>           # REQUIRED: Model identifier
  regions: [<string>, ...] # REQUIRED: At least one region
  commodities: [...]       # REQUIRED: Commodity definitions
  processes: [...]         # REQUIRED: Process definitions
  
  # Optional sections:
  description: <string>
  milestone_years: [<int>, ...]  # e.g., [2020, 2030, 2040, 2050]
  timeslices: {...}
  scenarios: [...]
  trade_links: [...]
  constraints: [...]
```

### Commodities

Define energy carriers, materials, emissions, and demands.

```yaml
commodities:
  - id: energy:electricity
    type: energy      # energy | material | emission | service | money
    unit: PJ
    description: Electricity

  - id: emission:co2
    type: emission
    unit: Mt
    description: Carbon dioxide

  - id: service:residential_demand
    type: service
    unit: PJ
    description: Residential demand
```

**Valid types:** `energy`, `material`, `emission`, `service`, `money`

### Commodity Namespaces

VedaLang uses namespace prefixes to unambiguously classify commodities. The compiler maps these to VEDA Csets:

| Namespace | Meaning | Compiles to (Csets) |
|-----------|---------|---------------------|
| `energy:` | Energy carriers (gas, electricity, hydrogen) | NRG |
| `material:` | Physical material streams (captured CO2, steel) | MAT |
| `service:` | Demand/service commodities (space heat, pkm) | DEM |
| `emission:` | Environmental ledger species (CO2, CH4, N2O) | ENV |
| `money:` | Monetary/financial commodities | FIN |

**Design rule:** TIMES 3-letter codes never appear in user-authored VedaLang. They are compiler output.

Example:
```yaml
commodities:
  - id: energy:electricity
    type: energy
    unit: PJ
  - id: service:space_heat
    type: service
    unit: PJ
  - id: emission:co2
    type: emission
    unit: Mt
```

### Emissions as Attributes

Emissions are **ledger entries**, not physical commodity flows. They must never appear in process `inputs` or `outputs`.

**Pattern:** Use `emission_factors` on the process:
```yaml
process_variants:
  - id: gas_heater
    role: provide_space_heat
    inputs:
      - commodity: energy:natural_gas
    outputs:
      - commodity: service:space_heat
    emission_factors:
      emission:co2: 0.056    # ledger entry, not a flow
```

**Negative emissions** (DAC, LULUCF) use negative values:
```yaml
process_variants:
  - id: dac
    role: remove_co2
    inputs:
      - commodity: energy:electricity
    emission_factors:
      emission:co2: -1.0     # removal from ENV ledger
```

**Lint rules enforced:**
- **L1**: `emission:*` MUST NOT appear in `inputs` or `outputs`
- **L2**: `emission_factors` keys MUST be `emission:*` namespaced
- **L3**: Negative emission factors allowed but recommend adding `description`/`notes`
- **L5**: Bare `co2`/`ch4`/`n2o` warns: "Did you mean `emission:co2` or `material:co2`?"

### Processes

Define technologies that transform commodities.

```yaml
processes:
  # Thermal power plant
  - name: PP_CCGT
    description: Combined cycle gas turbine
    sets: [ELE]
    primary_commodity_group: NRGO  # REQUIRED
    inputs:
      - commodity: energy:natural_gas
    outputs:
      - commodity: energy:electricity
    emission_factors:
      emission:co2: 0.05           # Mt CO2 per PJ fuel input
    efficiency: 0.55
    invcost: 800                 # Investment cost per GW
    fixom: 20                    # Fixed O&M per GW-year
    varom: 2                     # Variable O&M per PJ
    life: 30

  # With bounds
  - name: PP_WIND
    sets: [ELE]
    primary_commodity_group: NRGO
    outputs:
      - commodity: energy:electricity
    invcost: 1200
    cap_bound:
      up: 30                     # Max 30 GW total
      lo: 3                      # Min 3 GW total
    ncap_bound:
      up: 2                      # Max 2 GW new per period

  # Time-varying costs
  - name: PP_SOLAR
    sets: [ELE]
    primary_commodity_group: NRGO
    outputs:
      - commodity: energy:electricity
    invcost:
      values:
        "2020": 900
        "2030": 550
        "2040": 350
      interpolation: interp_extrap
```

**Primary Commodity Groups (PCG):**
- `NRGO` — Energy output (power plants)
- `DEMO` — Demand output (demand devices)
- `MATO` — Material output (hydrogen, steel)
- `NRGI`, `DEMI`, `MATI` — Input variants

**Bound types:** `up` (max), `lo` (min), `fx` (fixed)

### Scenario Parameters

Define time-varying parameters like prices and demand projections. These are organized by **category** and **case**.

```yaml
# Scenario parameters (old 'scenarios' key still works for backward compatibility)
scenario_parameters:
  - name: CO2_Price
    type: commodity_price      # commodity_price | demand_projection
    category: prices           # Optional: defaults from type
    commodity: emission:co2
    interpolation: interp_extrap
    values:
      "2025": 50
      "2030": 100
      "2050": 200

  - name: DemandRSD
    type: demand_projection
    category: demands          # Optional: defaults from type
    commodity: service:residential_demand
    interpolation: interp_extrap
    values:
      "2020": 100
      "2030": 120

# Define cases (combinations of scenario parameters)
cases:
  - name: baseline
    description: Reference case with standard assumptions
    is_baseline: true

  - name: ambitious
    description: Aggressive climate policy case
    excludes: []  # Include all parameters
```

**Categories:** `demands`, `prices`, `policies`, `technology_assumptions`, `resource_availability`, `global_settings`

**File output:** `Scen_{case}_{category}.xlsx` (e.g., `Scen_baseline_demands.xlsx`)

Case overlays are deterministic:
- `demand_overrides` and `fuel_price_overrides` target a single base series when available.
- `scale` multiplies base demand values first, then explicit `values` replace year-specific points.
- Conflicting or ambiguous overlay selectors are compile-time errors.

**Interpolation modes:**
- `none` — No interpolation
- `interp_only` — Interpolate, no extrapolation
- `interp_extrap` — Full interpolation and extrapolation (most common)
- `interp_extrap_back` — Extrapolate backward only
- `interp_extrap_forward` — Extrapolate forward only

### Constraints

Define emission caps, renewable targets, etc.

```yaml
constraints:
  # Emission cap
  - name: CO2_CAP
    type: emission_cap
    commodity: emission:co2
    limtype: up
    years:
      "2020": 100
      "2030": 75
      "2050": 25
    interpolation: interp_extrap

  # Renewable share target
  - name: REN_TARGET
    type: activity_share
    commodity: energy:electricity
    processes: [PP_WIND, PP_SOLAR]
    minimum_share: 0.30
```

### Trade Links

Define inter-regional commodity trade.

```yaml
trade_links:
  - origin: NORTH
    destination: SOUTH
    commodity: energy:electricity
    bidirectional: true
    efficiency: 0.97            # 3% transmission loss
```

### Timeslices

Define intra-annual temporal resolution.

```yaml
timeslices:
  season:
    - code: S
      name: Summer
    - code: W
      name: Winter
  daynite:
    - code: D
      name: Day
    - code: N
      name: Night
  fractions:
    SD: 0.25
    SN: 0.22
    WD: 0.28
    WN: 0.25    # Must sum to 1.0
```

---

## Attributes & TIMES Mapping

Reference `vedalang/schema/attribute-master.json` for the complete list. **Always use canonical TIMES attribute names** (middle column below), never VEDA aliases.

### Complete VedaLang → TIMES Mapping

The VedaLang compiler translates ergonomic snake_case field names to canonical UPPERCASE TIMES attributes. VedaLang enforces **canonical names only** — no aliases are accepted.

#### Process Parameters

| VedaLang Field | TIMES Attribute | VEDA Aliases (DO NOT USE) | Description |
|----------------|-----------------|---------------------------|-------------|
| `efficiency` | `EFF` / `ACT_EFF` | — | Process efficiency (0-1) |
| `invcost` | `NCAP_COST` | `INVCOST` | Investment cost per capacity unit |
| `fixom` | `NCAP_FOM` | `FIXOM` | Fixed O&M per capacity-year |
| `varom` | `ACT_COST` | `VAROM`, `ACTCOST` | Variable O&M per activity unit |
| `life` | `NCAP_TLIFE` | `TLIFE`, `LIFE` | Technical lifetime (years) |
| `availability_factor` | `NCAP_AF` | `AF` | Capacity availability factor (0-1) |

#### Bounds

| VedaLang Field | TIMES Attribute | VEDA Aliases (DO NOT USE) | Description |
|----------------|-----------------|---------------------------|-------------|
| `activity_bound.up/lo/fx` | `ACT_BND` | `BNDACT`, `ACTBND` | Activity bound |
| `cap_bound.up/lo/fx` | `CAP_BND` | `BNDCAP`, `CAPBND` | Total capacity bound |
| `ncap_bound.up/lo/fx` | `NCAP_BND` | `BNDNCAP`, `NCAPBND` | New capacity bound |
| `flow_bound.up/lo/fx` | `FLO_BND` | `BNDFLO`, `FLOBND` | Flow bound |

#### Commodity Parameters

| VedaLang Field | TIMES Attribute | VEDA Aliases (DO NOT USE) | Description |
|----------------|-----------------|---------------------------|-------------|
| `price` | `COM_BPRICE` | — | Commodity base price |
| `projection` | `COM_PROJ` | `CPROJ`, `DEMAND` | Demand projection |
| `fraction` | `COM_FR` | `CFR` | Commodity fraction |

#### Capacity & Investment

| VedaLang Field | TIMES Attribute | VEDA Aliases (DO NOT USE) | Description |
|----------------|-----------------|---------------------------|-------------|
| `past_investments` | `NCAP_PASTI` | `PASTI`, `STOCK` | Existing capacity by vintage |
| `residual_capacity` | `PRC_RESID` | `RESID` | Residual capacity |
| `construction_time` | `NCAP_ILED` | `ILED` | Lead time for construction |
| `economic_life` | `NCAP_ELIFE` | `ELIFE` | Economic lifetime |

### Why Canonical Names Only?

VedaLang intentionally rejects aliases to:
1. **Eliminate ambiguity** — One name per concept
2. **Improve tooling** — Simpler validation and error messages
3. **Ensure consistency** — All VedaLang files use the same vocabulary
4. **Match TIMES docs** — Canonical names match TIMES documentation

### Attribute Lookup

```python
# Check canonical name for an attribute
import json
with open("vedalang/schema/attribute-master.json") as f:
    attrs = json.load(f)["attributes"]
    
# Find by alias
for name, info in attrs.items():
    if "VAROM" in info.get("aliases", []):
        print(f"Canonical: {name}")  # ACT_COST
```

### Debugging Tip

When xl2times reports an error like `Invalid ACT_COST value`, trace back:
1. Find `ACT_COST` in the mapping table above → VedaLang field is `varom`
2. Search your VedaLang source for `varom:` to locate the issue

---

## Tag/Table Selection

VedaLang compiles to VEDA tags. Understanding the mapping helps debugging.

### Decision Tree

```
Is it defining structure?
├── Commodity → ~FI_COMM
├── Process definition → ~FI_PROCESS
└── Process topology/flow → ~FI_T

Is it scenario data?
├── Single value per row → ~TFM_INS
└── Time-series (YEAR column) → ~TFM_INS-TS
```

### Tag Summaries

| Tag | Purpose | Key Columns |
|-----|---------|-------------|
| `~FI_COMM` | Define commodities | Csets, CommName, Unit |
| `~FI_PROCESS` | Define processes | TechName, Sets, Tact, Tcap |
| `~FI_T` | Process topology | Process, Comm-IN, Comm-OUT, EFF |
| `~TFM_INS` | Insert parameters | Attribute, Value, (TechName) |
| `~TFM_INS-TS` | Time-series data | YEAR, Attribute, Value |

See `rules/constraints.yaml` for valid file/field combinations.

---

## Patterns: Reusable Templates

The pattern library (`rules/patterns.yaml`) provides templates for common constructs.

### Available Patterns

| Pattern | Use Case |
|---------|----------|
| `add_power_plant` | Thermal generation (CCGT, coal, oil) |
| `add_renewable_plant` | Wind, solar, hydro |
| `add_chp_plant` | Combined heat and power |
| `add_storage` | Battery, pumped hydro |
| `add_energy_commodity` | Fuel, electricity |
| `add_emission_commodity` | CO2, NOx |
| `co2_price_trajectory` | Carbon price scenario |

### Pattern Example

```yaml
# From patterns.yaml - add_power_plant template
processes:
  - name: {{ plant_name }}
    description: Thermal power plant
    sets: [ELE]
    primary_commodity_group: NRGO
    inputs:
      - commodity: {{ fuel_commodity }}
    outputs:
      - commodity: {{ output_commodity }}
    emission_factors:
      emission:co2: {{ emission_factor }}  # if applicable
    efficiency: {{ efficiency }}
```

### When to Use Patterns

- Starting a new model component
- Ensuring consistency across similar technologies
- Learning idiomatic VedaLang structure

---

## Validation Checklist

Before running `vedalang validate`, verify:

### Structure

- [ ] `model.name` is set
- [ ] `model.regions` has at least one region
- [ ] `model.commodities` is non-empty
- [ ] `model.processes` is non-empty

### Types & Enums

- [ ] Commodity `type` is: `energy`, `material`, `emission`, `service`, or `money`
- [ ] Commodity IDs use namespace prefixes (`energy:`, `service:`, `emission:`, etc.)
- [ ] `emission:*` commodities only appear in `emission_factors`, never in inputs/outputs
- [ ] Process `primary_commodity_group` is valid (NRGO, DEMO, MATO, etc.)
- [ ] `interpolation` mode is valid when using `values` maps
- [ ] Bound keys are: `up`, `lo`, or `fx`

### Numeric Ranges

- [ ] `efficiency` is 0-1
- [ ] `share` values are 0-1
- [ ] Costs are non-negative
- [ ] Timeslice fractions sum to 1.0

### Reference Integrity

- [ ] All commodities in process inputs/outputs are defined
- [ ] All processes in constraints are defined
- [ ] Trade link regions exist in `model.regions`
- [ ] Scenario commodities are defined

### Attribute Consistency

- [ ] Using canonical names from attribute-master.json
- [ ] Time-series have required `interpolation` field
- [ ] Year keys are valid 4-digit years (e.g., "2020")

---

## Quick Reference

### Minimal Valid Model

```yaml
model:
  name: MinimalExample
  regions: [REG1]
  
  commodities:
    - id: energy:electricity
      type: energy
      unit: PJ

  processes:
    - name: PP_GEN
      sets: [ELE]
      primary_commodity_group: NRGO
      outputs:
        - commodity: energy:electricity
```

### Validation Commands

```bash
# Full validation (lint + compile + xl2times)
uv run vedalang validate model.veda.yaml

# Lint only (fast, checks heuristics)
uv run vedalang lint model.veda.yaml

# With JSON output for automation
uv run vedalang validate model.veda.yaml --json
```

### Common Errors

| Error | Fix |
|-------|-----|
| Missing `primary_commodity_group` | Add PCG to process (usually `NRGO`) |
| Commodity not found | Define commodity before process reference |
| Invalid interpolation | Use valid enum value |
| Timeslice fractions don't sum to 1 | Adjust fractions |
