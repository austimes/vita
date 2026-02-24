---
name: vedalang-modeling-conventions
description: >-
  Advisory VedaLang modeling conventions for service-oriented, physical-only
  RES design. Use when authoring or reviewing toy_*/example models for
  role/variant structure, stage and commodity typing, cases overlays, and
  diagnostics boundaries.
---

# VedaLang Modeling Conventions (Skill)

This skill loads the canonical modeling conventions for VedaLang.
It is intentionally a thin wrapper and should not duplicate convention content.

**Primary reference in this skill folder:**
[`references/modeling-conventions.md`](references/modeling-conventions.md)

That file is symlinked to the canonical conventions document in `docs/`.

Read that file before authoring or reviewing any VedaLang model. It covers:

- Three-layer framework (guidance → lint → compiler)
- Service-level roles and technology variants
- Primary supply roles (zero-input supply is valid)
- Physical-only RES by default (no pseudo-technology carveouts)
- Naming conventions (snake_case, verb-noun roles, descriptive variants)
- Stage and commodity typing discipline
- Emissions as attributes (emission_factors, not outputs)
- Commodity namespace conventions (energy:, service:, emission:, etc.)
- Cases as scenario overlays
- Solve-independent diagnostics
- Authoring checklist
