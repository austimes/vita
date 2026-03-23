# LLM-Facing Documentation Map

This file defines the purpose and ownership of every LLM-facing artifact in the
repo so conventions updates do not require hunting across duplicate docs.

## Source-of-Truth Rules

1. **Schema enums and syntax truth:** `vedalang/schema/vedalang.schema.json`
2. **Runtime enum/mapping accessors:** `vedalang/conventions.py`
3. **Modeling convention guidance truth:** `docs/vedalang-user/modeling-conventions.md`
4. **User-agent operation truth:** `skills/vedalang/SKILL.md`
5. **Experiment execution + diff truth:** `skills/vita/SKILL.md`
6. **Design-agent execution truth:** `AGENTS.md`
7. **Skills are wrappers where possible:** keep heavy prose in dedicated references
8. **Generated enum snippets:** maintained by `tools/sync_conventions.py`

## LLM-Facing Surface Inventory

| Artifact | Audience | Purpose | Keep / Combine Decision |
|----------|----------|---------|-------------------------|
| `skills/vedalang/SKILL.md` (+ `references/`) | VedaLang User Agent | Authoring workflow and CLI pipeline operation | **Keep** as canonical user-agent skill |
| `skills/vita/SKILL.md` (+ `references/`) | VedaLang User Agent | Canonical experiment execution, diff interpretation, and narrative output loop | **Keep** as the canonical run/analyze skill |
| `docs/vedalang-user/modeling-conventions.md` | VedaLang User Agent + LLM lint | Canonical modeling conventions narrative (non-binding) | **Keep** as the single conventions narrative source |
| `.agents/skills` | Skill-enabled agents | Local mirror of `skills/` for agents expecting `.agents/skills/*` | **Keep** in sync with `skills/` |
| `AGENTS.md` | VedaLang Design Agent | Design-agent operating rules and workflow | **Keep** as design persona root |
| `docs/vedalang-design-agent/SKILL.md` | VedaLang Design Agent | Internal dev skill for primitive exploration and schema evolution | **Keep** as canonical design-agent skill (not public) |
| `vedalang/lint/llm_assessment.py` prompt template | LLM lint runtime | System/user prompt assembly for structural assessment | **Keep** as executable prompt logic; pull enums from schema-derived helpers |
| `vedalang/lint/llm_unit_check.py` prompt template | LLM unit-check runtime | System/user prompt assembly for unit and coefficient checks | **Keep** as executable prompt logic aligned to schema unit rules |
| `vedalang/lint/prompts/res-assessment/v1/*` | LLM lint runtime | Versioned prompt text and response schema for reproducible evaluation | **Keep** as canonical prompt text artifacts |
| `vedalang/lint/prompts/unit-check/v1/*` | LLM lint runtime | Versioned unit-check prompt text and response schema for reproducible evaluation | **Keep** as canonical prompt text artifacts |
| `vedalang/lint/prompt_registry.py` | LLM lint runtime | Prompt version registry + immutable hash verification | **Keep** as the guardrail for append-only prompt evolution |
| `tools/veda_dev/evals/` | Design-agent eval runtime | Model/effort benchmark runner + scoring + reporting | **Keep** as the canonical eval scaffold for prompt/model selection |
| `skills/llm-lint-eval-evolution/SKILL.md` (+ `references/`) | Design-agent calibration workflow | Converts llm-lint misfires into benchmark case updates and prompt evolution | **Keep** as canonical calibration loop skill |

## Placement Rules

- **User-authoring LLM docs:** `docs/vedalang-user/`
- **Design-agent LLM docs:** `AGENTS.md` + `docs/vedalang-design-agent/`
- **Skill roots (canonical):** `skills/`
- **Skill compatibility path:** `.agents/skills` (symlink to `skills/`)
- **Executable prompts:** code modules under `vedalang/` or `tools/`
- **Prompt text assets:** `vedalang/lint/prompts/`

## Change Workflow

When updating modeling conventions or canonical enums:

1. Update schema and/or `docs/vedalang-user/modeling-conventions.md`
2. Run:
   ```bash
   uv run python tools/sync_conventions.py
   uv run python tools/sync_conventions.py --check
   ```
3. Run relevant tests:
   ```bash
   uv run pytest tests/test_conventions_sync.py tests/test_llm_assessment.py
   ```
4. Confirm no stale duplicates in LLM-facing docs:
   ```bash
   rg -n "GENERATED:|Canonical Enums|scenario categories|Valid stages|Valid types" docs README.md AGENTS.md
   ```
