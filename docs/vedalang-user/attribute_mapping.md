# VedaLang Attribute Mapping

This document defines the **canonical mapping** between VedaLang attribute names and VEDA/TIMES attributes. VedaLang uses explicit, self-documenting names to avoid ambiguity.

## Design Principles

1. **Explicit over implicit**: Each VedaLang attribute maps to exactly one TIMES attribute
2. **Self-documenting names**: Names describe what the attribute represents
3. **No context inference**: The attribute name alone determines the TIMES mapping

---

## Quick Reference

All VedaLang process attributes with their TIMES/VEDA mappings:

| VedaLang Attribute | TIMES Attribute | VEDA Column | Category |
|-------------------|-----------------|-------------|----------|
| `efficiency` | ACT_EFF | eff | Efficiency |
| `investment_cost` | NCAP_COST | ncap_cost | Cost |
| `fixed_om_cost` | NCAP_FOM | ncap_fom | Cost |
| `variable_om_cost` | ACT_COST | act_cost | Cost |
| `import_price` | IRE_PRICE | ire_price | Cost |
| `lifetime` | NCAP_TLIFE | ncap_tlife | Capacity |
| `economic_life` | NCAP_ELIFE | ncap_elife | Capacity |
| `availability_factor` | NCAP_AF | ncap_af | Capacity |
| `stock` | PRC_RESID | prc_resid | Capacity |
| `existing_capacity` | NCAP_PASTI | ncap_pasti | Capacity |
| `activity_bound` | ACT_BND | act_bnd | Bound |
| `cap_bound` | CAP_BND | cap_bnd | Bound |
| `ncap_bound` | NCAP_BND | ncap_bnd | Bound |
| `emission_factors` | ENV_ACT | attribute=ENV_ACT | Emission |

**Source of truth**: `vedalang/compiler/compiler.py` defines `ATTR_TO_COLUMN` and `SEMANTIC_TO_TIMES` dicts.

---

## Process Cost Attributes

For P4 (`process_roles`/`process_variants`) models, unit ownership is role-level:

- `process_roles[].activity_unit`
- `process_roles[].capacity_unit`

Variants inherit these units from their role; variant-level unit overrides are
not supported.

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `investment_cost` | NCAP_COST | ncap_cost | `<moneyYY>/<capacity_unit>` | Capital cost per unit of new capacity |
| `fixed_om_cost` | NCAP_FOM | ncap_fom | `<moneyYY>/<capacity_unit>/yr` | Fixed O&M cost per unit of capacity per year |
| `variable_om_cost` | ACT_COST | act_cost | `<moneyYY>/<activity_unit>` | Variable cost per unit of activity |
| `import_price` | IRE_PRICE | ire_price | `<moneyYY>/<unit>` | Price for imported commodity (IMP/EXP only) |

Deterministic lint requires explicit monetary literals for cost fields
(even when `model.monetary` is not set), e.g.:

```yaml
model:
  monetary:
    canonical: MAUD24
    fx_table: rules/monetary/fx_aud_usd_world_bank_pa_nus_fcrf.yaml

process_variants:
  - investment_cost: "120 MAUD24/GW"
    fixed_om_cost: "4 MAUD24/GW/yr"
    variable_om_cost: "6.944444 MUSD24/PJ"
```

When `model.monetary` is set, these literals are additionally normalized to
the configured canonical currency-year token during compilation.

---

## Process Capacity/Lifetime Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `lifetime` | NCAP_TLIFE | ncap_tlife | years | Technical lifetime of new capacity |
| `economic_life` | NCAP_ELIFE | ncap_elife | years | Economic lifetime for cost amortization |
| `stock` | PRC_RESID | prc_resid | `<capacity_unit>` | Aggregate residual capacity (mixed vintages) |
| `existing_capacity` | NCAP_PASTI | ncap_pasti | `<capacity_unit>` | Past capacity with vintage year (preferred) |
| `availability_factor` | NCAP_AF | ncap_af | fraction | Annual availability/capacity factor |

