# Feature Demo Examples

Use this folder for focused feature demonstrations (timeslices, constraints,
bounds, trade, demand, facilities).

Typical contents:
- one-feature-per-file demos
- regression examples for specific schema/compiler features
- `example_with_facilities.veda.yaml` demonstrates facility templates,
  top-N selection + aggregation, safeguard intensity constraints,
  no-backswitch transition ordering, and fuel-mix constraints.
- Facility fuel switching currently requires separate `process_variants` per
  fuel option. A single variant that lists multiple alternate fuel inputs cannot
  express optimizer-selected fuel shares or no-backslide constraints.
