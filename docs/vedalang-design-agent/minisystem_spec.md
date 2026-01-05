# MiniSystem Model Specification

**Version:** 1.0  
**Issue:** `vedalang-5dw`  
**Purpose:** Stress-test VedaLang capabilities with a minimal but comprehensive energy model

---

## 1. Model Overview

MiniSystem represents a **2-region power system** with:
- Thermal and renewable electricity generation
- Inter-regional trade with transmission losses
- CO2 emissions and carbon pricing
- Demand projections and renewable policy targets
- Seasonal/daily timeslice variation

The model is intentionally small (2 regions, ~10 commodities, ~12 processes) but exercises every implemented VedaLang feature.

### Design Philosophy

| Principle | Implementation |
|-----------|----------------|
| **Minimal** | Only one process per technology type |
| **Complete** | Every schema feature used at least once |
| **Realistic** | Follows TIMES/VEDA naming conventions |
| **Testable** | Should compile and validate through xl2times |

---

## 2. Regions

| Code | Name | Purpose |
|------|------|---------|
| `NORTH` | Northern Region | Gas-rich, industrial demand |
| `SOUTH` | Southern Region | Solar-rich, residential demand |

Two regions enable testing of:
- Multi-region process deployment
- Trade links with efficiency losses
- Region-specific demand patterns

---

## 3. Commodities

### 3.1 Energy Commodities

| Name | Unit | Description | Features Tested |
|------|------|-------------|-----------------|
| `NG` | PJ | Natural Gas | Input to thermal plants, traded commodity |
| `ELC` | PJ | Electricity | Primary output, traded with losses |

### 3.2 Emission Commodities

| Name | Unit | Description | Features Tested |
|------|------|-------------|-----------------|
| `CO2` | Mt | Carbon dioxide | Emission factors, pricing scenario, cap constraint |

### 3.3 Demand Commodities

| Name | Unit | Description | Features Tested |
|------|------|-------------|-----------------|
| `RSD` | PJ | Residential demand | Demand projection scenario |
| `IND` | PJ | Industrial demand | Second demand type (region differentiation) |

### 3.4 Material Commodities (Optional)

| Name | Unit | Description | Features Tested |
|------|------|-------------|-----------------|
| `H2` | PJ | Hydrogen | Future-proofing, material commodity type |

**Total:** 6 commodities (2 energy, 1 emission, 2 demand, 1 material)

---

## 4. Processes

### 4.1 Supply Processes

| Name | Sets | PCG | Outputs | Features Tested |
|------|------|-----|---------|-----------------|
| `IMP_NG` | IMP | NRGO | NG | Activity cost, activity bounds |

### 4.2 Thermal Generation

| Name | Sets | PCG | Inputs | Outputs | Features Tested |
|------|------|-----|--------|---------|-----------------|
| `PP_CCGT` | ELE | NRGO | NG | ELC, CO2 | Efficiency, emission factor, costs (invcost/fixom/varom), lifetime, ncap_bound |

### 4.3 Renewable Generation

| Name | Sets | PCG | Outputs | Features Tested |
|------|------|-----|---------|-----------------|
| `PP_WIND` | ELE | NRGO | ELC | Zero-input process, cap_bound (lo/up) |
| `PP_SOLAR` | ELE | NRGO | ELC | Second renewable (activity_share constraint) |

### 4.4 Hydrogen Production

| Name | Sets | PCG | Inputs | Outputs | Features Tested |
|------|------|-----|--------|---------|-----------------|
| `PP_ELYZ` | ELE | MATO | ELC | H2 | Material output, efficiency <1 |

### 4.5 Demand Devices

| Name | Sets | PCG | Inputs | Outputs | Features Tested |
|------|------|-----|--------|---------|-----------------|
| `DMD_RSD` | DMD | DEMO | ELC | RSD | Demand commodity output |
| `DMD_IND` | DMD | DEMO | ELC, NG | IND | Multi-input demand device |

### 4.6 Process Summary by Region

All processes are defined once and **available in all regions** by default (VedaLang semantics).

**Total:** 7 processes

---

## 5. Timeslices

A simple 4-timeslice structure to test temporal resolution:

```yaml
timeslices:
  season:
    - code: S    # Summer
    - code: W    # Winter
  daynite:
    - code: D    # Day
    - code: N    # Night
  fractions:
    SD: 0.25     # Summer-Day (25% of year)
    SN: 0.22     # Summer-Night
    WD: 0.28     # Winter-Day
    WN: 0.25     # Winter-Night
```

**Features tested:** Timeslice definition, season/daynite levels, fraction specification

---

## 6. Trade Links

| Origin | Destination | Commodity | Bidirectional | Efficiency | Features Tested |
|--------|-------------|-----------|---------------|------------|-----------------|
| NORTH | SOUTH | ELC | yes | 0.97 | Electricity trade, 3% loss |
| NORTH | SOUTH | NG | yes | 1.0 | Gas trade, no loss |

