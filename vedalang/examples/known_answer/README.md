# Known-Answer Fixtures

These fixtures are intentionally small solver-backed examples used by the known-answer test suite.

## Current Fixtures

1. `ka01_gas_supply_base.veda.yaml` — baseline gas-supply activity level.
2. `ka02_gas_supply_double.veda.yaml` — doubles gas-supply stock to produce a predictable doubled activity level.

## Authoring Rules

1. Keep IDs short to avoid TIMES identifier-length compile failures.
2. Keep arithmetic simple and deterministic for stable assertions.
3. Prefer explicit parameter deltas between paired fixtures so tests assert directional behavior.
