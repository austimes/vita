# xl2times Local Modifications

This file tracks all local modifications made to the xl2times library, which is a third-party open-source project included in this repository for convenience.

**Policy**: xl2times should not be modified unless absolutely necessary. When changes are made, they must be documented here with justification.

## Changes

| Date | Commit | File | Description | Reason |
|------|--------|------|-------------|--------|
| 2025-12-23 | 675ee0c | (entire library) | Initial import of xl2times into repository | Include source locally for visibility and validation oracle |
| 2025-12-26 | b9ef966 | gams_scaffold/runmodel.gms | Changed GAMS call: `action=c` → `action=ce`, added `optfile=1` | Enable IIS/Conflict Refiner support for CPLEX to diagnose infeasible models |
| 2026-01-09 | (pending) | transforms.py | Added support for `~MILESTONEYEARS` tag in `process_time_periods()` | VedaLang emits explicit milestone years; xl2times had the tag defined but unimplemented |
| 2026-01-27 | (pending) | transforms.py | Fixed pandas 3.0 compatibility issues | Two bugs caused by pandas 3.0 breaking changes |
| 2026-03-04 | (pending) | main.py, utils.py | Added `--force-veda` flag to force VEDA filename filtering and require exactly one `SysSettings.*` root file | Needed strict VEDA-structure validation mode for VedaLang output checks |

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

### (pending) - Pandas 3.0 Compatibility Fixes (2026-01-27)

Modified `xl2times/transforms.py` with two fixes for pandas 3.0 breaking changes:

1. **`_process_comm_groups_vectorised()`** (lines 1636-1652):
   - In pandas 3.0, `groupby().apply()` no longer includes the groupby columns in the output
   - The previous code used `as_index=False` which now causes columns to be lost
   - Fix: Use regular groupby and reset the MultiIndex to recover group columns
   - This caused KeyError: "['region', 'process'] not in index" downstream

2. **`prepare_for_querying()`** (lines 1465-1476):
   - In pandas 3.0, stricter type coercion rejects assigning string values (e.g., 'EOH') to numeric columns
   - Fix: Convert column to object type before assigning string values
   - This caused TypeError: Invalid value 'EOH' for dtype 'float64'

3. **`include_cgs_in_topology()`** (lines 1526-1532):
   - Added early return guard when merge produces empty result
   - Preserves original topology columns with added nullable columns
   - Defensive measure to prevent downstream crashes with minimal models


### (pending) - `--force-veda` CLI mode (2026-03-04)

Modified `xl2times/main.py` and `xl2times/utils.py`:
- Added CLI flag `--force-veda` and threaded it into `read_xl()`
- `is_veda_based(..., force=True)` now enforces exactly one root `SysSettings.*` file
- In force mode, VEDA filename filtering is always applied

This was added to support strict structure validation when testing VedaLang-emitted model directories.
