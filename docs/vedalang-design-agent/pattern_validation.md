# Pattern Validation Catalog

This document catalogs each pattern in `rules/patterns.yaml` and its validation status.

## Summary

| Pattern | Status | Category | Validated In |
|---------|--------|----------|--------------|
| `add_power_plant` | ✅ Validated | generation | DC1, DC2, DC3, DC4, DC5 |
| `add_renewable_plant` | ✅ Validated | generation | DC2, DC3, DC4 |
| `add_energy_commodity` | ✅ Validated | commodity | DC1, DC2, DC3, DC4, DC5 |
| `add_emission_commodity` | ✅ Validated | commodity | DC3, DC4 |
| `co2_price_trajectory` | ✅ Validated | scenario | DC4 |

---

## add_power_plant ✅ Validated

**Description:** Define a thermal generation process that converts fuel to electricity.

**Category:** generation

**Produces VEDA Tags:** `~FI_PROCESS`, `~FI_T`

**Validated In:** DC1, DC2, DC3, DC4, DC5

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `plant_name` | string | ✅ | - | Unique identifier for the power plant |
| `fuel_commodity` | string | ✅ | - | Input fuel commodity (e.g., NG, COAL) |
| `output_commodity` | string | ✅ | - | Output commodity (typically ELC) |
| `efficiency` | number | ❌ | 0.40 | Thermal efficiency (0-1) |
| `capacity_unit` | string | ❌ | GW | Unit for capacity |
| `activity_unit` | string | ❌ | PJ | Unit for activity/generation |

### Example Expansion

```bash
uv run veda_pattern expand add_power_plant \
  --param plant_name=PP_CCGT \
  --param fuel_commodity=NG \
  --param output_commodity=ELC \
  --param efficiency=0.55
```

**Output:**
```yaml
processes:
  - name: PP_CCGT
    description: Thermal power plant
    sets: [ELE]
    activity_unit: PJ
    capacity_unit: GW
    inputs:
      - commodity: energy:natural_gas
        share: 1.0
    outputs:
      - commodity: energy:electricity
        share: 1.0
    emission_factors:
      emission:co2: 0.05
    efficiency: 0.55
```

### Usage in DC Fixtures

- **DC1:** Basic thermal plant (`vedalang/examples/dc1_thermal_from_patterns.veda.yaml`)
- **DC2-DC5:** Used as baseline thermal generation

---

## add_renewable_plant ✅ Validated

**Description:** Define a renewable generation process (solar, wind, hydro). No fuel input required.

**Category:** generation

**Produces VEDA Tags:** `~FI_PROCESS`

**Validated In:** DC2, DC3, DC4

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `plant_name` | string | ✅ | - | Unique identifier for the plant |
| `output_commodity` | string | ✅ | energy:electricity | Output commodity |
| `technology_type` | enum | ✅ | - | One of: solar_pv, wind_onshore, wind_offshore, hydro_ror, hydro_dam |
| `capacity_unit` | string | ❌ | GW | Unit for capacity |

### Example Expansion

```bash
uv run veda_pattern expand add_renewable_plant \
  --param plant_name=PP_WIND \
  --param output_commodity=energy:electricity \
  --param technology_type=wind_onshore
```

**Output:**
```yaml
processes:
  - name: PP_WIND
    description: wind_onshore renewable plant
    sets: [ELE, RNEW]
    capacity_unit: GW
    outputs:
      - commodity: energy:electricity
        share: 1.0
```

### Usage in DC Fixtures

- **DC2:** Wind plant sharing energy:electricity output with thermal
- **DC3-DC4:** Renewable plant with zero emissions

---

## add_energy_commodity ✅ Validated

**Description:** Define an energy carrier commodity (fuel, electricity).

**Category:** commodity

**Produces VEDA Tags:** `~FI_COMM`

**Validated In:** DC1, DC2, DC3, DC4, DC5

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `name` | string | ✅ | - | Commodity name (e.g., ELC, NG) |
| `unit` | string | ❌ | PJ | Energy unit |
| `description` | string | ❌ | "" | Optional description |

### Example Expansion

```bash
uv run veda_pattern expand add_energy_commodity \
  --param name=NG \
  --param unit=PJ \
  --param description="Natural Gas"
```

**Output:**
```yaml
commodities:
  - name: NG
    type: energy
    unit: PJ
    description: Natural Gas
```

### Usage in DC Fixtures

- All DC fixtures define ELC and NG commodities

---

## add_emission_commodity ✅ Validated

**Description:** Define an emission commodity (CO2, NOx, etc.).

**Category:** commodity

**Produces VEDA Tags:** `~FI_COMM`

**Validated In:** DC3, DC4

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `name` | string | ✅ | - | Emission name (e.g., CO2, NOX) |
| `unit` | string | ❌ | Mt | Emission unit |

### Example Expansion

```bash
uv run veda_pattern expand add_emission_commodity \
  --param name=CO2
```

**Output:**
```yaml
commodities:
  - name: CO2
    type: emission
    unit: Mt
```

### Usage in DC Fixtures

- **DC3:** Introduces CO2 as emission commodity
- **DC4:** CO2 with price trajectory

---

## co2_price_trajectory ✅ Validated

**Description:** Define a CO2 price trajectory over time for carbon pricing scenarios.

**Category:** scenario

**Produces VEDA Tags:** `~TFM_INS-TS` (via TableIR, not VedaLang)

**Validated In:** DC4

**Note:** This pattern only has a `tableir_template`, not a `vedalang_template`. Use `--format tableir` when expanding.

### Parameters

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `prices` | object | ✅ | - | Dictionary of year → price (e.g., `{2025: 50, 2030: 100}`) |
| `region` | string | ❌ | REG1 | Region code |

### Example Expansion (Programmatic)

```python
from tools.veda_patterns import expand_pattern

result = expand_pattern(
    "co2_price_trajectory",
    parameters={"prices": {2025: 50, 2030: 100}, "region": "REG1"},
    output_format="tableir"
)
```

**Output:**
```yaml
tag: ~TFM_INS-TS
rows:
  - Region: REG1
    YEAR: 2025
    Pset_CO: CO2
    COST: 50
  - Region: REG1
    YEAR: 2030
    Pset_CO: CO2
    COST: 100
```

### CLI Limitation

The CLI currently does not support passing complex object parameters (like `prices`). Use the Python API for this pattern.

### Usage in DC Fixtures

- **DC4:** `vedalang/examples/dc4_co2_price_scenario.veda.yaml` uses a VedaLang `scenarios` section that compiles to the same `~TFM_INS-TS` output.

---

## Validation Methodology

Each pattern was validated through the following process:

1. **Expansion Test:** Pattern expands without error with valid parameters
2. **YAML Validity:** Expanded output parses as valid YAML
3. **VedaLang Compilation:** Patterns with `vedalang_template` compile to TableIR
4. **TableIR Schema Validation:** Compiled TableIR validates against `tableir.schema.json`
5. **xl2times Validation:** Generated Excel passes xl2times (via `vedalang validate`)

See `tests/test_patterns_expand.py` for automated validation tests.

---

## Adding New Patterns

When adding new patterns:

1. Define in `rules/patterns.yaml`
2. Add test cases to `tests/test_patterns_expand.py`
3. Create a DC fixture demonstrating the pattern
4. Update this catalog with validation status
5. Run full test suite: `uv run pytest tests/ -v`
