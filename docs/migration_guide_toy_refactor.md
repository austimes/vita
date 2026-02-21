# Migration Guide: Toy Model Structural Refactor

This guide documents how to migrate legacy VedaLang toy model files to the
new service-oriented, physically-grounded conventions introduced by the
toy refactor PRD (`docs/prds/vedalang_toy_refactor_prd_updated.txt`).

## Overview of Changes

The refactor established a **three-layer convention framework**:

| Layer | Mechanism | Enforcement |
|-------|-----------|-------------|
| 1. Skill guidance | `.agents/skills/vedalang-modeling-conventions/SKILL.md` | Advisory |
| 2. Lint + LLM assessment | `vedalang lint --llm-assess` | Warnings / optional strict mode |
| 3. Compiler hard rules | `vedalang compile` / `vedalang validate` | Hard errors |

---

## Step-by-Step Migration

### 1. Merge Fuel-Pathway Roles into Service-Level Roles

**Before (prohibited):**

```yaml
process_roles:
  - id: heat_from_gas
    stage: end_use
    inputs: [{commodity: gas}]
    outputs: [{commodity: space_heat}]
  - id: heat_from_electricity
    stage: end_use
    inputs: [{commodity: electricity}]
    outputs: [{commodity: space_heat}]
```

**After (required):**

```yaml
process_roles:
  - id: provide_space_heat
    stage: end_use
    inputs: []                       # inputs moved to variants
    outputs: [{commodity: space_heat}]

process_variants:
  - id: gas_heater
    role: provide_space_heat
    inputs: [{commodity: natural_gas}]   # variant-level input
    efficiency: 0.9
  - id: heat_pump
    role: provide_space_heat
    inputs: [{commodity: electricity}]   # variant-level input
    efficiency: 3.2
```

**Principle:** `role` = *what* service is provided; `variant` = *how*.

**Compiler enforcement:** `[E1_DUPLICATE_SERVICE_ROLES]` — two roles sharing
the same primary output at the same stage will be rejected.

### 2. Replace Zero-Input End-Use Processes

**Before (prohibited):**

```yaml
process_roles:
  - id: insulation_effect
    stage: end_use
    inputs: []
    outputs: [{commodity: space_heat}]

process_variants:
  - id: insulation
    role: insulation_effect
    efficiency: 1.0
```

**After — option A (preferred): case demand override:**

```yaml
model:
  cases:
    - name: retrofit_policy
      demand_overrides:
        - commodity: space_heat
          sector: RES
          scale: {2030: 0.85, 2050: 0.70}
```

**After — option B: explicit demand_measure kind:**

```yaml
process_variants:
  - id: insulation
    role: provide_space_heat
    kind: demand_measure          # opt out of physical-input check
    efficiency: 1.0
```

**Compiler enforcement:** `[E_END_USE_PHYSICAL_INPUT]` — an end_use role
with zero inputs (at both role and variant level) requires all its variants
to have `kind: demand_measure`.

### 3. Add Commodity Typing

Every commodity must declare a `type`:

```yaml
commodities:
  - id: natural_gas
    type: fuel
  - id: electricity
    type: energy
  - id: space_heat
    type: service
  - id: co2
    type: emission
```

Valid types: `fuel`, `energy`, `service`, `material`, `emission`, `other`.

**Compiler enforcement:**
- `[E_COMMODITY_TYPE_ENUM]` — invalid type value.
- `[E_DEMAND_COMMODITY_TYPE]` — demand projections must target `type=service`.
- `[E_EMISSION_COMMODITY_TYPE]` — emission constraints must target `type=emission`.

### 4. Add Stage Annotations

Every `process_role` must declare a `stage`:

```yaml
process_roles:
  - id: supply_gas
    stage: supply
  - id: generate_power
    stage: conversion
  - id: store_electricity
    stage: storage
  - id: provide_space_heat
    stage: end_use
  - id: sequester_carbon
    stage: sink
```

Valid stages: `supply`, `conversion`, `storage`, `end_use`, `sink`.

**Compiler enforcement:** `[E_STAGE_ENUM]` — invalid stage value.

**Auto-derived classifications** (used in diagnostics, not enforced at compile):
- `end_use` + service output → `kind=device`
- `conversion` + electricity output → `kind=generator`
- `storage` → `kind=storage`

### 5. Consolidate Files with Case Overlays

If multiple files model the *same RES topology* with different policy
scenarios, collapse into one file with a `cases` block.

**Before (three files):**

```
toy_resources_ref.veda.yaml
toy_resources_co2cap.veda.yaml
toy_resources_forceshift.veda.yaml
```

**After (one file with cases):**

```yaml
# toy_resources.veda.yaml
model:
  cases:
    - name: ref
      is_baseline: true
    - name: co2cap
      constraints:
        - name: CO2_CAP
          type: emission_cap
          commodity: co2e
          limit: {2030: 80, 2040: 50, 2050: 20}
          limtype: up
    - name: force_shift
      ncap_bounds:
        - variant: electric_haul
          bound_type: lo
          values: {2030: 0.5, 2040: 1.0}
```

**Rule of thumb:** Keep separate files only when the RES *topology* differs
(e.g., different timeslice structures like `toy_electricity_2ts` vs `4ts`).

### 6. Ensure Primary Output Invariant

Non-storage, non-sink roles must have exactly **one** primary non-emission
output commodity.

**Compiler enforcement:** `[E_ROLE_PRIMARY_OUTPUT]`.

Emission outputs are declared via `emission_factors` on variants, not as
additional output commodities on the role:

```yaml
process_variants:
  - id: gas_heater
    role: provide_space_heat
    inputs: [{commodity: natural_gas}]
    efficiency: 0.9
    emission_factors:
      co2: 0.056
```

### 7. Verify Model After Migration

```bash
# Lint (schema + structural checks)
uv run vedalang lint model.veda.yaml

# Full pipeline (lint + compile + xl2times)
uv run vedalang validate model.veda.yaml

# Optional: LLM structural assessment
uv run vedalang lint model.veda.yaml --llm-assess

# Run regression suite
uv run pytest tests/test_prd_acceptance.py -v
```

---

## Summary of Compiler Error Codes

| Code | Severity | What It Catches |
|------|----------|-----------------|
| `E_STAGE_ENUM` | Hard error | Invalid stage value |
| `E_COMMODITY_TYPE_ENUM` | Hard error | Invalid commodity type |
| `E_DEMAND_COMMODITY_TYPE` | Hard error | Demand targeting non-service commodity |
| `E_EMISSION_COMMODITY_TYPE` | Hard error | Emission constraint targeting non-emission commodity |
| `E_ROLE_PRIMARY_OUTPUT` | Hard error | Role with ≠1 primary non-emission output |
| `E1_DUPLICATE_SERVICE_ROLES` | Hard error | Multiple roles sharing output+stage |
| `E_END_USE_PHYSICAL_INPUT` | Hard error | Zero-input end_use without demand_measure |
| `W1_SPLIT_IDENTICAL_IO_ROLES` | Warning | Roles with identical I/O signatures |
| `W2_FUEL_PATHWAY_ROLE_NAME` | Warning | Role name suggests fuel-pathway pattern |

## Reference

- **PRD:** `docs/prds/vedalang_toy_refactor_prd_updated.txt`
- **Modeling conventions:** `.agents/skills/vedalang-modeling-conventions/SKILL.md`
- **Acceptance tests:** `tests/test_prd_acceptance.py`
- **Schema:** `vedalang/schema/vedalang.schema.json`
