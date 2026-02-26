# VedaLang Project Status

**Last updated:** 2026-02-25

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. **All core phases (P0–P3) are complete.** The project has a mature toolchain, comprehensive test suite, and a progressive fixture series (minisystem1–8) validating end-to-end correctness.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ 755 tests passing, 11 skipped |
| Primitives Exploration | ✅ Complete |
| Schema Extensions | ✅ All implemented |
| MiniSystem Stress Test | ✅ Complete |
| Naming Conventions | ✅ Complete |
| RES Visualization | ✅ Complete |
| LSP / VSCode Plugin | ✅ Complete |
| Emissions Refactor | ✅ Complete |
| Progressive Fixtures (ms1-8) | ✅ All passing |

---

## Current Status: Maintenance & Extension

**210 issues closed.** All core design phases complete.

### Active Work

**Hygiene audit** (`vedalang-qv4`) — repository cleanup and documentation sync:

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-qv4` | P2 | Repository hygiene audit — 2026-02 | ○ Open (epic) |
| `vedalang-qv4.1` | P1 | Sync STATUS.md with reality | ✓ Closed |
| `vedalang-qv4.2` | P1 | Update AGENTS.md phase status and fix stale paths | ○ Open |
| `vedalang-qv4.3` | P2 | Fix 99 ruff lint errors | ○ Open |
| `vedalang-qv4.4` | P2 | Delete stale experiments/ directory | ○ Open |
| `vedalang-qv4.5` | P3 | Clean stale build artifacts in output/, output_invalid/, tmp/ | ○ Open |
| `vedalang-qv4.6` | P3 | Remove orphan one-off scripts | ○ Open |
| `vedalang-qv4.7` | P3 | Review stale test artifacts | ○ Open |

**Toy model structural refactor** (`vedalang-0pt`) — PRD-driven three-layer convention framework: ✅ **Complete**

All 13 subtasks closed. Deliverables:
- Compiler hard enforcement: stage enum, commodity typing, primary-output, fuel-pathway duplication, physical-only end_use
- Lint layer: RES JSON/Mermaid export, optional LLM structural assessment
- Modeling conventions SKILL.md
- All toy_* examples refactored (buildings, industry, transport, resources, electricity, agriculture)
- Cases overlay system for multi-case models
- A1-A8 acceptance test matrix (`tests/test_prd_acceptance.py`)

**Sector toy problems** (`vedalang-248`) — DSL syntax exploration via sector-specific models:

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-248` | P2 | Sector toy problem examples (epic) | ○ Open |
| `vedalang-248.1` | P2 | Toy 1: Electricity & Energy | ○ Open |
| `vedalang-248.2` | P2 | Toy 2: Transport — EV uptake | ○ Open |
| `vedalang-248.3` | P2 | Toy 3: Built Environment — heat pumps | ○ Open |
| `vedalang-248.4` | P2 | Toy 4: Industry — industrial heat decarb | ○ Open |
| `vedalang-248.5` | P2 | Toy 5: Resources — mining electrification | ○ Open |
| `vedalang-248.6` | P2 | Toy 6: Agriculture & Land — methane abatement | ○ Open |

**Other open issues:**

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-iil` | P2 | xl2times: Add --force-veda flag | ○ Open |

**Units & dimensions** (`vedalang-a9m`) — deterministic unit safety implementation:

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-a9m` | P3 | Units and dimension checking system (epic) | ○ Open |
| `vedalang-a9m.1` | P2 | Strict unit policy and enums in schema | ✓ Closed |
| `vedalang-a9m.2` | P2 | Deterministic unit registry + canonical conversion validation | ✓ Closed |
| `vedalang-a9m.3` | P2 | Coefficient magnitude checks with process anchors | ✓ Closed |
| `vedalang-a9m.4` | P2 | Detect and forbid fake unit-transformation processes | ✓ Closed |
| `vedalang-a9m.5` | P3 | LLM unit/coefficient certification workflow | ✓ Closed |

### Future Work (P4)

| Issue | Description |
|-------|-------------|
| `vedalang-jis` | Storage and flexibility primitives |
| `vedalang-9xy` | Scenario composition and variants |
| `vedalang-a9m` | Units and dimension checking system |

---

## Completed Phases

### Phase 0: Toolchain Validation ✅
- `vedalang compile` works
- `vedalang-dev emit-excel` emits valid Excel
- `vedalang validate` orchestrates pipeline
- xl2times emits structured diagnostics (hardened — graceful failures, never crashes)

### Phase 1: TableIR Experimentation ✅
- Design challenges DC1-DC5 complete
- Golden fixture regression tests
- Schema evolution policy
- Failure tracking infrastructure
- TableIR schema + roundtrip validation

### Phase 2: Primitives Exploration ✅

All 10 energy system primitives explored and implemented:

