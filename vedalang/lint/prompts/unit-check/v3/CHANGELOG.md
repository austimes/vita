# unit-check prompt v3

- tightened instructions to suppress speculative/advisory findings
- constrained `UNIT_OTHER` to concrete, actionable inconsistencies only
- clarified handling of `lhv_mj_per_unit`/`hhv_mj_per_unit` so absolute-value
  interpretation alone does not trigger false positives
- added explicit preference for `status=pass` with empty findings when consistent
- added brevity constraints (max findings, no duplicates)
