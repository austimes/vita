# VedaLang

A typed DSL that compiles to VEDA tables for TIMES energy system models.

VedaLang provides type safety, schema validation, and clear error messages while compiling to VEDA Excel tables that can be processed by xl2times and solved with GAMS/TIMES.

```
VedaLang Source (.veda.yaml) → CSIR/CPIR → VEDA Excel (.xlsx) → xl2times → TIMES DD files
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
| **Technology Role** | Service-oriented contract listing the technologies that may satisfy it |
| **Technology** | Concrete implementation with flows, performance, costs, and emissions |
| **Site** | Physical location anchor for facility assets |
| **Facility / Fleet** | Asset declarations that carry stock, allowed technologies, and policies |
| **Run** | Selected base-year/currency-year/region-partition compilation target |

<!-- GENERATED:scenario-categories:start -->
**Canonical scenario categories:** `demands` | `prices` | `policies` | `technology_assumptions` | `resource_availability` | `global_settings`
<!-- GENERATED:scenario-categories:end -->

**Current compiler output:** `syssettings.xlsx` and `vt_{book}_{run}.xlsx` (lowercase)

**Scenario workbook naming convention when referenced:** `scen_{case}_{category}.xlsx`
- Example: `scen_baseline_demands.xlsx`, `scen_ambitious_policies.xlsx`

This separation distinguishes between:
- **Model architecture** (`VT` in VEDA terminology; compiler emits lowercase `vt_*` files): processes, commodities, topology
- **Scenario instantiation** (`scen_*` files, when used): demands, prices, policies that instantiate the architecture

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
- `vedalang/conventions.py` — canonical runtime accessors used by compiler, linter, and LLM prompts
- `docs/vedalang-user/modeling-conventions.md` — canonical modeling conventions guidance text
- `skills/vedalang-dsl-cli/SKILL.md` — canonical user-agent DSL+CLI skill
- `tools/sync_conventions.py` — regenerates schema-derived enum snippets in docs

To verify docs are in sync with schema enums:

```bash
uv run python tools/sync_conventions.py --check
```

To verify runtime consumers stay aligned with canonical conventions:

```bash
uv run pytest tests/test_conventions_sync.py
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
uv run vedalang validate model.veda.yaml --run <run_id>

# Check formatting for VedaLang YAML
bun run format:veda:check

# Lint for heuristic issues
uv run vedalang lint model.veda.yaml

# Compile to Excel only
uv run vedalang compile model.veda.yaml --run <run_id> --out output/

# Run full pipeline (VedaLang → Excel → DD → TIMES)
uv run vedalang-dev pipeline model.veda.yaml --no-solver
```

### Explicit Quantities and Basis

VedaLang v0.2 uses explicit quantity strings and no implicit basis/defaulting:

- stock, costs, transfer capacities, and opportunity bounds carry explicit unit
  strings at the point where the value is authored
- combustible technology inputs must declare `basis: HHV|LHV` at the flow site
- asset-count stock requires an explicit `stock_characterization` before the
  compiler can lower it to installed-capacity or annual-activity views
- run-scoped compilation emits deterministic CSIR/CPIR/TableIR outputs rather
  than relying on implicit TIMES interpolation

See [docs/vedalang-user/attribute_mapping.md](docs/vedalang-user/attribute_mapping.md)
for supported quantity strings and backend attribute mapping details.

### CLI Command Boundaries

- `uv run vedalang fmt <path>`: canonical formatting (deterministic ordering + layout/blank-lines/indentation)
- `uv run vedalang lint <model>.veda.yaml`: semantic/modeling diagnostics
- `uv run vedalang compile <model>.veda.yaml --run <run_id> --out <dir>`: run-scoped compilation
- `uv run vedalang validate <model>.veda.yaml --run <run_id>`: full compile + oracle validation

### Minimal Example

```yaml
# Schema version for this model file.
dsl_version: "0.2"

# Commodities declare the fuel and service namespaces used elsewhere.
commodities:
  - id: primary:natural_gas
    kind: primary
  - id: service:space_heat
    kind: service

# Technologies define the concrete conversion behavior and coefficients.
technologies:
  - id: gas_heater
    provides: service:space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9

# Technology roles group the technologies that may provide a service.
technology_roles:
  - id: space_heat_supply
    primary_service: service:space_heat
    technologies: [gas_heater]

# Spatial layers point to the underlying geographic data source.
spatial_layers:
  - id: geo.demo
    kind: polygon
    key: region_id
    geometry_file: data/regions.geojson

# Region partitions group geometry members into the model regions used at compile time.
region_partitions:
  - id: toy_region
    layer: geo.demo
    members: [QLD]
    mapping:
      kind: constant
      value: QLD

# Sites anchor assets to a location and region membership.
sites:
  - id: brisbane_home
    location:
      point:
        lat: -27.47
        lon: 153.02
    membership_overrides:
      region_partitions:
        toy_region: QLD

# Facilities declare the real-world asset stock attached to each site.
facilities:
  - id: brisbane_space_heat
    site: brisbane_home
    technology_role: space_heat_supply
    stock:
      items:
        - technology: gas_heater
          metric: installed_capacity
          observed:
            value: 12 kW
            year: 2025

# Runs select the base year and regional view to compile.
runs:
  - id: toy_region_2025
    base_year: 2025
    currency_year: 2024
    region_partition: toy_region
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

# Check VedaLang YAML formatting
bun run format:veda:check

# Run linter
uv run ruff check .

# Validate a v0.2 example
uv run vedalang validate vedalang/examples/v0_2/mini_space_heat.veda.yaml --run toy_region_2025
```

---

## Installation

### Prerequisites

- Python 3.11+
- [Bun](https://bun.sh/) (for YAML formatting checks)
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
