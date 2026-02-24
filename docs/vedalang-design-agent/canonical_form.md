# VedaLang Canonical Table Form

**Status:** Normative specification  
**Last updated:** 2025-12-21

## Overview

VEDA input tables are extremely flexible by design - almost any pivot is supported (wide by year, wide by region, etc.). This flexibility was designed for humans pasting data into Excel.

**VedaLang takes the opposite approach:** We enforce ONE canonical form to prevent schema sprawl and ensure deterministic, predictable output.

## Core Principles

1. **One canonical form** - No alternative representations allowed
2. **Tidy long format** - One row = one fact
3. **Year as column** - Never as column headers
4. **No VEDA interpolation** - Compiler expands to explicit values
5. **Lowercase columns** - Mechanical mapping from VEDA headers

---

## Canonical Table Format

### Structure: Tidy Long-by-Year

Every TableIR table follows this structure:

| Dimension Columns | Year Column | Parameter Columns |
|-------------------|-------------|-------------------|
| `region`, `techname`, etc. | `year` (for TS) | `cost`, `eff`, etc. |

**One row = one logical record** keyed by dimension columns.

### Example: Time-Series Data

**Logical data:** ELC price in REG1: 10 in 2020, 20 in 2030, 30 in 2040

**Canonical form (REQUIRED):**

```yaml
tag: "~TFM_INS-TS"
rows:
  - { region: "REG1", year: 2020, pset_co: "ELC", cost: 10 }
  - { region: "REG1", year: 2030, pset_co: "ELC", cost: 20 }
  - { region: "REG1", year: 2040, pset_co: "ELC", cost: 30 }
```

**Forbidden alternatives:**

```yaml
# FORBIDDEN: Wide by year
rows:
  - { region: "REG1", pset_co: "ELC", "2020": 10, "2030": 20, "2040": 30 }

# FORBIDDEN: Wide by region
rows:
  - { year: 2020, pset_co: "ELC", "REG1": 10, "REG2": 15 }

# FORBIDDEN: Interpolation markers
rows:
  - { region: "REG1", year: 2020, pset_co: "ELC", cost: 10 }
  - { region: "REG1", year: 2030, pset_co: "ELC", cost: "I" }  # NO!
```

---

## Column Naming Convention

All TableIR column names are **lowercase** with consistent normalization:

| VEDA Header | TableIR Column |
|-------------|----------------|
| `TechName` | `techname` |
| `CommName` | `commname` |
| `Comm-IN` | `commodity-in` |
| `Comm-OUT` | `commodity-out` |
| `YEAR` | `year` |
| `Region` | `region` |
| `Sets` | `sets` |
| `EFF` | `eff` |
| `Csets` | `csets` |
| `Pset_CO` | `pset_co` |

This provides:
- Simple programmatic generation
- 1:1 mapping back to Excel headers
- Case-insensitive matching in xl2times

---

## Tag-Specific Column Requirements

### Non-Time-Series Tags

| Tag | Required Columns | Optional Columns |
|-----|------------------|------------------|
| `~FI_COMM` | `region`, `csets`, `commname` | `unit`, `desc` |
| `~FI_PROCESS` | `region`, `techname`, `sets` | `techdesc`, `tact`, `tcap` |
| `~FI_T` | `region`, `techname` | `commodity-in`, `commodity-out`, `eff`, `share-i`, `share-o` |
| `~BOOKREGIONS_MAP` | `bookname`, `region` | - |
| `~STARTYEAR` | `value` | - |
| `~TIMEPERIODS` | `p` | - |
| `~CURRENCIES` | `currency` | - |

### Time-Series Tags

| Tag | Required Columns | Entity Column(s) | Parameter Columns |
|-----|------------------|------------------|-------------------|
| `~TFM_INS-TS` | `region`, `year` | `techname` OR `pset_co` | `cost`, etc. |

**Invariant:** All `*-TS` tags MUST have a `year` column.

---

## Interpolation Handling

### VEDA-Compatible Interpolation Modes

VedaLang uses the same interpolation/extrapolation semantics as VEDA, but the
**compiler expands to dense data** at compile time. No year=0 rows are emitted;
interpolation is fully handled by VedaLang.

| VedaLang Enum | Behavior |
|---------------|----------|
| `none` | No interpolation/extrapolation - only specified years |
| `interp_only` | Interpolate between points, no extrapolation beyond |
| `interp_extrap_eps` | Interpolate, forward extrapolation (EPS behavior) |
| `interp_extrap` | Full interpolation and extrapolation (both directions) |
| `interp_extrap_back` | Interpolate, backward extrapolation only |
| `interp_extrap_forward` | Interpolate, forward extrapolation only |

### VedaLang Side: Interpolation is REQUIRED

VedaLang requires explicit interpolation mode - no defaults:

