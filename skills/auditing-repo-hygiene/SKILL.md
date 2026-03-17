---
name: auditing-repo-hygiene
description: "Audits the vedalang repository for cleanliness, dead code, stale experiments, documentation drift, and agent-first readiness. Creates bd issues for all findings. Use when asked to audit, clean up, assess repo hygiene, or check repository health."
---

# Repository Hygiene Audit

Performs a comprehensive audit of the vedalang repository and creates actionable `bd` issues for everything that needs attention. The goal is to keep the repo clean, simple, lightweight, and agent-friendly.

## Scope

**Audit these directories:**
- `vedalang/` — core language, compiler, schema, examples, heuristics
- `tools/` — dev CLI, emitter, check, patterns, LSP, and Vita command handlers
- `tests/` — all test files and fixtures
- `experiments/` — design agent experiment outputs
- `fixtures/` — golden test fixtures
- `docs/` — PRDs, status, design-agent docs, user docs, reference
- `rules/` — pattern library, decision tree, constraints
- `veda/` — VEDA support files
- Root files — `AGENTS.md`, `HISTORY.md`, `STATUS.md`, `pyproject.toml`, `README.md`

**ALWAYS IGNORE these directories (they are embedded third-party codebases):**
- `xl2times/` — third-party validation oracle, never audit
- `times/` — TIMES documentation and solver files, never audit
- `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`

## Audit Checklist

Work through each category below. For every finding, note the category, file(s), and a concise description of what's wrong and what to do about it.

### 1. Dead Code & Unused Modules

- Search for Python files with no imports from other files (orphaned modules)
- Check for functions/classes that are defined but never called/referenced
- Look for commented-out code blocks (more than 3 lines)
- Check `pyproject.toml` entry points — do all CLI commands still resolve?
- Check for unused dependencies in `pyproject.toml`

```bash
# Find Python files, then check if they're imported anywhere
find vedalang/ tools/ -name '*.py' -not -name '__init__.py' | while read f; do
  mod=$(basename "$f" .py)
  refs=$(grep -rl "$mod" vedalang/ tools/ tests/ --include='*.py' | grep -v "$f" | wc -l)
  if [ "$refs" -eq 0 ]; then echo "ORPHAN: $f"; fi
done
```

### 2. Stale Tests

- Run `uv run pytest --collect-only -q 2>&1` and check for collection errors or warnings
- Look for test files that test modules/features that no longer exist
- Check for `@pytest.mark.skip` or `@pytest.mark.xfail` with no tracking issue
- Look for tests with hardcoded paths or values that may have drifted
- Check `tests/failures/` — are failure test cases still relevant?
- Check `tests/agent_design/` — is this still needed?

### 3. Stale Experiments

Experiments in `experiments/` are design agent outputs from Phase 1. For each:
- Does the experiment correspond to a closed design challenge?
- Has the pattern been lifted into VedaLang schema or `rules/patterns.yaml`?
- If the experiment is fully captured elsewhere, flag it for removal

**Rule:** If an experiment's insights are already in HISTORY.md, the schema, or patterns.yaml, it can be deleted.

### 4. Documentation Drift

- **AGENTS.md vs reality:** Do the phase descriptions, design challenge table, and tool descriptions match the current codebase?
- **STATUS.md vs bd issues:** Run `bd list --all` and compare against STATUS.md — are they in sync?
- **HISTORY.md completeness:** Are recent schema changes and features documented?
- **docs/vedalang-user/:** Does user documentation match current schema?
- **docs/vedalang-design-agent/:** Are design agent docs current?
- **docs/prds/:** Are PRDs still relevant or superseded?
- **README.md:** Does it accurately describe the project?
- **rules/patterns.yaml:** Do patterns match current schema constructs?

### 5. Code Quality

- Run `uv run ruff check .` and note any findings
- Check for TODO/FIXME/HACK comments that should be tracked as issues:
  ```bash
  grep -rn 'TODO\|FIXME\|HACK\|XXX' vedalang/ tools/ tests/ --include='*.py'
  ```
- Check for overly long files (>500 lines) that could be split
- Check for duplicate or near-duplicate logic across modules
- Look for bare `except:` or `except Exception:` that swallow errors silently

### 6. Fixture & Example Hygiene

