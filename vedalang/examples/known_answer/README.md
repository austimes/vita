# Known-Answer Fixtures

These fixtures are intentionally small solver-backed examples used by the known-answer test suite.

For the modeler-facing catalog (current KA status + VedaLang to VEDA/TIMES
mapping to solved outputs), see
`docs/vedalang-user/known_answer_catalog.md`.

## Current Fixtures

1. `ka01_gas_supply_base.veda.yaml` — baseline gas-supply activity level.
2. `ka02_gas_supply_double.veda.yaml` — doubles gas-supply stock to produce a predictable doubled activity level.
3. KA05 traceability uses the KA01/KA02 paired-variant solver assertion path (`test_ka02_double_capacity_doubles_supply_activity`); there is intentionally no standalone `ka05_*.veda.yaml` fixture.
4. `ka03_emissions_factor.veda.yaml` — emission-enabled variant that preserves the baseline solved activity signal.
5. `ka04_merit_order_dispatch.veda.yaml` — dual-supply fixture where zero-cost gas supply dominates expensive fallback.
6. `ka06_stock_sufficient.veda.yaml` — stock-sufficient demand-chain fixture with no solved new-capacity expansion.
7. `ka07_demand_spike.veda.yaml` — demand-spike variant that increases solved activity and triggers positive solved `VAR_NCAP` on the same supply process.
8. `ka08_build_limit_tight.veda.yaml` and `ka08_build_limit_loose.veda.yaml` — paired fallback-build-limit fixtures for solved backup suppression versus expansion checks.
9. `ka09_zone_opportunity_tight.veda.yaml` and `ka09_zone_opportunity_loose.veda.yaml` — paired zone-opportunity fixtures that shift solved activity between process classes.
10. `ka10_network_transfer_open.veda.yaml` and `ka10_network_transfer_constrained.veda.yaml` — paired two-region transfer-direction fixtures for solved regional dispatch-flip checks.
11. `ka11_fleet_distribution_base.veda.yaml` and `ka11_fleet_distribution_stress.veda.yaml` — weighted-fleet baseline and stress fixtures with deterministic regional allocation assertions.
12. `ka12_temporal_growth_annual.veda.yaml` — annual-growth adjusted stock fixture that scales solved activity from 2020 to 2030.
13. KA13 diagnostics coverage intentionally reuses `ka08_build_limit_tight.veda.yaml` as the stressed bound fixture so assertion failures can point to stable diagnostics artifacts.
14. `ka14_run_selection_multi_run.veda.yaml` — multi-run fixture where selecting `reg1_2020` versus `reg1_2030` yields deterministic solved-output differences.

## Authoring Rules

1. Keep IDs short to avoid TIMES identifier-length compile failures.
2. Keep arithmetic simple and deterministic for stable assertions.
3. Prefer explicit parameter deltas between paired fixtures so tests assert directional behavior.
4. Use large cost gaps (≥10×) for dispatch tests to avoid tie-driven flakiness.
5. For proportional/custom fleet tests, pass deterministic weight maps through the shared solver harness instead of ad-hoc in-test compile plumbing.
