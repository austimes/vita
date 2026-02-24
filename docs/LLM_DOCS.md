# LLM-Facing Documentation Map

This file defines the purpose and ownership of every LLM-facing artifact in the
repo so conventions updates do not require hunting across duplicate docs.

## Source-of-Truth Rules

1. **Schema enums and syntax truth:** `vedalang/schema/vedalang.schema.json`
2. **Modeling convention guidance truth:** `docs/vedalang-user/modeling-conventions.md`
3. **Design-agent execution truth:** `AGENTS.md`
4. **Skills are wrappers:** `.agents/skills/*/SKILL.md` should point to canonical docs, not restate them
5. **Generated enum snippets:** maintained by `tools/sync_conventions.py`

## LLM-Facing Surface Inventory

| Artifact | Audience | Purpose | Keep / Combine Decision |
|----------|----------|---------|-------------------------|
| `docs/vedalang-user/LLMS.md` | VedaLang User Agent | Authoring workflow and syntax usage | **Keep** as user authoring guide; do not duplicate canonical enum values except generated blocks |
| `docs/vedalang-user/modeling-conventions.md` | VedaLang User Agent + LLM lint | Canonical modeling conventions narrative (non-binding) | **Keep** as the single conventions narrative source |
| `.agents/skills/vedalang-modeling-conventions/SKILL.md` | Skill-enabled agents | Thin pointer to conventions document | **Keep** as a wrapper only; no duplicated convention prose |
| `AGENTS.md` | VedaLang Design Agent | Design-agent operating rules and workflow | **Keep** as design persona root |
| `docs/vedalang-design-agent/exploration_prompt.md` | VedaLang Design Agent | Structured experimentation protocol | **Keep** as a specialist prompt, scoped to design exploration |
| `vedalang/lint/llm_assessment.py` prompt template | LLM lint runtime | System/user prompt assembly for structural assessment | **Keep** as executable prompt logic; pull enums from schema-derived helpers |

## Placement Rules

- **User-authoring LLM docs:** `docs/vedalang-user/`
- **Design-agent LLM docs:** `AGENTS.md` + `docs/vedalang-design-agent/`
- **Skill wrappers:** `.agents/skills/`
- **Executable prompts:** code modules under `vedalang/` or `tools/`

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
