# Feature Demo Examples

Use this folder for focused feature demonstrations (timeslices, constraints,
bounds, trade, demand, facilities).

Typical contents:
- one-feature-per-file demos
- regression examples for specific schema/compiler features
- `example_with_facilities.veda.yaml` demonstrates facility templates,
  top-N selection + aggregation, safeguard intensity constraints, and
  mode-based fuel switching constraints (`UC_CAP` coupling/no-backslide/ramp).
- Facility fuel switching now uses template `variants[].modes[]` and compiles
  one physical process per mode. Retrofit costs are represented as `NCAP_COST`
  on retrofit modes; no capability commodities are introduced.
