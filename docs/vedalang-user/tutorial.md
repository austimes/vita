# Your First VedaLang Model

This tutorial walks you through creating a simple energy system model in VedaLang. You'll build a minimal model with a natural gas power plant that generates electricity.

## Step 1: Create a Minimal Model File

Create a file called `my_first_model.veda.yaml` with this content:

```yaml
model:
  name: MyFirstModel
  description: A simple power plant model

  regions:
    - REG1

  milestone_years: [2020, 2030]

  commodities:
    - id: secondary:electricity
      type: energy
      unit: PJ
      description: Electricity

    - id: primary:natural_gas
      type: fuel
      unit: PJ
      description: Natural Gas

roles:
  - id: generate_electricity
    stage: conversion
    inputs:
      - commodity: primary:natural_gas
    outputs:
      - commodity: secondary:electricity

variants:
  - id: gas_plant
    role: generate_electricity
    efficiency: 0.50

availability:
  - variant: gas_plant
    regions: [REG1]
```

### What Each Section Does

- **model.regions**: Geographic regions in your model
- **model.milestone_years**: Time periods the model solves for
- **model.commodities**: Energy carriers, services, and emissions — with namespace prefixes (e.g., `secondary:`, `service:`, `emission:`)
- **roles**: Templates defining what a process does (inputs → outputs)
- **variants**: Specific technologies that implement a role
- **availability**: Where and when each variant is available

## Step 2: Validate Your Model

Run the validation command:

```bash
uv run vedalang validate my_first_model.veda.yaml
```

If successful, you'll see output like:

```
✓ Lint passed
✓ Compile passed
✓ xl2times validation passed
```

## Step 3: Understanding the Output

When you validate a model, VedaLang:

1. **Lints** the source file (checks for common modeling mistakes)
2. **Compiles** to Excel files in a temporary directory
3. **Validates** the Excel through xl2times

Generated files include:
- `base/base.xlsx` — Process definitions and topology
- `syssettings/syssettings.xlsx` — Model settings and timeslices

Use `--keep-workdir` to inspect generated files:

```bash
uv run vedalang validate my_first_model.veda.yaml --keep-workdir
```

## Step 4: Common Errors and How to Fix Them

### Missing Required Fields

**Error**: `'id' is a required property`

**Fix**: Every commodity, process_role, and process_variant needs an `id`:

```yaml
commodities:
  - id: secondary:electricity  # ← Required
    type: energy
    unit: PJ
```

### Invalid Commodity References

**Error**: `Unknown commodity 'elec' in process_role 'generate_electricity'`

**Fix**: Ensure commodity IDs in `inputs`/`outputs` match defined commodities:

```yaml
commodities:
  - id: secondary:electricity  # ← Defined here
    type: energy
    unit: PJ

roles:
  - id: generate_electricity
    outputs:
      - commodity: secondary:electricity  # ← Must match exactly
```

### Missing Availability

**Error**: Heuristic warning about unused process variants

**Fix**: Add an `availability` entry for each variant:

```yaml
availability:
  - variant: gas_plant
    regions: [REG1]
```

## Next Steps

- **[DSL + CLI skill](../../skills/vedalang-dsl-cli/SKILL.md)** — Canonical operational guidance
- **[vedalang/examples/](../../vedalang/examples/)** — More example models
- **[rules/patterns.yaml](../../rules/patterns.yaml)** — Pattern library for common modeling idioms
- **[attribute_mapping.md](attribute_mapping.md)** — How VedaLang maps to VEDA/TIMES