- Do all examples in `vedalang/examples/` compile successfully?
  ```bash
  uv run python tools/repo_hygiene/check_examples_compile.py --json
  ```
  - The sweep is run-aware: for multi-run models it records the expected
    `E002` run-selection response when compiled without `--run`, then compiles
    each declared run ID explicitly.
  - Treat only entries in `failures` as true compile failures.
- Are fixtures in `fixtures/` still referenced by tests?
- Are there output directories (`output/`, `output_invalid/`, `tmp/`) with stale artifacts?

### 7. Agent-First Repository Assessment

Score the repo on agent-friendliness (1-5 for each):

| Criterion | What to Check |
|-----------|---------------|
| **Discoverability** | Can an agent find what it needs via AGENTS.md, file naming, directory structure? |
| **Self-documenting** | Are schemas, types, and naming clear enough to work without prose docs? |
| **Feedback loops** | Do `vedalang validate`, `uv run pytest`, `uv run ruff check` give clear, actionable output? |
| **Minimal ambiguity** | Are there naming conflicts, multiple ways to do the same thing, or unclear conventions? |
| **Clean boundaries** | Are concerns well-separated (schema vs compiler vs emitter vs CLI)? |
| **Onboarding speed** | Could a new agent session be productive within its first 2-3 tool calls? |

### 8. Configuration & Build Hygiene

- Check `.gitignore` covers all generated artifacts
- Look for `.DS_Store` files that shouldn't be committed
- Check `pyproject.toml` for stale or mismatched metadata
- Verify `uv.lock` is up to date: `uv lock --check`
- Check for any hardcoded absolute paths

### 9. Issue Tracker Hygiene

- Run `bd list` to check open issues — are any stale or completed but not closed?
- Run `bd list --all` to check all issues — do closed issues match HISTORY.md?
- Are there orphaned sub-issues whose parent was closed?
- Are issue labels consistent and useful?

## Output Workflow

### Step 1: Perform the Audit

Work through all 9 categories above. Collect findings as a list:

```
Category | File(s) | Finding | Suggested Action | Priority
```

### Step 2: Create a PRD (if significant findings)

If there are 5+ findings, create a lightweight PRD at `docs/prds/repo_hygiene_YYYY_MM.md`:

```markdown
# Repository Hygiene Audit — YYYY-MM

## Summary
<2-3 sentence overview of findings>

## Findings by Category
<Grouped findings from the audit>

## Recommendation
<Overall assessment and prioritized action plan>
```

### Step 3: Create bd Issues

Create one parent epic issue:

```bash
bd create "Repository hygiene audit — YYYY-MM" \
  --type epic \
  --description "<summary of audit scope and findings count>" \
  --labels hygiene,cleanup \
  --priority 2
```

Then create child issues for each actionable finding (group small related findings):

```bash
bd create "<concise title>" \
  --parent <EPIC-ID> \
  --description "<what to do, which files, acceptance criteria>" \
  --labels hygiene,<category-label> \
  --priority <2-3>
```

**Category labels:** `dead-code`, `stale-tests`, `stale-experiments`, `docs-drift`, `code-quality`, `fixture-hygiene`, `agent-first`, `build-hygiene`, `issue-hygiene`

### Step 4: Update HISTORY.md

If the audit leads to immediate removals (e.g., deleting stale experiments), append a section:

```markdown
## Repository Hygiene — YYYY-MM-DD

- Removed `experiments/X/` — insights captured in HISTORY.md Phase 1 and patterns.yaml
- Removed `tests/test_old_thing.py` — tested feature that was refactored in Phase 2
- <other removals with rationale>
```

### Step 5: Summarize

Present a final summary to the user:

1. **Audit score card** — agent-first scores (the table from §7)
2. **Issues created** — list every bd issue ID, title, and priority
3. **Immediate actions taken** — anything that was cleaned up directly
4. **Recommendations** — top 3 highest-impact improvements

## Tips for a Better Audit

- **Be aggressive about deletion.** If something isn't actively used, flag it. The repo has git history as a safety net.
- **Group small findings.** Don't create 20 issues for 20 TODO comments — one "Clean up TODO comments" issue is fine.
- **Check cross-references.** When flagging dead code, verify it's truly dead — check tests, CLI entry points, and dynamic imports.
- **Time-box.** The audit should take 15-30 minutes of agent time. Don't go spelunking into every function body.
- **Be specific in issues.** Each issue should name exact files and have clear acceptance criteria so a sub-agent can execute it independently.