```yaml
scenarios:
  - name: CO2_Price
    type: commodity_price
    commodity: CO2
    interpolation: interp_extrap  # REQUIRED - must be explicit
    values:
      2020: 50
      2050: 200
```

### Compiler Side: Expand to Dense

The compiler:
1. Reads model years from `milestone_years`
2. Applies the specified interpolation/extrapolation mode
3. Emits **one row per model year** with explicit numeric values

**Example:**

VedaLang input:
```yaml
interpolation: interp_extrap
values:
  2020: 50
  2050: 200
```

With model years [2020, 2030, 2040, 2050]:

TableIR output (dense, one row per model year):
```yaml
rows:
  - { region: "REG1", year: 2020, pset_co: "CO2", cost: 50 }
  - { region: "REG1", year: 2030, pset_co: "CO2", cost: 100 }   # Interpolated
  - { region: "REG1", year: 2040, pset_co: "CO2", cost: 150 }   # Interpolated
  - { region: "REG1", year: 2050, pset_co: "CO2", cost: 200 }
```

### Why This Approach?

- **Explicit is better than implicit** - no hidden defaults to track down
- **Self-contained output** - TableIR has all values, no runtime dependencies
- **Predictable behavior** - what you see in TableIR is what TIMES gets
- **Uses VEDA semantics** - same modes, but compiled not runtime

---

## Validation Rules

### TableIR Schema Invariants

1. **Lowercase column names only**
   - Pattern: `^[a-z][a-z0-9_-]*$`
   
2. **No year-as-column-name**
   - Reject columns matching `^[12][0-9]{3}$` (4-digit years)
   
3. **No region-as-column-name**
   - Reject columns matching known region IDs
   
4. **Numeric fields are numbers**
   - Parameter columns (`cost`, `eff`, etc.) must be `int` or `float`
   - Never strings like `"I"`, `"E"`, `"10"`

### Per-Tag Validation

For each tag, validate:
1. All required columns present
2. No unknown columns (strict mode)
3. Correct types for each column
4. Uniqueness: at most one row per key combination

### Time-Series Validation

For `*-TS` tags:
1. `year` column is required and is an integer
2. All years are valid model years
3. No duplicate `(key, year)` combinations
4. Full year coverage (optional strict mode)

---

## Implementation Checklist

### TableIR Schema (`tableir.schema.json`)
- [ ] Add `propertyNames` pattern for lowercase
- [ ] Add `if/then` for TS tags requiring `year`
- [ ] Ban 4-digit numeric column names

### Compiler (`compiler.py`)
- [ ] Implement `_expand_series_to_years()` helper
- [ ] Add `interpolation` field to VedaLang scenario schema
- [x] Derive model years from `milestone_years`
- [ ] Densify all time-series before emission

### Invariants (`invariants.py`)
- [ ] Check for forbidden column patterns
- [ ] Validate numeric-only for parameter columns
- [ ] Check year coverage for TS tables

### Constraints (`constraints.yaml`)
- [ ] Add `strict: true` for known tags
- [ ] Define `numeric_fields` per tag
- [ ] Add `forbidden_column_patterns`

---

## Rationale

### Why not wide-by-year?
- Multiple valid representations = schema sprawl
- Harder to validate programmatically
- Harder to merge/compare tables

### Why not VEDA interpolation?
- Implicit behavior is hard to debug
- Different tools may interpolate differently
- Explicit values are self-documenting

### Why lowercase?
- Eliminates case-sensitivity issues
- Simpler string matching
- Consistent with Python/JSON conventions

---

## Examples

### Complete Canonical Example

The compiler maps VedaLang namespace prefixes to VEDA Csets (`primary:`/`secondary:`/`resource:` → NRG, `emission:` → ENV, `service:` → DEM, `material:` → MAT, `money:` → FIN). Emission commodities (`emission:*`) are emitted strictly through emission constructs (ENV_ACT), never as flow outputs.

```yaml
files:
  - path: "SysSettings/SysSettings.xlsx"
    sheets:
      - name: "Commodities"
        tables:
          - tag: "~FI_COMM"
            rows:
              - { region: "REG1", csets: "NRG", commname: "ELC", unit: "PJ" }
              - { region: "REG1", csets: "ENV", commname: "CO2", unit: "Mt" }

  - path: "Scen_CO2Price/Scen_CO2Price.xlsx"
    sheets:
      - name: "Scenario"
        tables:
          - tag: "~TFM_INS-TS"
            rows:
              # Dense: one row per model year
              - { region: "REG1", year: 2020, pset_co: "CO2", cost: 50 }
              - { region: "REG1", year: 2030, pset_co: "CO2", cost: 100 }
              - { region: "REG1", year: 2040, pset_co: "CO2", cost: 150 }
              - { region: "REG1", year: 2050, pset_co: "CO2", cost: 200 }
```

This is the **only valid representation**. No alternatives.
