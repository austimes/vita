# xl2times Local Modifications

This file tracks all local modifications made to the xl2times library, which is a third-party open-source project included in this repository for convenience.

**Policy**: xl2times should not be modified unless absolutely necessary. When changes are made, they must be documented here with justification.

## Changes

| Date | Commit | File | Description | Reason |
|------|--------|------|-------------|--------|
| 2025-12-23 | 675ee0c | (entire library) | Initial import of xl2times into repository | Include source locally for visibility and validation oracle |
| 2025-12-26 | b9ef966 | gams_scaffold/runmodel.gms | Changed GAMS call: `action=c` → `action=ce`, added `optfile=1` | Enable IIS/Conflict Refiner support for CPLEX to diagnose infeasible models |
| 2026-01-09 | (pending) | transforms.py | Added support for `~MILESTONEYEARS` tag in `process_time_periods()` | VedaLang emits explicit milestone years; xl2times had the tag defined but unimplemented |

## Details

### b9ef966 - IIS/Conflict Refiner Support (2025-12-26)

Modified `xl2times/gams_scaffold/runmodel.gms`:
- Changed `action=c` to `action=ce` (compile and execute)
- Added `optfile=1` to enable solver option files

This change was required to enable CPLEX's IIS (Irreducibly Inconsistent Subsystem) feature, which identifies the minimal set of conflicting constraints when a model is infeasible.

### (pending) - ~MILESTONEYEARS Support (2026-01-09)

Modified `xl2times/transforms.py`:
- Extended `process_time_periods()` to check for `~MILESTONEYEARS` table before falling back to `~TIMEPERIODS`
- Supports VEDA format: `type` column ("Endyear"/"milestoneyear") + year value column
- Uses milestone years directly as TIMES representative years instead of computing midpoints
- Endyear row defines the model horizon end for computing last period duration

The `~MILESTONEYEARS` tag was already defined in xl2times (`datatypes.py` and `veda-tags.json`) but had no processing logic. This change completes that feature, enabling VedaLang to use `~MILESTONEYEARS` as an alternative to `~ACTIVEPDEF` + `~TIMEPERIODS` (per VEDA documentation).
