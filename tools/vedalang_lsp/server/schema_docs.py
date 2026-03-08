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

**Status**: legacy archive surface

The active public DSL is v0.2 and no longer uses a `model:` root block.
Use top-level objects such as `commodities`, `technologies`,
`technology_roles`, `sites`, `facilities`, `fleets`, `opportunities`,
`networks`, and `runs`.
""",
    "name": """\
## VedaLang: `name`

**Type**: string
**Used in**: active v0.2 objects such as `commodity`, `technology`, `technology_role`, `site`, `facility`, `fleet`, `opportunity`, `network`, and `run`

Identifier or human-readable label, depending on context.

For the active v0.2 DSL, prefer `id` for stable references and use `name` only
where an object supports a human-readable label.

Legacy `model/process/process_template/process_instance/case/study` meanings are
archive-only and are not part of the active public authoring surface.
""",
    "description": """\
## VedaLang: `description`

**Type**: string
**Used in**: v0.2 objects that support human-readable documentation

Optional human-readable description to document the purpose of the object.

**Example**:
```yaml
technologies:
  - id: ccgt
    description: Combined-cycle gas turbine for baseload electricity
```
""",
    "regions": """\
## VedaLang: `regions`

**Status**: legacy archive field

The active v0.2 DSL does not use `model.regions`.
Define spatial context through `spatial_layers`, `region_partitions`, `sites`,
and `runs`.

**Example**:
```yaml
runs:
  - id: single_2025
    region_partition: single_region
```
""",
    "milestone_years": """\
## VedaLang: `milestone_years`

**Status**: legacy archive field

The active v0.2 DSL no longer defines milestone years on `model`.
Use `runs[*].base_year` plus explicit year-indexed values in stock and temporal
objects instead of an implicit model-root year list.

**Example**:
```yaml
runs:
  - id: single_2025
    base_year: 2025
```
""",
    "timeslices": """\
## VedaLang: `timeslices`

**Status**: legacy archive field

The active v0.2 public schema uses temporal reference objects such as
`temporal_index_series` rather than `model.timeslices`.
""",
    "commodities": """\
## VedaLang: `commodities`

**Type**: array of `commodity` objects
**Used in**: v0.2 root

List of v0.2 commodity definitions.
Each entry defines an `id` and `kind`.

**Example**:
```yaml
commodities:
  - id: secondary:electricity
    kind: secondary
  - id: service:space_heat
    kind: service
```
""",
    "technologies": """\
## VedaLang: `technologies`

**Type**: array of `technology` objects
**Used in**: v0.2 root

Concrete implementation pathways.
Technologies declare physical inputs/outputs, performance, costs, lifetime,
and emissions.

**Example**:
```yaml
technologies:
  - id: heat_pump
    provides: service:space_heat
    inputs:
      - commodity: secondary:electricity
    performance:
      kind: cop
      value: 3.0
```
""",
    "technology_roles": """\
## VedaLang: `technology_roles`

**Type**: array of `technology_role` objects
**Used in**: v0.2 root

Service-oriented role contracts that group substitutable technologies around
one `primary_service`.

**Example**:
```yaml
technology_roles:
  - id: space_heat_supply
    primary_service: service:space_heat
    technologies: [gas_heater, heat_pump]
```
""",
    "runs": """\
## VedaLang: `runs`

**Type**: array of `run` objects
**Used in**: v0.2 root

Defines the compiled model context: base year, currency year, and region
partition.

**Example**:
```yaml
runs:
  - id: single_2025
    base_year: 2025
    currency_year: 2024
    region_partition: single_region
```
""",
    "process_templates": """\
## VedaLang: `process_templates`

**Status**: legacy archive surface

The active v0.2 DSL does not use `process_templates`.
Author concrete pathways in `technologies` and group substitutions in
`technology_roles`.
""",
    "processes": """\
## VedaLang: `processes`

**Status**: legacy archive surface

The active v0.2 DSL does not use `processes`.
Author technologies at the top level and place stock/build options through
`facilities`, `fleets`, `opportunities`, and `networks`.
""",
    "scenario_parameters": """\
## VedaLang: `scenario_parameters`

**Status**: legacy archive surface

The active v0.2 public schema does not expose `scenario_parameters`.
Represent active temporal and run-specific context through v0.2 run, stock, and
reference-data objects instead.
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
      commodity: secondary:electricity
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
      commodity: emission:co2
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
      carrier: gas
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
  - commodity: emission:co2

scenario_parameters:
  - commodity: secondary:electricity

trade_links:
  - commodity: primary:natural_gas
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
    commodity: emission:co2
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
    commodity: emission:co2
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
    commodity: secondary:electricity
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

**Type**: number (0-1) or `time_varying_value`
**Used in**: v0.2 `technology.performance` objects where `kind: efficiency`

Energy or service conversion efficiency for a technology after lowering to
TIMES `ACT_EFF`.

