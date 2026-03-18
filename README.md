# Vita

Vita lets AI agents run the scientific method on energy system models. Ask a question about energy policy, technology, or infrastructure — Vita frames hypotheses, designs experiments, runs them through a physics-based solver, and interprets the results.

```
    ┌─────────────────────────────────────────────────────────────┐
    │                   THE VITA LOOP                             │
    │                                                             │
    │   ┌──────────┐    ┌────────────┐    ┌──────────────────┐    │
    │   │  Frame   │───▶│ Hypothesize│───▶│ Design Experiment│    │
    │   │ Question │    │            │    │  (VedaLang model) │    │
    │   └──────────┘    └────────────┘    └────────┬─────────┘    │
    │        ▲                                     │              │
    │        │                                     ▼              │
    │   ┌────┴─────┐    ┌────────────┐    ┌──────────────────┐    │
    │   │ Iterate  │◀───│ Interpret  │◀───│   Run Solver     │    │
    │   │          │    │  Results   │    │  (GAMS/TIMES)    │    │
    │   └──────────┘    └────────────┘    └──────────────────┘    │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

The agent handles the bookends (framing, hypothesizing, interpreting, iterating). The deterministic core (compile, solve, extract) runs without LLM involvement.

---

## Quick Start

```bash
# Install the latest CLI tools from GitHub
uv tool install git+https://github.com/austimes/vedalang

# Verify the commands are on PATH
vita --help
vedalang --help

# Initialize a new experiment workspace
vita init my-experiment
cd my-experiment

# Validate the starter model
vedalang validate models/example.veda.yaml --run demo_2025

# Run the starter model without the solver
vita run models/example.veda.yaml --run demo_2025 --no-solver --json
```

Rerun `uv tool install --force git+https://github.com/austimes/vedalang` to refresh to the latest GitHub HEAD.

Clone the repository only if you want the bundled examples, the agent skill files under `skills/`, or contributor workflows. The quick start above is the supported path for getting `vita` and `vedalang` onto your shell `PATH`.

Then open the workspace in your AI agent and start asking questions.

---

## How Vita Works

Vita separates what agents are good at from what deterministic tools are good at:

| Phase | Who | What happens |
|-------|-----|-------------|
| **Frame** | Agent | Translates a policy/engineering question into a testable hypothesis |
| **Design** | Agent | Authors a VedaLang model (baseline + variant) expressing the experiment |
| **Compile** | `vedalang compile` | Deterministic lowering: VedaLang → CSIR → CPIR → VEDA Excel |
| **Solve** | `vita run` | VEDA Excel → xl2times → DD files → GAMS/TIMES solver |
| **Extract** | `vita results` | Structured results from solver output (GDX → JSON) |
| **Interpret** | Agent | Reads results, draws conclusions, decides next iteration |

The compile → solve → extract core is fully deterministic. No LLM is involved in the physics.

---

## How the Pieces Fit Together

- **Vita** is the experiment loop — orchestrates question → model → solve → interpret cycles
- **VedaLang** is the language — a typed DSL for expressing energy system models as `.veda.yaml` files
- **GAMS/TIMES** is the solver backend — the physics engine that optimizes the energy system

```
VedaLang Source (.veda.yaml) → CSIR/CPIR → VEDA Excel (.xlsx) → xl2times → TIMES DD files → GAMS → Solution
```

---

## Three CLI Tools

This repository provides three CLI tools with distinct roles:

| CLI | Role | Audience |
|-----|------|----------|
| **`vita`** | The engine — run, analyze, and explain TIMES experiments | Anyone running models |
| **`vedalang`** | The language — author, lint, compile, validate models | Model developers |
| **`vedalang-dev`** | Internal R&D — pattern experimentation, evals, emit-excel | Language designers |

**Rule of thumb:** Use `vita` to *run and analyze* experiments, `vedalang` to *write* models, and `vedalang-dev` only for language design work.

---

## Choose Your Path

