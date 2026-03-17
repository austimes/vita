# VedaOnline Compatibility Fixes (vedalang-cma)

Epic to fix all table format issues preventing VedaOnline sync.

## Child Issues

### vedalang-nm6: Fix ~FI_T table format
- Use attribute as column header (e.g., DEMAND), year as row index
- No 'value' column - FI_T doesn't support it
- Move demand projections to base `vt_*` file

### vedalang-9mh: Use ~TFM_DINS-AT for scenarios  
- Commodity price scenarios use TFM_DINS-AT (attributes as columns)
- Explicit process/commodity names (compiler expands wildcards)
- No 'value' column

### vedalang-4zs: Fix ~UC_T format
- UC_RHS as column header
- UC_N, region, year, limtype as row IDs
- No 'value' column

### vedalang-9hq: Remove ~FI_T from ScenTrade files
- Trade topology belongs in base `vt_*` file only
- ScenTrade files only contain ~TRADELINKS matrix

## Validation
All issues validated by:
1. `uv run vedalang compile vedalang/examples/minisystem.veda.yaml`
2. `uv run xl2times output/MiniSystem/` 
3. VedaOnline sync succeeds without errors