### Technical Lifetime vs Economic Lifetime

TIMES distinguishes between two lifetime concepts:

| VedaLang | TIMES | Purpose | Default |
|----------|-------|---------|---------|
| `lifetime` | NCAP_TLIFE | How long the asset can physically operate | Required |
| `economic_life` | NCAP_ELIFE | How long investment costs are amortized | = TLIFE |

**When they differ:**
- **Loan financing**: Equipment may operate 30 years but loan is 20 years
- **Accelerated depreciation**: Tax benefits with shorter economic life
- **Leased equipment**: Economic life matches lease term, not physical life

**Default behavior**: When `economic_life` is not specified, TIMES uses `lifetime` (NCAP_TLIFE) for both purposes. This is appropriate for most models.

```yaml
# Typical case: same lifetime for both (economic_life not needed)
lifetime: 40

# Special case: shorter financing period than physical life
lifetime: 40           # Can operate for 40 years
economic_life: 20      # Loan paid off in 20 years
```

**Recommendation**: Omit `economic_life` unless your model explicitly requires different amortization periods. Most energy system models use the same value for technical and economic life.

### Stock vs Existing Capacity

VedaLang provides two ways to specify pre-existing capacity:

| Attribute | TIMES Attr | Use Case | Behavior |
|-----------|------------|----------|----------|
| `stock` | PRC_RESID | Aggregate unknown-vintage capacity | TIMES decays linearly over TLIFE |
| `existing_capacity` | NCAP_PASTI | Specific facilities with known build year | Retires based on vintage + lifetime |

**Recommendation**: Use `existing_capacity` for new models. It provides:
- Proper vintage tracking for retirement
- Economic life accounting
- Explicit control over capacity phaseout

```yaml
# Preferred: existing_capacity with vintage
existing_capacity:
  - vintage: 2010
    capacity: 2.5   # 2.5 GW built in 2010
  - vintage: 2015
    capacity: 1.0   # 1.0 GW built in 2015

# Legacy: aggregate stock (avoid for new models)
stock: 5.0  # 5 GW of unknown vintage - TIMES will decay linearly
```

---

## Process Efficiency Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Description |
|-------------------|-----------------|-------------|-------------|
| `efficiency` | ACT_EFF | eff | Activity-to-output conversion ratio |

---

## Process Bound Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Description |
|-------------------|-----------------|-------------|-------------|
| `cap_bound` | CAP_BND | cap_bnd | Bound on total installed capacity |
| `ncap_bound` | NCAP_BND | ncap_bnd | Bound on new capacity additions |
| `activity_bound` | ACT_BND | act_bnd | Bound on process activity |

Bound specifications use `up`, `lo`, `fx` keys:
```yaml
cap_bound:
  up: 1000  # Maximum capacity
  lo: 10    # Minimum capacity (optional)
  fx: 500   # Fixed capacity (mutually exclusive with up/lo)
```

---

## Emission Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Description |
|-------------------|-----------------|-------------|-------------|
| `emission_factors` | ENV_ACT | attribute=ENV_ACT | Emission coefficients per unit of activity |

Emissions are **ledger entries**, not flows. They are specified as a dict on the process, never in `inputs` or `outputs`:

```yaml
process_variants:
  - id: gas_plant
    inputs:
      - commodity: primary:natural_gas
    outputs:
      - commodity: secondary:electricity
    emission_factors:
      emission:co2: 0.05  # Mt CO2 per PJ fuel input

    # Negative values for removals (DAC, LULUCF):
    # emission_factors:
    #   emission:co2: -1.0
```

**Lint rules:**
- `emission:*` MUST NOT appear in `inputs` or `outputs` (L1)
- `emission_factors` keys MUST use `emission:*` namespace (L2)

---

## Commodity Attributes

