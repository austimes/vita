# VedaLang Modeling Conventions

Canonical reference for VedaLang modeling conventions. This document is the
single source of truth used by both the
[modeling conventions skill](../../skills/vedalang-modeling-conventions/SKILL.md)
and the LLM structural linter. It is **non-binding** at compile time — it
complements lint checks and compiler enforcement.

## Three-Layer Framework

Use these layers together:

1. **Layer 1: Convention guidance (this doc)**
2. **Layer 2: Lint/assessment checks**
   (heuristics today, optional LLM structural assessment as it lands)
3. **Layer 3: Compiler/schema hard enforcement** (must pass to compile)

If guidance in this file and current schema/compiler behavior disagree,
schema/compiler are authoritative.

## Terminology (Canonical)

- `role` = **what service/transformation is provided**
- `variant` = **how the role is provided** (technology pathway)
- `mode` = **operating state within a variant** (fuel/configuration)
- `provider` = **facility/fleet reporting object** hosting variant/mode choices
- `scope` = **commodity-only market partition** (not a process/type identity)
<!-- GENERATED:canonical-enums:start -->
- `stage` = one of `supply | conversion | distribution | storage | end_use | sink`
- `commodity.type` = one of `fuel | energy | service | material | emission | money | other`
- `commodity namespace prefix` = one of `primary | resource | secondary | service | material | emission | money`
<!-- GENERATED:canonical-enums:end -->

Keep these terms consistent in model docs, PRDs, lint narratives, and
diagnostics specs.

Hard hierarchy:
- `role -> variant -> mode` is the type axis.
- `provider` is the object axis.
- `scope` belongs only to commodity symbols/markets.

## Core Conventions

### 1) Service-Level Roles, Technology Variants

Prefer one service-oriented role with multiple pathway variants.

Good:

```yaml
roles:
  - id: provide_space_heat
    activity_unit: PJ
    capacity_unit: GW
    stage: end_use
    required_inputs:
      - commodity: primary:natural_gas
    required_outputs:
      - commodity: service:space_heat

variants:
  - id: gas_boiler
    role: provide_space_heat
    modes:
      - id: ng
        inputs:
          - commodity: primary:natural_gas
        outputs:
          - commodity: service:space_heat
        efficiency: 0.9
        emission_factors:
          emission:co2: 0.056
  - id: heat_pump
    role: provide_space_heat
    modes:
      - id: grid
        inputs:
          - commodity: secondary:electricity
        outputs:
          - commodity: service:space_heat
        efficiency: 3.2

providers:
  - id: fleet.space_heat.VIC.residential
    kind: fleet
    role: provide_space_heat
    region: VIC
    scopes: [RES]
    offerings:
      - variant: gas_boiler
        modes: [ng]
      - variant: heat_pump
        modes: [grid]
```

Avoid:

```yaml
roles:
  - id: heat_from_gas
    stage: end_use
    inputs: [{commodity: primary:natural_gas}]
    outputs: [{commodity: service:space_heat}]
  - id: heat_from_electricity
    stage: end_use
    inputs: [{commodity: secondary:electricity}]
    outputs: [{commodity: service:space_heat}]
```

Why: diagnostics and fuel-switch metrics stay stable under granularity
refactors when boundary selectors target a service role family rather than
fuel-pathway role names.

### 2) Primary Supply Roles

Supply-stage roles (`stage: supply`) with zero inputs are valid and expected.
They represent primary resource/source nodes at the left edge of the RES.

Good:

```yaml
roles:
  - id: supply_ag_inputs
    stage: supply
    outputs:
      - commodity: material:ag_inputs
    # No inputs — this is a primary supply node. Valid.
```

Only flag zero-input roles at **non-supply stages** (especially `end_use`) as
suspicious fake supply. One intentional exception is `stage: sink` when the
process represents ledger-only removals via negative `emission_factors`
(for example, reforestation/LULUCF accounting without explicit CO2 material
flows).

```yaml
# Suspicious — end_use role with no inputs looks like fake supply
roles:
  - id: create_space_heat
    stage: end_use
    outputs:
      - commodity: service:space_heat
    # No inputs at end_use stage → likely a modeling error
```

### 3) Physical-Only RES by Default

Model physical transformations in process roles/variants. Demand reduction
policy should generally be represented in case overlays, not fake physical
supply.

Preferred (case overlay demand change):

```yaml
model:
  cases:
    - name: policy
      demand_overrides:
        - commodity: service:space_heat
          scale: 0.85
```

Avoid (implicit fake supply):

```yaml
roles:
  - id: create_space_heat
    stage: end_use
    outputs:
      - commodity: service:space_heat
```

### 4) Naming Conventions

All IDs use **snake_case** (underscores, not dashes).

- **Role IDs** — verb-noun pattern describing the service:
  `supply_ag_inputs`, `provide_space_heat`, `sequester_carbon`,
  `provide_ag_output`

