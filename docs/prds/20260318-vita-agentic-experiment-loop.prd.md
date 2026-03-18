# Vita Agentic Experiment Loop — Structured Reasoning Artifacts

**Date:** 2026-03-18
**Status:** Proposed
**Epic:** `vedalang-ec3`
**Predecessor:** `vedalang-ec2` (declarative experiment manifest and CLI)

---

## Problem

The vita experiment system (`vedalang-ec2`) decomposed the agent experiment
workflow into CLI subcommands: `plan → run → conclude → present`. This made
experiments reproducible and declarative but introduced a fundamental design
tension: the `conclude` step uses purely deterministic pattern-matching to
generate "answers" and "hypothesis outcomes" — it checks whether numbers went
up or down and keyword-matches hypothesis text. **It does not capture the
agent's reasoning about WHY results look the way they do.**

The original workflow was agent-driven: the agent would design experiments,
run them, hold results in context, reason about what they mean, and produce
conclusions. By automating the conclusion step as a CLI subcommand, we lost
the agent's reasoning, intent, and causal interpretation.

### Specific deficiencies

1. **No planning rationale persisted.** The manifest captures WHAT the
   experiment does (variants, comparisons) but not WHY the agent chose those
   variants, what mechanisms it expects, or what would constitute confirmation
   vs refutation.

2. **Deterministic conclude masquerades as interpretation.** Functions like
   `_detect_surprises()` keyword-match hypothesis text (`"may not change"`,
   `"cost"`, `"increase"`) and `_build_hypothesis_outcomes()` labels hypotheses
   as "confirmed" or "refuted" based on delta direction. This is crude
   scaffolding, not real causal reasoning.

3. **No structured reasoning chain.** When the agent does reason about results,
   that reasoning lives only in thread context and is lost between sessions.
   Other agents cannot recover the interpretation.

4. **Presentation renders uninterpreted data.** The HTML presentation
   templates `summary.json` directly — it shows deltas and flags but cannot
   explain mechanisms or provide nuanced interpretation.

---

## Design Principle

> **CLI subcommands should correspond to stable artifact-producing mechanical
> steps. Reasoning-heavy steps are the agent's job.**

The experiment workflow has **agentic bookends** around a **deterministic core**:

```
Agentic: Design & Plan
  → Agent writes brief.json (structured planning rationale)
  → Validation gate: brief completeness check

Deterministic: Execute
  → vita experiment stage (snapshot inputs, create dirs)
  → vita experiment run (execute cases, compute diffs)
  → vita experiment summarize (extract metrics, package evidence)

Agentic: Interpret
  → Agent reads summary.json + diffs + results
  → Agent writes interpretation.json (structured reasoning chain)
  → Validation gate: interpretation completeness check

Deterministic: Present
  → vita experiment present (render brief + summary + interpretation → HTML)
```

---

## Artifact Specifications

### A. Planning Brief (`planning/brief.json`)

Written by the agent before execution begins. Captures experiment design
rationale.

**Schema version:** `vita-experiment-brief/v1`

**Required structure:**

```json
{
  "schema_version": "vita-experiment-brief/v1",
  "experiment_id": "<matches manifest.id>",
  "manifest_file": "manifest.yaml",
  "created_at": "<ISO 8601>",

  "research": {
    "question": "<primary research question>",
    "scope": "<what this experiment covers and doesn't>"
  },

  "design_summary": {
    "approach": "<why this set of variants was chosen>",
    "variant_ids": ["<all variant IDs>"],
    "comparison_ids": ["<all comparison IDs>"]
  },

  "variants": [
    {
      "variant_id": "<matches manifest variant ID>",
      "change_summary": "<what was changed>",
      "why_this_variant": "<why this tests the question>",
      "hypothesis": {
        "statement": "<what we expect>",
        "expected_direction": "increase|decrease|mixed|no_change|uncertain",
        "mechanism_chains": [
          {
            "id": "M1",
            "cause": "<input change>",
            "effect": "<expected outcome>",
            "because": "<causal reasoning>"
          }
        ],
        "confirmation_criteria": [
          {
            "id": "C1",
            "description": "<what would confirm the hypothesis>",
            "signals": [
              {
                "metric": "objective|var_ncap|var_act|...",
                "expected_direction": "increase|decrease|no_change"
              }
            ]
          }
        ],
        "refutation_criteria": [
          {
            "id": "R1",
            "description": "<what would refute the hypothesis>"
          }
        ]
      }
    }
  ],

  "comparison_plan": [
    {
      "comparison_id": "<matches manifest comparison ID>",
      "purpose": "<what this comparison is designed to show>",
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
      "statement": "<reasoning step>"
    }
  ]
}
```

