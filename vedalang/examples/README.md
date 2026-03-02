# VedaLang Examples

This directory holds example VedaLang source files and TableIR files for:

- Learning VedaLang syntax and patterns
- Testing the compiler and emitter
- Demonstrating modeling patterns

## File Types

- `*.veda.yaml` - VedaLang source files
- `*.tableir.yaml` - TableIR intermediate representation files

## Folder Layout

Use these subfolders for new examples:

- `quickstart/` - Minimal end-to-end examples for first use
- `design_challenges/` - `dc*` style language-design challenge examples
- `minisystem/` - MiniSystem progression and stress-test examples
- `toy_sectors/` - Small sector-specific models
- `feature_demos/` - Focused demos for single features
- `tableir/` - Raw TableIR fixtures (valid and invalid)
- `component_library/` - Component-library-based examples:
  - `component_library/components/`
  - `component_library/assemblies/`
  - `component_library/studies/`

## Migration Status

Examples have been moved into the folder layout above. Use subfolder paths in
docs/tests/commands (for example
`vedalang/examples/quickstart/mini_plant.veda.yaml`).
