# Your First VedaLang Model

This tutorial uses the v0.2 DSL. You will build a minimal space-heating model
with one service commodity, one technology, one facility, and one run.

## Step 1: Create a Minimal Model File

Create `my_first_model.veda.yaml` with this content:

```yaml
# Schema version for this model file.
dsl_version: "0.2"

# Commodities declare the fuel and service namespaces used elsewhere.
commodities:
  - id: primary:natural_gas
    kind: primary
  - id: service:space_heat
    kind: service

# Technologies define the concrete conversion behavior and coefficients.
technologies:
  - id: gas_heater
    provides: service:space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9

# Technology roles group the technologies that may provide a service.
technology_roles:
  - id: space_heat_supply
    primary_service: service:space_heat
    technologies: [gas_heater]

# Spatial layers point to the underlying geographic data source.
spatial_layers:
  - id: geo.demo
    kind: polygon
    key: region_id
    geometry_file: data/regions.geojson

# Region partitions group geometry members into the model regions used at compile time.
region_partitions:
  - id: toy_region
    layer: geo.demo
    members: [QLD]
    mapping:
      kind: constant
      value: QLD

# Sites anchor assets to a location and region membership.
sites:
  - id: brisbane_home
    location:
      point:
        lat: -27.47
        lon: 153.02
    membership_overrides:
      region_partitions:
        toy_region: QLD

# Facilities declare the real-world asset stock attached to each site.
facilities:
  - id: brisbane_space_heat
    site: brisbane_home
    technology_role: space_heat_supply
    stock:
      items:
        - technology: gas_heater
          metric: installed_capacity
          observed:
            value: 12 kW
            year: 2025

# Runs select the base year and regional view to compile.
runs:
  - id: toy_region_2025
    base_year: 2025
    currency_year: 2024
    region_partition: toy_region
```

### What Each Section Does

- `commodities`: declares the physical inputs and service outputs
- `technologies`: concrete technology definitions and coefficients
- `technology_roles`: service-oriented role contracts that group allowed technologies
- `spatial_layers`: the source geographic layer that sites and regions refer to
- `region_partitions`: how underlying spatial members are grouped into model regions
- `sites` and `facilities`: concrete assets and their existing stock
- `runs`: compile-time selection of base year, currency year, and region partition

## Step 2: Validate the Model

Use the run-scoped validation path:

```bash
uv run vedalang validate my_first_model.veda.yaml --run toy_region_2025
```

For compile-only output:

```bash
uv run vedalang compile my_first_model.veda.yaml --run toy_region_2025 --out out/
```

That compile writes the run-scoped artifacts:

- `toy_region_2025.csir.yaml`
- `toy_region_2025.cpir.yaml`
- `toy_region_2025.explain.json`

## Step 3: What Validation Does

`vedalang validate` runs three stages:

1. Lint and schema validation
2. v0.2 compilation to CSIR, CPIR, TableIR, and Excel
3. xl2times validation of the emitted Excel

Use `--keep-workdir` if you want to inspect the generated Excel and artifact
files.

## Step 4: Common v0.2 Errors

### Wrong Primary Service

**Error**: `E004 technology_role.primary_service must reference a service commodity`

**Fix**: point `technology_roles[*].primary_service` at a `service:*` commodity.

### Missing Run Selection

**Error**: compilation asks for `--run`

**Fix**: pass the run id explicitly:

```bash
uv run vedalang compile my_first_model.veda.yaml --run toy_region_2025 --out out/
```

### Unresolved Stock Conversion

**Error**: `E012 asset_count lowering requires a stock_characterization`

**Fix**: if you declare fleet/facility stock in `asset_count`, add a
`stock_characterizations` entry that converts to the required lowering metrics.

## Next Steps

- [DSL + CLI skill](../../skills/vedalang-dsl-cli/SKILL.md)
- [/Users/gre538/code/vedalang/vedalang/examples/v0_2/mini_space_heat.veda.yaml](/Users/gre538/code/vedalang/vedalang/examples/v0_2/mini_space_heat.veda.yaml)
- [/Users/gre538/code/vedalang/vedalang/examples/v0_2/toy_heat_network.veda.yaml](/Users/gre538/code/vedalang/vedalang/examples/v0_2/toy_heat_network.veda.yaml)
