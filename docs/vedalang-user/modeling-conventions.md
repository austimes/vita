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
<!-- GENERATED:canonical-enums:start -->
- `stage` = one of `supply | conversion | distribution | storage | end_use | sink`
- `commodity.type` = one of `fuel | energy | service | material | emission | money | other`
- `commodity namespace prefix` = one of `primary | resource | secondary | service | material | emission | money`
<!-- GENERATED:canonical-enums:end -->

Keep these terms consistent in model docs, PRDs, lint narratives, and
diagnostics specs.

## Core Conventions

### 1) Service-Level Roles, Technology Variants

Prefer one service-oriented role with multiple pathway variants.

Good:

```yaml
process_roles:
  - id: provide_space_heat
    stage: end_use
    inputs:
      - commodity: primary:natural_gas
    outputs:
      - commodity: service:space_heat

process_variants:
  - id: gas_boiler
    role: provide_space_heat
    efficiency: 0.9
    emission_factors:
      emission:co2: 0.056
  - id: heat_pump
    role: provide_space_heat
    efficiency: 3.2
```

Avoid:

```yaml
process_roles:
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
process_roles:
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
process_roles:
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
process_roles:
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
process_variants:
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
process_variants:
  - id: gas_boiler
    outputs:
      - commodity: service:space_heat
      - commodity: emission:co2   # ERROR: emission in outputs
```

For negative emissions (DAC, LULUCF), use negative `emission_factors`:

```yaml
process_variants:
  - id: dac
    role: remove_co2
    inputs:
      - commodity: secondary:electricity
    emission_factors:
      emission:co2: -1.0
```

If physical CO2 transport/storage is needed, use `material:co2` as a flow.

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
