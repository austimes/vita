# VedaLang

A typed DSL that compiles to VEDA tables for TIMES energy system models.

VedaLang provides type safety, schema validation, and clear error messages while compiling to VEDA Excel tables that can be processed by xl2times and solved with GAMS/TIMES.

```
VedaLang Source (.veda.yaml) → Compiler → VEDA Excel (.xlsx) → xl2times → TIMES DD files
```

---

## Terminology

VedaLang uses precise terminology to avoid ambiguity:

| Term | Definition |
|------|------------|
| **Scenario Parameter** | An atomic time-series or value assumption (e.g., CO2 price path, demand projection) |
| **Category** | Logical grouping of scenario parameters (canonical enum below) |
| **Case** | A named combination of scenario parameters for a specific model run (e.g., `baseline`, `ambitious`) |
| **Study** | A collection of cases for comparison |

<!-- GENERATED:scenario-categories:start -->
**Canonical scenario categories:** `demands` | `prices` | `policies` | `technology_assumptions` | `resource_availability` | `global_settings`
<!-- GENERATED:scenario-categories:end -->

**File naming convention:** `Scen_{case}_{category}.xlsx`
- Example: `Scen_baseline_demands.xlsx`, `Scen_ambitious_policies.xlsx`

This separation distinguishes between:
- **Model architecture** (VT_* files): processes, commodities, topology
- **Scenario instantiation** (Scen_* files): demands, prices, policies that instantiate the architecture

---

## Two Ways to Use This Repository

| Goal | You are a... | Start here |
|------|--------------|------------|
| **Author energy system models** using VedaLang | Model Developer | [Using VedaLang](#using-vedalang) |
| **Extend or improve** the VedaLang language itself | Language Designer | [Developing VedaLang](#developing-vedalang) |

## LLM-Facing Docs

The repo keeps LLM-facing guidance split by persona, with explicit ownership:

- [docs/LLM_DOCS.md](docs/LLM_DOCS.md) — full index of each LLM-facing file, purpose, and source-of-truth
- `vedalang/schema/vedalang.schema.json` — canonical enums and syntax truth
- `docs/vedalang-user/modeling-conventions.md` — canonical modeling conventions guidance text
- `skills/vedalang-dsl-cli/SKILL.md` — canonical user-agent DSL+CLI skill
- `tools/sync_conventions.py` — regenerates schema-derived enum snippets in docs

To verify docs are in sync with schema enums:

```bash
uv run python tools/sync_conventions.py --check
```

---

## Using VedaLang

Write `.veda.yaml` files to define energy system models. The compiler handles Excel generation and validation.

### Documentation

- **[skills/vedalang-dsl-cli/SKILL.md](skills/vedalang-dsl-cli/SKILL.md)** — Canonical agent skill for VedaLang DSL + CLI usage
- **[docs/vedalang-user/modeling-conventions.md](docs/vedalang-user/modeling-conventions.md)** — Canonical modeling conventions guidance
- **[vedalang/examples/](vedalang/examples/)** — Example models
- **[vedalang/schema/vedalang.schema.json](vedalang/schema/vedalang.schema.json)** — Language schema
- **[rules/patterns.yaml](rules/patterns.yaml)** — Pattern "standard library"

### Quick Start

```bash
# Install
git clone https://github.com/austimes/vedalang.git
cd vedalang
uv sync

# Validate a model
uv run vedalang validate model.veda.yaml

# Lint for heuristic issues
uv run vedalang lint model.veda.yaml

# Compile to Excel only
uv run vedalang compile model.veda.yaml --out output/

# Run full pipeline (VedaLang → Excel → DD → TIMES)
uv run vedalang-dev pipeline model.veda.yaml --no-solver
```

### Minimal Example

```yaml
model:
  name: MinimalExample
  regions: [REG1]
  
  commodities:
    - name: ELC
      type: energy
      unit: PJ

  processes:
    - name: PP_GEN
      sets: [ELE]
      primary_commodity_group: NRGO
      outputs:
        - commodity: ELC
```

---

## Developing VedaLang

Extend the VedaLang DSL, improve the compiler, or discover new VEDA patterns.

### Documentation

- **[AGENTS.md](AGENTS.md)** — Primary instructions for the VedaLang Design Agent
- **[docs/vedalang-design-agent/](docs/vedalang-design-agent/)** — Design workflows, schema evolution, pattern validation

### Key Concepts

- **xl2times is the oracle** — Its verdict on compiled Excel is final
- **Schema-first design** — Update JSON Schema before compiler changes
- **TableIR experimentation** — Prototype at TableIR level, lift to VedaLang when valid

### Design Workflow

```
1. Prototype at TableIR level (raw YAML tables)
2. Emit Excel: vedalang-dev emit-excel tables.yaml --out test.xlsx
3. Validate: xl2times test.xlsx --diagnostics-json diag.json
4. If valid → lift pattern to VedaLang syntax
5. If invalid → fix and retry
```

### Development Commands

```bash
# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Validate the mini_plant example
uv run vedalang validate vedalang/examples/mini_plant.veda.yaml
```

---

## Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- GAMS with a valid license (for running the solver)
- TIMES source code

### Setup

```bash
# Clone and install
git clone https://github.com/austimes/vedalang.git
cd vedalang
uv sync
uv pip install -e .

# Configure environment
cp .env.example .env
# Edit .env to set TIMES_SRC=/path/to/your/TIMES_model
```

### Getting TIMES Source

```bash
git clone https://github.com/etsap-TIMES/TIMES_model.git ~/TIMES_model
```

Then set `TIMES_SRC` in your `.env` file to point to this directory.

---

## Project Structure

```
veda-devtools/
├── vedalang/              # VedaLang compiler and schema
│   ├── compiler/          # VedaLang → TableIR compiler
│   ├── schema/            # JSON Schema definitions
│   └── examples/          # Example VedaLang models
├── tools/
│   ├── vedalang_cli/      # User CLI (vedalang lint/compile/validate)
│   ├── vedalang_dev_cli/  # Design agent CLI (vedalang-dev)
│   └── emit_excel/        # TableIR → Excel emitter
├── xl2times/              # Local fork of xl2times (Excel → DD)
├── rules/                 # Pattern library
├── docs/
│   ├── vedalang-user/     # Documentation for model authors
│   └── vedalang-design-agent/  # Documentation for language designers
└── tests/                 # Test suite
```

---

## License

See LICENSE file for details.