| VedaLang Attribute | TIMES Concept | Description |
|-------------------|---------------|-------------|
| `type` | COM_TYPE | energy, service, emission, material, money |
| `unit` | COM_UNIT | PJ, Mt, etc. |

---

## Scenario Parameter Types

| VedaLang Type | TIMES Attribute | Description |
|--------------|-----------------|-------------|
| `demand_projection` | COM_PROJ | Annual demand projection by year |
| `commodity_price` | COM_CSTNET | Commodity price trajectory |

---

## Unit Conventions

VedaLang uses consistent unit conventions:

| Quantity | Standard Unit | Alternatives |
|----------|--------------|--------------|
| Energy | PJ | TJ, GWh, TWh |
| Power/Capacity | GW | MW, TW |
| Throughput Capacity | `<activity_unit>/yr` | e.g., PJ/yr, Bvkm/yr |
| Emissions | Mt | kt, Gt |
| Currency | $ (or USD) | - |
| Time | years | - |
| Efficiency | fraction (0-1) | - |

### Capacity-to-Activity Conversion

`PRC_CAPACT` is derived from an explicit annual basis:

- Formula: `PRC_CAPACT = convert(1 * capacity_unit * 1 yr -> activity_unit)`
- Example: `GW -> PJ` gives `31.536`
- Example: `PJ/yr -> PJ` gives `1.0`
- Example: `Bvkm/yr -> Bvkm` gives `1.0`

Rules:
- `activity_unit` must be an extensive unit (e.g., `PJ`, `Bvkm`, `Mt`)
- `capacity_unit` must be either power (`GW`, `MW`, `TW`, `kW`) or explicit annual rate (`<unit>/yr`)
- Ambiguous non-power pairs like `capacity_unit: PJ` with `activity_unit: PJ` are rejected

---

## Complete Attribute Reference

### Process Attributes

```yaml
processes:
  - name: PP_CCGT
    description: "CCGT plant"
    sets: [ELE]
    primary_commodity_group: NRGO
    
    # I/O topology
    inputs:
      - commodity: primary:natural_gas
    outputs:
      - commodity: secondary:electricity
    
    # Emissions (ledger entries, not flows)
    emission_factors:
      emission:co2: 0.05
    
    # Efficiency
    efficiency: 0.55
    
    # Costs
    investment_cost: 800
    fixed_om_cost: 20
    variable_om_cost: 2
    
    # Lifetime and capacity
    lifetime: 40
    availability_factor: 0.85
    
    # Existing capacity
    existing_capacity:
      - vintage: 2010
        capacity: 3.0
      - vintage: 2015
        capacity: 2.0
    
    # Bounds
    cap_bound:
      up: 500
    ncap_bound:
      up: 50
    
    # Units
    activity_unit: PJ
    capacity_unit: GW
```

### Import Process Attributes

```yaml
processes:
  - name: IMP_NG
    sets: [IMP]
    primary_commodity_group: NRGO
    outputs:
      - commodity: primary:natural_gas
    efficiency: 1.0
    import_price: 5.0                # IRE_PRICE ($/PJ)
    stock: 1000                      # Effectively unlimited import capacity
```

---

## Validation Rules

VedaLang validates attribute usage:

1. **`import_price`** only valid on IMP/EXP/IRE processes
2. **`investment_cost`**, **`fixed_om_cost`**, **`variable_om_cost`** valid on any process
3. **`emission_factors`** dict keys must be `emission:*` namespaced; `emission:*` must not appear in inputs/outputs

---

## Time-Varying Attributes

Most cost and efficiency attributes support time-varying values:

```yaml
investment_cost:
  values:
    "2020": 800
    "2030": 600
    "2050": 400
  interpolation: interp_extrap
```

Supported attributes:
- `efficiency`, `investment_cost`, `fixed_om_cost`, `variable_om_cost`
- `import_price`, `availability_factor`, `lifetime`, `economic_life`