**Features tested:** Inter-regional trade, bidirectional flows, efficiency (IRE_FLO)

---

## 7. Scenarios

### 7.1 CO2 Price Trajectory

```yaml
- name: CO2_Price
  type: commodity_price
  commodity: CO2
  interpolation: interp_extrap
  values:
    "2025": 50
    "2030": 100
    "2050": 200
```

**Features tested:** Commodity price scenario, interpolation modes, sparse year specification

### 7.2 Residential Demand Projection

```yaml
- name: DemandProjection
  type: demand_projection
  commodity: RSD
  interpolation: interp_extrap
  values:
    "2020": 100
    "2030": 120
    "2050": 160
```

**Features tested:** Demand projection scenario, time-series values

### 7.3 Industrial Demand Projection

```yaml
- name: IndustryDemand
  type: demand_projection
  commodity: IND
  interpolation: interp_extrap
  values:
    "2020": 200
    "2030": 220
    "2050": 250
```

**Features tested:** Multiple demand scenarios, different growth rates

---

## 8. User Constraints

### 8.1 CO2 Emission Cap

```yaml
- name: CO2_CAP
  type: emission_cap
  commodity: CO2
  limtype: up
  years:
    "2020": 100
    "2030": 75
    "2050": 25
  interpolation: interp_extrap
```

**Features tested:** Emission cap constraint, year-varying RHS, limtype

### 8.2 Renewable Energy Target

```yaml
- name: REN_TARGET
  type: activity_share
  commodity: ELC
  processes: [PP_WIND, PP_SOLAR]
  minimum_share: 0.30
```

**Features tested:** Activity share constraint, process grouping, minimum share

---

## 9. Bounds

### 9.1 Process Bounds Summary

| Process | Bound Type | Limit | Value | Features Tested |
|---------|------------|-------|-------|-----------------|
| `IMP_NG` | activity_bound | up | 500 | Activity upper bound |
| `PP_CCGT` | cap_bound | up | 10 | Total capacity limit |
| `PP_CCGT` | ncap_bound | up | 2 | New capacity per period |
| `PP_WIND` | cap_bound | lo | 3 | Minimum capacity (RPS) |
| `PP_WIND` | cap_bound | up | 30 | Maximum capacity (grid) |
| `PP_SOLAR` | ncap_bound | fx | 1 | Fixed capacity addition |

**Features tested:** All three bound types, up/lo/fx limit types

---

## 10. Feature Coverage Matrix

| VedaLang Feature | Schema Element | Tested By |
|------------------|----------------|-----------|
| Multi-region | `regions[]` | NORTH, SOUTH |
| Energy commodity | `commodities[].type: energy` | NG, ELC |
| Emission commodity | `commodities[].type: emission` | CO2 |
| Demand commodity | `commodities[].type: demand` | RSD, IND |
| Material commodity | `commodities[].type: material` | H2 |
| Process definition | `processes[]` | All 7 processes |
| Primary commodity group | `primary_commodity_group` | NRGO, DEMO, MATO |
| Process efficiency | `efficiency` | PP_CCGT, PP_ELYZ, DMD_IND |
| Emission factor | `outputs[].share` on emission | PP_CCGT → CO2 |
| Process costs | `invcost`, `fixom`, `varom` | PP_CCGT, PP_WIND |
| Activity cost | `cost` | IMP_NG |
| Lifetime | `life` | PP_CCGT, PP_WIND |
| Activity bounds | `activity_bound` | IMP_NG |
| Capacity bounds | `cap_bound` | PP_CCGT, PP_WIND |
| New capacity bounds | `ncap_bound` | PP_CCGT, PP_SOLAR |
| Bound limit types | `up`, `lo`, `fx` | Various bounds |
| Timeslices | `timeslices` | 2 seasons × 2 daynite |
| Trade links | `trade_links[]` | ELC and NG trade |
| Trade efficiency | `efficiency` on trade | ELC trade (0.97) |
| Bidirectional trade | `bidirectional` | Both links |
| Commodity price | `scenarios[].type: commodity_price` | CO2_Price |
| Demand projection | `scenarios[].type: demand_projection` | RSD, IND |
| Interpolation modes | `interpolation` | interp_extrap on all |
| Emission cap | `constraints[].type: emission_cap` | CO2_CAP |
| Activity share | `constraints[].type: activity_share` | REN_TARGET |
| Year-varying values | `years` object | CO2_CAP, scenarios |

---

## 11. Model Summary

| Metric | Count |
|--------|-------|
| Regions | 2 |
| Commodities | 6 |
| Processes | 7 |
| Trade links | 2 |
| Scenarios | 3 |
| Constraints | 2 |
| Timeslices | 4 |
| **Total schema features exercised** | **26** |

