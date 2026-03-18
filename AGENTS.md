Use 'bd' for task tracking

---

# Three-Layer CLI Architecture

This repository provides **three CLI tools**, each with a distinct role:

| CLI | Role | Audience |
|-----|------|----------|
| **`vedalang`** | The language — author, lint, compile, validate models | Model developers (User Agent) |
| **`vita`** | The engine — run, analyze, and explain TIMES experiments | Anyone running models |
| **`vedalang-dev`** | Internal R&D — pattern experimentation, evals, emit-excel | Language designers (Design Agent) |

**Rule of thumb:** Use `vedalang` to *write* models, `vita` to *run and analyze* them, and `vedalang-dev` only for language design work.

---

# Two Distinct Personas

This repository serves **two distinct AI personas** — understanding this distinction is critical:

| Persona | Purpose | Documentation |
|---------|---------|---------------|
| **VedaLang User Agent** | Uses VedaLang to author energy system models | `skills/vedalang-dsl-cli/` and `docs/vedalang-user/` |
| **VedaLang Design Agent** | Designs and evolves the VedaLang DSL itself | This file (`AGENTS.md`) and `docs/vedalang-design-agent/` |

## VedaLang User Agent

An AI agent that **uses VedaLang** to create `.veda.yaml` models for energy system analysis. This agent:
- Reads the VedaLang schema and examples
- Writes valid VedaLang source files
- Uses `vedalang fmt`, `vedalang lint`, and `vedalang validate` to check models
- Uses `vita run` and `vita results` to run and inspect solver output
- Does NOT modify the language, compiler, or schema

**User agent documentation:**
- `docs/LLM_DOCS.md` — LLM-facing documentation map (purpose + ownership)
- `skills/vedalang-dsl-cli/SKILL.md` — Canonical DSL + CLI operational skill
- `skills/vedalang-modeling-conventions/SKILL.md` — Modeling conventions skill
- `docs/vedalang-user/` — User documentation index
- `vedalang/schema/vedalang.schema.json` — Language schema
- `vedalang/examples/` — Example models
- `rules/patterns.yaml` — Pattern "standard library"

## VedaLang Design Agent

An AI agent that **designs and evolves VedaLang** — the DSL, compiler, schemas, and tooling. This agent:
- Extends the VedaLang schema with new constructs
- Improves the compiler and emitters
- Discovers new VEDA patterns through experimentation
- Validates changes against xl2times (the oracle)

Canonical exploration workflow skill:
- `skills/vedalang-design-exploration/SKILL.md`

**The rest of this file is for the VedaLang Design Agent.**

---

## Package Manager

This project uses **uv** as the Python package manager.

```bash
# Sync dependencies (install/update from lockfile)
uv sync

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run a command in the venv
uv run <command>

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run xl2times
uv run xl2times <args>
```

## xl2times (Third-Party Library)

`xl2times` is a **third-party open-source library** that we include in-repo for convenience and visibility. **Do not modify xl2times unless absolutely necessary.**

- We keep the source locally so we can see exactly what it does
- It serves as the validation oracle — its behavior defines correctness
- Changes to `xl2times/` require strong justification (e.g., critical bug blocking development)
- Prefer workarounds in VedaLang tooling over modifying xl2times
- **All changes MUST be documented in [XL2TIMES_CHANGES.md](xl2times/XL2TIMES_CHANGES.md)** with date, commit, description, and reason

# VEDA DevTools - Agent Instructions

## Project Vision

Build a **safer, typed DSL** that compiles to VEDA tables — analogous to how TypeScript compiles to JavaScript. The new language (working name: **VedaLang**) provides:

- Type safety (units, symbols, constraints)
- Schema validation  
- Cross-reference checking
- Clear error messages

VEDA Excel tables become a **compiled artifact**, not the source. xl2times validates the compiled output.

## Current Project Status

As of **2026-03-07**, the original core phases (**P0-P3**) remain complete and
the **package/run/CSIR/CPIR** reset has landed as the active public DSL.

What this means for design-agent work:
- Prefer the current object-model terminology and architecture:
  `package`, `run`, `commodity`, `technology`, `technology_role`,
  `stock_characterization`, `site`, `facility`, `fleet`, `zone_opportunity`,
  `network`, `CSIR`, `CPIR`, `explain.json`.