| Primitive | Outcome | Implementation |
|-----------|---------|----------------|
| Thermal generation | Pattern | DC1, DC2 |
| Renewable generation | Pattern | DC2 |
| Emissions & pricing | Pattern | DC3, DC4 |
| CHP | Pattern | Multi-output works |
| Storage | Pattern | Same-commodity I/O |
| Transmission | Pattern | Voltage-level commodities |
| Demand trajectories | Schema extension | `demand_projection` |
| Fuel supply / Costs | Schema extension | `invcost`, `fixom`, `varom`, `life`, `cost` |
| Capacity bounds | Schema extension | `activity_bound`, `cap_bound`, `ncap_bound` |
| Timeslices | Schema extension | `timeslices` section |
| Trade | Schema extension | `trade_links` array |
| User constraints | Schema extension | `emission_cap`, `activity_share` |

### Phase 3: MiniSystem Stress Test ✅

- MiniSystem specification designed and implemented
- Progressive fixture series (minisystem1–8) all passing
- Time-varying process attributes
- Ergonomic improvements (shorthand syntax, defaults)
- VedaOnline/Veda2 directory compatibility
- Opinionated naming conventions (process templates, abbreviation registry)
- Emissions refactored to role-output pattern
- Curated attribute/tag registry with compile-time validation
- GAMS/TIMES solver integration and results interpretation
- RES visualization (Cytoscape.js + WebSocket live reload)
- Language Server Protocol (LSP) with TIMES attribute docs
- Heuristic linter (H001–H004)
- LLMS.txt for AI agent guidance
- CLI overhaul (vedalang + vedalang-dev)

---

## VedaLang Capabilities

### What VedaLang Can Express

| Concept | Schema Support |
|---------|----------------|
| Single/multi-region models | ✅ |
| Energy/emission/demand commodities | ✅ |
| Thermal & renewable plants | ✅ |
| CHP (multi-output) | ✅ |
| Storage (same-commodity I/O) | ✅ |
| Transmission (voltage levels) | ✅ |
| Process efficiency | ✅ |
| Process costs | ✅ |
| Capacity/activity bounds | ✅ |
| Emission factors (role-output pattern) | ✅ |
| CO2 price scenarios | ✅ |
| Demand projections | ✅ |
| Timeslices | ✅ |
| Inter-regional trade | ✅ |
| User constraints | ✅ |
| Trade link efficiency (IRE_FLO) | ✅ |
| Time-varying process attributes | ✅ |
| Shorthand input/output syntax | ✅ |
| Default commodity units | ✅ |
| Process templates & instances | ✅ |
| Opinionated naming conventions | ✅ |
| Explicit milestone years | ✅ |
| Existing stock vs facility capacity | ✅ |
| PRC_CAPACT (unit conversion) | ✅ |
| Strict unit policy (`model.unit_policy`) | ✅ |
| Coefficient anchor magnitude checks (`coefficient`) | ✅ |
| Advisory LLM unit certification (`llm-lint --category units`) | ✅ |
| Primary commodity group (explicit + inferred) | ✅ |

### Not Yet Implemented

| Concept | Issue | Priority |
|---------|-------|----------|
| Storage primitives (enhanced) | `vedalang-jis` | P4 |
| Scenario composition | `vedalang-9xy` | P4 |
| Units/dimension checking (advanced) | `vedalang-a9m` | P4 |
| Vintage/age tracking | — | Future |
| Growth rate constraints | — | Future |

---

## Commands Reference

```bash
# Validate a VedaLang model (lint + compile + xl2times)
uv run vedalang validate model.veda.yaml --json

# Lint for heuristic issues only
uv run vedalang lint model.veda.yaml --json

# Compile to TableIR only
uv run vedalang compile model.veda.yaml --tableir output.yaml

# Emit Excel from TableIR (design agent)
uv run vedalang-dev emit-excel tableir.yaml --out output_dir/

# Visualize model RES
uv run vedalang viz model.veda.yaml

# Run all tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .

# Check issue status
bd list --all | grep " open "
```

---

## Keeping This Document Updated

**This document should be updated when:**
1. Issues are closed → move from "Open" to completed section
2. New issues are created → add to appropriate section
3. Phase transitions occur → update "Current Phase"

**Quick sync command:**
```bash
# Show current open issues
bd list --all | grep " open "

# Count closed issues
bd list --all | grep "^✓" | wc -l
```

---

## Repository Structure

```
vedalang/
├── AGENTS.md                 # Agent instructions
├── docs/
│   ├── project-status/
│   │   └── STATUS.md         # This file (living status)
│   ├── vedalang-user/        # User documentation
│   └── vedalang-design-agent/# Design agent docs
├── vedalang/
│   ├── schema/               # JSON Schema (complete)
│   ├── compiler/             # Compiler (complete)
│   ├── heuristics/           # Heuristic linter (H001-H004)
│   └── examples/             # minisystem1-8 + other examples
├── tools/
│   ├── veda_dev/             # Design agent CLI
│   ├── veda_emit_excel/      # TableIR → Excel emitter
│   ├── veda_check/           # Model validation
│   ├── veda_run_times/       # TIMES solver runner
│   └── vedalang_lsp/         # Language server
├── rules/                    # Pattern library
├── tests/                    # 755 tests
├── fixtures/                 # MiniVEDA2 + golden fixtures
└── xl2times/                 # Validation oracle (third-party)
```