**Examples**:
```yaml
technologies:
  - id: ccgt
    performance:
      kind: efficiency
      value: 0.55
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

**Type**: string enum (context-dependent)
**Used in**: multiple v0.2 sections (for example `commodities.kind`, `networks.kind`, `performance.kind`)

`kind` does not have one global enum. The valid values depend on where the field appears.
Use schema-aware hover/completion in the LSP for the current location's allowed values.
""",
    "context": """\
## VedaLang: `context`

**Status**: legacy archive field

The active v0.2 DSL does not use `context` on commodities or process
instances. Prefer explicit spatial placement with `sites`, `facilities`,
`fleets`, `region_partitions`, and `runs`.
""",
    "unit": """\
## VedaLang: `unit`

**Type**: string
**Used in**: v0.2 commodities, temporal reference data, and stock metrics

Unit of measurement for the surrounding value. For commodities, this anchors
physical interpretation of flows and coefficients. For reference data, it
documents the index or measurement basis used during adjustment.

**Example**:
```yaml
commodities:
  - id: secondary:electricity
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
**Used in**: v0.2 technology and deployment objects that define process activity

Unit for modeled activity, i.e., the denominator for efficiency, variable cost,
and emission-factor terms after lowering to TIMES.

Must be an **extensive (non-rate)** unit.
Supported families:

- Energy: `PJ`, `TJ`, `GJ`, `MWh`, `GWh`, `TWh`, `MTOE`, `KTOE`
- Service: `Bvkm`
- Mass: `Mt`, `kt`, `t`, `Gt`

**Example**:
```yaml
technologies:
  - id: ccgt
    activity_unit: PJ
```
""",
    "capacity_unit": """\
## VedaLang: `capacity_unit`

**Type**: string
**Default**: `GW`
**Used in**: v0.2 technology and deployment objects that define buildable stock

Unit for modeled capacity, used in capacity-related TIMES attributes such as
capital cost, fixed O&M, and technical lifetime.

Must be either:

- Power unit: `GW`, `MW`, `kW`, `TW`
- Explicit annual rate: `<unit>/yr` (e.g., `PJ/yr`, `Bvkm/yr`, `Mt/yr`)

For non-power capacities, include explicit `/yr`.
Ambiguous forms like `capacity_unit: PJ` are invalid.

Cap-to-activity linkage is derived as:
`PRC_CAPACT = convert(1 * capacity_unit * 1 yr -> activity_unit)`

**Example**:
```yaml
technologies:
  - id: ccgt
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
    input: primary:natural_gas
```
""",
    "inputs": """\
## VedaLang: `inputs`

**Type**: array of `flow` objects
**Used in**: v0.2 `technology` objects

Detailed specification of physical input commodities consumed by a technology.
Each flow names a commodity and may add metadata such as `share`.

**Example**:
```yaml
technologies:
  - id: boiler
    inputs:
      - commodity: primary:natural_gas
      - commodity: primary:oil
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
**Used in**: v0.2 `technology` objects

Detailed specification of physical output commodities produced by a technology.

**Example**:
```yaml
technologies:
  - id: ccgt
    outputs:
      - commodity: secondary:electricity
```
""",
    "investment_cost": """\
## VedaLang: `investment_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 technologies and deployment/stock objects that carry new-build cost data

Investment cost per unit of **new capacity**.

- Maps to TIMES attribute **`NCAP_COST`**.
- Units: typically currency per `capacity_unit` (e.g., `$/GW`).

**Example**:
```yaml
technologies:
  - id: heat_pump
    investment_cost:
      values:
        "2030": 1000
        "2040": 800
      interpolation: interp_extrap
```
""",
    "fixed_om_cost": """\
## VedaLang: `fixed_om_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 technologies and deployment/stock objects with fixed cost assumptions

Fixed operation & maintenance cost per unit **installed capacity per year**.

- Maps to TIMES attribute **`NCAP_FOM`**.
- Units: e.g., `$/GW/yr` or currency/`capacity_unit`/year.
""",
    "variable_om_cost": """\
## VedaLang: `variable_om_cost`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 technologies and deployment objects with activity-linked cost assumptions

Variable operation & maintenance cost per unit of **activity**.

- Maps to TIMES attribute **`ACT_COST`**.
- Units: currency per `activity_unit` (e.g., `$/PJ`).
""",
    "import_price": """\
## VedaLang: `import_price`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 technologies or opportunities that model import-style supply

Price of imported commodities.

- Maps to TIMES attribute **`IRE_PRICE`** for import processes.
- Units: currency per energy/material unit (e.g., `$/PJ`).
""",
    "lifetime": """\
## VedaLang: `lifetime`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 technologies and stock-bearing deployment objects

Technical lifetime of **new capacity**.

- Maps to TIMES attribute **`NCAP_TLIFE`**.
- Units: years.

Affects when capacity retires and how capital costs are annualized.
""",
    "availability_factor": """\
## VedaLang: `availability_factor`

**Type**: number (0–1) or `time_varying_value`
**Used in**: v0.2 technologies and deployment objects with annual utilization limits

Fraction of time capacity is available for use.

- Maps to TIMES attribute **`NCAP_AF`**.
- Often interpreted as maximum annual utilization factor.
""",
    "activity_bound": """\
## VedaLang: `activity_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: v0.2 technologies, facilities, fleets, opportunities, and networks where activity is bounded

