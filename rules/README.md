# VedaLang Rules Directory

This directory contains the pattern library and constraints that guide model construction.

## Files

- **patterns.yaml** - Reusable patterns for common modeling constructs
- **constraints.yaml** - Valid tag/field combinations and requirements  
- **decision_tree.yaml** - Intent routing for natural language to patterns

## Usage

These rules are used by:
1. The VedaLang compiler for validation
2. AI agents for understanding how to build models
3. The pattern expansion tool (`veda_pattern`)

The active public DSL is v0.2-only. The pattern library is currently:

- `tableir` for supported expansion workflows
- archive-only for pre-v0.2 `vedalang` source fragments

## Adding New Patterns

1. Define the pattern in `patterns.yaml` with:
   - Clear description
   - Parameter definitions with types and defaults
   - TableIR template, or an explicitly archived legacy VedaLang template
   - Working example

2. Add any new tags to `constraints.yaml`

3. Add relevant intents to `decision_tree.yaml`

4. Test with: `uv run pytest tests/test_patterns.py`
