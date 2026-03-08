"""Comprehensive hover documentation for all VedaLang schema fields.

This module contains markdown documentation strings with intentionally long lines
for better readability when rendered. Line length limits are disabled.
"""
# ruff: noqa: E501

SCHEMA_FIELD_DOCS: dict[str, str] = {
    # ----------------------------------------------------------------------
    # Top-level model structure
    # ----------------------------------------------------------------------
    "name": """\
## VedaLang: `name`

**Type**: string
**Used in**: active v0.2 objects such as `commodity`, `technology`, `technology_role`, `site`, `facility`, `fleet`, `opportunity`, `network`, and `run`

Identifier or human-readable label, depending on context.

For the active v0.2 DSL, prefer `id` for stable references and use `name` only
where an object supports a human-readable label.
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
    "commodity": """\
## VedaLang: `commodity`

**Type**: string (reference to `commodity.name`)
**Used in**: v0.2 flow specs, emission factors, and network definitions

Selects a defined commodity as the target of a flow, network, or technology-level
emission factor.

**Examples**:
```yaml
technologies:
  - id: heat_pump
    inputs:
      - commodity: secondary:electricity

networks:
  - id: transmission
    commodity: secondary:electricity
```
""",
    "interpolation": """\
## VedaLang: `interpolation`

**Type**: string enum
**Used in**: v0.2 time-varying values and temporal reference data

VEDA interpolation/extrapolation mode for year→value data.
Allowed values:

- `none` – no interpolation; values apply only to specified years.
- `interp_only` – interpolate between points; no extrapolation.
- `interp_extrap_eps` – interpolate and extrapolate with small epsilon limits.
- `interp_extrap` – interpolate and extrapolate normally.
- `interp_extrap_back` – fill backwards to earlier years.
- `interp_extrap_forward` – fill forwards to later years.

During lowering this maps to the matching VEDA year=0 option codes:
`none=-1`, `interp_only=1`, `interp_extrap_eps=2`, `interp_extrap=3`, `interp_extrap_back=4`, `interp_extrap_forward=5`.

**Example**:
```yaml
temporal_index_series:
  - id: cpi
    interpolation: interp_extrap
```
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
    # Commodity
    # ----------------------------------------------------------------------
    "kind": """\
## VedaLang: `kind`

**Type**: string enum (context-dependent)
**Used in**: multiple v0.2 sections (for example `commodities.kind`, `networks.kind`, `performance.kind`)

`kind` does not have one global enum. The valid values depend on where the field appears.
Use schema-aware hover/completion in the LSP for the current location's allowed values.
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
    # Technology and deployment
    # ----------------------------------------------------------------------
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
    # Deployment and stock references
    # ----------------------------------------------------------------------
    "technology": """\
## VedaLang: `technology`

**Type**: string
**Used in**: v0.2 deployment objects that select one technology by ID

Reference to a technology defined in the top-level `technologies` collection.
""",
    "region": """\
## VedaLang: `region`

**Type**: string
**Used in**: v0.2 network arcs, spatial reference objects, and run-derived diagnostics

Region identifier within the active run's selected `region_partition`.
Source models usually express placement through `sites`, memberships, and run
selection rather than attaching regions directly to authored deployment objects.
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
