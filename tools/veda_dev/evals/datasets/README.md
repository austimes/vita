# LLM Lint Eval Dataset

`llm_lint_cases.yaml` is a purpose-built synthetic benchmark corpus for
`vedalang-dev eval`.

- It intentionally does **not** use `vedalang/examples/` production examples.
- Cases are grounded in fixtures under
  `tools/veda_dev/evals/fixtures/ground_truth/`.
- Profiles are fixed-size:
  - `smoke`: 5 cases
  - `ci`: 10 cases
  - `deep`: 30 cases (10 structure + 20 units)

## Label Schema

Each case can include `expected.labels` entries with:

- `error_code`: controlled benchmark code
- `error_family`: coarse grouping for confusion slices
- `difficulty`: `easy | medium | hard`
- `expected_presence`: `present | absent`

These labels are used by deterministic eval scoring (non-judge) to compute:

- precision/recall/F1
- presence accuracy
- difficulty accuracy
- family accuracy

## Current Controlled Codes

Structure:

- `STR_ZERO_INPUT_DEVICE`
- `STR_OVER_FRAGMENTED_ROLES`
- `STR_COMMODITY_TYPE_MISMATCH`
- `STR_AMBIGUOUS_VARIANT_NAMING`
- `STR_STAGE_MISMATCH`
- `STR_FUEL_PATHWAY_ROLE`

Units:

- `UNIT_BASIS_MISSING`
- `UNIT_VARIABLE_COST_DENOM_MISMATCH`
- `UNIT_INVESTMENT_COST_DENOM_MISMATCH`
- `UNIT_CAPACITY_DENOM_MISMATCH`
