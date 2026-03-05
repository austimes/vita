# VedaLang History

Chronological record of major design decisions, schema changes, and milestone events in VedaLang development.

---

## Phase 0: Toolchain Validation (2025-12-21)

**Goal:** Prove that the VedaLang → TableIR → Excel → xl2times pipeline works end-to-end.

- Scaffolded repo directory structure (schema, compiler, emitter, tests)
- Created `vedalang.schema.json` and `tableir.schema.json`
- First example: `quickstart/mini_plant.veda.yaml` — a single thermal plant
- Wired `vedalang compile`, `vedalang-dev emit-excel`, and `vedalang validate`
- Added MiniVEDA2 fixture with xl2times integration test
- Hardened xl2times diagnostics: graceful errors, structured JSON output
- **Decision:** xl2times is the validation oracle — its verdict defines correctness
- **Decision:** Excel is compiled output, never hand-edited source

## Phase 1: Primitives Exploration (2025-12-21 → 2026-02-17)

### Design Challenges (DC1–DC5)

- **DC1:** Thermal plant from patterns — basic process/commodity/topology
- **DC2:** Renewable sharing output commodity — multiple processes, shared commodities
- **DC3:** Emission tracking with ENV_ACT
- **DC4:** CO2 price trajectory — TFM tags, time-varying parameters
- **DC5:** Two-region model — multi-region, trade, IRE processes

### Primitives Discovered and Schema Extensions

- **Interpolation** (2025-12-22): Made interpolation REQUIRED on all time-series. Uses VEDA option codes (none=-1, interp_only=1, etc.). Compiler expands sparse values to dense milestone-year rows. **Decision:** Never rely on TIMES implicit interpolation.
- **Storage** (2025-12-22): Validated same-commodity I/O pattern for batteries
- **CHP** (2025-12-22): Verified expressible with existing schema (no extension needed)
- **Timeslices** (2025-12-22): Added `model.timeslices` with season/weekly/daynite levels and fractions
- **Trade** (2025-12-22): Added `model.trade_links` for inter-regional commodity exchange
- **User constraints** (2025-12-22): Added `model.constraints` supporting `emission_cap` and `activity_share`
- **Primary commodity group** (2025-12-22): Made PCG required (removed inference)
- **Cross-reference validation** (2025-12-22): Semantic checks with unit validation at compile time

### Canonical Table Form (2025-12-21)

- **Decision:** All VEDA tables use tidy long-by-year format. No wide pivots, no VEDA interpolation in Excel output.
- Rationale: Explicit values are self-documenting, predictable, and avoid TIMES interpolation surprises.

### Compiler Architecture

- **Scenario separation** (2025-12-24): Model architecture (VT_* files) separated from scenario data (Scen_* files)
- **File naming:** `Scen_{case}_{category}.xlsx` convention established
- **VedaOnline compatibility** (2025-12-23): Directory structure, scalar tables, UC_SETS format fixed
- **TIMES runner** (2025-12-23): Added `vedalang-dev run-times` with IIS/Conflict Refiner support

### Curated Registry (2025-12-23 → 2026-01-08)

- Created `attributes-supported.yaml` and `tags-supported.yaml` — curated allowlists
- `VedaRegistry` class for compile-time attribute/tag validation
- Enforced canonical attribute names only — no aliases
- Context-aware cost mapping (IMP→ire_price, others→act_cost)
- Explicit cost attribute names with VedaLang→TIMES mapping documented

### MiniSystem Test Series (2026-01-06 → 2026-01-10)

Progressive complexity series (`minisystem1` through `minisystem8`):
1. Minimal solvable toy model
2. Fuel and conversion chain
3. Investment and stock dynamics
4. Emissions and climate policy
5. Technology competition with renewables
6. Intra-annual timeslices
7. Multi-region with unidirectional trade
8. Australian baseline scaffold with multi-sector

- Added `existing_capacity` (NCAP_PASTI) support
- Compiler emits PRC_CAPACT for GW→PJ unit conversion
- Scalar values expanded to explicit milestone year rows

## Phase 2: Composable Syntax — Roles, Variants, Segments (2026-01-15)

**Major schema redesign** introducing composable process modeling:

- **`roles`**: Abstract topology definitions (what transformation happens — inputs/outputs, stage)
- **`variants`**: Concrete technology implementations of roles (efficiency, costs, lifetime)
- **`segments`**: Sector/end-use segmentation for demand-side modeling
- **`availability`**: Where variants are available (region × sector × segment)
- **`process_parameters`**: Selector-based parameter blocks (stock, bounds, existing capacity)
- **`demands`**: Service commodity demands by region/sector/segment

