# unit-check prompt changelog

## v2

- Added required per-finding classification fields for deterministic eval
  scoring: `error_code`, `error_family`, and `difficulty`.
- Added controlled unit-code taxonomy and difficulty rubric.

## v1

- Initial externalized prompt set extracted from `vedalang/lint/llm_unit_check.py`.
- Added explicit JSON response schema for status/findings payload.
