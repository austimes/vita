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
| `availability_factor` | NCAP_AF | ncap_af | Capacity |
| `stock` | PRC_RESID | prc_resid | Capacity |
| `existing_capacity` | NCAP_PASTI | ncap_pasti | Capacity |
| `activity_bound` | ACT_BND | act_bnd | Bound |
| `cap_bound` | CAP_BND | cap_bnd | Bound |
| `ncap_bound` | NCAP_BND | ncap_bnd | Bound |
| `emission_factor` | ENV_ACT | attribute=ENV_ACT | Flow |

**Source of truth**: `vedalang/compiler/compiler.py` defines `ATTR_TO_COLUMN` and `SEMANTIC_TO_TIMES` dicts.

---

## Process Cost Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `investment_cost` | NCAP_COST | ncap_cost | $/GW | Capital cost per unit of new capacity |
| `fixed_om_cost` | NCAP_FOM | ncap_fom | $/GW/yr | Fixed O&M cost per unit of capacity per year |
| `variable_om_cost` | ACT_COST | act_cost | $/PJ | Variable cost per unit of activity |
| `import_price` | IRE_PRICE | ire_price | $/PJ | Price for imported commodity (IMP/EXP only) |

---

## Process Capacity/Lifetime Attributes

| VedaLang Attribute | TIMES Attribute | VEDA Column | Unit | Description |
|-------------------|-----------------|-------------|------|-------------|
| `lifetime` | NCAP_TLIFE | ncap_tlife | years | Technical lifetime of new capacity |
| `stock` | PRC_RESID | prc_resid | GW | Aggregate residual capacity (mixed vintages) |
| `existing_capacity` | NCAP_PASTI | ncap_pasti | GW | Past capacity with vintage year (preferred) |
| `availability_factor` | NCAP_AF | ncap_af | fraction | Annual availability/capacity factor |

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
    
    # Costs
    investment_cost: 800             # NCAP_COST ($/GW)
    fixed_om_cost: 20                # NCAP_FOM ($/GW/yr)
    variable_om_cost: 2              # ACT_COST ($/PJ)
    
    # Lifetime and capacity
    lifetime: 40                     # NCAP_TLIFE (years)
    availability_factor: 0.85        # NCAP_AF (fraction)
    
    # Existing capacity (choose one approach)
    existing_capacity:               # NCAP_PASTI - preferred for new models
      - vintage: 2010
        capacity: 3.0                # 3 GW built in 2010
      - vintage: 2015
        capacity: 2.0                # 2 GW built in 2015
    # OR: stock: 5                   # PRC_RESID - aggregate (legacy)
    
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
3. **`emission_factor`** only valid on emission commodity outputs

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