| Goal | You are a... | Start here |
|------|--------------|------------|
| **Answer energy system questions** with an AI agent | Analyst / Researcher | [Running Experiments](#running-experiments) |
| **Author energy system models** using VedaLang | Model Developer | [Authoring Models in VedaLang](#authoring-models-in-vedalang) |
| **Extend or improve** the VedaLang language itself | Language Designer | [For Contributors](#for-contributors) |

---

## Core Commands

### Vita (run and analyze)

```bash
# Run full pipeline: VedaLang → Excel → DD → TIMES
vita run model.veda.yaml --run <run_id> --json

# Run without solver (useful when GAMS unavailable)
vita run model.veda.yaml --run <run_id> --no-solver --json

# Compare baseline vs variant
vita diff runs/<study>/baseline runs/<study>/<variant> --json

# Extract results from a solved model
vita results --gdx tmp/gams/scenario.gdx --json
```

### VedaLang (author and validate)

```bash
# Validate a model (compile + oracle validation)
vedalang validate model.veda.yaml --run <run_id>

# Compile to Excel only
vedalang compile model.veda.yaml --run <run_id> --out output/

# Lint for heuristic issues
vedalang lint model.veda.yaml

# Format YAML
vedalang fmt model.veda.yaml
```

### CLI Command Boundaries

- `vedalang fmt <path>`: canonical formatting (deterministic ordering + layout/blank-lines/indentation)
- `vedalang lint <model>.veda.yaml`: semantic/modeling diagnostics
- `vedalang compile <model>.veda.yaml --run <run_id> --out <dir>`: run-scoped compilation
- `vedalang validate <model>.veda.yaml --run <run_id>`: full compile + oracle validation
- `vita run <model>.veda.yaml --run <run_id> [--json]`: solve/execution and artifact generation
- `vita diff <baseline_run_dir> <variant_run_dir> --json`: run-to-run comparison and deltas

---

## Authoring Models in VedaLang

Write `.veda.yaml` files to define energy system models. The compiler handles Excel generation and validation.

### Documentation

- **[skills/vedalang-dsl-cli/SKILL.md](skills/vedalang-dsl-cli/SKILL.md)** — Canonical agent skill for VedaLang DSL + CLI usage
- **[docs/vedalang-user/modeling-conventions.md](docs/vedalang-user/modeling-conventions.md)** — Canonical modeling conventions guidance
- **[docs/vedalang-user/known_answer_catalog.md](docs/vedalang-user/known_answer_catalog.md)** — Solver-backed known-answer suite catalog with coverage status and solved-output mappings
- **[vedalang/examples/](vedalang/examples/)** — Example models
- **[vedalang/schema/vedalang.schema.json](vedalang/schema/vedalang.schema.json)** — Language schema
- **[rules/patterns.yaml](rules/patterns.yaml)** — Pattern "standard library"

### Terminology

VedaLang uses precise terminology to avoid ambiguity:

| Term | Definition |
|------|------------|
| **Scenario Parameter** | An atomic time-series or value assumption (e.g., CO2 price path, demand projection) |
| **Category** | Logical grouping of scenario parameters (canonical values listed below) |
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

These category names are currently a compiler/runtime convention for
`scen_{case}_{category}.xlsx` naming. They are not yet declared as a
`vedalang.schema.json` enum because scenario workbooks are outside the authored
v0.3 DSL surface.

**Current compiler output:** `syssettings.xlsx` and `vt_{book}_{run}.xlsx` (lowercase)

**Scenario workbook naming convention when referenced:** `scen_{case}_{category}.xlsx`
- Example: `scen_baseline_demands.xlsx`, `scen_ambitious_policies.xlsx`

This separation distinguishes between:
- **Model architecture** (`VT` in VEDA terminology; compiler emits lowercase `vt_*` files): processes, commodities, topology
- **Scenario instantiation** (`scen_*` files, when used): demands, prices, policies that instantiate the architecture

### Explicit Quantities and Basis

VedaLang v0.3 uses explicit quantity strings and no implicit basis/defaulting:

- stock, costs, transfer capacities, and zone-opportunity bounds carry explicit unit
  strings at the point where the value is authored
- combustible technology inputs must declare `basis: HHV|LHV` at the flow site
- asset-count stock requires an explicit `stock_characterization` before the
  compiler can lower it to installed-capacity or annual-activity views
- run-scoped compilation emits deterministic CSIR/CPIR/TableIR outputs rather
  than relying on implicit TIMES interpolation

See [docs/vedalang-user/attribute_mapping.md](docs/vedalang-user/attribute_mapping.md)
for supported quantity strings and backend attribute mapping details.

### Minimal Example

<!-- GENERATED:minimal-example-enums:start -->
### Enum-backed Fields In This Example

- `dsl_version`: `0.3`
- `commodities[*].type`: `energy | service | material | emission | money | certificate`
- `commodities[*].energy_form`: `primary | secondary | resource`
- `technologies[*].inputs[*].basis`: `HHV | LHV`
- `technologies[*].performance.kind`: `efficiency | cop | custom`
- `spatial_layers[*].kind`: `polygon | point | grid`
- `region_partitions[*].mapping.kind`: `constant | file | spatial_join`
- `facilities[*].stock.items[*].metric`: `asset_count | installed_capacity | annual_activity`
<!-- GENERATED:minimal-example-enums:end -->

```yaml
# Schema version for this model file.
dsl_version: "0.3"

# Commodities declare the fuel and service namespaces used elsewhere.
commodities:
  - id: natural_gas
    type: energy
    energy_form: primary
  - id: space_heat
    type: service

# Technologies define the concrete conversion behavior and coefficients.
technologies:
  - id: gas_heater
    provides: space_heat
    inputs:
      - commodity: primary:natural_gas
        basis: HHV
    performance:
      kind: efficiency
      value: 0.9

# Technology roles group the technologies that may provide a service.
technology_roles:
  - id: space_heat_supply
    primary_service: space_heat
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

## Running Experiments

Toy-sector examples live in `vedalang/examples/toy_sectors/`. Use `vedalang` for authoring/validation and `vita` to execute and compare runs.

```bash
# Run a toy example (recommended default for toy-sector runs: keep --no-sankey)
uv run vita run vedalang/examples/toy_sectors/<toy_model>.veda.yaml \
  --run <run_id> --no-sankey --out runs/<study>/<case> --json

# Compare baseline vs variant artifacts
uv run vita diff runs/<study>/baseline runs/<study>/<variant> --json
```

For a concrete reproducible loop, see
`vedalang/examples/toy_sectors/README.md` and
`docs/vedalang-user/toy_industry_experiment_notes.md`.

---

## Project Structure

```
vedalang/
├── vita/                  # Vita engine CLI (run, results, sankey, diff)
├── vedalang/              # VedaLang compiler, schema, examples
│   ├── compiler/          # VedaLang → TableIR compiler
│   ├── schema/            # JSON Schema definitions
│   ├── examples/          # Example VedaLang models
│   ├── heuristics/        # Pre-compilation checks
│   ├── identity/          # Process/commodity identity system
│   ├── lint/              # LLM-based structural assessment
│   └── viz/               # RES graph visualization and inspector
├── tools/
│   ├── veda_dev/          # Design agent CLI (vedalang-dev)
│   ├── veda_emit_excel/   # TableIR → Excel emitter
│   ├── veda_check/        # Model validation utilities
│   ├── veda_patterns/     # Pattern library tools
│   ├── veda_run_times/    # Internal TIMES solver runner used by vita
│   └── vedalang_lsp/      # Language server protocol
├── xl2times/              # Local fork of xl2times (Excel → DD)
├── rules/                 # Pattern library
├── skills/                # Agent skills (DSL, modeling, experiments)
├── docs/
│   ├── vedalang-user/     # Documentation for model authors
│   └── vedalang-design-agent/  # Documentation for language designers
├── tests/                 # Test suite
└── fixtures/              # Golden test fixtures
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
git clone https://github.com/austimes/vita.git
cd vita
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

## For Contributors

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
uv run vedalang fmt --check <path>

# Run linter
uv run ruff check .

# Validate a v0.3 example
uv run vedalang validate vedalang/examples/quickstart/mini_space_heat.veda.yaml --run toy_region_2025
```

---

## LLM-Facing Docs

The repo keeps LLM-facing guidance split by persona, with explicit ownership:

- [docs/LLM_DOCS.md](docs/LLM_DOCS.md) — full index of each LLM-facing file, purpose, and source-of-truth
- `vedalang/schema/vedalang.schema.json` — canonical authored-DSL enums and syntax truth
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

## License

See LICENSE file for details.
