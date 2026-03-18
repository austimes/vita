---
name: vita-experiment-loop
description: >-
  Runs the Vita experiment cycle from question framing through baseline/variant
  runs, diff interpretation, and visual presentation. Use when asked to run
  policy experiments or explain model outcomes.
---

# Vita Experiment Loop

Use this skill for agent-led analysis with Vita. The workflow has **agentic
bookends** (planning brief + interpretation) around a **deterministic core**
(stage/run/summarize).

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

### Phase 3: Interpret (Agentic)

9. Read the evidence:
   - `conclusions/summary.json` — metrics, deltas, anomaly flags
   - `diffs/*/diff.json` — detailed comparison data
   - `runs/*/results.json` — per-case solver results
   - `analyses/run_matrix.json` — cross-case comparison matrix
10. Reason about what the results mean: WHY did things change? What mechanisms?
11. **Write `conclusions/interpretation.json`** (MANDATORY — see schema below).
12. **Run `vita experiment validate-interpretation <experiment_dir> --agent-mode`** —
    do not continue until validation passes.

### Phase 4: Present (Deterministic)

13. `vita experiment present <experiment_dir> --agent-mode`
14. Open `presentation/index.html` in browser.

### Agent Checklist

- [ ] `manifest.yaml` written
- [ ] `planning/brief.json` written
- [ ] Brief validation passed
- [ ] All runs completed
- [ ] Summary generated
- [ ] Evidence read and analyzed
- [ ] `conclusions/interpretation.json` written
- [ ] Interpretation validation passed
- [ ] Presentation generated

## Convenience Mode

For the full deterministic pipeline (stage + run + summarize):
```bash
vita experiment manifest.yaml --out experiments/ --agent-mode --json
```
This does NOT produce interpretation or presentation — those require agentic
steps.

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

## Interpretation Schema (`vita-experiment-interpretation/v1`)

The interpretation captures WHAT the results mean and WHY. Write it AFTER
reading all evidence.

```json
{
  "schema_version": "vita-experiment-interpretation/v1",
  "experiment_id": "<must match manifest.id>",
  "summary_file": "conclusions/summary.json",
  "created_at": "<ISO 8601 timestamp>",

  "research_question": "<primary research question>",

  "executive_summary": {
    "short_answer": "<one-sentence answer>",
    "answer": "<paragraph-length answer with reasoning>",
    "confidence": "high|medium|low",
    "evidence_refs": ["E1", "E2"],
    "supporting_step_ids": ["<comparison>.R1", "<comparison>.R3"]
  },

  "evidence_index": [
    {
      "id": "E1",
      "kind": "comparison_metric|process_delta|run_metric|key_finding",
      "comparison_id": "<optional>",
      "metric": "<metric name>",
      "source_file": "<path to source artifact>"
    }
  ],

  "question_answers": [
    {
      "question_id": "Q",
      "question": "<the research question>",
      "comparison_ids": ["<relevant comparisons>"],
      "short_answer": "<one sentence>",
      "answer": "<detailed answer with reasoning>",
      "confidence": "high|medium|low",
      "uncertainty": "<what we don't know>",
      "evidence_refs": ["E1"],
      "supporting_step_ids": ["<step IDs>"]
    }
  ],

  "comparison_interpretations": [
    {
      "comparison_id": "<must match manifest comparison ID>",
      "takeaway": "<one-sentence interpretation>",
      "hypothesis_assessment": {
        "status": "supports|refutes|mixed|inconclusive",
        "rationale": "<why this assessment>"
      },
      "key_evidence_refs": ["E1", "E2"],
      "reasoning_steps": [
        {
          "id": "<comparison>.R1",
          "kind": "observation",
          "statement": "<what the data shows>",
          "evidence_refs": ["E1"],
          "depends_on": []
        },
        {
          "id": "<comparison>.R2",
          "kind": "mechanism",
          "statement": "<causal explanation>",
          "evidence_refs": ["E2"],
          "depends_on": ["<comparison>.R1"]
        },
        {
          "id": "<comparison>.R3",
          "kind": "conclusion",
          "statement": "<what this means>",
          "evidence_refs": ["E1", "E2"],
          "depends_on": ["<comparison>.R2"]
        }
      ],
      "primary_mechanism": "<main causal explanation>",
      "alternative_mechanisms": ["<other possible explanations>"],
      "confidence": "high|medium|low",
      "surprises": [
        {
          "description": "<what was unexpected>",
          "possible_mechanisms": ["<why it might have happened>"],
          "evidence_refs": ["E2"]
        }
      ]
    }
  ],

  "cross_comparison_synthesis": {
    "overall_pattern": "<what emerges across all comparisons>",
    "open_questions": ["<unanswered questions>"],
    "limits": ["<interpretation caveats>"]
  }
}
```

**Required:**

- `question_answers` must include one entry with `question_id: "Q"` answering the
  top-level research `question` from the manifest, **plus** one entry per analysis ID
  defined in `analyses[]`. The validator checks all expected question IDs are present.
- Every comparison must have reasoning steps with at least one
  `observation` and one `conclusion`, connected via `depends_on`. All evidence
  refs must point to valid entries in `evidence_index`.

## Reasoning Steps

The `reasoning_steps` array creates a **lightweight reasoning DAG** — not raw
chain-of-thought, but organized claims connected by evidence:

| Kind | Purpose | Example |
|------|---------|---------|
| `observation` | What the data shows | "Objective increased by 131%" |
| `mechanism` | Causal explanation | "Higher capex makes gas less competitive" |
| `comparison` | Cross-variant comparison | "Gas capex has 5× the impact of H2 capex" |
| `conclusion` | What this means | "Cost sensitivity to gas capex is high" |
| `uncertainty` | What we don't know | "Single-period model may miss dynamic effects" |

Rules:
- `observation` steps have empty `depends_on`
- All other steps must reference at least one prior step in `depends_on`
- Every `conclusion` must be reachable from an `observation` via the DAG

## Ordered Marginal Recipe

Use for "which lever matters most?" requests:

1. Run each lever independently vs baseline.
2. Rank by `|Δ objective|` (or another agreed metric).
3. Apply the largest lever, treat as new baseline.
4. Re-run remaining levers against updated baseline.
5. Repeat until no material change remains.
6. Summarize as a waterfall-style narrative in interpretation.json.

## Conventions

- Always use stable, meaningful run directory names.
- Keep baseline immutable once variant comparisons start.
- For toy-sector workflows, default to `--no-sankey`.
- Use `--focus-processes` in `vita diff` for targeted technology comparisons.
- Keep interpretation tied to evidence artifacts, not hypothetical effects.
- Every claim in interpretation.json must reference evidence from summary/diff/run.
- The brief and interpretation are **mandatory outputs**, not optional notes.

## Toy Industry Example

```bash
# Stage + run + summarize (deterministic)
vita experiment vedalang/examples/toy_sectors/experiments/toy_industry_core.experiment.yaml --out experiments/ --agent-mode --json

# Or step by step:
vita experiment stage vedalang/examples/toy_sectors/experiments/toy_industry_core.experiment.yaml --out experiments/ --agent-mode
vita experiment run experiments/toy_industry_core --agent-mode --json
vita experiment summarize experiments/toy_industry_core --agent-mode --json

# Validate agentic artifacts
vita experiment validate-brief experiments/toy_industry_core --agent-mode
vita experiment validate-interpretation experiments/toy_industry_core --agent-mode

# Generate presentation
vita experiment present experiments/toy_industry_core --agent-mode
```