**Rendered output:** `planning/brief.md` is deterministically generated from
`brief.json`.

---

### B. Evidence Summary (`conclusions/summary.json`)

This is the **renamed and narrowed** version of the current `conclude` output.
It extracts metrics and flags anomalies but **makes no interpretive claims**.

**Key changes from current `experiment_conclusions.py`:**

- Rename `generate_conclusions()` → `generate_summary()`
- Remove `answers` field (interpretive — belongs in `interpretation.json`)
- Remove `hypothesis_outcomes` field (interpretive — belongs in
  `interpretation.json`)
- Keep `runs`, `comparisons`, `key_findings` (factual observations)
- Rename `surprises` → `candidate_anomalies` (flags, not interpretations)
- Keep `limitations` (factual caveats)

The evidence summary is a **fact sheet**, not a conclusion document.

---

### C. Interpretation (`conclusions/interpretation.json`)

Written by the agent after reading the evidence summary. Captures structured
reasoning about what the results mean.

**Schema version:** `vita-experiment-interpretation/v1`

**Required structure:**

```json
{
  "schema_version": "vita-experiment-interpretation/v1",
  "experiment_id": "<matches manifest.id>",
  "summary_file": "conclusions/summary.json",
  "created_at": "<ISO 8601>",

  "research_question": "<primary research question>",

  "executive_summary": {
    "short_answer": "<one-sentence answer>",
    "answer": "<paragraph-length answer>",
    "confidence": "high|medium|low",
    "evidence_refs": ["E1", "E2"],
    "supporting_step_ids": ["<comparison_id>.R1"]
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
      "question_id": "Q|A|B|...",
      "question": "<the question>",
      "comparison_ids": ["<relevant comparisons>"],
      "short_answer": "<one sentence>",
      "answer": "<detailed answer>",
      "confidence": "high|medium|low",
      "uncertainty": "<what we don't know>",
      "evidence_refs": ["E1"],
      "supporting_step_ids": ["<step IDs>"]
    }
  ],

  "comparison_interpretations": [
    {
      "comparison_id": "<matches manifest comparison>",
      "takeaway": "<one-sentence interpretation>",
      "hypothesis_assessment": {
        "status": "supports|refutes|mixed|inconclusive",
        "rationale": "<why this assessment>"
      },
      "key_evidence_refs": ["E1", "E2"],
      "reasoning_steps": [
        {
          "id": "<comparison_id>.R1",
          "kind": "observation|mechanism|comparison|conclusion|uncertainty",
          "statement": "<reasoning step>",
          "evidence_refs": ["E1"],
          "depends_on": []
        },
        {
          "id": "<comparison_id>.R2",
          "kind": "mechanism",
          "statement": "<causal claim>",
          "evidence_refs": ["E2"],
          "depends_on": ["<comparison_id>.R1"]
        },
        {
          "id": "<comparison_id>.R3",
          "kind": "conclusion",
          "statement": "<what this means>",
          "evidence_refs": ["E1", "E2"],
          "depends_on": ["<comparison_id>.R2"]
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
    "overall_pattern": "<what emerges across comparisons>",
    "open_questions": ["<what remains unanswered>"],
    "limits": ["<interpretation limitations>"]
  }
}
```

**Key design properties:**

- **Reasoning DAG:** Each `reasoning_steps` entry has `id`, `depends_on`, and
  `evidence_refs`. This creates a lightweight directed acyclic graph from
  observations through mechanisms to conclusions. Downstream tools can traverse
  it programmatically.