- **Variant IDs** — descriptive pathway/method names. Do NOT repeat the
  role ID in the variant; the `role:` field provides that linkage.

  When variants represent **complete replacement pathways** (not bolt-on
  modifiers), use bundle naming anchored on the baseline:
  `traditional_baseline`, `traditional_with_feed_additives`,
  `traditional_with_improved_manure`. The `*_with_*` pattern makes clear
  each variant is a complete end-to-end replacement, not an add-on.

  Good: `gas_boiler`, `heat_pump`, `traditional_baseline`,
  `traditional_with_feed_additives`, `reforestation`

  Avoid: `provide_space_heat_gas_boiler` (redundant with `role:` field)

  Avoid: `feed_additives`, `improved_manure` (ambiguous — sounds like a
  bolt-on modifier rather than a complete replacement pathway)

- **Commodity IDs** — namespaced snake_case descriptive names:
  `secondary:electricity`, `service:space_heat`, `emission:co2`, `primary:natural_gas`, `resource:wind_resource`, `material:biomass`

### 5) Stage and Commodity Typing Discipline

Always declare and respect stage/commodity semantics.

Good:

```yaml
model:
  commodities:
    - id: secondary:electricity
      type: energy
    - id: primary:natural_gas
      type: fuel
    - id: resource:wind_resource
      type: other
    - id: service:space_heat
      type: service
    - id: emission:co2
      type: emission
```

Avoid:

```yaml
model:
  commodities:
    - id: service:space_heat
      type: energy   # should be service
```

Preferred namespace discipline for primary-vs-secondary energy clarity:

- `primary:*` + `type: fuel` for combustible/extractable primary fuels
  (`primary:natural_gas`, `primary:coal`, `primary:diesel`)
- `resource:*` + `type: other` for exogenous non-combustible resources
  (`resource:wind_resource`, `resource:solar_irradiance`)
- `secondary:*` + `type: energy` for secondary carriers
  (`secondary:electricity`, `secondary:hydrogen`, `secondary:delivered_electricity`)

Legacy models that use older `fuel:*`/`energy:*` namespaces should be migrated
to `primary:*`/`secondary:*` for clarity.

### 5a) Combustion Heating Basis: Explicit Metadata + Point-of-Use Basis

For combustible commodities, heating-basis handling must be explicit everywhere.
Do not rely on implicit defaults or inherited basis.

- Every commodity must explicitly set `combustible: true|false`.
- If `combustible: true`, the commodity must provide both
  `lhv_mj_per_unit` and `hhv_mj_per_unit`.
- If `combustible: false`, it must not provide heating-value metadata.
- The compiler uses the `HHV/LHV` ratio (`hhv_mj_per_unit / lhv_mj_per_unit`)
  to convert point-of-use values between bases.
- Canonical emitted basis is HHV.

Point-of-use basis must be declared on fields that can be basis-sensitive:

- Variant combustible flow anchors: `inputs[*].basis` / `outputs[*].basis`
- Variant costs: `variable_om_cost_basis` (when activity is energy-based and
  combustible flows are present)
- Variant emissions: `emission_factor_basis` (when combustible flows are present)
- Scenario commodity prices: `scenario_parameters[*].value_basis`
- Case fuel price overrides: `fuel_price_overrides[*].value_basis`
- Case provider override costs:
  `provider_overrides[*].variable_om_cost_basis`

Recommended authoring pattern:

```yaml
model:
  commodities:
    - id: primary:natural_gas
      type: fuel
      unit: PJ
      combustible: true
      lhv_mj_per_unit: 50.0
      hhv_mj_per_unit: 55.0

variants:
  - id: gas_supply
    role: supply_gas
    outputs:
      - commodity: primary:natural_gas
        basis: HHV
    variable_om_cost: "6 MUSD24/PJ"
    variable_om_cost_basis: HHV
```

Note on absolute values:
`lhv_mj_per_unit`/`hhv_mj_per_unit` are currently used to derive a conversion
ratio for basis normalization. Absolute calorific values become essential when
converting across dimensions (for example mass/volume/energy), which is a
separate modeling concern.

### 6) Cases Are Scenario Overlays, Not New RES Architectures

Use one physical RES plus case overlays for deltas (policy, prices, demand
scaling, technology assumptions). Keep separate files only when the
underlying network topology is fundamentally different (for example,
different timeslice structure).

### 7) Diagnostics Must Be Solve-Independent

Diagnostics boundaries and metrics should be metadata-driven and deterministic
from solved outputs + compiled metadata map. They should not alter solve
behavior.

Boundary selectors should use semantics (`stage_in`, `service_in`, `kind_in`,
`sector_in`) before string filters (`include_any`, `exclude_any`).

### 8) Emissions as Attributes, Not Flows

Emission commodities (`emission:*`) represent ledger entries, not physical flows.
They MUST NOT appear in process `inputs` or `outputs`.

Good:

```yaml
variants:
  - id: gas_boiler
    role: provide_space_heat
    inputs:
      - commodity: primary:natural_gas
    outputs:
      - commodity: service:space_heat
    emission_factors:
      emission:co2: 0.056
```

