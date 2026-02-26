# Monetary Conversion Data

This directory stores deterministic conversion inputs used by VedaLang
monetary normalization.

## Current files

- `fx_aud_usd_world_bank_pa_nus_fcrf.yaml`
  - Annual AUD/USD exchange rates (2000-2024)
  - Source: World Bank indicator `PA.NUS.FCRF`
  - Definition in source series: `AUD per USD` (period average)
  - This file also includes the inverse `USD per AUD`

## Notes

- Values are annual period averages.
- Future compiler normalization can use these factors to convert source
  monetary units like `MUSD23` to canonical units like `MAUD24`.
