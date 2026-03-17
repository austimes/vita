---
name: vita-experiment-loop
description: >-
  Runs the Vita experiment cycle from question framing through baseline/variant
  runs, diff interpretation, and visual presentation. Use when asked to run
  policy experiments or explain model outcomes.
---

# Vita Experiment Loop

Use this skill for agent-led analysis with Vita.

## Core Workflow

1. Read the question and target model (including toy-sector README prompts).
2. Run baseline: `uv run vita run <model>.veda.yaml --run <run_id> --out runs/<study>/baseline --json` (for toy-sector models, add `--no-sankey` by default unless Sankey support is explicitly confirmed).
3. Inspect baseline outputs:
   - `uv run vita results --run runs/<study>/baseline --json`
   - `uv run vita diff runs/<study>/baseline runs/<study>/baseline --json` (sanity check)
4. Create one variant per hypothesis (copy model file, change one assumption).
5. Run each variant to a named run directory under `runs/<study>/` (apply the same toy-sector `--no-sankey` default).
6. Diff each variant against baseline with `vita diff ... --json`.
7. Interpret: explain what changed, magnitude, and likely mechanism.
8. Decide whether another experiment is needed or synthesis is complete.
9. Present findings with the `visual-explainer` skill.

## Ordered Marginal Recipe

Use this for "which lever matters most?" requests.

1. Run each lever independently vs baseline.
2. Rank by `|Δ objective|` (or another agreed metric).
3. Apply the largest lever, treat as new baseline.
4. Re-run remaining levers against updated baseline.
5. Repeat until no material change remains.
6. Summarize as a waterfall-style narrative.

## Conventions

- Always use stable, meaningful run directory names.
- Keep baseline immutable once variant comparisons start.
- Store model snapshots in run directories via `vita run --out`.
- For toy-sector workflows, default to `--no-sankey` unless Sankey support is
  explicitly confirmed.
- Use `--focus-processes` in `vita diff` for targeted technology comparisons.
- Keep interpretation tied to produced artifacts, not hypothetical effects.

## Toy Industry Example

```bash
uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/baseline --json
uv run vita run vedalang/examples/toy_sectors/toy_industry.veda.yaml --run s25_co2_cap --no-sankey --out runs/toy_industry/co2_cap --json
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_gas_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_gas_capex --json
uv run vita run vedalang/examples/toy_sectors/toy_industry_high_h2_capex.veda.yaml --run single_2025 --no-sankey --out runs/toy_industry/high_h2_capex --json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/co2_cap --json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_gas_capex --json
uv run vita diff runs/toy_industry/baseline runs/toy_industry/high_h2_capex --json
```

Follow by generating a concise HTML narrative with `visual-explainer`.
