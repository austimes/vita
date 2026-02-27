# res-assessment prompt changelog

## v2

- Added explicit per-finding classification fields for eval scoring:
  `error_code`, `error_family`, and `difficulty`.
- Added controlled structural codebook and difficulty rubric for deterministic
  benchmark slicing.

## v1

- Initial externalized prompt set extracted from `vedalang/lint/llm_assessment.py`.
- Added explicit instruction that modeling conventions are provided in user prompt and should be treated as authoritative guidance.