- Keep the run-scoped frontend and the Excel/xl2times/TIMES backend path in
  parity when making changes.

The completed rollout epics were:
- `vedalang-txa.1` — governance and version contract
- `vedalang-txa.3` — public schema and AST reset
- `vedalang-txa.4` — package/run/spatial/stock resolution
- `vedalang-txa.5` — CSIR/CPIR/explain artifacts
- `vedalang-txa.6` — backend parity through Excel/xl2times/TIMES
- `vedalang-txa.7` — diagnostics, tooling, docs, and regression coverage

## Terminology

VedaLang uses precise terminology to avoid ambiguity in the VEDA ecosystem:

| Term | Definition |
|------|------------|
| **Scenario Parameter** | An atomic time-series or value assumption (e.g., CO2 price path, demand projection) |
| **Category** | Logical grouping of scenario parameters (canonical values listed below) |
| **Case** | A named combination of scenario parameters for a specific model run (e.g., `baseline`, `ambitious`) |
| **Study** | A collection of cases for comparison |

<!-- GENERATED:scenario-categories:start -->
**Canonical scenario categories:** `demands` | `prices` | `policies` | `technology_assumptions` | `resource_availability` | `global_settings`
<!-- GENERATED:scenario-categories:end -->

These category names are currently a compiler/runtime convention for
`scen_{case}_{category}.xlsx` naming. They are not yet declared as a
`vedalang.schema.json` enum because scenario workbooks are outside the authored
public DSL surface.

**Key distinctions:**
- **Model architecture** (`vt_*` files): processes, commodities, topology — the Reference Energy System
- **Scenario instantiation** (`scen_{case}_{category}.xlsx`): demands, prices, policies that instantiate the RES

**File naming convention:** `scen_{case}_{category}.xlsx`
- Example: `scen_baseline_demands.xlsx`, `scen_ambitious_policies.xlsx`

This terminology maps to VEDA concepts:
- "Scenario file" (`scen_*.xlsx`) → contains scenario parameters grouped by case and category
- "High-level scenario" → **case** (a specific combination of scenario parameters)
- "Study" → collection of cases for comparison

## Architecture Overview

```
Authored VedaLang package (.veda.yaml)
    │
    │  (1) Parse + schema-validate
    ▼
Public AST / package graph
    │
    │  (2) Resolve one run
    ▼
CSIR (Canonical Semantic IR)
    │
    │  (3) Lower semantics to explicit process form
    ▼
CPIR (Canonical Process IR)
    │
    │  (4) Bridge to existing backend path
    ▼
TableIR  ──►  VEDA Excel (.xlsx)  ──►  xl2times  ──►  TIMES DD files
                                                     │
                                                     │  (5) vita run --from dd
                                                     ▼
                                              GAMS/TIMES Solution (.gdx)
```

**Key insight**: the active frontend target is `package/run -> CSIR -> CPIR`,
and the existing backend path through TableIR/Excel/xl2times remains the
required parity target.

## Toolchain Build Order

Tools needed for an agent to **design VedaLang itself**:

| Order | Tool | Purpose |
|-------|------|---------|
| **T1** | `xl2times` + JSON outputs | Validation oracle — "Is this valid VEDA?" |
| **T2** | `vedalang-dev emit-excel` | Existing backend emitter (TableIR → Excel) |
| **T3** | `vedalang` compiler | Active frontend under reset: source → CSIR/CPIR → backend path |
| **T4** | `vedalang validate` | Compile + xl2times oracle validation (no solver) |
| **T5** | `vita run` | Run full pipeline or DD files through GAMS/TIMES solver |

## Key Principle: Agent-Designed Language

The goal is for an **AI agent to iteratively design VedaLang** using feedback tools:

1. **xl2times validation** — "Did I produce valid VEDA tables?"
2. **vedalang validate** — Unified lint + compile + validate feedback
3. **Decision heuristics** — Mapping physical concepts → VEDA table patterns

We are not porting older models. This is for new model development.

## Two Separate Concerns

### 1. Language Mechanics (VedaLang)
- Syntax, types, allowed constructs
- Schema-defined (JSON Schema)
- Compiler lowers through CSIR/CPIR and then the existing TableIR → Excel path

