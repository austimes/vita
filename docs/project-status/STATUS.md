# VedaLang Project Status

**Last updated:** 2026-03-07

## Executive Summary

VedaLang is a typed DSL that compiles to VEDA Excel tables for TIMES energy models. **All core phases (P0–P3) remain complete**, the v0.2 package/run/CSIR/CPIR rollout is landed end-to-end, and the full example catalog is on the v0.2 DSL. The current `bd` tracker state is 121 closed issues and 5 open issues, all concentrated in the new v0.2-only cleanup epic.

| Milestone | Status |
|-----------|--------|
| Core toolchain | ✅ Complete |
| xl2times diagnostics | ✅ Hardened |
| Design challenges (DC1-DC5) | ✅ All passing |
| Schema evolution policy | ✅ In place |
| Test coverage | ✅ Regression suites green |
| Primitives Exploration | ✅ Complete |
| Schema Extensions | ✅ All implemented |
| MiniSystem Stress Test | ✅ Complete |
| Naming Conventions | ✅ Complete |
| RES Visualization | ✅ Complete |
| LSP / VSCode Plugin | ✅ Complete |
| Emissions Refactor | ✅ Complete |
| Progressive Fixtures (ms1-8) | ✅ All passing |
| v0.2 backend parity | ✅ Complete |
| v0.2 rollout backlog | ✅ Complete |

---

## Current Status: v0.2 Cleanup Epic
Core design phases remain complete. The v0.2 frontend, diagnostics, downstream tooling surfaces, flagship examples/docs, regression matrix, and example catalog migration are all complete. The current follow-on work is a focused cleanup epic to remove the remaining runtime/tooling/docs/test compatibility surfaces that still preserve the pre-v0.2 public DSL.

### Active Work

Open `bd` work is now the cleanup epic `vedalang-y8e` and its child tasks:
- `vedalang-y8e.2` — retire provider-based facility lowering in favor of v0.2 asset lowering only
- `vedalang-y8e.5` — collapse RES query, viz, and export tooling onto the v0.2 graph stack
- `vedalang-y8e.3` — purge legacy role/variant/provider guidance from user docs and LSP schema help
- `vedalang-y8e.4` — rewrite LLM lint prompts, component selection, and eval fixtures to v0.2 semantics
- `vedalang-y8e.6` — remove legacy compatibility tests and fixtures after the runtime hard cut

### Recently Completed

