Use 'bd' for task tracking

---

# Two Distinct Personas

This repository serves **two distinct AI personas** — understanding this distinction is critical:

| Persona | Purpose | Documentation |
|---------|---------|---------------|
| **VedaLang User Agent** | Uses VedaLang to author energy system models | `docs/vedalang-user/` and `docs/vedalang-user/LLMS.md` |
| **VedaLang Design Agent** | Designs and evolves the VedaLang DSL itself | This file (`AGENTS.md`) and `docs/vedalang-design-agent/` |

## VedaLang User Agent

An AI agent that **uses VedaLang** to create `.veda.yaml` models for energy system analysis. This agent:
- Reads the VedaLang schema and examples
- Writes valid VedaLang source files
- Uses `vedalang lint` and `vedalang validate` to check models
- Does NOT modify the language, compiler, or schema

**User agent documentation:**
- `docs/LLM_DOCS.md` — LLM-facing documentation map (purpose + ownership)
- `docs/vedalang-user/` — User documentation index
- `docs/vedalang-user/LLMS.md` — LLM guide for authoring VedaLang
- `vedalang/schema/vedalang.schema.json` — Language schema
- `vedalang/examples/` — Example models
- `rules/patterns.yaml` — Pattern "standard library"

## VedaLang Design Agent

An AI agent that **designs and evolves VedaLang** — the DSL, compiler, schemas, and tooling. This agent:
- Extends the VedaLang schema with new constructs
- Improves the compiler and emitters
- Discovers new VEDA patterns through experimentation
- Validates changes against xl2times (the oracle)

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
- **All changes MUST be documented in [XL2TIMES_CHANGES.md](XL2TIMES_CHANGES.md)** with date, commit, description, and reason

# VEDA DevTools - Agent Instructions

## Project Vision

Build a **safer, typed DSL** that compiles to VEDA tables — analogous to how TypeScript compiles to JavaScript. The new language (working name: **VedaLang**) provides:

- Type safety (units, symbols, constraints)
- Schema validation  
- Cross-reference checking
- Clear error messages

VEDA Excel tables become a **compiled artifact**, not the source. xl2times validates the compiled output.

## Terminology

VedaLang uses precise terminology to avoid ambiguity in the VEDA ecosystem:

| Term | Definition |
|------|------------|
| **Scenario Parameter** | An atomic time-series or value assumption (e.g., CO2 price path, demand projection) |
| **Category** | Logical grouping of scenario parameters (canonical enum below) |
| **Case** | A named combination of scenario parameters for a specific model run (e.g., `baseline`, `ambitious`) |
| **Study** | A collection of cases for comparison |

<!-- GENERATED:scenario-categories:start -->
**Canonical scenario categories:** `demands` | `prices` | `policies` | `technology_assumptions` | `resource_availability` | `global_settings`
<!-- GENERATED:scenario-categories:end -->

**Key distinctions:**
- **Model architecture** (VT_* files): processes, commodities, topology — the Reference Energy System
- **Scenario instantiation** (Scen_{case}_{category}.xlsx): demands, prices, policies that instantiate the RES

**File naming convention:** `Scen_{case}_{category}.xlsx`
- Example: `Scen_baseline_demands.xlsx`, `Scen_ambitious_policies.xlsx`

This terminology maps to VEDA concepts:
- "Scenario file" (Scen_*.xlsx) → contains scenario parameters grouped by case and category
- "High-level scenario" → **case** (a specific combination of scenario parameters)
- "Study" → collection of cases for comparison

## Architecture Overview

```
VedaLang Source (.veda.yaml)
    │
    │  (1) Parse + schema-validate
    ▼
VedaLang AST  ──►  TableIR (in-memory)
    │                  │
    │  (2) Type check  │  (3) Deterministic Excel emission
    ▼                  ▼
Typed VedaLang    VEDA Excel (.xlsx)
                      │
                      │  (4) xl2times --diagnostics-json
                      ▼
               TIMES DD files + Diagnostics
                      │
                      │  (5) vedalang-dev run-times
                      ▼
               GAMS/TIMES Solution (.gdx)
```

**Key insight**: VedaLang is the source; Excel is compiled output; xl2times validates; GAMS solves.