### 2. Modeling Decisions (Heuristics)
- "Given intent X, which tags/files/fields do I use?"
- Data-driven pattern library (`rules/patterns.yaml`)
- Agent discovers these through experimentation

**These are kept separate.** VedaLang is a general-purpose VEDA authoring language; heuristics are the "standard library" of patterns.

## Design Principle: Commodity Namespaces and Emissions-as-Attributes

**Commodity namespaces** map human-readable prefixes to VEDA Csets:
- `primary:` → NRG, `secondary:` → NRG, `resource:` → NRG, `material:` → MAT, `service:` → DEM, `emission:` → ENV, `money:` → FIN

**Decision (2026-02-24):** Use `primary:*` for primary combustible/extractable fuels and
`secondary:*` for secondary carriers to make primary-vs-secondary energy
pedigree explicit.

**Emissions are ledger entries, not flows.** `emission:*` commodities MUST NOT appear in process `inputs` or `outputs`. They enter the model only via `emission_factors`:

```yaml
technologies:
  - id: gas_heater
    provides: service:space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    outputs:
      - commodity: service:space_heat
    emissions:
      emission:co2: 0.056  # ledger entry, not a flow
```

Negative emission factors are valid for DAC/LULUCF. Physical CO2 streams use `material:co2`.

**Lint rules:** L1 (emission:* not in I/O), L2 (emission_factors keys must be emission:*), L3 (negative EF allowed), L5 (bare co2 warns).

## Design Principle: Heating-Value Basis Must Be Explicit

**No defaults, no inheritance.** Heating-value basis metadata must never be
implicit.

Policy:
- Do not apply a default HHV/LHV basis anywhere.
- Do not inherit basis from model-level or commodity-level context when reading
  coefficients/attributes. Basis must be specified at the same site as the
  value it qualifies.
- Internal compiler normalization target is **HHV**. Inputs authored as LHV are
  converted explicitly during compilation.

Combustible commodity requirements:
- Combustible commodities must be explicitly marked as combustible.
- Combustible commodities must carry enough metadata to derive both bases
  (store both LHV and HHV references, or an equivalent deterministic ratio).
- Non-combustible commodities (e.g., electricity) must be explicitly marked
  non-combustible and must not carry HHV/LHV basis tags.

Point-of-use requirements (combustible commodities only):
- Fuel input/output coefficients
- Fuel-linked prices/cost coefficients
- Emission factors tied to fuel combustion
- Any other energy coefficient that depends on HHV/LHV interpretation

Each of the above must declare its basis explicitly (HHV or LHV) at the field
where the numeric value is provided. Compiler/lint checks must fail when basis
is omitted or inconsistent.

Combustibility detection strategy:
- Primary enforcement must be deterministic (schema + compiler/linter), not
  LLM-only.
- Commodity verification workflows may infer combustibility from naming
  conventions/registries, but models must still carry explicit combustible
  metadata for compile-time checks.

## Design Principle: Avoid Implicit TIMES Interpolation

**VedaLang should always emit explicit values for all milestone years.** Never rely on TIMES implicit interpolation.

Rationale:
- TIMES has 5+ interpolation modes with subtle differences
- Implicit behavior surprises users (e.g., PRC_RESID linear decay)
- Explicit values are self-documenting and predictable

When the VedaLang compiler encounters a single value that TIMES would interpolate:
1. Expand to all milestone years with the same value, OR
2. Require the user to specify values for each year explicitly

Examples of parameters that TIMES interpolates:
- `PRC_RESID` — residual capacity (decays linearly over TLIFE by default)
- `NCAP_COST` — investment costs
- `ACT_BND`, `CAP_BND` — activity/capacity bounds
- `COM_PROJ` — demand projections

## Repository Structure

