---
name: vita-experiment-loop
description: >-
  Runs the Vita experiment cycle from question framing through baseline/variant
  runs, narrative reporting, and visual presentation. Use when asked to run
  policy experiments or explain model outcomes.
---

# Vita Experiment Loop

Use this skill for agent-led analysis with Vita. The workflow has **agentic
bookends** (planning brief + narrative report) around a **deterministic core**
(stage/run/summarize). The final report is written directly as HTML using the
`visual-explainer` skill; there is no intermediate structured artifact.

## Core Workflow

Always pass `--agent-mode` to `vita` and `vedalang`. Add `--json` whenever the
command supports structured output and you will consume it programmatically.

### Phase 1: Design & Plan (Agentic)

1. Read the question and target model.
2. Design the experiment: choose variants, form hypotheses, plan comparisons.
3. Write `manifest.yaml` following experiment manifest schema.
4. **Write `planning/brief.json`** (MANDATORY — see schema below).
5. **Run `vita experiment validate-brief <experiment_dir> --agent-mode`** — do not
   continue until validation passes.

### Phase 2: Execute (Deterministic)

6. Stage: `vita experiment stage manifest.yaml --out <dir> --agent-mode`
7. Run: `vita experiment run <experiment_dir> --agent-mode --json`
8. Summarize: `vita experiment summarize <experiment_dir> --agent-mode --json`

### Phase 3: Narrate (Agentic — via visual-explainer)

9. Read the full evidence set:
   - `planning/brief.json` — your design rationale and hypotheses
   - `conclusions/summary.json` — metrics, deltas, anomaly flags
   - `diffs/*/diff.json` — detailed comparison data
   - `runs/*/results.json` — per-case solver results
   - `analyses/run_matrix.json` — cross-case comparison matrix (if present)
10. Load and use the `visual-explainer` skill to create a **single narrative
    HTML report** at `report/index.html`.
11. The report tells the story of a scientific investigation (see **Narrative
    Report Contract** below).
12. Every substantive claim must be tied to concrete evidence from the summary,
    diffs, or run results. Do not invent mechanisms unsupported by the artifacts.
13. Open `report/index.html` in the browser for the user.

### Agent Checklist

- [ ] `manifest.yaml` written
- [ ] `planning/brief.json` written
- [ ] Brief validation passed
- [ ] All runs completed
- [ ] Summary generated
- [ ] Evidence read and analyzed
- [ ] `report/index.html` written with `visual-explainer`
- [ ] Report cites evidence and includes reproducibility appendix

## Convenience Mode

For the full deterministic pipeline (stage + run + summarize):
```bash
vita experiment manifest.yaml --out experiments/ --agent-mode --json
```
This does NOT produce the narrative report — that requires agentic work with
the visual-explainer skill.

## Brief Schema (`vita-experiment-brief/v1`)

The brief captures WHY you designed the experiment this way. Write it BEFORE
running the experiment.

```json
{
  "schema_version": "vita-experiment-brief/v1",
  "experiment_id": "<must match manifest.id>",
  "manifest_file": "manifest.yaml",
  "created_at": "<ISO 8601 timestamp>",

  "research": {
    "question": "<primary research question from manifest>",
    "scope": "<what this experiment covers and does not cover>"
  },

  "design_summary": {
    "approach": "<why this set of variants was chosen>",
    "variant_ids": ["<all variant IDs from manifest>"],
    "comparison_ids": ["<all comparison IDs from manifest>"]
  },

  "variants": [
    {
      "variant_id": "<must match manifest variant ID>",
      "change_summary": "<what was changed vs baseline>",
      "why_this_variant": "<why this tests the research question>",
      "hypothesis": {
        "statement": "<what you expect to happen>",
        "expected_direction": "increase|decrease|mixed|no_change|uncertain",
        "mechanism_chains": [
          {
            "id": "M1",
            "cause": "<the input change>",
            "effect": "<the expected outcome>",
            "because": "<causal reasoning connecting cause to effect>"
          }
        ],
        "confirmation_criteria": [
          {
            "id": "C1",
            "description": "<what result would confirm this hypothesis>",
            "signals": [
              {
                "metric": "objective|var_ncap|var_act|var_cap|var_flo",
                "expected_direction": "increase|decrease|no_change"
              }
            ]
          }
        ],
        "refutation_criteria": [
          {
            "id": "R1",
            "description": "<what result would refute this hypothesis>"
          }
        ]
      }
    }
  ],

  "comparison_plan": [
    {
      "comparison_id": "<must match manifest comparison ID>",
      "purpose": "<what this comparison will show>",
      "metrics_of_interest": [
        {
          "metric": "<metric name>",
          "priority": "primary|secondary",
          "why_it_matters": "<why this metric is relevant>"
        }
      ]
    }
  ],

  "design_reasoning_steps": [
    {
      "id": "P1",
      "kind": "question_framing|variant_selection|comparison_design|metric_selection|risk_check",
      "statement": "<reasoning step explaining a design choice>"
    }
  ]
}
```

