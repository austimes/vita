# Known-Answer Fixtures

These fixtures are intentionally small solver-backed examples used by the known-answer test suite.

For the modeler-facing catalog (current KA status + VedaLang to VEDA/TIMES
mapping to solved outputs), see
`docs/vedalang-user/known_answer_catalog.md`.

## Current Fixtures

1. `ka01_gas_supply_base.veda.yaml` — baseline gas-supply activity level.
2. `ka02_gas_supply_double.veda.yaml` — doubles gas-supply stock to produce a predictable doubled activity level.
3. `ka03_emissions_factor.veda.yaml` — emission-enabled variant that preserves the baseline solved activity signal.
4. `ka04_merit_order_dispatch.veda.yaml` — dual-supply fixture where zero-cost gas supply dominates expensive fallback.

## Authoring Rules

1. Keep IDs short to avoid TIMES identifier-length compile failures.
2. Keep arithmetic simple and deterministic for stable assertions.
3. Prefer explicit parameter deltas between paired fixtures so tests assert directional behavior.
4. Use large cost gaps (≥10×) for dispatch tests to avoid tie-driven flakiness.
