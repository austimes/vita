# VedaLang Language Server

Language Server Protocol (LSP) implementation for VedaLang, providing IDE support for `.veda.yaml` files in VS Code, Cursor, and other LSP-compatible editors.

## Features

- **Hover Documentation**: Hover over VedaLang attributes to see:
  - The TIMES attribute it maps to (e.g., `efficiency` → `ACT_EFF`)
  - Full description from the TIMES attribute master
  - Indexes, units, and metadata

- **Autocompletion**: Context-aware suggestions for:
  - VedaLang v0.3 root objects (`commodities`, `technologies`, `technology_roles`, `sites`, `facilities`, `fleets`, `zone_opportunities`, `networks`, `runs`)
  - Technology and asset attributes (`performance`, `costs`, `stock`, `membership_overrides`, etc.)
  - Enum values (`primary`, `secondary`, `service`, `material`, `emission`, etc.)

- **Real-time Diagnostics**: Validates `.veda.yaml` files for:
  - YAML syntax errors
  - Missing required properties
  - Undefined commodity/technology/technology-role references
  - Duplicate symbol names
  - public-surface structural and semantic diagnostics

- **Code Actions (Quick Fixes)**: For undefined reference errors:
  - Offers valid symbols as replacement suggestions
  - Works for commodities, technologies, technology roles, and runs
  - Diagnostic data includes `valid_symbols` for AI agent consumption

## Installation

### Prerequisites

1. Python 3.11+ with the project's virtual environment
2. Bun (for building the VS Code extension)
3. The `pygls` and `lsprotocol` packages

### Install Python Dependencies

```bash
# From the veda-devtools root
uv add pygls lsprotocol
```

### Build the VS Code Extension

```bash
cd tools/vedalang_lsp/extension
bun install
bun run compile
```

### Install in VS Code/Cursor

**Option 1: Development Mode**

1. Open VS Code/Cursor
2. Open the folder `tools/vedalang_lsp/extension` (File → Open Folder…)
3. Start the extension in an **Extension Development Host**:
   - Run “Debug: Start Debugging” from the Command Palette, or
   - Press **F5** (on many Mac keyboards this is **fn+F5** unless you’ve enabled “Use F1, F2, etc. keys as standard function keys” in macOS settings)

**Option 2: Link for Development**

```bash
# Create a stable development symlink in the VS Code extensions directory
ln -s $(pwd)/tools/vedalang_lsp/extension ~/.vscode/extensions/vedalang-dev
```

**Option 3: Build a VSIX (so you have something to “Install from VSIX…”)**

```bash
cd tools/vedalang_lsp/extension
bun install
bun run compile
bun run package
```

This produces a `.vsix` in the same folder, which you can install via “Extensions: Install from VSIX…” in VS Code/Cursor.

### Manual LSP Server Testing

Run the server directly to test:

```bash
# From veda-devtools root
uv run python -m tools.vedalang_lsp.server.server
```

## Usage

1. Open any `.veda.yaml` file
2. Hover over attributes like `efficiency`, `investment_cost` to see TIMES documentation
3. Start typing to see autocompletion suggestions
4. Errors and warnings appear in the Problems panel

## Configuration

In VS Code settings (`settings.json`):

```json
{
  "vedalang.server.pythonPath": "/path/to/python",
  "vedalang.server.enabled": true,
  "vedalang.trace.server": "verbose"  // For debugging
}
```

## Architecture

```
tools/
├── vedalang_lsp/        # Python LSP server (pygls)
│   ├── __init__.py
│   └── server/
│       ├── __init__.py
│       └── server.py    # Main server with hover/completion/diagnostics
└── vedalang-lsp/
    ├── extension/       # VS Code extension (TypeScript)
    │   ├── package.json # Extension manifest
    │   ├── src/extension.ts # Extension entry point
    │   └── syntaxes/    # TextMate grammar for syntax highlighting
    └── README.md
```

## Supported Attributes

The LSP provides documentation for all VedaLang semantic attributes:

| VedaLang | TIMES Attribute | Description |
|----------|-----------------|-------------|
| `efficiency` | ACT_EFF | Process efficiency |
| `investment_cost` | NCAP_COST | Capital cost per capacity |
| `fixed_om_cost` | NCAP_FOM | Fixed O&M per capacity/year |
| `variable_om_cost` | ACT_COST | Variable cost per activity |
| `lifetime` | NCAP_TLIFE | Technical lifetime |
| `availability_factor` | NCAP_AF | Capacity factor |
| `stock` | PRC_RESID | Existing/residual capacity |
| `existing_capacity` | NCAP_PASTI | Past investment with vintage |
| `import_price` | IRE_PRICE | Import/export commodity price |

Additionally, hovering over any TIMES attribute name (e.g., `NCAP_COST`, `act_cost`) shows the full attribute documentation from the 331-attribute master.

## Development

### Running Tests

```bash
# From veda-devtools root
uv run pytest tests/test_lsp.py -v
```

### Debugging the Server

Set `"vedalang.trace.server": "verbose"` in VS Code settings, then check the "VedaLang Language Server" output channel.

## License

Same as veda-devtools project.