```
vedalang/
├── AGENTS.md                    # This file
├── docs/
│   └── VEDA2_NL_to_VEDA_PRD_v0_3.txt
├── vedalang/
│   ├── cli.py                   # User CLI (vedalang fmt/lint/compile/validate)
│   ├── schema/                  # JSON Schema definitions
│   │   ├── vedalang.schema.json # VedaLang source schema
│   │   └── tableir.schema.json  # TableIR schema
│   ├── compiler/                # VedaLang → TableIR
│   └── examples/                # Example VedaLang sources
├── tools/
│   ├── veda_dev/                # Design agent CLI (vedalang-dev)
│   ├── veda_emit_excel/         # TableIR → Excel emitter
│   ├── veda_check/              # Model validation utilities
│   ├── veda_patterns/           # Pattern library tools
│   ├── veda_run_times/          # Internal TIMES solver runner used by vita
├── rules/
│   ├── patterns.yaml            # Concept → VedaLang templates
│   ├── decision_tree.yaml       # Intent routing
│   └── constraints.yaml         # Valid tag/file combinations
├── fixtures/
│   └── MiniVEDA2/               # Minimal test model
└── tests/
```

## CLI Tools

The Design Agent has access to three CLI layers:

### `vedalang` — The Language CLI

Author, lint, compile, and validate VedaLang models.

```bash
# Validate VedaLang source
vedalang validate model.veda.yaml --run <run_id>

# Compile to Excel
vedalang compile model.veda.yaml --run <run_id> --out output/

# Lint for heuristic issues
vedalang lint model.veda.yaml

# Format YAML
vedalang fmt model.veda.yaml
```

### `vita` — The Engine CLI

Run, analyze, and explain TIMES experiments.

```bash
# Full pipeline: VedaLang → Excel → DD → TIMES (preferred workflow)
vita run model.veda.yaml --run <run_id> --json

# Full pipeline without solver (useful when GAMS unavailable)
vita run model.veda.yaml --run <run_id> --no-solver --json

# Run TIMES solver on DD files only
vita run dd_dir/ --from dd --times-src ~/TIMES_model --json

# Extract results from GDX
vita results --gdx tmp/gams/scenario.gdx --json

# Generate Sankey diagram
vita sankey --gdx tmp/gams/scenario.gdx
```

### `vedalang-dev` — Internal R&D CLI

Design agent tooling for pattern experimentation and evals. Not for user-facing workflows.

```bash
# Validate VedaLang source (wraps veda_check)
vedalang-dev check model.veda.yaml --json

# Emit Excel from TableIR (for pattern experimentation)
vedalang-dev emit-excel tables.yaml --out output/

# Pattern library utilities
vedalang-dev pattern list --json
vedalang-dev pattern show thermal_plant --json

# LLM lint evals
vedalang-dev eval run --profile quick --json
```

**Key flags:**
- `--json` — Machine-readable output for agent consumption
- `--no-solver` — Stop before TIMES (useful when GAMS unavailable)
- `--keep-workdir` — Preserve temp files for debugging
- `-v` — Verbose output

### Standalone Tools

These remain available for validation:

| Tool | Purpose |
|------|---------|
| `xl2times` | Excel → DD files (validation oracle) |

```bash
# Validate Excel through xl2times
xl2times model.xlsx --case base --diagnostics-json diag.json
```

## TableIR Example

The intermediate representation between VedaLang and Excel:

```yaml
files:
  - path: base/base.xlsx
    sheets:
      - name: "Base"
        tables:
          - tag: "~FI_PROCESS"
            rows:
              - { PRC: "PP_CCGT", Sets: "ELE", TACT: "PJ", TCAP: "GW" }
          - tag: "~FI_T"
            rows:
              - { PRC: "PP_CCGT", COM_IN: "NG", COM_OUT: "ELC", EFF: 0.55 }
```

## xl2times Integration

xl2times is the **validation oracle** for compiled output. Required extensions:

- `--diagnostics-json <path>` — Structured error output
- `--manifest-json <path>` — What was parsed and how

These outputs tell the agent whether the VEDA tables it generated are valid.

## Schema-Based Design

VedaLang and TableIR are defined via **JSON Schema**:

- Enables agent introspection of valid constructs
- Tooling (validators, docs) derived from schemas
- Tests ensure schema ↔ implementation alignment

Cross-reference checks and semantic constraints live in code/rules, not just schema.

## Decision Heuristics (Pattern Library)

Mapping physical/modeling concepts to VEDA patterns:

