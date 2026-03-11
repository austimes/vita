# VedaLang DSL + CLI Pipeline Reference

Use this as the practical authoring and validation reference for model
generation agents.

## Source Priority

1. `vedalang/schema/vedalang.schema.json` (syntax truth)
2. `docs/vedalang-user/modeling-conventions.md` (conventions guidance)
3. `rules/constraints.yaml` (valid combinations)
4. `rules/patterns.yaml` (reusable patterns)

<!-- GENERATED:dsl-cli-canonical-enums:start -->
### Canonical Enums (Schema-Derived)

- `stage`: `supply | conversion | distribution | storage | end_use | sink`
- `commodity.type`: `energy | service | material | emission | money | certificate`
- `commodity namespace prefix`: `primary | secondary | resource | service | material | emission | money | certificate`
- `scenario category`: `demands | prices | policies | technology_assumptions | resource_availability | global_settings`
<!-- GENERATED:dsl-cli-canonical-enums:end -->

## Standard Commands

```bash
# Normalize YAML formatting first
uv run vedalang fmt model.veda.yaml

# Fast structural checks
uv run vedalang lint model.veda.yaml

# Full end-to-end validation
uv run vedalang validate model.veda.yaml --run <run_id>

# Compile only
uv run vedalang compile model.veda.yaml --run <run_id> --out output/

# Design-agent full pipeline (no solver)
uv run vedalang-dev pipeline model.veda.yaml --no-solver
```

## Reliability Rules

- Always run `validate` before treating model output as valid.
- Prefer explicit run selection with `--run`, even when the file currently has
  one run.
- Prefer explicit milestone-year values over implicit interpolation.
- Keep emissions in `emission_factors`; do not model `emission:*` as physical flows.