## Toolchain Build Order

Tools needed for an agent to **design VedaLang itself**:

| Order | Tool | Purpose |
|-------|------|---------|
| **T1** | `xl2times` + JSON outputs | Validation oracle — "Is this valid VEDA?" |
| **T2** | `vedalang-dev emit-excel` | TableIR → Excel emitter (test VEDA patterns) |
| **T3** | `vedalang` compiler | VedaLang → TableIR → Excel |
| **T4** | `vedalang validate` | Orchestration wrapper with unified diagnostics |
| **T5** | `vedalang-dev run-times` | Run DD files through GAMS/TIMES solver |

## Key Principle: Agent-Designed Language

The goal is for an **AI agent to iteratively design VedaLang** using feedback tools:

1. **xl2times validation** — "Did I produce valid VEDA tables?"
2. **vedalang validate** — Unified lint + compile + validate feedback
3. **Decision heuristics** — Mapping physical concepts → VEDA table patterns

We are NOT porting legacy models. This is for new model development.

## Two Separate Concerns

### 1. Language Mechanics (VedaLang)
- Syntax, types, allowed constructs
- Schema-defined (JSON Schema)
- Compiler lowers to TableIR → Excel

### 2. Modeling Decisions (Heuristics)
- "Given intent X, which tags/files/fields do I use?"
- Data-driven pattern library (`rules/patterns.yaml`)
- Agent discovers these through experimentation

**These are kept separate.** VedaLang is a general-purpose VEDA authoring language; heuristics are the "standard library" of patterns.

## Design Principle: Commodity Namespaces and Emissions-as-Attributes

**Commodity namespaces** map human-readable prefixes to VEDA Csets:
- `energy:` → NRG, `material:` → MAT, `service:` → DEM, `emission:` → ENV, `money:` → FIN

**Emissions are ledger entries, not flows.** `emission:*` commodities MUST NOT appear in process `inputs` or `outputs`. They enter the model only via `emission_factors`:

```yaml
process_variants:
  - id: gas_heater
    inputs:
      - commodity: energy:natural_gas
    outputs:
      - commodity: service:space_heat
    emission_factors:
      emission:co2: 0.056  # ledger entry, not a flow
```

Negative emission factors are valid for DAC/LULUCF. Physical CO2 streams use `material:co2`.

**Lint rules:** L1 (emission:* not in I/O), L2 (emission_factors keys must be emission:*), L3 (negative EF allowed), L5 (bare co2 warns).

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
│   ├── cli.py                   # User CLI (vedalang lint/compile/validate)
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
│   ├── veda_run_times/          # TIMES solver runner
│   └── vedalang_lsp/            # Language server protocol
├── rules/
│   ├── patterns.yaml            # Concept → VedaLang templates
│   ├── decision_tree.yaml       # Intent routing
│   └── constraints.yaml         # Valid tag/file combinations
├── fixtures/
│   └── MiniVEDA2/               # Minimal test model
└── tests/
```

## CLI Tools

The Design Agent has access to the following CLI tools:

### Primary Tool: `vedalang-dev` (Design Agent Hub)

The unified CLI for VedaLang design iteration. Use this for most workflows.

```bash
# Full pipeline: VedaLang → TableIR → Excel → DD (preferred workflow)
vedalang-dev pipeline model.veda.yaml --no-solver --json

# Full pipeline with TIMES solver
vedalang-dev pipeline model.veda.yaml --times-src ~/TIMES_model --case base --json

# Validate VedaLang source
vedalang-dev check model.veda.yaml --json

# Emit Excel from TableIR (for pattern experimentation)
vedalang-dev emit-excel tables.yaml --out output/

# Run TIMES solver on DD files
vedalang-dev run-times dd_dir/ --times-src ~/TIMES_model --json

# Pattern library utilities
vedalang-dev pattern list --json
vedalang-dev pattern show thermal_plant --json
```

**Key flags:**
- `--json` — Machine-readable output for agent consumption
- `--no-solver` — Stop before TIMES (useful when GAMS unavailable)
- `--keep-workdir` — Preserve temp files for debugging
- `-v` — Verbose output

### Standalone Tools

These remain available for users and external tooling:

| Tool | Purpose |
|------|---------|
| `vedalang compile` | VedaLang → TableIR/Excel compiler |
| `xl2times` | Excel → DD files (validation oracle) |

```bash
# Compile VedaLang to Excel
vedalang compile src/ --out model.xlsx