```yaml
# rules/patterns.yaml
patterns:
  add_power_plant:
    description: "Thermal generation process"
    veda_templates:
      - type: process
        technology_type: "thermal"
        default_efficiency: 0.55
        # expands into ~FI_PROCESS + ~FI_T
  
  co2_price_trajectory:
    veda_templates:
      - type: scenario_parameter
        tag: "~TFM_INS-TS"
        commodity: "CO2"
```

The agent discovers and refines these heuristics through experimentation.

## Guardrails

- **xl2times is single source of truth** — any discrepancy is a bug
- **Test-driven expansion** — no new tag/pattern without passing test
- **Schema-first changes** — update schema → docs → tests → code
- **Heuristic discipline** — every pattern must link to a fixture example

## Notes for AI Agents

- Excel is OUTPUT, not source — never edit Excel directly
- Always validate through `vedalang validate` after generating tables
- VedaLang schema is evolving — propose improvements via schema changes
- Decision heuristics are learned, not hardcoded
- TableIR is your experimentation layer before committing to VedaLang syntax
- The active design target is the package/run/CSIR/CPIR surface; avoid adding
  public features outside that object model unless they are required backend
  plumbing for emitted artifacts

---

## Agent Design Workflow

The agent iteratively designs VedaLang through a structured feedback loop:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Prototype at TableIR                                     │
│     - Write raw YAML tables (files/sheets/tables structure) │
│     - Low friction experimentation                          │
├─────────────────────────────────────────────────────────────┤
│  2. Emit Excel                                               │
│     - vedalang-dev emit-excel tables.yaml --out test.xlsx   │
├─────────────────────────────────────────────────────────────┤
│  3. Validate with xl2times                                   │
│     - xl2times test.xlsx --diagnostics-json diag.json       │
│     - xl2times is the ORACLE - its verdict is final         │
├─────────────────────────────────────────────────────────────┤
│  4. Fix or Lift                                              │
│     - If errors: adjust TableIR, repeat from step 2         │
│     - If valid: lift pattern to VedaLang syntax             │
└─────────────────────────────────────────────────────────────┘
```

**Preferred workflow:** Use `vedalang validate` for compile + oracle validation, and `vita run` for execution/analyze:
```bash
# Validate VedaLang source end-to-end (lint + compile + xl2times; no solver)
uv run vedalang validate vedalang/examples/quickstart/mini_plant.veda.yaml

# Check TableIR directly
uv run vedalang-dev check tables.yaml --from-tableir --json