Avoid:

```yaml
variants:
  - id: gas_boiler
    outputs:
      - commodity: service:space_heat
      - commodity: emission:co2   # ERROR: emission in outputs
```

For negative emissions (DAC, LULUCF), use negative `emission_factors`:

```yaml
variants:
  - id: dac
    role: remove_co2
    inputs:
      - commodity: secondary:electricity
    emission_factors:
      emission:co2: -1.0
```

If physical CO2 transport/storage is needed, use `material:co2` as a flow.

### 9) Explicit Process Units (No Ambiguity)

Treat process units as first-class modeling semantics:

- `activity_unit` must be an extensive quantity unit (energy/service/mass), not a
  rate. Examples: `PJ`, `GWh`, `Bvkm`, `Mt`.
- `capacity_unit` must be either:
  - power (`GW`, `MW`, `kW`, `TW`), or
  - explicit annual rate (`<unit>/yr`, e.g., `PJ/yr`, `Bvkm/yr`, `Mt/yr`).
- Avoid ambiguous non-power capacity declarations such as
  `activity_unit: PJ` + `capacity_unit: PJ`.

Capacity-to-activity linkage should always be explainable from units:

- `PRC_CAPACT = convert(1 * capacity_unit * 1 yr -> activity_unit)`
- `GW -> PJ` gives `31.536`
- `PJ/yr -> PJ` gives `1.0`

Supported explicit activity base units:

- Energy: `PJ`, `TJ`, `GJ`, `MWh`, `GWh`, `TWh`, `MTOE`, `KTOE`
- Service: `Bvkm`
- Mass: `Mt`, `kt`, `t`, `Gt`

Supported explicit capacity units:

- Power: `GW`, `MW`, `kW`, `TW`
- Annual rates: each supported activity base unit with `/yr`

## Conventions vs Current Enforcement

The following are enforced today by schema/compiler behavior:

- `stage` enum values are schema-enforced
- `commodity.type` enum values are schema-enforced
- non-storage/non-sink roles require exactly one primary non-emission output
- end-use variants must include at least one physical input
  (`fuel`/`energy`/`material`)
- `demand_projection` must target `commodity.type=service` (semantic xref check)
- diagnostics export contract is solve-independent
  (`diagnostics_are_solve_independent`)
- `emission:*` must not appear in inputs/outputs (L1)
- `activity_unit` must be extensive; `capacity_unit` must be power or `<unit>/yr`
- ambiguous non-power capacity/activity pairs are rejected
- `emission_factors` keys must be `emission:*` namespaced (L2)
- Bare `co2`/`ch4`/`n2o` trigger migration warnings (L5)

The following should be treated as guidance/lint focus (unless hard rules are added):

- detecting fuel-pathway role fragmentation and suggesting role merges
- flagging suspicious zero-input roles at **non-supply** stages (especially
  `end_use`) — zero-input `supply` stage roles are valid primary sources;
  `sink` roles can also be intentionally zero-input for ledger-style removals
- flagging service commodities used as intermediate carriers when this
  obscures diagnostics intent
- enforcing snake_case naming for role, variant, and commodity IDs
- detecting variant IDs that redundantly repeat their role ID

## Authoring Checklist

- [ ] All IDs use snake_case (no dashes)
- [ ] Roles describe services/transformations, not fuel pathways
- [ ] Role IDs follow verb-noun pattern
- [ ] Variants encode technology pathways and costs/performance
- [ ] Variant IDs are descriptive pathway names (not repeating the role ID)
- [ ] Zero-input roles are intentional only for `supply` or specific
  `sink` ledger-removal patterns
- [ ] End-use demand changes use case `demand_overrides` where possible
- [ ] End-use variants include at least one physical input
- [ ] Commodity typing is explicit and consistent with use
- [ ] Stages are explicit and from the canonical enum
- [ ] Diagnostics boundaries are semantic and solver-independent
- [ ] Commodity IDs use namespace prefixes (`primary:`, `resource:`, `secondary:`,
  `service:`, `emission:`, etc.) consistently
- [ ] Emissions use emission_factors dict, not inputs/outputs
- [ ] `uv run vedalang fmt --check <model>.veda.yaml` passes
- [ ] `uv run vedalang lint <model>.veda.yaml` and
  `uv run vedalang validate <model>.veda.yaml` pass

## Cross-References

- `skills/vedalang-dsl-cli/SKILL.md` (authoring workflow)
- `docs/vedalang-user/heuristics.md` (lint heuristics)
- `docs/prds/vedalang_toy_refactor_prd_updated.txt`
  (three-layer convention framework)
- `docs/prds/vedalang_vnext_prd.txt` (cases + diagnostics design)
- `vedalang/schema/vedalang.schema.json` (authoritative schema)
- `vedalang/compiler/compiler.py`
  (semantic validation and diagnostics export behavior)
