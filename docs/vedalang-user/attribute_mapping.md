# VedaLang Attribute Mapping

This document defines the **canonical mapping** between VedaLang attribute names and VEDA/TIMES attributes. VedaLang uses explicit, self-documenting names to avoid ambiguity.

## Design Principles

1. **Explicit over implicit**: Each VedaLang attribute maps to exactly one TIMES attribute
2. **Self-documenting names**: Names describe what the attribute represents
3. **No context inference**: The attribute name alone determines the TIMES mapping
4. **Backward compatibility**: Legacy names remain supported but deprecated

---

## Process Cost Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `investment_cost` | NCAP_COST | ncap_cost | $/GW | Capital cost per unit of new capacity |
| `fixed_om_cost` | NCAP_FOM | ncap_fom | $/GW/yr | Fixed O&M cost per unit of capacity per year |
| `variable_om_cost` | ACT_COST | act_cost | $/PJ | Variable cost per unit of activity |
| `import_price` | IRE_PRICE | ire_price | $/PJ | Price for imported commodity (IMP/EXP only) |

### Legacy Names (Deprecated)

| Legacy Name | Preferred Name | Notes |
|------------|----------------|-------|
| `invcost` | `investment_cost` | Alias retained for compatibility |
| `fixom` | `fixed_om_cost` | Alias retained for compatibility |
| `varom` | `variable_om_cost` | Alias retained for compatibility |
| `cost` | *context-dependent* | **Deprecated**: Use explicit names |

### Migration Guide

```yaml
# OLD (deprecated)
processes:
  - name: PP_CCGT
    invcost: 800
    fixom: 20
    varom: 2

# NEW (explicit)
processes:
  - name: PP_CCGT
    investment_cost: 800
    fixed_om_cost: 20
    variable_om_cost: 2
```

For import processes:

```yaml
# OLD (deprecated, ambiguous)
processes:
  - name: IMP_NG
    cost: 5.0  # What kind of cost?

# NEW (explicit)
processes:
  - name: IMP_NG
    import_price: 5.0  # Clearly an import price
```

---

## Process Capacity/Lifetime Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `lifetime` | NCAP_TLIFE | ncap_tlife | years | Technical lifetime of new capacity |
| `stock` | PRC_RESID | prc_resid | GW | Pre-existing (residual) capacity |
| `availability_factor` | NCAP_AF | ncap_af | fraction | Annual availability/capacity factor |

### Legacy Names (Deprecated)

| Legacy Name | Preferred Name |
|------------|----------------|
| `life` | `lifetime` |

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
| `emission_factor` | ENV_ACT | attribute=ENV_ACT | Emission coefficient per unit of activity |

Used on output commodities:
```yaml
outputs:
  - commodity: ELC
  - commodity: CO2
    emission_factor: 0.05  # Mt CO2 per PJ fuel input
```

---

## Commodity Attributes

| VedaLang Attribute | TIMES Concept | Description |
|-------------------|---------------|-------------|
| `type` | COM_TYPE | energy, demand, emission, material |
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
| Emissions | Mt | kt, Gt |
| Currency | $ (or USD) | - |
| Time | years | - |
| Efficiency | fraction (0-1) | - |

### Capacity-to-Activity Conversion

When capacity is in **power units** (GW) and activity is in **energy units** (PJ):
- 1 GW at 100% capacity factor = 31.536 PJ/year
- Formula: `PRC_CAPACT = 8760 hours × 3600 sec/hour / 1e15 = 31.536`

VedaLang automatically emits `PRC_CAPACT` when these units differ.

---

## Complete Attribute Reference

### Process Attributes

```yaml
processes:
  - name: PP_CCGT                    # Required: unique process identifier
    description: "CCGT plant"        # Optional: human-readable description
    sets: [ELE]                      # Required: process type (ELE, DMD, IMP, etc.)
    primary_commodity_group: NRGO    # Required: PCG for activity definition
    
    # I/O topology
    inputs:
      - commodity: NG
    outputs:
      - commodity: ELC
      - commodity: CO2
        emission_factor: 0.05
    
    # Efficiency
    efficiency: 0.55                 # ACT_EFF
    
    # Costs (explicit names)
    investment_cost: 800             # NCAP_COST ($/GW)
    fixed_om_cost: 20                # NCAP_FOM ($/GW/yr)
    variable_om_cost: 2              # ACT_COST ($/PJ)
    
    # Lifetime and capacity
    lifetime: 40                     # NCAP_TLIFE (years)
    stock: 5                         # PRC_RESID (GW)
    availability_factor: 0.85        # NCAP_AF (fraction)
    
    # Bounds
    cap_bound:
      up: 500                        # CAP_BND UP
    ncap_bound:
      up: 50                         # NCAP_BND UP (per period)
    
    # Units (optional, defaults shown)
    activity_unit: PJ                # TACT
    capacity_unit: GW                # TCAP
```

### Import Process Attributes

```yaml
processes:
  - name: IMP_NG
    sets: [IMP]
    primary_commodity_group: NRGO
    outputs:
      - commodity: NG
    efficiency: 1.0
    import_price: 5.0                # IRE_PRICE ($/PJ)
    stock: 1000                      # Effectively unlimited import capacity
```

---

## Validation Rules

VedaLang validates attribute usage:

1. **`import_price`** only valid on IMP/EXP/IRE processes
2. **`investment_cost`**, **`fixed_om_cost`**, **`variable_om_cost`** valid on any process
3. Deprecated **`cost`** will warn and map based on process type (not recommended)
4. **`emission_factor`** only valid on emission commodity outputs

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
- `import_price`, `availability_factor`, `lifetime`