Bounds on **annual process activity**.

- Conceptually maps to TIMES **`ACT_BND`** attributes.

**Example**:
```yaml
technologies:
  - id: coal_plant
    activity_bound:
      up: 100    # max activity
```
""",
    "cap_bound": """\
## VedaLang: `cap_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: v0.2 stock-bearing deployment objects

Bounds on **total installed capacity**.

- Conceptually maps to TIMES **`CAP_BND`** attributes.
""",
    "ncap_bound": """\
## VedaLang: `ncap_bound`

**Type**: `bound` object (`up`, `lo`, `fx`)
**Used in**: v0.2 stock-bearing deployment objects

Bounds on **new capacity additions per period**.

- Conceptually maps to TIMES **`NCAP_BND`** attributes.
""",
    "stock": """\
## VedaLang: `stock`

**Type**: number (≥0) or `time_varying_value`
**Used in**: v0.2 facilities, fleets, and other stock-bearing deployment objects

Aggregate **residual capacity** stock.

- Maps to TIMES attribute **`PRC_RESID`**.
- Represents a lumped existing capacity that decays linearly over `lifetime`.

For new models, prefer `existing_capacity` to track vintages explicitly.
""",
    "existing_capacity": """\
## VedaLang: `existing_capacity`

**Type**: array of `past_investment` objects
**Used in**: v0.2 technologies and stock-bearing deployment objects

Past capacity investments with explicit **vintage years**.

- Maps to TIMES attribute **`NCAP_PASTI`**.
- Enables proper tracking of retirement based on `lifetime`.

**Example**:
```yaml
facilities:
  - id: existing_ccgt
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
**Used in**: v0.2 deployment objects that select one technology by ID

Reference to a technology defined in the top-level `technologies` collection.
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

Some roles impose additional requirements (e.g., `EUS` often needs `scope`/`context`).
""",
    "scope": """\
## VedaLang: `scope`

**Status**: legacy archive field

The active v0.2 public DSL does not use `scope` as an authoring primitive.
Model service intent through `technology_roles`, placement through `sites` and
`runs`, and reporting overlays through explicit v0.2 reference objects.
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

**Status**: legacy archive field

The active v0.2 DSL does not use `process_instance.template`.
Use `technology_role`, `technology`, and deployment objects instead.
""",
    "region": """\
## VedaLang: `region`

**Type**: string
**Used in**: v0.2 network arcs, spatial reference objects, and run-derived diagnostics

Region identifier within the active run's selected `region_partition`.
Source models usually express placement through `sites`, memberships, and run
selection rather than attaching regions directly to legacy process instances.
""",
    "variant": """\
## VedaLang: `variant`

**Status**: legacy archive field

The active v0.2 public DSL does not expose a top-level `variant` field.
Technology alternatives should be modeled as separate `technologies` linked by
one `technology_role`.
""",
    "vintage": """\
## VedaLang: `vintage`

**Type**: integer year (≥1900)
**Used in**: `past_investment`

Build year for existing stock. Controls retirement timing when combined with the
parent technology's `lifetime`.
""",
    # ----------------------------------------------------------------------
    # Past investment & bounds
    # ----------------------------------------------------------------------
    "capacity": """\
## VedaLang: `capacity`

**Type**: number (≥0)
**Used in**: `past_investment`

Installed capacity associated with a specific vintage year.

- Units: `capacity_unit` of the parent technology or stock-bearing object
  (for example `GW`).
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
  - commodity: secondary:electricity
    share: 0.8
  - commodity: service:space_heat
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
  - commodity: emission:co2
    emission_factor: 0.07   # Mt CO2 per PJ activity
```
""",
    # ----------------------------------------------------------------------
    # Scenario parameters and time series
    # ----------------------------------------------------------------------
    "values": """\
## VedaLang: `values`

**Type**: object mapping `YYYY` → number
**Used in**: v0.2 `time_varying_value`-style objects, temporal reference data, and year-indexed stock/cost series

Sparse time-series of year-indexed values.

- Keys: 4-digit years (`^[12][0-9]{3}$`).
- Values: numeric values (demands, prices, costs, etc.).
- Interpolation/extrapolation behavior is controlled by `interpolation`.

**Examples**:
```yaml
temporal_index_series:
  - id: cpi
    values:
      "2025": 1.00
      "2030": 1.12

technologies:
  - id: heat_pump
    investment_cost:
      values:
        "2030": 1000
        "2040": 800
```
""",
}

LEGACY_ONLY_SCHEMA_FIELDS = {
    "model",
    "regions",
    "milestone_years",
    "timeslices",
    "code",
    "season",
    "weekly",
    "daynite",
    "fractions",
    "process_templates",
    "processes",
    "scenario_parameters",
    "trade_links",
    "destination",
    "bidirectional",
    "constraints",
    "cases",
    "studies",
    "context",
    "sets",
    "primary_commodity_group",
    "input",
    "output",
    "role",
    "sankey_stage",
    "template",
    "variant",
}

for _legacy_field in LEGACY_ONLY_SCHEMA_FIELDS:
    SCHEMA_FIELD_DOCS.pop(_legacy_field, None)
