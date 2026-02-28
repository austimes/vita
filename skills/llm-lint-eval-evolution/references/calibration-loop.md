# Calibration Loop

## 1) Open tracking issue

Use `bd` for every calibration pass.

```bash
bd create "Calibrate llm-lint extras for <case>" \
  --description "Assess additional findings and decide fixture vs linter/prompt correction" \
  -t task -p 2 --json
bd update <id> --status in_progress --json
```

## 2) Run a restartable sweep and persist artifacts

Always write both run artifact and cache so long runs are restartable.

```bash
uv run vedalang-dev eval run \
  --profile ci \
  --no-judge \
  --progress \
  --max-concurrency 4 \
  --cache tmp/evals/cache-calibration.json \
  --out tmp/evals/eval-calibration.json
```

Notes:
- Cache is reused by default on later runs with the same `--cache` path.
- Use `--no-cache` only when you intentionally want fresh calls.

## 3) Extract and cluster extras

List rows where extra findings were produced:

```bash
jq -r '.results[]
  | select(.status=="ok" and .additional_issues_count>0)
  | [.candidate_id, .case_id, (.additional_issue_codes|join(","))]
  | @tsv' tmp/evals/eval-calibration.json
```

Count repeated extras by case+code:

```bash
jq -r '.results[]
  | select(.status=="ok" and .additional_issues_count>0)
  | [.case_id, (.additional_issue_codes[])]
  | @tsv' tmp/evals/eval-calibration.json \
| sort | uniq -c | sort -nr
```

Inspect full diagnostics for a specific row:

```bash
jq '.results[]
  | select(.candidate_id=="gpt-5-mini:medium" and .case_id=="s02@v2")
  | {candidate_id, case_id, diagnostics}' tmp/evals/eval-calibration.json
```

## 4) Decide: fixture gap or linter/prompt error

For each repeated extra finding, perform manual review against the source fixture.

Decision rubric:
- Real issue in fixture: add/update expected labels and deterministic references so it is no longer "extra".
- Invalid/speculative issue: tighten prompt instructions/response schema and parsing guards.
- New valid class not yet tracked: add a new controlled `error_code` and labels in dataset.

## 5) Update benchmark corpus

Dataset file:
- `tools/veda_dev/evals/datasets/llm_lint_cases.yaml`

Fixture roots:
- `tools/veda_dev/evals/fixtures/ground_truth/structure/`
- `tools/veda_dev/evals/fixtures/ground_truth/units/`

Required case fields:
- `check_id`, `category`, `engine`, `source`
- `expected.labels[]` with:
  - `error_code`
  - `error_family`
  - `difficulty` (`easy|medium|hard`)
  - `expected_presence` (`present|absent`)

Keep profile lists (`smoke`, `ci`, `deep`) intentional and size-controlled.

## 6) Evolve prompts (append-only)

Prompt roots:
- Structure: `vedalang/lint/prompts/res-assessment/`
- Units: `vedalang/lint/prompts/unit-check/`

Workflow:
1. Copy latest prompt version directory to a new `vN`.
2. Edit `system.txt`, `user_prefix.txt`, `response_schema.json`, `CHANGELOG.md`.
3. Update `manifest.json` hash for the new version.

Example hash update command:

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from vedalang.lint.prompt_registry import PromptBundle, compute_prompt_bundle_hash

check_id = "llm.units.component_quorum"
version = "v4"
dir_path = Path("vedalang/lint/prompts/unit-check") / version
bundle = PromptBundle(check_id=check_id, version=version, directory=dir_path)
manifest_path = bundle.manifest_path
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["content_sha256"] = compute_prompt_bundle_hash(bundle)
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(manifest["content_sha256"])
PY
```

Do not edit old prompt versions after release into eval history.

## 7) Validate and compare

Run targeted tests:

```bash
uv run pytest \
  tests/test_prompt_registry.py \
  tests/test_eval_framework.py \
  tests/test_llm_categories.py \
  tests/test_llm_assessment.py \
  tests/test_llm_unit_check.py -q
```

Run eval checks:

```bash
uv run vedalang-dev eval run --profile smoke --no-judge --progress \
  --cache tmp/evals/cache-smoke-calibration.json \
  --out tmp/evals/eval-smoke-calibration.json

uv run vedalang-dev eval run --profile ci --no-judge --progress \
  --cache tmp/evals/cache-ci-calibration.json \
  --out tmp/evals/eval-ci-calibration.json
```

Compare candidate movement:

```bash
uv run vedalang-dev eval compare \
  tmp/evals/eval-before.json \
  tmp/evals/eval-ci-calibration.json
```

Acceptance focus:
- `label_match` and `control_match` improve or stay stable
- `additional_issues_count` decreases on calibrated cases
- latency/cost do not regress unexpectedly for default candidate

## 8) Close tracking

```bash
bd close <id> --reason "Completed" --json
```

If new follow-up work is discovered, create linked issues:

```bash
bd create "Follow-up: <title>" --deps discovered-from:<id> -t task -p 2 --json
```
