# Facility Modes (PRD 2026-03-05)

This note records the design shift from facility fuel switching via separate
technology variants + activity-share constraints to a mode-based, capacity
partition formulation.

## Core distinction

- `process_variant`: technology archetype in the global process library.
- `facility_template.variants[].modes[]`: operational configurations for a
  single physical facility variant (e.g. coal, retrofit_to_ng, retrofit_to_h2).

Modes are compiled to separate physical processes that share service output, with
facility-level `UC_CAP` constraints coupling their capacities.

## Why this replaces the previous approach

The old facility implementation depended on multiple user-authored process
variants plus `UC_ACT` constraints (`FAC_NB_*`, `FAC_MIX_*`). That made
commodity-group fuel switching and retrofit semantics hard to express and tied
no-backslide logic to activity proxies.

The new implementation keeps LP linearity while making retrofit capacity,
ramp limits, and no-backsliding explicit in capacity space.

## Current compiler behavior

For each selected facility entity and template variant:

- compile one synthetic process variant per mode;
- set retrofit CAPEX via `investment_cost` (`NCAP_COST`) on retrofit modes;
- emit `FAC_CAP_COUPLE_*` constraints using `uc_cap`;
- emit optional `FAC_CAP_MONO_*` constraints for no-backsliding;
- emit optional `FAC_CAP_RAMP_*` constraints when `ramp_rate` is provided.

Safeguard intensity constraints remain activity-based (`FAC_INT_*`) but are now
applied across mode processes.
