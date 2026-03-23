---
name: vita
description: >-
  Runs the Vita experiment cycle from question framing through baseline/variant
  runs, narrative reporting, and visual presentation. Use when asked to run
  models, analyze results, or conduct policy experiments.
---

# Vita (Skill)

Use this skill for running VedaLang models, analyzing results, and conducting
agent-led experiments with Vita.

## Read Order

1. [`references/experiment-loop.md`](references/experiment-loop.md) — full
   experiment workflow (design → execute → narrate)
2. For model authoring, load the `vedalang` skill.

## Command Inventory

| Command               | Purpose                                              |
|-----------------------|------------------------------------------------------|
| `run`                 | Run full VedaLang → TIMES pipeline                   |
| `results`             | Extract and display TIMES results from GDX           |
| `sankey`              | Generate Sankey diagram from TIMES results           |
| `diff`                | Compare two Vita run directories                     |
| `experiment stage`    | Stage experiment inputs and create directory structure|
| `experiment run`      | Execute pending runs and diffs                       |
| `experiment summarize`| Extract evidence summary from completed runs         |
| `experiment validate-brief` | Run brief validation gate                      |
| `experiment status`   | Show experiment lifecycle status                     |
| `init`                | Bootstrap a new Vita project directory               |
| `update`              | Refresh installed vita and vedalang tools             |

### Transitional

- `experiment validate-interpretation` — legacy interpretation validation gate;
  may be removed in a future release.

## CLI Rules

- Always pass `--agent-mode` to `vita` and `vedalang`.
- Add `--json` whenever the command supports structured output and you intend
  to parse the result.

## CLI Boundary

- Use `vita` for run execution, solver outputs, experiment diffs, and result
  narratives.
- Use `vedalang` for author/lint/compile/validate actions on `.veda.yaml` —
  see the `vedalang` skill.

## Quick Examples

```bash
# Single model run
vita run model.veda.yaml --run <run_id> --agent-mode --json

# Compare two runs
vita diff runs/<study>/baseline runs/<study>/variant --agent-mode --json

# Full experiment (stage + run + summarize)
vita experiment manifest.yaml --out experiments/ --agent-mode --json

# Step-by-step experiment
vita experiment stage manifest.yaml --out experiments/ --agent-mode
vita experiment run experiments/<id> --agent-mode --json
vita experiment summarize experiments/<id> --agent-mode --json
```

For the full experiment workflow including agentic planning briefs and
narrative reports, see `references/experiment-loop.md`.
