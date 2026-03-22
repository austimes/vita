# Your First VedaLang Model

This tutorial uses the v0.3 DSL. You will build a minimal space-heating model
with one service commodity, one technology, one fleet, and one run.

## Step 1: Create a Minimal Model File

Create `my_first_model.veda.yaml` with this content:

<!-- GENERATED:minimal-example-enums:start -->
### Enum-backed Fields In This Example

- `dsl_version`: `0.3`
- `commodities[*].type`: `energy | service | material | emission | money | certificate`
- `commodities[*].energy_form`: `primary | secondary | resource`
- `technologies[*].inputs[*].basis`: `HHV | LHV`
- `technologies[*].performance.kind`: `efficiency | cop | custom`
- `spatial_layers[*].kind`: `polygon | point | grid`
- `region_partitions[*].mapping.kind`: `constant | file | spatial_join`
- `facilities[*].stock.items[*].metric`: `asset_count | installed_capacity | annual_activity`
<!-- GENERATED:minimal-example-enums:end -->

```yaml
# Schema version for this model file.
dsl_version: "0.3"

# Commodities declare the fuel and service namespaces used elsewhere.
commodities:
  - id: natural_gas
    type: energy
    energy_form: primary
  - id: space_heat
    type: service

# Technologies define the concrete conversion behavior and coefficients.
technologies:
  - id: gas_heater
    provides: space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9

# Technology roles group the technologies that may provide a service.
technology_roles:
  - id: space_heat_supply
    primary_service: space_heat
    technologies: [gas_heater]

# Spatial layers point to the underlying geographic data source.
spatial_layers:
  - id: geo_demo
    kind: polygon
    key: region_id
    geometry_file: data/regions.geojson

# Region partitions group geometry members into the model regions used at compile time.
region_partitions:
  - id: toy_region
    layer: geo_demo
    members: [QLD]
    mapping:
      kind: constant
      value: QLD

# Fleets are the simplest way to place generic toy-model stock.
fleets:
  - id: residential_space_heat
    technology_role: space_heat_supply
    stock:
      items:
        - technology: gas_heater
          metric: installed_capacity
          observed:
            value: 12 kW
            year: 2025
    distribution:
      method: direct

# Year sets declare the solve years; runs pick one and the regional view.
year_sets:
  - id: pathway_2025_2035
    start_year: 2025
    milestone_years: [2025, 2035]

runs:
  - id: toy_region_2025
    veda_book_name: TOYREGION2025
    year_set: pathway_2025_2035
    currency_year: 2024
    region_partition: toy_region
    reporting:
      value_flows: false
```

### What Each Section Does

- `commodities`: declares the physical inputs and service outputs
- `technologies`: concrete technology definitions and coefficients
- `technology_roles`: service-oriented role contracts that group allowed technologies
- `spatial_layers`: the source geographic layer that sites and regions refer to
- `region_partitions`: how underlying spatial members are grouped into model regions
- `fleets`: generic or distributed stock, using `distribution.method: direct`
  for toy single-region models
- `year_sets`: explicit solve-year catalogs with a `start_year` and milestone years
- `runs`: compile-time selection of year set, currency year, region partition,
  and optional reporting toggles such as `reporting.value_flows`. When enabled,
  VedaLang emits the matching `RPT_OPT` control into `SysSettings.xlsx` and
  documents it on the workbook's `Reporting` tab.

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
2. v0.3 compilation to CSIR, CPIR, TableIR, and Excel
3. xl2times validation of the emitted Excel

Use `--keep-workdir` if you want to inspect the generated Excel and artifact
files.

## Step 4: Common v0.3 Errors

### Wrong Primary Service

**Error**: `E004 technology_role.primary_service must reference a service commodity`

**Fix**: point `technology_roles[*].primary_service` at a commodity with `type: service`.

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

### Missing Direct Fleet Targets

**Error**: `E020 direct fleet distribution requires target_regions for multi-region runs`

**Fix**: on multi-region runs, add `distribution.target_regions` to the fleet,
or switch to `proportional`/`custom` distribution if you actually want an
allocation.

## Next Steps

- [DSL + CLI skill](../../skills/vedalang-dsl-cli/SKILL.md)
- [mini_space_heat.veda.yaml](../../vedalang/examples/quickstart/mini_space_heat.veda.yaml)
- [toy_heat_network.veda.yaml](../../vedalang/examples/feature_demos/toy_heat_network.veda.yaml)
