# IIS (Irreducible Infeasible Set) Diagnostics

When a TIMES model is infeasible, the VedaLang toolchain can provide detailed diagnostics about which constraints are in conflict using CPLEX's Conflict Refiner.

## How It Works

1. **Solver Profiles**: Use `--solver CPLEX` for debug runs with IIS enabled
2. **Automatic cplex.opt**: When using CPLEX, the toolchain generates a `cplex.opt` file with:
   - `iis 1` — Run conflict refiner if infeasible
   - `conflictdisplay 2` — Detailed IIS output
   - `names 1` — Preserve GAMS names in output
   - `rerun auto` — Better diagnostics around presolve

3. **Output Parsing**: The `.lst` file is parsed for the "Conflict Refiner" section

## Accessing IIS Information

After a run, the `RunResult.diagnostics["iis"]` field contains:

```python
{
    "available": True,  # Was IIS generated?
    "counts": {
        "equations": 3,
        "variables": 2,
        "indicator_constraints": None,
        "sos_sets": None,
    },
    "members": [
        {"role": "upper", "symbol": "EQ_DEMAND(2020)", "detail": "< 100"},
        {"role": "lower", "symbol": "VAR_CAP(PP_CCGT)", "detail": "> 0"},
        # ...
    ],
    "raw_section": "..."  # Raw text from listing
}
```

## Member Roles

| Role | Description |
|------|-------------|
| `upper` | Upper bound constraint in conflict |
| `lower` | Lower bound constraint in conflict |
| `equality` | Equality constraint in conflict |
| `fixed` | Fixed variable in conflict |
| `sos` | SOS set member in conflict |
| `indic` | Indicator constraint in conflict |

## Usage Example

```bash
# Run with CPLEX for IIS diagnostics
uv run vedalang-dev pipeline model.veda.yaml --solver CPLEX --no-solver --json

# Or directly:
uv run vedalang-dev run-times dd_output/ --solver CPLEX --times-src ~/TIMES_model
```

## Interpreting IIS Results

The IIS tells you the **minimal set of constraints** that cannot all be satisfied simultaneously. To fix the model:

1. **Identify the conflicting constraints** from `members`
2. **Trace back to VedaLang source** — map TIMES equation names to your model definitions
3. **Relax one or more constraints** — adjust bounds, capacities, or demands

Common TIMES equation patterns:
- `EQ_COMBAL` — Commodity balance equations
- `EQ_PTRANS` — Process transformation equations
- `VAR_CAP` — Capacity variables
- `VAR_NCAP` — New capacity variables

## Solver Recommendations

| Profile | Solver | Use Case |
|---------|--------|----------|
| **Fast** | CBC | Quick iteration, no IIS |
| **Debug** | CPLEX | Infeasibility diagnosis with IIS |

The fast profile is recommended for normal development; switch to debug when you encounter infeasibilities that need investigation.