---

## 12. Known Limitations

The following VedaLang features are **not yet implemented** and therefore not tested:

| Feature | Issue | Notes |
|---------|-------|-------|
| Time-varying process attributes | `vedalang-6qs` | e.g., efficiency declining over time |
| Enhanced storage primitives | `vedalang-jis` | Charge/discharge, round-trip efficiency |
| Scenario composition | `vedalang-9xy` | Combining scenarios into variants |
| Units/dimension checking | `vedalang-a9m` | Compile-time unit validation |

---

## 13. Implementation Notes

### File Name
`minisystem.veda.yaml`

### Validation Approach

```bash
# Full validation (lint + compile + xl2times)
uv run vedalang validate vedalang/examples/minisystem.veda.yaml --json

# Lint only
uv run vedalang lint vedalang/examples/minisystem.veda.yaml --json

# Expected outcome: 0 errors from compilation
# Known warnings: UC tables may warn until uc_sets emission is implemented
```

### CI Integration
The MiniSystem model should become a **golden fixture** test case:
- Compile to TableIR → snapshot test
- Emit Excel → validate with xl2times
- Any regression = build failure

---

## Appendix: Full Model Structure (Preview)

```yaml
model:
  name: MiniSystem
  description: Comprehensive stress-test for VedaLang
  
  regions: [NORTH, SOUTH]
  
  timeslices:
    season: [{code: S}, {code: W}]
    daynite: [{code: D}, {code: N}]
    fractions: {SD: 0.25, SN: 0.22, WD: 0.28, WN: 0.25}
  
  commodities:
    - {name: NG, type: energy, unit: PJ}
    - {name: ELC, type: energy, unit: PJ}
    - {name: CO2, type: emission, unit: Mt}
    - {name: RSD, type: demand, unit: PJ}
    - {name: IND, type: demand, unit: PJ}
    - {name: H2, type: material, unit: PJ}
  
  processes:
    - name: IMP_NG
      sets: [IMP]
      primary_commodity_group: NRGO
      outputs: [{commodity: NG}]
      cost: 5.0
      activity_bound: {up: 500}
    
    - name: PP_CCGT
      sets: [ELE]
      primary_commodity_group: NRGO
      inputs: [{commodity: NG}]
      outputs: [{commodity: ELC}, {commodity: CO2, share: 0.05}]
      efficiency: 0.55
      invcost: 800
      fixom: 20
      varom: 2
      life: 30
      cap_bound: {up: 10}
      ncap_bound: {up: 2}
    
    - name: PP_WIND
      sets: [ELE]
      primary_commodity_group: NRGO
      outputs: [{commodity: ELC}]
      invcost: 1200
      fixom: 25
      life: 25
      cap_bound: {lo: 3, up: 30}
    
    - name: PP_SOLAR
      sets: [ELE]
      primary_commodity_group: NRGO
      outputs: [{commodity: ELC}]
      invcost: 900
      fixom: 15
      life: 25
      ncap_bound: {fx: 1}
    
    - name: PP_ELYZ
      sets: [ELE]
      primary_commodity_group: MATO
      inputs: [{commodity: ELC}]
      outputs: [{commodity: H2}]
      efficiency: 0.70
      invcost: 500
      life: 20
    
    - name: DMD_RSD
      sets: [DMD]
      primary_commodity_group: DEMO
      inputs: [{commodity: ELC}]
      outputs: [{commodity: RSD}]
    
    - name: DMD_IND
      sets: [DMD]
      primary_commodity_group: DEMO
      inputs: [{commodity: ELC}, {commodity: NG}]
      outputs: [{commodity: IND}]
      efficiency: 0.90
  
  trade_links:
    - {origin: NORTH, destination: SOUTH, commodity: ELC, bidirectional: true, efficiency: 0.97}
    - {origin: NORTH, destination: SOUTH, commodity: NG, bidirectional: true}
  
  scenarios:
    - name: CO2_Price
      type: commodity_price
      commodity: CO2
      interpolation: interp_extrap
      values: {"2025": 50, "2030": 100, "2050": 200}
    
    - name: DemandRSD
      type: demand_projection
      commodity: RSD
      interpolation: interp_extrap
      values: {"2020": 100, "2030": 120, "2050": 160}
    
    - name: DemandIND
      type: demand_projection
      commodity: IND
      interpolation: interp_extrap
      values: {"2020": 200, "2030": 220, "2050": 250}
  
  constraints:
    - name: CO2_CAP
      type: emission_cap
      commodity: CO2
      limtype: up
      years: {"2020": 100, "2030": 75, "2050": 25}
      interpolation: interp_extrap
    
    - name: REN_TARGET
      type: activity_share
      commodity: ELC
      processes: [PP_WIND, PP_SOLAR]
      minimum_share: 0.30
```
