# Contributing to VedaLang

Welcome! This guide will help you get started contributing to VedaLang.

## Prerequisites

- **Python 3.11+**
- **[uv](https://github.com/astral-sh/uv)** — Fast Python package manager
- **[Bun](https://bun.sh/)** — Required for YAML formatting checks (`prettier`)
- *(Optional)* **GAMS + TIMES** — For full solver integration

## Quick Setup

```bash
git clone https://github.com/austimes/vedalang.git
cd vedalang
uv sync
bun install
```

That's it! You're ready to run tests.

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Check VedaLang YAML formatting
bun run format:veda:check

# Run linter
uv run ruff check .
```

## Validating a Model (No Solver Required)

You can validate VedaLang models without GAMS/TIMES installed:

```bash
uv run vedalang validate vedalang/examples/quickstart/mini_plant.veda.yaml
```

This runs the full pipeline up to DD file generation, checking that your model compiles correctly.

## Full Pipeline with Solver (Requires GAMS/TIMES)

To run models through the TIMES solver:

1. Copy `.env.example` to `.env` and set your TIMES path:
   ```bash
   cp .env.example .env
   # Edit .env and set TIMES_SRC=/path/to/your/TIMES_model
   ```

2. Run the full pipeline:
   ```bash
   uv run vedalang-dev pipeline vedalang/examples/quickstart/mini_plant.veda.yaml --case base
   ```

## Project Structure

| Directory | Description |
|-----------|-------------|
| `vedalang/` | Core compiler, schema, and examples |
| `vedalang/examples/` | Example VedaLang models |
| `vedalang/schema/` | JSON Schema definitions |
| `tools/` | CLI tools (`vedalang`, `vedalang-dev`) |
| `tests/` | Test suite |
| `docs/vedalang-user/` | User documentation |
| `fixtures/` | Test fixtures and reference models |
| `xl2times/` | Third-party validation oracle (do not modify) |

## Where to Start

1. **Explore the examples** — Browse `vedalang/examples/` to see how models are written
2. **Read the user docs** — Check `docs/vedalang-user/README.md` for language overview
3. **Run the minisystem tests** — A good first step to verify everything works:
   ```bash
   uv run pytest tests/ -k minisystem -v
   ```

Happy hacking! 🎉
