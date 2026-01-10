# VedaLang Ergonomic Improvements

Analysis of friction points in VedaLang authoring and proposed improvements.

## Friction Points Identified

### High Priority (Significant Boilerplate Reduction)

#### 1. ❌ `primary_commodity_group` is Always Required
**Friction**: Every process requires explicit `primary_commodity_group` even when it could be inferred from context.
**Example in MiniSystem**: `PP_WIND` outputs only `ELC` but still needs `primary_commodity_group: NRGO`.
**Proposal**: Infer PCG from process sets and commodity types:
- `sets: [ELE, DMD]` + energy output → `NRGO` (energy output)
- `sets: [DMD]` + demand output → `DEMO`
- `sets: [IMP]` + single output → output commodity's group
**Status**: DEFERRED - PCG inference is complex and error-prone. Keep explicit for now.

#### 2. ✅ Single Input/Output as String Instead of Array
**Friction**: Most processes have a single input or output, but must use array syntax.
**Example**:
```yaml
# Current (verbose)
inputs:
  - commodity: NG
outputs:
  - commodity: ELC

# Proposed (shorthand)
input: NG
output: ELC
```
**Complexity**: Low - schema oneOf, compiler normalization
**Status**: IMPLEMENTING

#### 3. ✅ Default `milestone_years`
**Friction**: Must specify even for simple models.
**Proposal**: Default `milestone_years: [2020]` if not specified.
**Complexity**: Very low - already defaulted in compiler
**Status**: Implemented. Uses explicit `milestone_years` list (e.g., `[2020, 2030, 2040, 2050]`) instead of `start_year` + `time_periods` for clarity.

#### 4. ✅ Commodity `unit` Optional with Sensible Defaults
**Friction**: Every commodity needs explicit unit.
**Proposal**: Default based on commodity type:
- `energy` → `PJ`
- `emission` → `Mt`
- `material` → `Mt`
- `demand` → `PJ`
**Complexity**: Low - compiler logic
**Status**: IMPLEMENTING

### Medium Priority (Nice to Have)

#### 5. ⏳ Shorthand for Emission Output
**Friction**: Emission outputs require full flow syntax with share.
```yaml
# Current
outputs:
  - commodity: ELC
  - commodity: CO2
    share: 0.05

# Proposed shorthand
output: ELC
emissions:
  CO2: 0.05
```
**Complexity**: Medium - new schema construct, compiler translation
**Status**: FUTURE

#### 6. ⏳ Process Templates
**Friction**: Similar processes (e.g., multiple power plants) repeat common attributes.
```yaml
# Proposed
templates:
  thermal_plant:
    sets: [ELE]
    primary_commodity_group: NRGO
    inputs: [NG]
    
processes:
  - name: PP_CCGT
    template: thermal_plant
    efficiency: 0.55
```
**Complexity**: High - template inheritance, validation
**Status**: FUTURE

#### 7. ⏳ Inline Efficiency with Flow
**Friction**: Efficiency is separate from flow definition.
```yaml
# Proposed
inputs:
  - commodity: NG
    efficiency: 0.55  # Applied to this flow
```
**Complexity**: Medium - changes ~FI_T emission logic
**Status**: FUTURE

### Low Priority (Minor Improvements)

#### 8. ✅ Schema Descriptions for All Properties
**Friction**: Some schema properties lack descriptions.
**Proposal**: Add descriptions to all properties for IDE tooltips.
**Complexity**: Very low
**Status**: IMPLEMENTING

#### 9. ⏳ Year Shorthand in Time-Series
**Friction**: YAML requires string keys for years.
```yaml
# Current
values:
  "2020": 100
  "2030": 120

# Proposed (if YAML supported)
values:
  2020: 100
  2030: 120
```
**Status**: YAML limitation, cannot change

#### 10. ✅ Implicit `share: 1.0` for Single Flows
**Friction**: `share` defaults to 1.0 but is often specified explicitly.
**Status**: Already implemented in schema with `default: 1.0`

## Improvements Implemented

### 1. Single Input/Output String Shorthand ✅

**Files changed:**
- `vedalang/schema/vedalang.schema.json` - Added `input` and `output` string properties
- `vedalang/compiler/compiler.py` - Added `_normalize_process_flows()` function

**Usage:**
```yaml
# Both are now valid:
processes:
  - name: PP_CCGT
    input: NG       # Shorthand - equivalent to inputs: [{commodity: NG}]
    output: ELC     # Shorthand - equivalent to outputs: [{commodity: ELC}]
    
  - name: PP_CHP
    inputs:         # Array (for multiple commodities)
      - commodity: NG
    outputs:        # Array (for multiple commodities)
      - commodity: ELC
      - commodity: HEAT
```

**Tests added:** 4 new tests in `test_vedalang_compiler.py`
- `test_single_input_string_shorthand`
- `test_single_output_string_shorthand`
- `test_both_input_output_shorthand`
- `test_shorthand_validation_unknown_commodity`

### 2. Default Commodity Units ✅

**Files changed:**
- `vedalang/compiler/compiler.py` - Added `DEFAULT_UNITS` dict and `_get_default_unit()` function

**Defaults:**
| Commodity Type | Default Unit |
|---------------|--------------|
| `energy`      | `PJ`         |
| `demand`      | `PJ`         |
| `emission`    | `Mt`         |
| `material`    | `Mt`         |

**Usage:**
```yaml
commodities:
  - name: ELC
    type: energy    # unit defaults to PJ (no need to specify)
  - name: CO2
    type: emission  # unit defaults to Mt
  - name: H2
    type: material
    unit: PJ        # Can still override with explicit unit
```

**Tests added:** 5 new tests in `test_vedalang_compiler.py`
- `test_default_commodity_units_energy`
- `test_default_commodity_units_emission`
- `test_default_commodity_units_demand`
- `test_default_commodity_units_material`
- `test_explicit_unit_overrides_default`

### 3. Enhanced Schema Descriptions ✅

**Files changed:**
- `vedalang/schema/vedalang.schema.json` - Added detailed descriptions to all properties

**Benefits:**
- Better IDE tooltips and autocomplete
- Self-documenting schema
- Clearer error messages

### 4. New Example File ✅

Added `vedalang/examples/mini_plant_shorthand.veda.yaml` demonstrating all new features.

## Backward Compatibility

All changes are backward compatible:
- `inputs`/`outputs` arrays still work
- Explicit `unit` still works
- No breaking changes to existing files

## Testing

New tests added:
- `test_single_input_string_shorthand`
- `test_single_output_string_shorthand`
- `test_default_commodity_units`
- All existing tests pass

## Future Considerations

1. **Process Templates** - Would significantly reduce repetition for large models
2. **Emission Shorthand** - Common pattern that deserves dedicated syntax
3. **Region-Specific Defaults** - Allow region-level default overrides
4. **LSP Integration** - Schema descriptions enable better IDE support
