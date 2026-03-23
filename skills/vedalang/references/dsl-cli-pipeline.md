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
vedalang fmt model.veda.yaml --agent-mode

# Fast structural checks
vedalang lint model.veda.yaml --agent-mode --json

# Full end-to-end validation
vedalang validate model.veda.yaml --run <run_id> --agent-mode --json

# Compile only
vedalang compile model.veda.yaml --run <run_id> --out output/ --agent-mode --json

# Full pipeline without solver
vita run model.veda.yaml --run <run_id> --no-solver --agent-mode --json

# Compare baseline vs variant run artifacts
vita diff runs/<study>/baseline runs/<study>/variant --agent-mode --json
```

## CLI Boundary

- Use `vedalang` for author/lint/compile/validate actions on `.veda.yaml`.
- Use `vita` for run execution, solver outputs, experiment diffs, and results narratives.
- Agents should always pass `--agent-mode` to `vedalang` and `vita`.
- Add `--json` whenever the command supports structured output and the response
  will be consumed programmatically.
- For toy-sector workflows, keep `--no-sankey` on `vita run` unless Sankey
  support is explicitly confirmed.

## Reliability Rules

- Always run `validate` before treating model output as valid.
- Prefer explicit run selection with `--run`, even when the file currently has
  one run.
- Prefer explicit milestone-year values over implicit interpolation.
- Keep emissions in `technologies[*].emissions`; do not model `emission:*` as physical flows.