- **Evidence index:** All claims reference evidence items by ID. Evidence items
  point to specific source artifacts (summary.json, diff.json, results.json).
  This creates a citation chain from interpretation back to raw data.

- **Not raw chain-of-thought.** The reasoning steps are organized, edited
  claims — not a transcript of internal deliberation. They explain the
  reasoning process in a way that other agents and humans can follow.

**Rendered output:** `conclusions/interpretation.md` is deterministically
generated from `interpretation.json`.

---

## Validation Gates

After each agentic step, a deterministic validator checks structural
completeness (not reasoning quality).

### Brief Validation (`planning/brief.validation.json`)

**Checks:**
- `experiment_id` matches manifest
- `variants[].variant_id` covers all manifest variant IDs exactly
- `comparison_plan[].comparison_id` covers all manifest comparison IDs exactly
- All cross-references resolve (variant IDs, comparison IDs)
- No duplicate IDs in mechanism chains, criteria, reasoning steps
- Required narrative fields pass substance check (≥24 chars, not placeholder)
- Every variant has non-empty `mechanism_chains` and `confirmation_criteria`

### Interpretation Validation (`conclusions/interpretation.validation.json`)

**Checks:**
- `experiment_id` matches manifest
- `comparison_interpretations[].comparison_id` covers all manifest comparisons
- `question_answers[].question_id` covers primary + all extension questions
- `evidence_index[].id` values are unique
- All `evidence_refs` point to valid evidence IDs
- All `supporting_step_ids` point to valid reasoning step IDs
- All `depends_on` references point to valid step IDs
- Every comparison has ≥1 observation step and ≥1 conclusion step
- Every conclusion is reachable from an observation via `depends_on`
- Required narrative fields pass substance check

**Validation output shape:**
```json
{
  "schema_version": "vita-experiment-validation/v1",
  "artifact_kind": "brief|interpretation",
  "artifact_file": "<path>",
  "checked_at": "<ISO 8601>",
  "valid": true,
  "errors": [],
  "warnings": [],
  "coverage": {
    "expected_variant_ids": [],
    "documented_variant_ids": [],
    "missing_variant_ids": [],
    "expected_comparison_ids": [],
    "documented_comparison_ids": [],
    "missing_comparison_ids": []
  }
}
```

---

## CLI Subcommand Changes

### Renames
| Current | New | Rationale |
|---------|-----|-----------|
| `vita experiment plan` | `vita experiment stage` | "Plan" implies reasoning; staging is mechanical |
| `vita experiment conclude` | `vita experiment summarize` | Evidence extraction, not interpretation |

### New subcommands
| Command | Purpose |
|---------|---------|
| `vita experiment validate-brief <dir>` | Run brief validation gate |
| `vita experiment validate-interpretation <dir>` | Run interpretation validation gate |

