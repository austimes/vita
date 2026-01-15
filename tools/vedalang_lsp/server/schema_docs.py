"""Comprehensive hover documentation for all VedaLang schema fields.

This module contains markdown documentation strings with intentionally long lines
for better readability when rendered. Line length limits are disabled.
"""
# ruff: noqa: E501

SCHEMA_FIELD_DOCS: dict[str, str] = {
    # ----------------------------------------------------------------------
    # Top-level model structure
    # ----------------------------------------------------------------------
    "model": """\
## VedaLang: `model`

**Type**: object
**Required**: yes (root key)

Container for the entire VedaLang model definition.
All other sections (`regions`, `commodities`, `processes`, etc.) live under this key.

**Example**:
```yaml
model:
  name: my_model
  regions: [R1, R2]
  milestone_years: [2020, 2030, 2040, 2050]
  commodities: []
  processes: []
```
""",
    "name": """\
## VedaLang: `name`

**Type**: string
**Used in**: `model`, `commodity`, `process`, `process_template`, `process_instance`, `scenario_parameter`, `case`, `study`

Identifier or human-readable name, depending on context:

- **model.name** – model identifier.
- **commodity.name** – commodity identifier (e.g., `C:ELC`, `S:HEAT:RES.ALL`).
- **process.name** – process identifier (e.g., `PP_CCGT`, `IMP_NG`).
- **process_template.name** – reusable technology template name (e.g., `CCGT_GEN`).
- **process_instance.name** – instance label (for documentation; not a TIMES ID).
- **scenario_parameter.name** – scenario parameter identifier.
- **case.name** – case identifier (must match `^[a-z][a-z0-9_]*$`).
- **study.name** – study name.

**Notes**:
- Names are used for reference and must be unique within their collections.
- `case.name` is used in filenames: `Scen_{case}_{category}.xlsx`.
""",
    "description": """\
## VedaLang: `description`

**Type**: string
**Used in**: most objects (`model`, `commodity`, `process`, `process_template`, `scenario_parameter`, `constraint`, `case`, `study`)

Optional human-readable description to document the purpose of the object.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    description: Combined-cycle gas turbine for baseload electricity
```
""",
    "regions": """\
## VedaLang: `regions`

**Type**: array of string
**Required**: yes on `model`

List of region codes used in the model.
All region references (e.g., `process_instance.region`, `trade_link.origin`) must come from this list.

**Example**:
```yaml
model:
  regions: [R1, R2, R3]
```
""",
    "milestone_years": """\
## VedaLang: `milestone_years`

**Type**: array of integer (>= 1900)
**Required**: recommended on `model` (schema requires >=1 item)

Ordered list of **model milestone years**.
The **first year** is the model start year; later years define the planning horizon.

**Example**:
```yaml
model:
  milestone_years: [2020, 2030, 2040, 2050]
```
""",
    "timeslices": """\
## VedaLang: `timeslices`

**Type**: object (`season`, `weekly`, `daynite`, `fractions`)
**Used in**: `model`

Defines intra-annual temporal resolution, mapped to TIMES timeslices.

- `season`: seasonal codes (e.g., summer/winter).
- `weekly`: optional weekly codes.
- `daynite`: within-day codes (e.g., day/night).
- `fractions`: year fraction of each **composite** timeslice. Must sum to 1.0.

**Example**:
```yaml
model:
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
      SN: 0.25
      WD: 0.25
      WN: 0.25
```
""",
    "commodities": """\
## VedaLang: `commodities`

**Type**: array of `commodity` objects
**Required**: yes on `model`

List of commodity definitions (energy, materials, demands, emissions, etc.).
Each entry must at least define `name` and `kind`.

**Example**:
```yaml
model:
  commodities:
    - name: C:ELC
      kind: TRADABLE
      unit: PJ
      description: Electricity
    - name: S:HEAT:RES.ALL
      kind: SERVICE
      context: RES.ALL
      unit: PJ
```
""",
    "process_templates": """\
## VedaLang: `process_templates`

**Type**: array of `process_template` objects

Region-agnostic process/technology templates reused across regions.
Templates capture technology-level attributes; region-specific overrides go in `process_instance`.

**Example**:
```yaml
model:
  process_templates:
    - name: CCGT_GEN
      technology: CCG
      role: GEN
      efficiency: 0.55
```
""",
    "processes": """\
## VedaLang: `processes`

**Type**: array of `process` or `process_instance` objects
**Required**: recommended on `model`

Collection of:

- **Inline processes** (`process`) – full definition inside the model.
- **Process instances** (`process_instance`) – region-specific instantiation of a `process_template`.

**Example**:
```yaml
model:
  processes:
    - name: PP_CCGT
      sets: [ELE]
      efficiency: 0.55
      input: C:GAS
      output: C:ELC

    - name: R1_CCGT_1
      template: CCGT_GEN
      region: R1
```
""",
    "scenario_parameters": """\
## VedaLang: `scenario_parameters`

**Type**: array of `scenario_parameter` objects

Atomic assumptions like demand projections or price paths, grouped by `category`.
Replaces the deprecated `scenarios` section.

**Example**:
```yaml
model:
  scenario_parameters:
    - name: elec_demand_ref
      type: demand_projection
      commodity: S:ELC:RES.ALL
      category: demands
      interpolation: interp_extrap
      values:
        "2020": 10
        "2030": 12
```
""",
    "trade_links": """\
## VedaLang: `trade_links`

**Type**: array of `trade_link` objects

Inter-regional trade relationships for specific commodities.

**Example**:
```yaml
model:
  trade_links:
    - origin: R1
      destination: R2
      commodity: C:ELC
      bidirectional: true
      efficiency: 0.95
```
""",
    "constraints": """\
## VedaLang: `constraints`

**Type**: array of `constraint` objects

User-defined constraints such as **emission caps** or **activity share** limits.
Maps primarily to TIMES UC constraints (`UC_RHS`, `UC_RHSP`, etc.), with `name` becoming `UC_N`.

**Example**:
```yaml
model:
  constraints:
    - name: CO2_CAP
      type: emission_cap
      commodity: E:CO2
      limit: 50
      limtype: up
```
""",
    "cases": """\
## VedaLang: `cases`

**Type**: array of `case` objects

Model cases: named combinations of scenario parameters representing a single run configuration.

**Example**:
```yaml
model:
  cases:
    - name: ref
      description: Reference case
      includes: [elec_demand_ref, co2_price_low]
      is_baseline: true
```
""",
    "studies": """\
## VedaLang: `studies`

**Type**: array of `study` objects

Studies are collections of cases for comparison and analysis (e.g., reference vs policy cases).

**Example**:
```yaml
model:
  studies:
    - name: policy_vs_ref
      cases: [ref, high_co2]
```
""",
    "scenarios": """\
## VedaLang: `scenarios` (DEPRECATED)

**Type**: array of `scenario_parameter` objects
**Status**: deprecated – use `scenario_parameters` instead.

Kept only for backward compatibility with earlier VedaLang/VEDA models.
New models should define assumptions under `scenario_parameters`.
""",
    # ----------------------------------------------------------------------
    # Shared enums and utility defs
    # ----------------------------------------------------------------------
    "category": """\
## VedaLang: `category`

**Type**: string enum
**Used in**: `scenario_parameter`, `constraint` (via `$defs/category`)

Logical grouping for scenario parameters and constraints.
Allowed values:

- `demands` – demand projections and service-level assumptions.
- `prices` – prices, taxes, subsidies, or cost-related assumptions.
- `policies` – policy levers: caps, standards, quota constraints, etc.
- `technology_assumptions` – efficiencies, costs, performance improvements.
- `resource_availability` – resource potentials, reserves, extraction limits.
- `global_settings` – general or cross-cutting assumptions.

**Defaults**:
- `scenario_parameter.type = commodity_price` → default `prices`
- `scenario_parameter.type = demand_projection` → default `demands`
- `constraint` → default `policies`
""",
    # ----------------------------------------------------------------------
    # Case & Study
    # ----------------------------------------------------------------------
    "is_baseline": """\
## VedaLang: `is_baseline`

**Type**: boolean
**Default**: false
**Used in**: `case`

Marks a case as the **baseline/reference** case for comparisons.

**Example**:
```yaml
cases:
  - name: ref
    is_baseline: true
```
""",
    "includes": """\
## VedaLang: `includes`

**Type**: array of string
**Used in**: `case`

Explicit list of **scenario_parameter names** to include in this case.
If omitted, the case includes **all** scenario parameters except those in `excludes`.

**Example**:
```yaml
cases:
  - name: high_co2
    includes: [co2_price_high]
```
""",
    "excludes": """\
## VedaLang: `excludes`

**Type**: array of string
**Used in**: `case`

List of **scenario_parameter names** to exclude from this case.
Useful for "remove this one thing from the default assumption set."

**Example**:
```yaml
cases:
  - name: no_co2_price
    excludes: [co2_price_default]
```
""",
    "tags": """\
## VedaLang: `tags`

**Type**:
- `case.tags`: array of string
- `process_template.tags`: object mapping string → string

Flexible labeling for organization, reporting, or tooling.

**Examples**:
```yaml
cases:
  - name: ref
    tags: [reference, published]

process_templates:
  - name: CCGT_GEN
    tags:
      fuel: gas
      flexibility: high
```
""",
    # ----------------------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------------------
    "type": """\
## VedaLang: `type`

**Type**: string enum (context-dependent)

Used in several contexts:

- `constraint.type`:
  - `emission_cap` – cap on emission commodity (maps to UC constraints).
  - `activity_share` – min/max share constraints on process activity.
- `scenario_parameter.type`:
  - `commodity_price` – time series for commodity prices.
  - `demand_projection` – time series for service/commodity demands.

Other locations may use `type` in the future; always refer to the local enum in the schema.

**Example**:
```yaml
constraints:
  - name: CO2_CAP
    type: emission_cap

scenario_parameters:
  - name: elec_demand_ref
    type: demand_projection
```
""",
    "commodity": """\
## VedaLang: `commodity`

**Type**: string (reference to `commodity.name`)
**Used in**: `constraint`, `trade_link`, `scenario_parameter`, `flow`, etc.

Selects a defined commodity as the target of a constraint, price path, trade link, or flow.

**Examples**:
```yaml
constraints:
  - commodity: E:CO2

scenario_parameters:
  - commodity: C:ELC

trade_links:
  - commodity: C:NG
```
""",
    "limit": """\
## VedaLang: `limit`

**Type**: number
**Used in**: `constraint` (`emission_cap`)

Base RHS value for an `emission_cap` constraint.
Can be overridden or made time-varying using `years`.

**Example**:
```yaml
constraints:
  - name: CO2_CAP
    type: emission_cap
    commodity: E:CO2
    limit: 50   # e.g. Mt CO2
```
""",
    "limtype": """\
## VedaLang: `limtype`

**Type**: string enum (`up`, `lo`, `fx`)
**Default**: `up`
**Used in**: `constraint`

Indicates the **limit type**:

- `up` – upper bound (≤ limit)
- `lo` – lower bound (≥ limit)
- `fx` – fixed equality (= limit)

Maps conceptually to the bound semantics in TIMES UC formulations.

**Example**:
```yaml
constraints:
  - name: MIN_RES_SHARE
    type: activity_share
    limtype: lo
```
""",
    "minimum_share": """\
## VedaLang: `minimum_share`

**Type**: number (0–1)
**Used in**: `constraint` (`activity_share`)

Minimum allowed **share** of activity for selected processes relative to total activity of the constrained group.

**Example**:
```yaml
constraints:
  - name: RES_SHARE
    type: activity_share
    minimum_share: 0.5
```
""",
    "maximum_share": """\
## VedaLang: `maximum_share`

**Type**: number (0–1)
**Used in**: `constraint` (`activity_share`)

Maximum allowed **share** of activity for selected processes.

**Example**:
```yaml
constraints:
  - name: COAL_LIMIT
    type: activity_share
    maximum_share: 0.2
```
""",
    "years": """\
## VedaLang: `years`

**Type**: object mapping `YYYY` → number
**Used in**: `constraint` (`emission_cap` or `activity_share`)

Year-specific RHS values that **override** the scalar `limit` for given years.

- Keys: 4-digit years (`^[12][0-9]{3}$`).
- Values: numeric RHS for that year.

**Example**:
```yaml
constraints:
  - name: CO2_CAP
    type: emission_cap
    commodity: E:CO2
    years:
      "2030": 45
      "2040": 30
```
""",
    "interpolation": """\
## VedaLang: `interpolation`

**Type**: string enum
**Used in**: `constraint`, `scenario_parameter`, `time_series`, `time_varying_value`

VEDA interpolation/extrapolation mode for year→value data.
Allowed values:

- `none` – no interpolation; values apply only to specified years.
- `interp_only` – interpolate between points; no extrapolation.
- `interp_extrap_eps` – interpolate and extrapolate with small epsilon limits.
- `interp_extrap` – interpolate and extrapolate normally.
- `interp_extrap_back` – fill backwards to earlier years.
- `interp_extrap_forward` – fill forwards to later years.

In `scenario_parameter` this maps to VEDA year=0 option codes:
`none=-1`, `interp_only=1`, `interp_extrap_eps=2`, `interp_extrap=3`, `interp_extrap_back=4`, `interp_extrap_forward=5`.

**Example**:
```yaml
scenario_parameters:
  - name: elec_demand_ref
    interpolation: interp_extrap
```
""",
    # ----------------------------------------------------------------------
    # Trade links
    # ----------------------------------------------------------------------
    "origin": """\
## VedaLang: `origin`

**Type**: string (region code)
**Used in**: `trade_link`

Origin region of an inter-regional trade link. Must be in `model.regions`.

**Example**:
```yaml
trade_links:
  - origin: R1
    destination: R2
    commodity: C:ELC
```
""",
    "destination": """\
## VedaLang: `destination`

**Type**: string (region code)
**Used in**: `trade_link`

Destination region of a trade link. Must be in `model.regions`.
""",
    "bidirectional": """\
## VedaLang: `bidirectional`

**Type**: boolean
**Default**: true
**Used in**: `trade_link`

Whether trade is allowed in **both directions** between `origin` and `destination`.
If `false`, only `origin → destination` flows are modeled.
""",
    "efficiency": """\
## VedaLang: `efficiency`

**Type**:
- In `process` / `process_template`: number (0–1) or `time_varying_value`
- In `trade_link`: number (0–1)

**Purpose**:

- **Process / template** – process energy/service efficiency.
  - Maps to TIMES attribute **`ACT_EFF`**.
  - Ratio of useful primary output to input based on **primary commodity group**.
- **Trade link** – transport efficiency (1.0 = no losses).

**Examples**:
```yaml
processes:
  - name: PP_CCGT
    efficiency: 0.55    # ACT_EFF

trade_links:
  - efficiency: 0.95    # 95% of energy arrives after transport
```
""",
    # ----------------------------------------------------------------------
    # Timeslices
    # ----------------------------------------------------------------------
    "code": """\
## VedaLang: `code`

**Type**: string (1–3 uppercase letters)
**Used in**: `timeslice_level`

Short identifier for a season/daynite/weekly timeslice.
Codes are combined (e.g., `S` + `D` → `SD`) to form composite timeslices in TIMES.

**Example**:
```yaml
timeslices:
  season:
    - code: S   # Summer
    - code: W   # Winter
```
""",
    "season": """\
## VedaLang: `season`

**Type**: array of `timeslice_level`
**Used in**: `timeslices`

Defines seasonal timeslices (e.g., summer/winter/shoulder).
""",
    "weekly": """\
## VedaLang: `weekly`

**Type**: array of `timeslice_level`
**Used in**: `timeslices`

Optional weekly timeslice codes. Rarely used outside advanced temporal resolution setups.
""",
    "daynite": """\
## VedaLang: `daynite`

**Type**: array of `timeslice_level`
**Used in**: `timeslices`

Within-day timeslice codes (e.g., day vs night, peak vs off-peak).
""",
    "fractions": """\
## VedaLang: `fractions`

**Type**: object mapping `<composite_timeslice>` → number (0–1)
**Used in**: `timeslices`

Fraction of the **year** represented by each composite timeslice.
All fractions must sum to **1.0**.

Composite keys are generated from `SEASON (+ WEEKLY) + DAYNITE` codes (e.g., `SD`, `SN`, `WD`, `WN`).

**Example**:
```yaml
timeslices:
  fractions:
    SD: 0.25
    SN: 0.25
    WD: 0.25
    WN: 0.25
```
""",
    # ----------------------------------------------------------------------
    # Commodity
    # ----------------------------------------------------------------------
    "kind": """\
## VedaLang: `kind`

**Type**: string enum (`TRADABLE`, `SERVICE`, `EMISSION`)
**Used in**: `commodity`

Classifies the commodity:

- `TRADABLE` – physical flows that can be transported/traded (e.g., fuels, electricity).
- `SERVICE` – demand satisfaction or end-use services (e.g., heating, mobility).
- `EMISSION` – byproduct or waste streams (e.g., CO2, NOx).

Rules:

- `SERVICE` commodities **must** define `context`.
- `TRADABLE` and `EMISSION` commodities **must not** define `context`.
""",
    "context": """\
## VedaLang: `context`

**Type**: string matching `^[A-Z]{3}\\.[A-Z0-9_]+(\\.[A-Z0-9_]+)?$`
**Used in**: `commodity` (only when `kind = SERVICE`), `process_instance`

Sectoral/segment context for **service** commodities, typically:

`{SECTOR}.{SEGMENT}[.{SUBSEGMENT}]`

Examples:

- `RES.ALL` – residential, all dwellings.
- `COM.OFFICE` – commercial, office buildings.
- `IND.METALS.ALUMINA` – industrial, metals, alumina segment.

**Rules**:

- REQUIRED when `kind = SERVICE`.
- Forbidden for `TRADABLE` and `EMISSION` commodities.
""",
    "unit": """\
## VedaLang: `unit`

**Type**: string
**Used in**: `commodity`, implicitly referenced by processes/parameters

Unit of measurement for the commodity (e.g., `PJ`, `MWh`, `Mt`, `kNm3`).
Cost, price, and emission factor units are interpreted relative to this.

**Example**:
```yaml
commodities:
  - name: C:ELC
    unit: PJ
```
""",
    # ----------------------------------------------------------------------
    # Process (inline)
    # ----------------------------------------------------------------------
    "sets": """\
## VedaLang: `sets`

**Type**: array of string
**Used in**: `process`, `process_template`

List of TIMES **process sets** (e.g., `ELE`, `DMD`, `IMP`) that this process belongs to.
These sets control reporting, classification, and special behaviors.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    sets: [ELE]
```
""",
    "primary_commodity_group": """\
## VedaLang: `primary_commodity_group`

**Type**: string enum (`DEMI`, `DEMO`, `MATI`, `MATO`, `NRGI`, `NRGO`, `ENVI`, `ENVO`, `FINI`, `FINO`)
**Used in**: `process`, `process_template`

Determines how **process activity and capacity** are defined in TIMES:

- Activity is computed from flows in this group (VAR_ACT).
- Capacity is tied to the primary group flows.
- Efficiency direction (input vs output) is resolved based on this group.

Format: `<commodity_type><I/O_direction>`.

Examples:

- `NRGO` – energy output (typical for power plants).
- `DEMO` – demand output (typical for demand devices).
- `MATO` – material output.

**TIMES/VEDA note**:
VEDA/xl2times can infer PCG using internal rules (DEM > MAT > NRG > ENV > FIN, outputs first, then inputs).
VedaLang makes it explicit to avoid surprises.
""",
    "activity_unit": """\
## VedaLang: `activity_unit`

**Type**: string
**Default**: `PJ`
**Used in**: `process`

Unit for **process activity**, i.e., the denominator for `ACT_EFF`, `ACT_COST`, and emission factors.

Common choices: `PJ`, `MWh`, service-specific units.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    activity_unit: PJ
```
""",
    "capacity_unit": """\
## VedaLang: `capacity_unit`

**Type**: string
**Default**: `GW`
**Used in**: `process`

Unit for **process capacity**, used in capacity-related TIMES attributes like `NCAP_COST`, `NCAP_FOM`, `NCAP_TLIFE`.

Examples: `GW`, `MW`, `kt/yr`.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    capacity_unit: GW
```
""",
    "input": """\
## VedaLang: `input`

**Type**: string (commodity name)
**Used in**: `process`, `process_template`

Shorthand for a single **input** commodity when only one input exists.
Equivalent to `inputs: [{commodity: <name>}]`.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    input: C:GAS
```
""",
    "inputs": """\
## VedaLang: `inputs`

**Type**: array of `flow` objects
**Used in**: `process`, `process_template`

Detailed specification of input commodity flows.
Each flow may define a `share` and/or `emission_factor`.

**Example**:
```yaml
processes:
  - name: BOILER
    inputs:
      - commodity: C:GAS
      - commodity: C:OIL
        share: 0.2
```
""",
    "output": """\
## VedaLang: `output`

**Type**: string (commodity name)
**Used in**: `process`, `process_template`

Shorthand for a single **output** commodity when only one output exists.
Equivalent to `outputs: [{commodity: <name>}]`.
""",
    "outputs": """\
## VedaLang: `outputs`

**Type**: array of `flow` objects
**Used in**: `process`, `process_template`

Detailed specification of output commodity flows.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    outputs:
      - commodity: C:ELC
```
""",
    "investment_cost": """\
## VedaLang: `investment_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance`

Investment cost per unit of **new capacity**.

- Maps to TIMES attribute **`NCAP_COST`**.
- Units: typically currency per `capacity_unit` (e.g., `$/GW`).

**Example**:
```yaml
processes:
  - investment_cost: 1200   # e.g., $/kW aggregated as $/GW

process_instances:
  - investment_cost:
      values:
        "2030": 1000
        "2040": 800
      interpolation: interp_extrap
```
""",
    "fixed_om_cost": """\
## VedaLang: `fixed_om_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance`

Fixed operation & maintenance cost per unit **installed capacity per year**.

- Maps to TIMES attribute **`NCAP_FOM`**.
- Units: e.g., `$/GW/yr` or currency/`capacity_unit`/year.
""",
    "variable_om_cost": """\
## VedaLang: `variable_om_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance`

Variable operation & maintenance cost per unit of **activity**.

- Maps to TIMES attribute **`ACT_COST`**.
- Units: currency per `activity_unit` (e.g., `$/PJ`).
""",
    "import_price": """\
## VedaLang: `import_price`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance` (for import processes)

Price of imported commodities.

- Maps to TIMES attribute **`IRE_PRICE`** for import processes.
- Units: currency per energy/material unit (e.g., `$/PJ`).
""",
    "lifetime": """\
## VedaLang: `lifetime`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance`

Technical lifetime of **new capacity**.

- Maps to TIMES attribute **`NCAP_TLIFE`**.
- Units: years.

Affects when capacity retires and how capital costs are annualized.
""",
    "availability_factor": """\
## VedaLang: `availability_factor`

**Type**: number (0–1) or `time_varying_value`
**Used in**: `process`, `process_template`, `process_instance`

Fraction of time capacity is available for use.

- Maps to TIMES attribute **`NCAP_AF`**.
- Often interpreted as maximum annual utilization factor.
""",
    "activity_bound": """\
## VedaLang: `activity_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: `process`, `process_instance`

Bounds on **annual process activity**.

- Conceptually maps to TIMES **`ACT_BND`** attributes.

**Example**:
```yaml
processes:
  - name: PP_COAL
    activity_bound:
      up: 100    # max activity
```
""",
    "cap_bound": """\
## VedaLang: `cap_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: `process`, `process_instance`

Bounds on **total installed capacity**.

- Conceptually maps to TIMES **`CAP_BND`** attributes.
""",
    "ncap_bound": """\
## VedaLang: `ncap_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: `process`, `process_instance`

Bounds on **new capacity additions per period**.

- Conceptually maps to TIMES **`NCAP_BND`** attributes.
""",
    "stock": """\
## VedaLang: `stock`

**Type**: number (≥0) or `time_varying_value`
**Used in**: `process`, `process_instance`

Aggregate **residual capacity** stock.

- Maps to TIMES attribute **`PRC_RESID`**.
- Represents a lumped existing capacity that decays linearly over `lifetime`.

For new models, prefer `existing_capacity` to track vintages explicitly.
""",
    "existing_capacity": """\
## VedaLang: `existing_capacity`

**Type**: array of `past_investment` objects
**Used in**: `process`, `process_instance`

Past capacity investments with explicit **vintage years**.

- Maps to TIMES attribute **`NCAP_PASTI`**.
- Enables proper tracking of retirement based on `lifetime`.

**Example**:
```yaml
processes:
  - name: PP_CCGT
    existing_capacity:
      - vintage: 2010
        capacity: 1.0   # in capacity_unit, e.g., GW
```
""",
    # ----------------------------------------------------------------------
    # Process template & instance-specific
    # ----------------------------------------------------------------------
    "technology": """\
## VedaLang: `technology`

**Type**: string
**Used in**: `process_template`

Technology code from a registry or naming convention (e.g., `CCG`, `PV`, `BAT`).
Used for grouping templates and for external documentation.
""",
    "role": """\
## VedaLang: `role`

**Type**: string enum (`GEN`, `EUS`, `CNV`, `EXT`, `TRD`, `STO`, `CAP`, `SEQ`)
**Used in**: `process_template`

Functional role of the template:

- `GEN` – generation (e.g., power plants).
- `EUS` – end-use service devices (e.g., heaters, cars).
- `CNV` – conversion of one commodity to another (refining, transformation).
- `EXT` – resource extraction (mines, wells).
- `TRD` – trade or transport between regions.
- `STO` – storage technologies.
- `CAP` – capture (e.g., CO2 capture).
- `SEQ` – sequestration (e.g., CO2 storage).

Some roles impose additional requirements (e.g., `EUS` often needs `segment`/`context`).
""",
    "segment": """\
## VedaLang: `segment`

**Type**:
- In `process_template`: string (`^[A-Z]{3}$`) – sector code
- In `process_instance`: string (`^[A-Z]{3}\\.[A-Z0-9_]+(\\.[A-Z0-9_]+)?$`) – sector.segment[.subsegment]

**Usage**:

- `process_template.segment` – sector code only (e.g., `RES`, `COM`, `IND`).
- `process_instance.segment` – full sectoral context, REQUIRED when `template.role = EUS`.

Examples:

```yaml
process_templates:
  - name: RES_BOILER
    role: EUS
    segment: RES

processes:
  - name: R1_RES_BOILER_1
    template: RES_BOILER
    region: R1
    segment: RES.ALL
```
""",
    "sankey_stage": """\
## VedaLang: `sankey_stage`

**Type**: string enum
**Used in**: `process_template`

Assigns the template to a **column** in Sankey diagrams.
Allowed values:

- `SUP` – supply
- `PRC` – processing
- `XFR` – transfer
- `STO` – storage
- `GEN` – generation
- `END` – final demand
- `SRV` – service/end-use
- `EMI` – emission
- `CCS` – capture and storage
- `EXP` – export

This is purely for visualization/reporting.
""",
    "template": """\
## VedaLang: `template`

**Type**: string (reference to `process_template.name`)
**Used in**: `process_instance`

Selects which **process_template** this instance is based on.
The instance can then override costs, lifetimes, bounds, etc.
""",
    "region": """\
## VedaLang: `region`

**Type**: string (region code)
**Used in**: `process_instance`

Region where this process instance exists.
Must be a member of `model.regions`.
""",
    "variant": """\
## VedaLang: `variant`

**Type**: string
**Used in**: `process_instance`

Variant code differentiating instances of the same template/technology.
Often used for technology options like different CCS capture rates or sizes.

**Example**:
```yaml
processes:
  - name: R1_CCGT_CCS90
    template: CCGT_GEN
    variant: CCS90
```
""",
    "vintage": """\
## VedaLang: `vintage`

**Type**:
- In `process_instance`: string (label, e.g., `EXIST`, `NEW`).
- In `past_investment`: integer year (≥1900).

In `process_instance`, distinguishes vintages for documentation or special handling.
In `past_investment`, is the **build year** controlling retirement timing.
""",
    # ----------------------------------------------------------------------
    # Past investment & bounds
    # ----------------------------------------------------------------------
    "capacity": """\
## VedaLang: `capacity`

**Type**: number (≥0)
**Used in**: `past_investment`

Installed capacity associated with a specific vintage year.

- Units: `capacity_unit` of the parent process (e.g., GW).
""",
    "up": """\
## VedaLang: `up`

**Type**: number (≥0)
**Used in**: `bound`

Upper bound (maximum allowed) for a quantity.

- `activity_bound.up` – max activity.
- `cap_bound.up` – max installed capacity.
- `ncap_bound.up` – max new capacity.
""",
    "lo": """\
## VedaLang: `lo`

**Type**: number (≥0)
**Used in**: `bound`

Lower bound (minimum required) for a quantity.
""",
    "fx": """\
## VedaLang: `fx`

**Type**: number (≥0)
**Used in**: `bound`

Fixed value – the quantity must equal this value (no range).
""",
    # ----------------------------------------------------------------------
    # Flow
    # ----------------------------------------------------------------------
    "share": """\
## VedaLang: `share`

**Type**: number (0–1), default 1.0
**Used in**: `flow` (usually outputs)

Share of a **non-emission** flow among multiple outputs.

- Maps to TIMES attribute **`FLO_SHAR`** for non-emission outputs.
- For **emission commodities**, use `emission_factor` instead of `share`.

Example:
```yaml
outputs:
  - commodity: C:ELC
    share: 0.8
  - commodity: C:HEAT
    share: 0.2
```
""",
    "emission_factor": """\
## VedaLang: `emission_factor`

**Type**: number (≥0)
**Used in**: `flow` (for emission commodities)

Emission per unit **process activity**, not per-flow.

- Units: `<emission_commodity.unit>` per `<process.activity_unit>`
  e.g., `Mt CO2 per PJ activity`.
- Implemented via TIMES **`ENV_ACT`**; VEDA typically maps this to `FLO_EMIS`.

Use this instead of `share` for emission commodities.

**Example**:
```yaml
outputs:
  - commodity: E:CO2
    emission_factor: 0.07   # Mt CO2 per PJ activity
```
""",
    # ----------------------------------------------------------------------
    # Scenario parameters and time series
    # ----------------------------------------------------------------------
    "values": """\
## VedaLang: `values`

**Type**: object mapping `YYYY` → number
**Used in**: `scenario_parameter`, `time_series`, `time_varying_value`

Sparse time-series of year-indexed values.

- Keys: 4-digit years (`^[12][0-9]{3}$`).
- Values: numeric values (demands, prices, costs, etc.).
- Interpolation/extrapolation behavior is controlled by `interpolation`.

**Examples**:
```yaml
scenario_parameters:
  - name: co2_price
    values:
      "2025": 30
      "2030": 50

time_varying_value:
  values:
    "2030": 1000
    "2040": 800
```
""",
}
