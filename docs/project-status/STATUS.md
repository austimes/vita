# VedaLang Project Status

**Last updated:** 2026-03-06

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. **All core phases (P0–P3) are complete.** The core abstraction v2 rollout is now landed (role/variant/mode type axis + provider object axis + scope-only commodity axis), and current focus is maintenance/extension follow-up.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ 1033 tests passing, 38 skipped |
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

Core design phases remain complete. Active work is concentrated on post-rollout cleanup and extension.

### Active Work

No open `bd` issues at this time.

### Recently Completed

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-rm5` | P2 | Trade lens now emits `NO_TRADE_LINKS` diagnostic for empty trade graph without links | ✓ Closed |
| `vedalang-1gf` | P2 | Component-scoped deterministic unit parity + deterministic→taxonomy mapping + richer parity scoring | ✓ Closed |
| `vedalang-2kz` | P2 | LSP schema docs/examples migrated to canonical namespaces and commodity.type wording | ✓ Closed |
| `vedalang-4k8` | P2 | Runtime helpers migrated off legacy C/S/E semantics (registry emitter + graph builder + tests) | ✓ Closed |
| `vedalang-cgl` | P1 | Core abstraction v2 epic completed across schema/compiler/viz/tests/docs | ✓ Closed |
| `vedalang-hh4` | P1 | Schema v2 provider model + provider-aware case override contract | ✓ Closed |
| `vedalang-3gm` | P1 | Compiler provider-native instance expansion + mixed source merge path | ✓ Closed |
| `vedalang-ezz` | P1 | Canonical provider-token process naming + parseable metadata | ✓ Closed |
| `vedalang-4y6` | P1 | Facility/fleet lowering rewritten to provider-native semantics | ✓ Closed |
| `vedalang-ihm` | P1 | Provider-aware selector semantics for case overlays + conflict detection | ✓ Closed |
| `vedalang-dy4` | P1 | Deterministic identity checks for provider/type scope leakage | ✓ Closed |
| `vedalang-2gz` | P1 | Expanded provider regression matrix (schema/compiler/viz/tests) | ✓ Closed |
| `vedalang-22a` | P1 | Docs/examples rollout for provider-first abstraction | ✓ Closed |
| `vedalang-dmn` | P1 | RES query/viz decoupled process grouping from commodity scope collapse | ✓ Closed |
| `vedalang-8k9` | P1 | CLI/LSP/web UI parity for provider hierarchy + commodity aggregation | ✓ Closed |

### Future Work (P4+)

Planned work remains in the P4 roadmap (`vedalang-6qs`, `vedalang-9xy`, `vedalang-a9m`) rather than currently open `bd` tickets.

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
| Facility mode-based fuel switching (`UC_CAP`) | ✅ |

### Not Yet Implemented

| Concept | Issue | Priority |
|---------|-------|----------|
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

# Check VedaLang YAML formatting
bun run format:veda:check

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
├── tests/                    # 1033 tests (+ skipped)
├── fixtures/                 # MiniVEDA2 + golden fixtures
└── xl2times/                 # Validation oracle (third-party)
```
