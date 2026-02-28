# VedaLang Project Status

**Last updated:** 2026-03-01

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. **All core phases (P0–P3) are complete.** The project has a mature toolchain, comprehensive test suite, and a progressive fixture series (minisystem1–8) validating end-to-end correctness.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ 990 tests passing, 18 skipped |
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

All core design phases remain complete.

### Active Work

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-1gf` | P2 | Phase 2: full deterministic parity with llm unit taxonomy | Open |
| `vedalang-2kz` | P2 | Update LSP schema docs/examples to canonical namespace conventions | Open |
| `vedalang-4k8` | P2 | Migrate remaining C/S/E runtime helpers to canonical commodity namespaces | Open |

### Recently Completed

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-1wk` | P2 | Route negative-emission unit guidance through deterministic `units` lint category | ✓ Closed |
| `vedalang-a19` | P1 | Deterministic lint unit-cost denominator checks, all-category default lint, and legacy-syntax guard | ✓ Closed |
| `vedalang-6hy` | P1 | Fix N001 to use `id`-backed diagnostic paths (line mapping works on new syntax examples) | ✓ Closed |
| `vedalang-4wy` | P1 | Add lint line/column + source excerpt diagnostics in CLI output | ✓ Closed |
| `vedalang-dlt` | P2 | Set llm-lint default target + add eval-evolution skill | ✓ Closed |
| `vedalang-i9e` | P2 | Ground-truth llm-lint eval corpus + difficulty ladder | ✓ Closed |
| `vedalang-7dk` | P2 | Eval reorder (effort/case/model) + judge cache reuse | ✓ Closed |
| `vedalang-9zg` | P2 | Parallel execution for eval runner | ✓ Closed |
| `vedalang-3t3` | P2 | bd/Dolt metadata migration chore | ✓ Closed |

### Future Work (P4+)

| Issue | Description |
|-------|-------------|
| `vedalang-1gf` | Full deterministic parity with llm unit-check taxonomy |
| `vedalang-2kz` | LSP schema docs/examples canonical namespace migration |
| `vedalang-4k8` | Runtime helper migration to canonical commodity namespaces |

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
| Deterministic parity with llm unit taxonomy | `vedalang-1gf` | P2 |
| Canonical LSP docs/examples | `vedalang-2kz` | P2 |
| Canonical runtime helper migration | `vedalang-4k8` | P2 |
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
