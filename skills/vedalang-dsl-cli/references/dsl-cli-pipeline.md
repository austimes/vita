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
- `commodity.type`: `fuel | energy | service | material | emission | money | other`
- `commodity namespace prefix`: `primary | resource | secondary | service | material | emission | money`
- `scenario category`: `demands | prices | policies | technology_assumptions | resource_availability | global_settings`
<!-- GENERATED:dsl-cli-canonical-enums:end -->

## Standard Commands

```bash
# Fast structural checks
uv run vedalang lint model.veda.yaml

# Full end-to-end validation
uv run vedalang validate model.veda.yaml

# Compile only
uv run vedalang compile model.veda.yaml --out output/

# Design-agent full pipeline (no solver)
uv run vedalang-dev pipeline model.veda.yaml --no-solver
```

## Reliability Rules

- Always run `validate` before treating model output as valid.
- Prefer explicit milestone-year values over implicit interpolation.
- Keep emissions in `emission_factors`; do not model `emission:*` as physical flows.