**Required:** Every variant must have `mechanism_chains` (≥1) and
`confirmation_criteria` (≥1). All narrative fields must be substantive
(≥24 chars, not placeholder text).

## Narrative Report Contract

The report replaces the old `interpretation.json` + `presentation/index.html`
with a single agentic HTML artifact at `report/index.html`. Use the
`visual-explainer` skill to produce it.

### Required report structure

1. **Title + short abstract**
   - One-paragraph answer to the research question
   - Key result up front

2. **Research question and starting hypothesis**
   - What we were trying to learn
   - What we expected before running the experiment

3. **Model / experiment design**
   - Baseline description
   - Variants and what each was intended to test
   - Comparisons planned

4. **Results up front**
   - Headline findings first
   - Key objective deltas, major process shifts, surprises
   - Concise tables or visuals before deep discussion

5. **How the evidence updated the hypothesis**
   - Walk comparison-by-comparison
   - For each: what changed, what evidence shows it, what mechanism is most
     plausible, whether it supports/weakens/refutes the prior hypothesis

6. **Convergence to conclusion**
   - Synthesize across comparisons
   - Answer the original question directly
   - State confidence and what remains uncertain

7. **Limits and next experiments**
   - What the experiment cannot establish
   - What follow-up would most reduce uncertainty

8. **Reproducibility appendix**
   - Exact artifact inventory with relative paths:
     `manifest.yaml`, `planning/brief.json`, `conclusions/summary.json`,
     `diffs/*/diff.json`, `runs/*/results.json`, `analyses/run_matrix.json`
   - Run IDs and comparison IDs
   - Key evidence tables

### Writing rules

- Every claim must trace back to a concrete artifact.
- Distinguish clearly between **observation** (what changed), **interpretation**
  (what it probably means), and **uncertainty** (what remains unresolved).
- Prefer quantitative statements over vague summaries.
- Include failed or counter-hypothesis results, not just confirming ones.
- Use `visual-explainer` for layout and visual hierarchy, not decorative fluff.

### Provenance

Embed a machine-readable provenance block in the HTML:

```html
<script id="vita-report-provenance" type="application/json">
{
  "experiment_id": "...",
  "manifest_file": "manifest.yaml",
  "brief_file": "planning/brief.json",
  "summary_file": "conclusions/summary.json",
  "diff_files": ["diffs/.../diff.json"],
  "run_files": ["runs/.../results.json"],
  "generated_by": "visual-explainer"
}
</script>
```

## Ordered Marginal Recipe

Use for "which lever matters most?" requests:

1. Run each lever independently vs baseline.
2. Rank by `|Δ objective|` (or another agreed metric).
3. Apply the largest lever, treat as new baseline.
4. Re-run remaining levers against updated baseline.
5. Repeat until no material change remains.
6. Present as a waterfall-style narrative in the report.

## Conventions

- Always use stable, meaningful run directory names.
- Keep baseline immutable once variant comparisons start.
- For toy-sector workflows, default to `--no-sankey`.
- Use `--focus-processes` in `vita diff` for targeted technology comparisons.
- Keep narrative claims tied to evidence artifacts, not hypothetical effects.
- The brief and narrative report are **mandatory outputs**, not optional notes.

## Toy Industry Example

```bash
# Stage + run + summarize (deterministic)
vita experiment vedalang/examples/toy_sectors/experiments/toy_industry_core.experiment.yaml --out experiments/ --agent-mode --json

# Or step by step:
vita experiment stage vedalang/examples/toy_sectors/experiments/toy_industry_core.experiment.yaml --out experiments/ --agent-mode
vita experiment run experiments/toy_industry_core --agent-mode --json
vita experiment summarize experiments/toy_industry_core --agent-mode --json

# Validate planning brief
vita experiment validate-brief experiments/toy_industry_core --agent-mode

# Narrate results (agentic — use visual-explainer skill to write report/index.html)
```