# Validate Excel through xl2times
xl2times model.xlsx --case base --diagnostics-json diag.json
```

### VedaLang LSP Extension (Cursor/VS Code)

The LSP has two parts: a **Python server** (`tools/vedalang_lsp/server/`) and a **TypeScript extension** (`tools/vedalang_lsp/extension/`). The Mermaid RES diagram is rendered server-side in Python — the extension just displays it.

**Rebuilding after TypeScript changes:**

```bash
# 1. Compile TypeScript
cd tools/vedalang_lsp/extension && npm run compile

# 2. Copy compiled JS to the installed extension (Cursor)
cp tools/vedalang_lsp/extension/out/*.js ~/.cursor/extensions/austimes.vedalang-0.1.0/out/

# 3. Reload window: Cmd+Shift+P → "Developer: Reload Window"
```

**Important:** Cursor loads the extension from `~/.cursor/extensions/austimes.vedalang-0.1.0/`, NOT from the repo's `out/` directory. After `npm run compile`, you MUST copy the built JS files to the installed extension path. For VS Code, the equivalent path is `~/.vscode/extensions/`.

Python server changes (e.g., `tools/vedalang_lsp/server/server.py`) take effect on window reload without any build step.

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

**Preferred workflow:** Use `vedalang validate` for the full pipeline:
```bash
# Validate VedaLang source end-to-end
uv run vedalang validate vedalang/examples/mini_plant.veda.yaml

# Validate TableIR directly
uv run vedalang-dev validate-tableir tables.yaml
```

---

## Design Phases

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| **P0** | Validate Toolchain | Tools work, feedback loop closes | ✅ DONE |
| **P1** | TableIR Experimentation | Learn valid VEDA patterns via trial | ✅ DONE |
| **P2** | Primitives Exploration | All energy system primitives | ✅ DONE |
| **P3** | MiniSystem Stress Test | Real model validation | ✅ DONE |
| **P4** | Advanced Features | Time-series, scenario composition | PLANNED |

### P0: Validate Toolchain (DONE)
- ✅ `vedalang compile` works
- ✅ `vedalang-dev emit-excel` emits valid Excel
- ✅ `vedalang validate` orchestrates pipeline
- ✅ xl2times emits structured diagnostics (not crashes)
- ✅ `mini_plant.veda.yaml` passes VedaLang compilation

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

### P4: Advanced Features (PLANNED)
- `vedalang-6qs` — Time-varying process attributes
- `vedalang-9xy` — Scenario composition
- `vedalang-a9m` — Units and dimension checking

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
# Run before committing
uv run pytest tests/
uv run ruff check .

# Full validation
uv run vedalang validate vedalang/examples/mini_plant.veda.yaml
```

---

## Diagnostic Codes Reference

xl2times emits structured diagnostics. See [docs/vedalang-design-agent/baseline_diagnostics.md](docs/vedalang-design-agent/baseline_diagnostics.md) for details.

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

## Keeping STATUS.md Updated

The living status document is [`docs/project-status/STATUS.md`](docs/project-status/STATUS.md). Keep it in sync with `bd` issues.

### When to Update STATUS.md

- **At session start** — Run sync script to check current state
- **When closing issues** — Move from "Open Tasks" to completed section
- **When creating issues** — Add to appropriate section
- **On phase transitions** — Update "Current Phase" section

### Quick Sync Commands

```bash
# Generate status summary from bd issues
uv run python tools/sync_status.py

# Show current open issues
bd list --all | grep " open "

# Count closed issues  
bd list --all | grep " closed " | wc -l
```

### What to Update

1. **Open Tasks table** — Must match `bd list --all | grep " open "`
2. **Closed count** — Update "X issues closed" number
3. **Current Phase** — Update when epic completes
4. **Capabilities table** — Add new features as implemented

---

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Update STATUS.md** - Sync with current bd issue state
5. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
6. **Clean up** - Clear stashes, prune remote branches
7. **Verify** - All changes committed AND pushed
8. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
