---
name: vedalang-modeling-conventions
description: >-
  Advisory VedaLang modeling conventions for service-oriented, physical-only
  RES design. Use when authoring or reviewing current public-surface example models for
  technology_role/technology structure, asset stock declarations, run-scoped
  compilation, and diagnostics boundaries.
---

# VedaLang Modeling Conventions (Skill)

This skill loads the canonical modeling conventions for VedaLang.
It is intentionally a thin wrapper and should not duplicate convention content.

**Primary reference in this skill folder:**
[`references/modeling-conventions.md`](references/modeling-conventions.md)

That file is symlinked to the canonical conventions document in `docs/`.

Read that file before authoring or reviewing any VedaLang model. It covers:

- Three-layer framework (guidance → lint → compiler)
- Service-level technology roles and technologies
- Primary supply roles (zero-input supply is valid)
- Physical-only RES by default (no pseudo-technology carveouts)
- Naming conventions (snake_case, service-oriented role IDs, descriptive technology IDs)
- Stage and commodity typing discipline
- Explicit process unit semantics (activity as extensive, capacity as power or `<unit>/yr`)
- Emissions as attributes (emission_factors, not outputs)
- Commodity namespace conventions (primary:, secondary:, service:, emission:, etc.)
- Runs as compile selections and scenario overlays where present
- Solve-independent diagnostics
- Authoring checklist
