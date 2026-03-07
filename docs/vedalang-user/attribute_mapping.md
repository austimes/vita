# VedaLang Attribute Mapping

This document maps the active **v0.2** source attributes to the compiled
TIMES/VEDA concepts.

## Where Attributes Live in v0.2

- `technologies` carry physical inputs, outputs, performance, emissions, and
  technology-level costs.
- `technology_roles` carry service intent and allowed substitutions.
- `facilities` and `fleets` carry existing stock observations.
- `opportunities` carry future build limits.
- `runs` carry base year and currency year context.

## Technology Attributes

| VedaLang v0.2 attribute | TIMES concept | Notes |
|---|---|---|
| `performance.kind: efficiency` | `ACT_EFF` | Technology conversion efficiency |
| `performance.kind: cop` | `ACT_EFF`-like derived performance | Used for heat pumps and similar devices |
| `investment_cost` | `NCAP_COST` | Explicit currency-year literal per stock/capacity denominator |
| `fixed_om` | `NCAP_FOM` | Explicit currency-year literal per denominator per year |
| `variable_om` | `ACT_COST` | Explicit currency-year literal per activity/service denominator |
| `lifetime` | `NCAP_TLIFE` | Technical lifetime |
| `emissions[*].factor` | `ENV_ACT` | Ledger emission coefficient |

Example:

```yaml
technologies:
  - id: gas_heater
    provides: service:space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9
    investment_cost: 220 AUD2024/kW
    fixed_om: 8 AUD2024/kW/year
    variable_om: 25 AUD2024/MWh
    lifetime: 20 year
    emissions:
      - commodity: emission:co2
        factor: 0.056 t/GJ
```

## Stock Placement

| VedaLang v0.2 attribute | TIMES concept | Notes |
|---|---|---|
| `facilities[*].stock.items[*]` | `PRC_RESID` / stock initialization | Site-bound existing stock |
| `fleets[*].stock.items[*]` | regional stock initialization | Distributed stock rolled up by run region |
| `opportunities[*].max_new_capacity` | new-build cap | Optional future build limit |

Example:

```yaml
facilities:
  - id: residential_heat
    site: single_energy_hub
    technology_role: space_heat_supply
    stock:
      items:
        - technology: gas_heater
          metric: installed_capacity
          observed:
            value: 80 MW
            year: 2025
```

## Run Context

| VedaLang v0.2 attribute | TIMES concept | Notes |
|---|---|---|
| `runs[*].base_year` | model base year | Used for stock adjustment and compilation context |
| `runs[*].currency_year` | reporting currency year | Normalizes compiled cost literals |
| `runs[*].region_partition` | model-region set | Controls spatial lowering |

## Conventions

- Keep heating-value basis explicit on combustible inputs.
- Emit emissions via `technologies[*].emissions`, not via output flows.
- Prefer service-oriented `technology_roles` with multiple technologies over
  fuel-specific roles.
- Treat Excel and DD files as compiled artifacts, not authoring surfaces.
