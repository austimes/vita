# Fix ~FI_T table format (vedalang-nm6)

## Problem
The compiler currently emits ~FI_T tables with 'year', 'attribute', 'value' columns which VedaOnline rejects.

## Root Cause
- ~FI_T does NOT support a 'value' column
- VedaOnline expects attributes as column headers, year as row index

## Required Changes

### 1. Update _compile_demand_projections() in compiler.py
Current (wrong):
```python
rows.append({
    'region': region,
    'attribute': 'DEMAND',
    'commodity': commodity,
    'year': year,
    'value': dense_values[year],
})
```

Correct:
```python
rows.append({
    'region': region,
    'comm_out': commodity,
    'year': year,
    'DEMAND': dense_values[year],  # Attribute as column header
})
```

### 2. Update Excel emitter
- Map attribute names directly to column headers
- Remove any 'value' column emission for ~FI_T tables
- Ensure 'year' is a row index column, not a data column

### 3. Move demand projections to base file
- Demand projections should emit to `vt_*` base files, not `scen_*` files
- ~FI_T is only valid in Base and SubRES files

## Validation
- Compile minisystem.veda.yaml
- Run xl2times - should pass
- Sync with VedaOnline - should pass GeneratingYearsData step