### Removed from deterministic pipeline
- `answers` generation (moved to agent's `interpretation.json`)
- `hypothesis_outcomes` generation (moved to agent's `interpretation.json`)
- `surprises` detection (replaced by `candidate_anomalies` flags in summary)

### Convenience mode change
`vita experiment <manifest.yaml>` now runs only the deterministic steps:
`stage → run → summarize`. It does NOT conclude or present, because those
require agentic artifacts.

---

## State Machine Changes

### Lifecycle
```
planned → running → complete → interpreted → presented
```

- `complete` = all runs and diffs finished, summary generated
- `interpreted` = agent has written interpretation.json and it validates
- `presented` = HTML presentation generated

### Artifact tracking in `state.json`
New artifact keys:
```json
{
  "brief_json": "planning/brief.json",
  "brief_md": "planning/brief.md",
  "brief_validation_json": "planning/brief.validation.json",
  "summary_json": "conclusions/summary.json",
  "summary_md": "conclusions/summary.md",
  "interpretation_json": "conclusions/interpretation.json",
  "interpretation_md": "conclusions/interpretation.md",
  "interpretation_validation_json": "conclusions/interpretation.validation.json",
  "presentation_html": "presentation/index.html"
}
```

### Gates
- Before `run`: `brief_json` must exist and validate
- Before `present`: `interpretation_json` must exist and validate
- `mark_concluded()` replaced by `mark_interpreted()` + `mark_presented()`

---

## Skill Integration

The `vita-experiment-loop` skill must be updated to make agentic artifacts
**mandatory, not optional**. The skill workflow becomes:

1. Read manifest and research question
2. **Write `planning/brief.json`** following schema
3. **Run `vita experiment validate-brief`** — do not continue until it passes
4. Run `vita experiment stage` + `vita experiment run`
5. Run `vita experiment summarize`
6. Read `summary.json`, `diffs/*/diff.json`, `runs/*/results.json`
7. **Write `conclusions/interpretation.json`** following schema
8. **Run `vita experiment validate-interpretation`** — do not continue until it passes
9. Run `vita experiment present`

The skill must include the JSON schemas inline or by reference so the agent
knows exactly what structure to produce.

---

## Experiment Directory Layout (Final)

```
experiments/<id>/
├── manifest.yaml                          # Input contract (immutable)
├── state.json                             # Lifecycle state
├── planning/
│   ├── brief.json                         # Agentic: design rationale
│   ├── brief.md                           # Rendered from brief.json
│   └── brief.validation.json              # Validation result
├── inputs/
│   └── models/                            # Snapshotted model files
├── runs/
│   ├── baseline/
│   │   ├── manifest.json
│   │   └── results.json
│   ├── <variant>/
│   │   ├── manifest.json
│   │   └── results.json
│   └── ...
├── diffs/
│   ├── <comparison>/
│   │   └── diff.json
│   └── ...
├── analyses/
│   └── run_matrix.json
├── conclusions/
│   ├── summary.json                       # Deterministic evidence
│   ├── summary.md                         # Rendered from summary.json
│   ├── interpretation.json                # Agentic: reasoning chain
│   ├── interpretation.md                  # Rendered from interpretation.json
│   └── interpretation.validation.json     # Validation result
└── presentation/
    └── index.html                         # Final rendered presentation
```

---

## Implementation Plan

### Issue 1: Schema files and validation module
- Create `vita/schemas/brief.schema.json`
- Create `vita/schemas/interpretation.schema.json`
- Create `vita/schemas/validation.schema.json`
- Create `vita/experiment_validation.py` with brief and interpretation validators

### Issue 2: Refactor `conclude` → `summarize`
- Rename `generate_conclusions()` → `generate_summary()`
- Remove interpretive fields (`answers`, `hypothesis_outcomes`)
- Rename `surprises` → `candidate_anomalies`
- Update `experiment_conclusions.py` → `experiment_summary.py`
- Add `brief.md` and `interpretation.md` renderers

### Issue 3: State machine updates
- Add `interpreted` and `presented` states
- Replace `mark_concluded()` with `mark_interpreted()` + `mark_presented()`
- Add brief/interpretation artifact tracking
- Add validation gates

### Issue 4: CLI refactoring
- Rename `plan` → `stage`, `conclude` → `summarize`
- Add `validate-brief` and `validate-interpretation` subcommands
- Update convenience mode to stop at `summarize`
- Update handlers

### Issue 5: Presentation updates
- Update `experiment_presentation.py` to consume `interpretation.json`
- Render reasoning chains, mechanism explanations, confidence levels
- Visually separate observed results from agent interpretation

### Issue 6: Skill update
- Rewrite `vita-experiment-loop` skill with mandatory agentic steps
- Include schema references
- Add validation checkpoints

### Issue 7: Test updates
- Update all experiment tests for new function names and schemas
- Add validation gate tests
- Add brief/interpretation round-trip tests

---

## Non-Goals

- **LLM calls inside CLI subcommands.** The CLI remains purely deterministic.
  Interpretation is done by the agent in its own context.

- **Evaluating reasoning quality.** Validation gates check structural
  completeness and reference integrity, not whether the interpretation is
  insightful or correct.

- **Cross-experiment retrieval.** No index or search over interpretation
  artifacts across experiments. That can come later.

- **Backward compatibility with `vedalang-ec2`.** The experiment system is
  pre-1.0; breaking changes are acceptable per project policy.
