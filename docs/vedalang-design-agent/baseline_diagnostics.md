# Baseline Diagnostics - VedaLang Toolchain

Generated: 2024-12-21
Updated: 2024-12-21 (Added structured diagnostic support)

## Overview

This document captures the baseline state of the VedaLang toolchain and xl2times diagnostic capabilities.

## Diagnostic Infrastructure

### Key Improvement: Structured Diagnostics

xl2times now emits structured diagnostics in JSON format instead of crashing silently:

- `--diagnostics-json <path>` - Outputs structured diagnostics to file
- `--manifest-json <path>` - Outputs parsing manifest

Even on exceptions, diagnostics are captured with full traceback context.

### Diagnostic Codes

| Code | Severity | Description |
|------|----------|-------------|
| `MISSING_REQUIRED_TABLE` | error | A required VEDA table is not present |
| `MISSING_REQUIRED_COLUMN` | error | A required column is missing from a table |
| `INVALID_SCALAR_TABLE` | error | A table expected to have exactly one value has wrong shape |
| `MISSING_TIMESLICES` | warning | No timeslice definitions found |
| `INTERNAL_ERROR` | error | Uncaught exception during processing |

### Example Diagnostics Output

```json
{
  "version": "1.0.0",
  "status": "error",
  "xl2times_version": "0.3.0",
  "timestamp": "2025-12-21T18:30:34.968151",
  "diagnostics": [
    {
      "severity": "error",
      "code": "INTERNAL_ERROR",
      "message": "Uncaught exception during processing: 'tact'",
      "context": {
        "exception_type": "KeyError",
        "message": "'tact'",
        "traceback": "..."
      }
    }
  ],
  "summary": {
    "error_count": 1,
    "warning_count": 0,
    "info_count": 0
  }
}
```

## Toolchain Status

### Python Pipeline: ✅ WORKING

The Python components work end-to-end without exceptions:

| Tool | Status | Notes |
|------|--------|-------|
| `vedalang compile` | ✅ Pass | Compiles .veda.yaml → TableIR |
| `vedalang-dev emit-excel` | ✅ Pass | Emits TableIR → Excel files |
| `vedalang validate` | ✅ Pass | Orchestrates full pipeline |

### xl2times Validation: ⚠️ EXPECTED FAILURE WITH DIAGNOSTICS

xl2times fails on minimal VedaLang output because **system tables are missing**, but now produces structured diagnostics.

**Logged warnings:**
```
Required table ~BOOKREGIONS_MAP is missing (required for region processing)
Required table ~STARTYEAR is missing (required for time period processing)
Required table ~CURRENCIES is missing (required for currency validation)
```

**Error (captured in diagnostics.json):**
```
INTERNAL_ERROR: Uncaught exception during processing: 'tact'
```

**Root cause:** xl2times requires various system tables and column mappings that VedaLang doesn't yet emit.

## Test Results

```
57 tests passed (2024-12-21)

Key test files:
- test_vedalang_compiler.py - VedaLang → TableIR compilation
- test_emit_excel.py - TableIR → Excel emission
- test_validate.py - Full pipeline orchestration
- test_xl2times_integration.py - xl2times with fixture models
- test_require_table_diagnostics.py - Diagnostic code tests
```

## What VedaLang Can Currently Express

From `quickstart/mini_plant.veda.yaml`:

```yaml
model:
  name: MiniModel
  regions: [REG1]
  
  commodities:
    - name: ELC
      type: energy
      unit: PJ
    - name: NG
      type: energy
      unit: PJ
  
  processes:
    - name: PP_CCGT
      sets: [ELE]
      activity_unit: PJ
      capacity_unit: GW
      inputs: [{commodity: NG, share: 1.0}]
      outputs: [{commodity: ELC, share: 1.0}]
      efficiency: 0.55
```

### Generated Tables

| Tag | Rows | Description |
|-----|------|-------------|
| `~FI_COMM` | 2 | Commodity definitions (ELC, NG) |
| `~FI_PROCESS` | 1 | Process definition (PP_CCGT) |
| `~FI_T` | 3 | Topology rows (inputs, outputs, efficiency) |

### Missing for Complete xl2times Processing

Required system tables not yet emitted:
- `~BOOKREGIONS_MAP` - Region mapping (required)
- `~TIMESLICES` - Timeslice definitions
- `~CURRENCIES` - Currency definitions  
- `~STARTYEAR` - Model start year

Required columns in existing tables:
- `tact`, `tcap`, `primarycg` in process tables
- Various topology columns

## Reference: vedalang validate JSON Output

```json
{
  "success": false,
  "source": "vedalang/examples/quickstart/mini_plant.veda.yaml",
  "tables": ["~FI_COMM", "~FI_PROCESS", "~FI_T"],
  "total_rows": 6,
  "warnings": 0,
  "errors": 1,
  "error_messages": [
    "Uncaught exception during processing: 'tact'"
  ]
}
```

**Key change from before:** Now `errors: 1` because the exception is captured as a structured diagnostic. Previously the crash prevented any diagnostic output.

## Next Steps

1. **Phase 0.5**: Add system table emission to VedaLang compiler
2. **Improve defensive coding**: Handle missing columns gracefully in xl2times transforms
3. **Schema evolution**: Richer process/commodity types in VedaLang
