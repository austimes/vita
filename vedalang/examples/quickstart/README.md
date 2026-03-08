# Quickstart Examples

Use this folder for the smallest v0.2 end-to-end examples that introduce the
current VedaLang object model.

`mini_plant.veda.yaml` is the shortest complete run-scoped example. Read its
top-level blocks as:

```yaml
# Schema version for the example file.
dsl_version: "0.2"

# Commodities declare the fuel, carrier, and service namespaces.
commodities: ...

# Technologies define concrete process behavior and coefficients.
technologies: ...

# Technology roles group allowed technologies under a service contract.
technology_roles: ...

# Spatial layers and region partitions define the geographic compile target.
spatial_layers: ...
region_partitions: ...

# Sites anchor assets to coordinates and region membership.
sites: ...

# Facilities declare installed stock at each site.
facilities: ...

# Runs choose the base year and region partition to compile.
runs: ...
```

Typical contents:
- minimal run-scoped models with `commodities`, `technologies`,
  `technology_roles`, `sites`, `facilities`, and `runs`
- small supply/conversion/delivery chains that compile cleanly through the
  Excel and xl2times path
- first-run validation examples that can be used with
  `uv run vedalang validate <file> --run <run_id>`