| Issue | Priority | Description | Status |
|-------|----------|-------------|--------|
| `vedalang-y8e` | P1 | Opened the v0.2-only cleanup epic to remove the remaining compiler/tooling/docs/test compatibility surfaces for the pre-v0.2 DSL | Open |
| `vedalang-y8e.1` | P1 | Public CLI/runtime validation now hard-rejects legacy pre-v0.2 public DSL and no longer auto-routes through the legacy schema | ✓ Closed |
| `vedalang-bqz` | P1 | Completed the example-catalog migration epic: all 35 supported `.veda.yaml` examples now use the v0.2 DSL and remain regression-covered | ✓ Closed |
| `vedalang-3m8` | P1 | Expanded the regression matrix to cover the newly ported example families and hard-cut schema/tooling expectations | ✓ Closed |
| `vedalang-2w5` | P1 | Ported the minisystem example family to v0.2 and refreshed golden/regression coverage | ✓ Closed |
| `vedalang-xd6` | P1 | Ported the toy sector example family to v0.2 and refreshed family docs | ✓ Closed |
| `vedalang-elc` | P1 | Ported the feature demo example family to v0.2 and refreshed family docs | ✓ Closed |
| `vedalang-isn` | P1 | Ported the design challenge example family to v0.2 while preserving the DC1-DC5 teaching arc | ✓ Closed |
| `vedalang-zgk` | P1 | Ported the quickstart example family to v0.2 and added compile regression coverage for the family | ✓ Closed |
| `vedalang-mv0` | P1 | Fixed v0.2 core lint to stop applying legacy commodity-type cross-reference checks to valid v0.2 sources | ✓ Closed |
| `vedalang-txa` | P1 | Umbrella v0.2 rollout completed across schema, resolution, IR, backend, diagnostics, tooling, docs, and regressions | ✓ Closed |
| `vedalang-txa.7` | P1 | Diagnostics/tooling/docs/regression epic completed with Section 14 diagnostics, CSIR/CPIR consumers, flagship docs/examples, and Section 16 golden tests | ✓ Closed |
| `vedalang-txa.7.5` | P2 | Synced README, AGENTS, STATUS, and HISTORY to the landed v0.2 architecture | ✓ Closed |
| `vedalang-txa.7.4` | P1 | Added Section 16 worked-example regressions, byte-stability checks, and dedicated legacy rejection coverage | ✓ Closed |
| `vedalang-txa.7.3` | P1 | Rewrote flagship examples/tutorial/skills to the v0.2 DSL and compile-tested the example set in regression tests | ✓ Closed |
| `vedalang-txa.7.2` | P1 | Ported query/viz/LSP consumers to v0.2 CSIR/CPIR-era data while preserving legacy compatibility | ✓ Closed |
| `vedalang-txa.7.1` | P1 | Landed PRD Section 14 hard errors, warnings, and shared source-map diagnostics across CLI/lint/LSP | ✓ Closed |
| `vedalang-txa.6` | P1 | Backend parity completed with CPIR->TableIR lowering, run-scoped artifact emission, and xl2times-successful v0.2 fixture coverage | ✓ Closed |
| `vedalang-txa.6.3` | P1 | Added flagship v0.2 parity fixture plus xl2times regressions for opportunity/network and emission-bearing backend paths | ✓ Closed |
| `vedalang-txa.6.2` | P1 | Compile/validate and vedalang-dev pipeline now emit run-scoped CSIR/CPIR/explain artifacts alongside backend outputs | ✓ Closed |
| `vedalang-txa.6.1` | P1 | Added v0.2 backend bridge from resolved CPIR into TableIR/Excel with facility/fleet/opportunity/network coverage | ✓ Closed |
| `vedalang-txa.5` | P1 | Canonical IR tranche completed with CSIR/CPIR/explain schemas, emitters, lowering, and deterministic artifact tests | ✓ Closed |
| `vedalang-txa.5.4` | P1 | Added CSIR-to-CPIR lowering for process specs, transition edges, opportunity processes, and network arcs | ✓ Closed |
| `vedalang-txa.5.3` | P1 | Added explain artifact emission for provenance, temporal adjustment, spatial allocation, stock characterization, and lowering traces | ✓ Closed |
| `vedalang-txa.5.2` | P1 | Added deterministic CSIR emission for resolved sites, role instances, opportunities, and networks | ✓ Closed |
| `vedalang-txa.5.1` | P1 | Added dedicated CSIR/CPIR/explain schemas plus deterministic ordering tests | ✓ Closed |
| `vedalang-txa.4` | P1 | Resolution layer completed for imports, runs, site/opportunity membership, stock adjustment, and fleet allocation/stock-view derivation | ✓ Closed |
| `vedalang-txa.4.5` | P1 | Added deterministic fleet allocation plus stock_characterization-based derived stock views with regression coverage | ✓ Closed |
| `vedalang-txa.4.4` | P1 | Added base-year stock adjustment for temporal-index and annual-growth methods with item-level override precedence | ✓ Closed |
| `vedalang-txa.4.3` | P1 | Added site membership resolution, membership override validation, zone overlay resolution, and opportunity siting checks | ✓ Closed |
| `vedalang-txa.4.2` | P1 | Added run selection and deterministic model_region context resolution | ✓ Closed |
| `vedalang-txa.4.1` | P1 | Added import resolution with alias qualification, dependency closure, and cycle/conflict diagnostics | ✓ Closed |
| `vedalang-txa.3.1` | P1 | Added v0.2 schema support for commodities, technologies, technology_roles, and stock_characterizations | ✓ Closed |
| `vedalang-txa.1.2` | P1 | Added top-level `dsl_version` and emitted artifact/check/pipeline version metadata | ✓ Closed |
| `vedalang-txa.1.1` | P1 | Normalized the 2026-03-07 PRD to v0.2 wording and recorded the hard-cut policy in governance docs | ✓ Closed |
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

The longer-term P4 roadmap (`vedalang-6qs`, `vedalang-9xy`, `vedalang-a9m`) still exists, but it is now a secondary backlog after completion of the `vedalang-txa` v0.2 reset.

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
uv run vedalang validate model.veda.yaml --run <run_id> --json

# Lint for heuristic issues only
uv run vedalang lint model.veda.yaml --json

# Compile to TableIR only
uv run vedalang compile model.veda.yaml --run <run_id> --tableir output.yaml

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
├── tests/                    # Regression suites
├── fixtures/                 # MiniVEDA2 + golden fixtures
└── xl2times/                 # Validation oracle (third-party)
```