# Run the full pipeline through the solver
uv run vita run model.veda.yaml --run <run_id> --json
```

---

## Design Status

### Historical Completed Phases

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| **P0** | Validate Toolchain | Tools work, feedback loop closes | ✅ DONE |
| **P1** | TableIR Experimentation | Learn valid VEDA patterns via trial | ✅ DONE |
| **P2** | Primitives Exploration | All energy system primitives | ✅ DONE |
| **P3** | MiniSystem Stress Test | Real model validation | ✅ DONE |

### Landed Public DSL

The `vedalang-txa` rollout tree is complete. The hard-cut public DSL reset is
now the baseline design surface rather than an active migration.

| Landed Epic | Result |
|-------------|--------|
| `vedalang-txa.1` | Governance, versioning, and unsupported-syntax diagnostics |
| `vedalang-txa.3` | Public schema and AST reset |
| `vedalang-txa.4` | Resolution: imports, runs, spatial/stock/site logic |
| `vedalang-txa.5` | Canonical artifacts: CSIR, CPIR, explain.json |
| `vedalang-txa.6` | Backend parity through Excel/xl2times/TIMES |
| `vedalang-txa.7` | Diagnostics, tooling, docs, and regression coverage |

### Longer-Term Backlog

The older P4 ideas still exist as secondary backlog after the reset:
- `vedalang-6qs` — Time-varying process attributes
- `vedalang-9xy` — Scenario composition
- `vedalang-a9m` — Units and dimension checking

### P0: Validate Toolchain (DONE)
- ✅ `vedalang compile` works
- ✅ `vedalang-dev emit-excel` emits valid Excel
- ✅ `vedalang validate` performs compile + oracle validation
- ✅ xl2times emits structured diagnostics (not crashes)
- ✅ `quickstart/mini_plant.veda.yaml` passes VedaLang compilation

### P1: TableIR Experimentation (DONE)
- ✅ DC1-DC5 design challenges complete
- ✅ Golden fixture regression tests
- ✅ Schema evolution policy
- ✅ Failure tracking infrastructure

### P2: Primitives Exploration (DONE)
All 10 energy system primitives explored and schema extensions implemented:
- ✅ Thermal/renewable generation, CHP, storage, transmission (patterns)
- ✅ Demand projections, costs, bounds, timeslices, trade, user constraints (schema)

### P3: MiniSystem Stress Test (DONE)
- ✅ MiniSystem model specification designed
- ✅ MiniSystem implemented in VedaLang
- ✅ Golden CI test wired and passing

---

## Design Challenges

Incremental challenges to validate VedaLang expressiveness:

| ID | Challenge | Concepts Tested |
|----|-----------|-----------------|
| **DC1** | Reproduce mini thermal plant via patterns | Basic process, commodity, topology |
| **DC2** | Add renewable plant sharing output commodity | Multiple processes, shared commodities |
| **DC3** | Introduce emission commodity and emission factor | Emission tracking, ENV_ACT |
| **DC4** | Add CO2 price trajectory scenario | TFM tags, time-varying parameters |
| **DC5** | Two-region model extension | Multi-region, trade, IRE processes |

### Challenge Protocol

For each challenge:
1. **Describe intent** in natural language
2. **Prototype** in TableIR
3. **Validate** with xl2times
4. **Capture pattern** if successful
5. **Lift to VedaLang** syntax if pattern is general

---

## Failure Handling

Every failure is a learning opportunity. Failures are categorized and preserved.

### Failure Types

| Type | Description | Action |
|------|-------------|--------|
| **A** | Wrong VEDA structure | Fix TableIR, re-validate |
| **B** | VedaLang can't express valid pattern | Extend VedaLang schema |
| **C** | Compiler bug | Fix compiler, add regression test |

### Failure-to-Test Workflow

1. Reproduce failure with minimal input
2. Capture as an inline test case in the relevant test file
3. Write test that:
   - For Type A: expects xl2times error diagnostic
   - For Type B: documents the gap (skip with reason)
   - For Type C: expects correct behavior after fix

### Heuristics-Catchable Issues

When debugging reveals a **modeling pattern that causes infeasibility** (or other solver failures), create a `bd` issue to track adding a pre-compilation heuristic check:

```bash
# Create issue for new heuristic
bd create "H0XX: <descriptive name>" --label heuristics

# Include in description:
# 1. The modeling pattern that causes the problem
# 2. Why it causes infeasibility/errors
# 3. What the heuristic should check
# 4. Example from the model where it was discovered
```

**Current heuristics** (in `vedalang/heuristics/linter.py`):

| Code | Name | What it catches |
|------|------|-----------------|
| H001 | FixedNewCapShortLife | Fixed ncap_bound with lifetime < horizon |
| H002 | DemandDeviceNoStock | Demand devices without stock/capacity |
| H003 | BaseYearCapacityAdequacy | Insufficient base year capacity for demand |
| H004 | StockCoversAllDemand | Stock can satisfy nearly all projected demand |

**When to add a new heuristic:**
- Pattern reliably causes solver infeasibility
- Can be detected from VedaLang AST (before Excel/DD generation)
- Provides actionable guidance to fix the issue

**Implementation:**
1. Add rule class in `vedalang/heuristics/linter.py`
2. Register in `ALL_RULES` list
3. Add test in `tests/test_heuristics.py`
4. Close the tracking issue

---

## Guardrails

### Golden Fixtures

- `fixtures/MiniVEDA2/` is the regression reference
- Any change that breaks fixture validation is a bug
- Run `uv run pytest tests/` after any changes

### Breaking Changes Policy

VedaLang is a **new project under active development**. We prioritize getting the design right over maintaining backward compatibility.

Current status: this is still a prototype. Do not preserve backward compatibility when it conflicts with cleaner design.

- **Breaking changes are acceptable** — schema, compiler, APIs may all change
- **No deprecation cycles required** — remove or rename freely when it improves the design
- **Focus on correctness** — better to fix a design flaw now than carry it forward
- **Examples and fixtures are updated in-place** — when schema changes, update all examples
- **Do not keep migration guides by default** — transitional compatibility docs create agent/dev confusion and should be removed unless explicitly needed for an external release handoff
- **Do not carry backward-compat shims** — remove compatibility aliases and transitional pathways once the new design lands
- **Record decisions in `HISTORY.md`** — concise dated rationale entries plus git history are sufficient for traceability during prototype phase

This policy applies until VedaLang reaches a stable 1.0 release.

### Schema Evolution

See [docs/vedalang-design-agent/schema_evolution.md](docs/vedalang-design-agent/schema_evolution.md) for details.

**Quick rules:**
- **Add** fields freely (optional or required)
- **Remove** fields that are wrong or unnecessary
- **Rename** for clarity when it improves the API
- Run `uv run pytest tests/` after schema changes

### Pattern Library

- Patterns in `rules/patterns.yaml` document known-good VedaLang idioms
- Update patterns when schema changes — no versioning needed during development

### Validation Gates

```bash
# Run before starting work (session-start guardrail)
uv run python tools/sync_conventions.py --check