**Decision:** Roles describe physics (commodity transformation). Variants describe technology (costs, performance). This separation enables the same topology to have multiple competing technologies.

**Decision:** Commodity `type` field is canonical — uses semantic types (`fuel`, `energy`, `service`, `material`, `emission`, `other`) that drive COM_TYPE mapping, diagnostics, and tradability defaults.

## Cases and Diagnostics (2026-01-15)

Added scenario composition and solve-independent diagnostics:

- **`model.cases`**: Named parameter combinations for model runs with overlay semantics (demand/price/constraint/variant overrides)
- **`model.studies`**: Collections of cases for comparison
- **`diagnostics`**: Boundaries and metrics defined by semantic selectors, not specific process IDs
- **Decision:** Diagnostics are solve-independent — changing boundaries never requires re-solving the LP
- **Decision:** Boundaries are granularity-invariant — same boundary works whether a service has 2 variants or 200

## Emissions Refactor (2026-02-17)

- **`emission_factors` dict on variants**: Replaced variant-level emissions array with keyed dict. Keys are emission commodity IDs referenced in the role's outputs. Values are scalars or time-varying specs per unit process activity (TIMES ENV_ACT).
- **Rationale:** Emissions are role outputs (part of the topology), emission factors are variant parameters. Cleaner separation of concerns.

## Sector Toy Problems (2026-02-17)

Created comprehensive sector-specific toy models testing all major features:
- `toy_electricity_2ts` / `toy_electricity_4ts` — VRE + gas + storage with timeslices
- `toy_transport` — ICE vs EV with activity_share constraint
- `toy_buildings` — Gas heater vs heat pump vs building retrofit
- `toy_industry` — Gas vs electricity vs H2 under tightening CO2 cap
- `toy_resources_co2cap` / `toy_resources_forceshift` — Mining electrification policies
- `toy_agriculture` — Methane abatement and carbon sequestration
- `toy_integrated_6sector` — Complete multi-sector model with shared grids and economy-wide CO2 cap

## Heuristic Linting (ongoing)

Pre-compilation checks that catch modeling patterns causing solver infeasibility:
- **H001:** Fixed ncap_bound with lifetime shorter than horizon
- **H002:** Demand devices without stock/capacity
- **H003:** Insufficient base year capacity for demand

---

## Design Principles (cumulative)

1. **xl2times is the oracle** — any discrepancy between VedaLang output and xl2times expectations is a VedaLang bug
2. **Excel is compiled output** — never the source
3. **Explicit over implicit** — always emit values for all milestone years; never rely on TIMES interpolation
4. **Schema-first** — all language changes start with schema updates, then docs, tests, code
5. **Test-driven** — no new tag/pattern without a passing test
6. **Breaking changes are OK** — this is pre-1.0; design correctness over backward compatibility

---

## Repository Hygiene — 2026-02-21

- Removed `experiments/` directory — all Phase 1 exploration artifacts (capacity_bounds, chp, demand, fuel_supply, storage, timeslices, trade, transmission, user_constraints) fully captured in HISTORY.md and patterns.yaml

## Prototype Governance — 2026-02-25

- **Decision:** During pre-1.0 prototype phase, do not maintain migration guides or backward-compatibility scaffolding unless explicitly required for external release communication.
- **Decision:** Prefer direct in-place design evolution (schema/compiler/examples/tests) with clear commits.
- **Decision:** Use git history + concise dated decisions in `HISTORY.md` as the canonical change log and rationale record.

## Facility Modes Refactor (2026-03-05)

- **Breaking change:** Replaced facility primitive fuel switching based on
  `candidate_variants` + `transition_graph` + `input_mix` + `variant_policies`
  with mode-based template definitions (`facility_templates[].variants[].modes[]`).
- **New facility semantics:** Added `cap_base`, `capacity_coupling` (`le|eq`),
  and `no_backsliding` controls at facility level.
- **Compiler lowering:** Facilities now compile to one synthetic process variant
  per mode and emit LP-safe `UC_CAP` constraints for capacity coupling,
  no-backsliding monotonicity, and ramp-rate limits.
- **Cost accounting:** Retrofit costs represented as mode `investment_cost`
  (`NCAP_COST`) on retrofit mode capacity.
- **Removed old facility constraints:** `FAC_MIX_*` and `FAC_NB_*` no longer
  generated for facility fuel switching.