# Run before committing
bun run format:veda:check
uv run pytest tests/
uv run ruff check .

# Full validation (compile + xl2times; no solver)
uv run vedalang validate vedalang/examples/quickstart/mini_plant.veda.yaml

# Run full pipeline (VedaLang → Excel → DD → TIMES)
uv run vita run model.veda.yaml --run <run_id> --json
```

---

## Diagnostic Codes Reference

xl2times emits structured diagnostics. Use `--diagnostics-json` and inspect the
machine-readable output directly during design work.

### Quick Reference

| Code | Severity | Description |
|------|----------|-------------|
| `MISSING_REQUIRED_TABLE` | error | Required VEDA table not present |
| `MISSING_REQUIRED_COLUMN` | error | Required column missing from table |
| `INVALID_SCALAR_TABLE` | error | Table expected one value, got wrong shape |
| `MISSING_TIMESLICES` | warning | No timeslice definitions found |
| `INTERNAL_ERROR` | error | Uncaught exception during processing |

### Reading Diagnostics

```bash
# Generate diagnostics
uv run xl2times model.xlsx --diagnostics-json diag.json

# Key fields in output
cat diag.json | jq '.diagnostics[] | {code, severity, message}'
```

---

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Bump versions before commit** - Increment shipped version markers BEFORE
   creating the git commit that will be pushed. Do not wait until after commit
   or after push.
   Required markers:
   `pyproject.toml`
   `vita/version.py`
   `vedalang/version.py`
   Update any related tests/docs that assert version strings.
   Version policy:
   Bump the shipped release number on every push.
   Use a final-segment increment for each push (for example `0.4.0 -> 0.4.1`).
   `vita` and `vedalang` have distinct CLI version markers, but they are not
   independent release trains:
   any shipped change to `vedalang` MUST bump both `vedalang` and `vita`
   version markers.
   a shipped `vita`-only change MUST bump `vita`; keep `vedalang` aligned with
   the shared shipped release markers unless there is an explicit repo decision
   to split them.
3. **Run quality gates** (if code changed) - Tests, linters, builds
4. **Commit all completed work** - Stage and commit all intended changes before handoff
5. **Update issue status** - Close finished work, update in-progress items
6. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git add -A
   git commit -m "<clear summary>"
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
7. **Clean up** - Clear stashes, prune remote branches
8. **Verify** - All changes committed AND pushed
9. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until all intended changes are committed
- Work is NOT complete until `git push` succeeds
- Do NOT push shipped code without incrementing the repo/tool version markers
- Do NOT bump versions after committing; the pushed commit itself must contain
  the new version markers
- Any `vedalang` change that ships requires a `vita` version bump as well
- NEVER leave finished work only in the working tree
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready --json` - Find unblocked work
- `bd create "Title" --type task --priority 2 --json` - Create issue
- `bd update <id> --status in_progress --json` - Claim work
- `bd close <id> --reason "Completed" --json` - Complete work
- `bd dolt push` - Push beads to remote

Project note: prefer `--json` for agent workflows.

For full workflow details: `bd prime`

<!-- END BEADS INTEGRATION -->
