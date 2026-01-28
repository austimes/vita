"""VedaLang Language Server using pygls."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from .schema_docs import SCHEMA_FIELD_DOCS

# Load schemas and attribute data
SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "vedalang" / "schema"


def load_attribute_master() -> dict:
    """Load the TIMES attribute master data."""
    path = SCHEMA_DIR / "attribute-master.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
            return data.get("attributes", {})
    return {}


def load_vedalang_schema() -> dict:
    """Load the VedaLang JSON schema."""
    path = SCHEMA_DIR / "vedalang.schema.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


ATTR_MASTER = load_attribute_master()
VEDALANG_SCHEMA = load_vedalang_schema()

# VedaLang semantic attribute → TIMES attribute mapping
SEMANTIC_TO_TIMES = {
    "efficiency": "ACT_EFF",
    "investment_cost": "NCAP_COST",
    "fixed_om_cost": "NCAP_FOM",
    "variable_om_cost": "ACT_COST",
    "import_price": "IRE_PRICE",
    "lifetime": "NCAP_TLIFE",
    "availability_factor": "NCAP_AF",
    "stock": "PRC_RESID",
    "existing_capacity": "NCAP_PASTI",
}

# Top-level VedaLang keywords for completion
VEDALANG_KEYWORDS = [
    "model",
    "name",
    "description",
    "regions",
    "milestone_years",
    "timeslices",
    "commodities",
    "processes",
    "scenario_parameters",
    "trade_links",
    "constraints",
    "cases",
    "studies",
]

# Process-level keywords
PROCESS_KEYWORDS = [
    "name",
    "description",
    "type",
    "sets",
    "primary_commodity_group",
    "inputs",
    "outputs",
    "input",
    "output",
    "efficiency",
    "investment_cost",
    "fixed_om_cost",
    "variable_om_cost",
    "lifetime",
    "availability_factor",
    "stock",
    "existing_capacity",
    "emission_factor",
    "cap2act",
    "region",
    "activity_unit",
    "capacity_unit",
    "cap_bound",
    "ncap_bound",
    "activity_bound",
]

# Commodity-level keywords
COMMODITY_KEYWORDS = [
    "name",
    "description",
    "type",
    "unit",
    "region",
]

# Enum values from schema
COMMODITY_TYPES = [
    "energy", "emission", "material", "demand", "financial", "environment"
]
PROCESS_TYPES = ["standard", "storage", "interregional_exchange"]

# Known TIMES sets (commonly used in VedaLang)
KNOWN_SETS = [
    "ELE", "DMD", "PRE", "PRW", "REF", "MIN", "CHP", "HPL", "STG", "DISTR",
    "IRE", "XTRACT", "RENEW", "ANNUAL", "DAYNITE", "WEEKLY", "SEASONAL",
    "NRG", "MAT", "DEM", "ENV", "FIN", "NRGO", "DEMO",
]

# Primary Commodity Group (PCG) values and documentation
PCG_VALUES = [
    "DEMI", "DEMO", "MATI", "MATO", "NRGI", "NRGO", "ENVI", "ENVO", "FINI", "FINO"
]

# noqa: E501 - documentation strings intentionally exceed line length for readability
PCG_DOCUMENTATION = """\
## VedaLang: `primary_commodity_group` (PCG)

**Type**: string enum
**Required**: Yes (on process definitions)
**Values**: `DEMI` `DEMO` `MATI` `MATO` `NRGI` `NRGO` `ENVI` `ENVO` `FINI` `FINO`

### Purpose

Defines which commodity flows determine a process's activity and capacity in TIMES:

- **Activity definition**: Sum of flows in the PCG equals process activity (VAR_ACT)
- **Capacity relationship**: Capacity is tied to activity through PCG flows
- **Efficiency direction**: Controls which side (input/output) is "primary" in EQ_PTRANS

### Value Format

`<commodity_type><I/O_direction>`

| Suffix | Meaning |
|--------|---------|
| `NRG` | Energy commodity |
| `DEM` | Demand commodity |
| `MAT` | Material commodity |
| `ENV` | Environment/emission |
| `FIN` | Financial commodity |
| `I` | Input side |
| `O` | Output side |

### Common Patterns

| Process Type | PCG | Reason |
|--------------|-----|--------|
| Power plant | `NRGO` | Activity = electricity output |
| Demand device (heater, car) | `DEMO` | Activity = demand served |
| Refinery/material process | `MATO` | Activity = material output |
| Import process | `NRGI` | Activity = energy imported |
| Mining/extraction | `MATO` or `NRGO` | Activity = resource extracted |

### Why Required?

VedaLang makes PCG **explicit** to avoid hidden inference surprises.
VEDA/xl2times would otherwise infer PCG using complex rules
(output DEM > MAT > NRG > ENV > FIN, then inputs).
Making it explicit ensures the modeler understands and controls activity definition.
"""


@dataclass
class SymbolDef:
    """Definition of a commodity, process, or set in the model."""
    kind: str  # "commodity" | "process" | "set"
    name: str
    uri: str
    range: types.Range
    data: dict = field(default_factory=dict)


@dataclass
class SymbolRef:
    """Reference to a commodity, process, or set."""
    kind: str  # "commodity" | "process" | "set"
    name: str
    uri: str
    range: types.Range
    context: str  # e.g., "process.inputs", "scenario_parameters.commodity"


class VedaLangServer(LanguageServer):
    """Language server for VedaLang .veda.yaml files."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostics: dict = {}
        self.symbols: dict[str, dict[str, dict[str, SymbolDef]]] = {}
        self.references: dict[str, list[SymbolRef]] = {}


server = VedaLangServer("vedalang-lsp", "v0.1.0")


def get_word_at_position(
    document: TextDocument, position: types.Position
) -> str | None:
    """Extract the word at the given position."""
    try:
        line = document.lines[position.line]
        start = position.character
        end = position.character

        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1

        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1

        if start < end:
            return line[start:end]
    except (IndexError, AttributeError):
        pass
    return None


def get_yaml_key_at_position(
    document: TextDocument, position: types.Position
) -> str | None:
    """Extract the YAML key at or near the given position."""
    try:
        line = document.lines[position.line].rstrip()
        match = re.match(r"^\s*-?\s*([a-zA-Z_][a-zA-Z0-9_]*):", line)
        if match:
            return match.group(1)
        if ":" in line:
            key_part = line.split(":")[0].strip().lstrip("-").strip()
            if key_part:
                return key_part
    except (IndexError, AttributeError):
        pass
    return None


def get_parent_section(document: TextDocument, line_no: int, indent: int) -> str | None:
    """Find the parent section key by scanning upward for less-indented lines."""
    for i in range(line_no - 1, -1, -1):
        line = document.lines[i].rstrip()
        if not line or line.strip().startswith("#"):
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent < indent and ":" in line:
            key = line.split(":", 1)[0].strip().lstrip("-").strip()
            if key:
                return key
    return None


def find_definition_range(
    document: TextDocument, kind: str, name: str
) -> types.Range:
    """Find the line range where a definition occurs."""
    section = "commodities" if kind == "commodity" else "processes"
    name_pattern = re.compile(rf"\bname:\s*{re.escape(name)}\b")
    in_section = False
    section_indent = None

    for i, line in enumerate(document.lines):
        stripped = line.strip()
        if stripped.startswith(f"{section}:"):
            in_section = True
            section_indent = len(line) - len(line.lstrip())
            continue

        if in_section:
            indent = len(line) - len(line.lstrip())
            left_section = (
                section_indent is not None
                and indent <= section_indent
                and stripped
                and not stripped.startswith("#")
            )
            if left_section:
                if not stripped.startswith("-"):
                    in_section = False
                    continue

            if name_pattern.search(line):
                col = line.index("name:")
                start = col + len("name:")
                while start < len(line) and line[start].isspace():
                    start += 1
                end = start + len(name)
                return types.Range(
                    start=types.Position(line=i, character=start),
                    end=types.Position(line=i, character=end),
                )

    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=0, character=0),
    )


def find_reference_range(
    document: TextDocument, name: str, context_key: str
) -> types.Range:
    """Find where a reference appears in the document."""
    pattern = re.compile(rf"\b{re.escape(name)}\b")

    for i, line in enumerate(document.lines):
        if f"{context_key}:" not in line and context_key not in line:
            continue
        m = pattern.search(line)
        if m:
            return types.Range(
                start=types.Position(line=i, character=m.start()),
                end=types.Position(line=i, character=m.end()),
            )

    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=0, character=0),
    )


def parse_and_index(ls: VedaLangServer, document: TextDocument) -> dict | None:
    """Parse YAML and build symbol index."""
    source = document.source
    try:
        parsed = yaml.safe_load(source) or {}
    except yaml.YAMLError:
        ls.symbols.pop(document.uri, None)
        ls.references.pop(document.uri, None)
        return None

    model = parsed.get("model", {})
    uri = document.uri

    commodity_defs: dict[str, SymbolDef] = {}
    process_defs: dict[str, SymbolDef] = {}
    set_defs: dict[str, SymbolDef] = {}
    refs: list[SymbolRef] = []

    # Index commodities
    for c in model.get("commodities", []) or []:
        name = c.get("name")
        if not name:
            continue
        rng = find_definition_range(document, "commodity", name)
        commodity_defs[name] = SymbolDef(
            kind="commodity", name=name, uri=uri, range=rng, data=c
        )

    # Index processes and collect references
    for p in model.get("processes", []) or []:
        name = p.get("name")
        if not name:
            continue
        rng = find_definition_range(document, "process", name)
        process_defs[name] = SymbolDef(
            kind="process", name=name, uri=uri, range=rng, data=p
        )

        # Collect set references
        for s in p.get("sets", []) or []:
            refs.append(SymbolRef(
                kind="set", name=s, uri=uri,
                range=find_reference_range(document, s, "sets"),
                context=f"process.{name}.sets"
            ))

        # Collect commodity references from flows
        for key in ("inputs", "outputs"):
            for flow in p.get(key, []) or []:
                cname = flow.get("commodity")
                if not cname:
                    continue
                refs.append(SymbolRef(
                    kind="commodity", name=cname, uri=uri,
                    range=find_reference_range(document, cname, "commodity"),
                    context=f"process.{name}.{key}.commodity"
                ))

        # Shorthand input/output
        for key in ("input", "output"):
            cname = p.get(key)
            if cname:
                refs.append(SymbolRef(
                    kind="commodity", name=cname, uri=uri,
                    range=find_reference_range(document, cname, key),
                    context=f"process.{name}.{key}"
                ))

    # Scenario parameters commodity refs
    for sp in model.get("scenario_parameters", []) or []:
        cname = sp.get("commodity")
        if cname:
            refs.append(SymbolRef(
                kind="commodity", name=cname, uri=uri,
                range=find_reference_range(document, cname, "commodity"),
                context="scenario_parameters.commodity"
            ))

    # Constraints references
    for c in model.get("constraints", []) or []:
        cname = c.get("commodity")
        if cname:
            refs.append(SymbolRef(
                kind="commodity", name=cname, uri=uri,
                range=find_reference_range(document, cname, "commodity"),
                context="constraints.commodity"
            ))
        for pname in c.get("processes", []) or []:
            refs.append(SymbolRef(
                kind="process", name=pname, uri=uri,
                range=find_reference_range(document, pname, "processes"),
                context="constraints.processes"
            ))

    # Trade links references
    for t in model.get("trade_links", []) or []:
        cname = t.get("commodity")
        if cname:
            refs.append(SymbolRef(
                kind="commodity", name=cname, uri=uri,
                range=find_reference_range(document, cname, "commodity"),
                context="trade_links.commodity"
            ))

    ls.symbols[uri] = {
        "commodity": commodity_defs,
        "process": process_defs,
        "set": set_defs,
    }
    ls.references[uri] = refs

    return parsed


def format_times_attribute_hover(attr_name: str, attr_data: dict) -> str:
    """Format hover documentation for a TIMES attribute."""
    lines = [f"## TIMES Attribute: `{attr_name}`", ""]

    if desc := attr_data.get("description"):
        lines.append(desc)
        lines.append("")

    if indexes := attr_data.get("indexes"):
        lines.append(f"**Indexes**: `{', '.join(indexes)}`")

    if units := attr_data.get("units_ranges_defaults"):
        lines.append(f"**Units/Defaults**: {units}")

    flags = []
    if attr_data.get("time_series"):
        flags.append("time-series")
    if attr_data.get("process"):
        flags.append("process")
    if attr_data.get("commodity"):
        flags.append("commodity")
    if attr_data.get("currency"):
        flags.append("currency")
    if flags:
        lines.append(f"**Flags**: {', '.join(flags)}")

    if ts := attr_data.get("timeslice"):
        lines.append(f"**Timeslice**: {ts}")

    if related := attr_data.get("related_sets_and_parameters"):
        lines.append(f"**Related**: {related}")

    if affected := attr_data.get("affected_equations_or_variables"):
        lines.append("")
        lines.append(f"**Affects**: {affected}")

    return "\n".join(lines)


def format_vedalang_attribute_hover(vedalang_attr: str) -> str | None:
    """Format hover documentation for a VedaLang semantic attribute."""
    times_attr = SEMANTIC_TO_TIMES.get(vedalang_attr)
    if not times_attr:
        return None

    attr_data = ATTR_MASTER.get(times_attr)
    if not attr_data:
        return (
            f"## VedaLang: `{vedalang_attr}`\n\n"
            f"Maps to TIMES attribute: `{times_attr}`"
        )

    lines = [
        f"## VedaLang: `{vedalang_attr}`",
        "",
        f"➜ Maps to TIMES attribute: **`{times_attr}`**",
        "",
    ]

    if desc := attr_data.get("description"):
        lines.append(desc)
        lines.append("")

    if indexes := attr_data.get("indexes"):
        lines.append(f"**Indexes**: `{', '.join(indexes)}`")

    if units := attr_data.get("units_ranges_defaults"):
        lines.append(f"**Units/Defaults**: {units}")

    flags = []
    if attr_data.get("time_series"):
        flags.append("📈 time-series")
    if attr_data.get("process"):
        flags.append("⚙️ process")
    if attr_data.get("commodity"):
        flags.append("📦 commodity")
    if flags:
        lines.append(f"**Flags**: {', '.join(flags)}")

    return "\n".join(lines)


def format_commodity_hover(sym: SymbolDef) -> str:
    """Format hover documentation for a commodity."""
    c = sym.data or {}
    lines = [f"### Commodity `{sym.name}`", ""]
    if desc := c.get("description"):
        lines.append(desc)
        lines.append("")
    if t := c.get("type"):
        lines.append(f"- **Type**: `{t}`")
    if u := c.get("unit"):
        lines.append(f"- **Unit**: `{u}`")
    if r := c.get("region"):
        lines.append(f"- **Region**: `{r}`")
    return "\n".join(lines)


def format_process_hover(sym: SymbolDef) -> str:
    """Format hover documentation for a process."""
    p = sym.data or {}
    lines = [f"### Process `{sym.name}`", ""]
    if desc := p.get("description"):
        lines.append(desc)
        lines.append("")
    if t := p.get("type"):
        lines.append(f"- **Type**: `{t}`")
    if sets := p.get("sets"):
        lines.append(f"- **Sets**: `{', '.join(sets)}`")
    if pcg := p.get("primary_commodity_group"):
        lines.append(f"- **Primary CG**: `{pcg}`")
    if au := p.get("activity_unit"):
        lines.append(f"- **Activity unit**: `{au}`")
    if cu := p.get("capacity_unit"):
        lines.append(f"- **Capacity unit**: `{cu}`")
    if eff := p.get("efficiency"):
        lines.append(f"- **Efficiency**: `{eff}`")
    if lt := p.get("lifetime"):
        lines.append(f"- **Lifetime**: `{lt}` years")

    # Show inputs/outputs summary
    inputs = p.get("inputs", []) or []
    inp = p.get("input")
    if inp:
        inputs = [{"commodity": inp}]
    if inputs:
        comm_names = [f.get("commodity", "?") for f in inputs]
        lines.append(f"- **Inputs**: `{', '.join(comm_names)}`")

    outputs = p.get("outputs", []) or []
    out = p.get("output")
    if out:
        outputs = [{"commodity": out}]
    if outputs:
        comm_names = [f.get("commodity", "?") for f in outputs]
        lines.append(f"- **Outputs**: `{', '.join(comm_names)}`")

    return "\n".join(lines)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: VedaLangServer, params: types.HoverParams) -> types.Hover | None:
    """Provide hover information for symbols and attributes."""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    word = get_word_at_position(doc, params.position)
    if not word:
        return None

    uri = params.text_document.uri
    symtab = ls.symbols.get(uri) or {}

    # Check if hovering over a commodity name
    commodity = (symtab.get("commodity") or {}).get(word)
    if commodity:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=format_commodity_hover(commodity),
            ),
            range=commodity.range,
        )

    # Check if hovering over a process name
    process = (symtab.get("process") or {}).get(word)
    if process:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=format_process_hover(process),
            ),
            range=process.range,
        )

    # Check if hovering over a known set
    if word in KNOWN_SETS:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=f"### TIMES Set `{word}`\n\nPredefined TIMES process set.",
            ),
        )

    # Check if hovering over a PCG value (e.g., NRGO, DEMO)
    if word in PCG_VALUES:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=PCG_DOCUMENTATION,
            ),
        )

    # Fallback: check for VedaLang attribute hover
    key = get_yaml_key_at_position(doc, params.position)
    if key:
        # Check for primary_commodity_group key
        if key == "primary_commodity_group":
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown,
                    value=PCG_DOCUMENTATION,
                )
            )
        # Check TIMES-mapped attributes first
        if md := format_vedalang_attribute_hover(key):
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown, value=md
                )
            )
        # Check comprehensive schema field docs
        if schema_doc := SCHEMA_FIELD_DOCS.get(key):
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown, value=schema_doc
                )
            )

    return None


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def goto_definition(
    ls: VedaLangServer, params: types.DefinitionParams
) -> types.Location | None:
    """Go to definition for commodity/process references."""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    uri = params.text_document.uri

    word = get_word_at_position(doc, params.position)
    if not word:
        return None

    symtab = ls.symbols.get(uri) or {}

    # Check commodities, then processes
    for kind in ("commodity", "process"):
        sym = (symtab.get(kind) or {}).get(word)
        if sym:
            return types.Location(uri=uri, range=sym.range)

    return None


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=[":", " ", "\n", "-"]),
)
def completions(params: types.CompletionParams) -> types.CompletionList:
    """Provide autocompletion for VedaLang keywords, attributes, and references."""
    document = server.workspace.get_text_document(params.text_document.uri)
    pos = params.position
    uri = params.text_document.uri
    symtab = server.symbols.get(uri) or {}

    items = []

    try:
        line = document.lines[pos.line] if pos.line < len(document.lines) else ""
        line_before = line[: pos.character] if pos.character <= len(line) else line
        stripped = line_before.strip()
        indent = len(line_before) - len(line_before.lstrip())
    except (IndexError, AttributeError):
        return types.CompletionList(is_incomplete=False, items=[])

    key = get_yaml_key_at_position(document, pos)
    parent = get_parent_section(document, pos.line, indent)

    # Complete commodity references
    if key in ("commodity", "input", "output") or (
        parent in ("inputs", "outputs") and "commodity" in stripped
    ):
        commodities = (symtab.get("commodity") or {}).values()
        for c in commodities:
            desc = (c.data or {}).get("description", "")
            ctype = (c.data or {}).get("type", "")
            items.append(
                types.CompletionItem(
                    label=c.name,
                    kind=types.CompletionItemKind.Variable,
                    detail=f"Commodity ({ctype})" if ctype else "Commodity",
                    documentation=desc,
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Complete process references (in constraints.processes, etc.)
    if key == "processes" and parent == "constraints":
        processes = (symtab.get("process") or {}).values()
        for p in processes:
            desc = (p.data or {}).get("description", "")
            items.append(
                types.CompletionItem(
                    label=p.name,
                    kind=types.CompletionItemKind.Function,
                    detail="Process",
                    documentation=desc,
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Complete sets
    if key == "sets" or parent == "sets":
        for s in KNOWN_SETS:
            items.append(
                types.CompletionItem(
                    label=s,
                    kind=types.CompletionItemKind.Enum,
                    detail="TIMES Set",
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Complete commodity types
    if key == "type" and parent == "commodities":
        for ct in COMMODITY_TYPES:
            items.append(
                types.CompletionItem(
                    label=ct,
                    kind=types.CompletionItemKind.EnumMember,
                    detail="Commodity type",
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Complete process types
    if key == "type" and parent == "processes":
        for pt in PROCESS_TYPES:
            items.append(
                types.CompletionItem(
                    label=pt,
                    kind=types.CompletionItemKind.EnumMember,
                    detail="Process type",
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Context-based completion
    if indent == 0 or stripped == "" or stripped == "model":
        items.append(
            types.CompletionItem(
                label="model",
                kind=types.CompletionItemKind.Keyword,
                detail="VedaLang model definition",
                insert_text="model:\n  name: ",
            )
        )
    elif indent <= 2:
        for kw in VEDALANG_KEYWORDS[1:]:
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail=f"Model property: {kw}",
                )
            )
    elif parent == "processes" or (
        "processes" in document.source.lower() and indent >= 4
    ):
        for kw in PROCESS_KEYWORDS:
            detail = ""
            if kw in SEMANTIC_TO_TIMES:
                times_attr = SEMANTIC_TO_TIMES[kw]
                detail = f"→ TIMES: {times_attr}"
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail=detail or "Process property",
                )
            )
    elif parent == "commodities" or (
        "commodities" in document.source.lower() and indent >= 4
    ):
        for kw in COMMODITY_KEYWORDS:
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail="Commodity property",
                )
            )
    else:
        for vedalang_attr, times_attr in SEMANTIC_TO_TIMES.items():
            items.append(
                types.CompletionItem(
                    label=vedalang_attr,
                    kind=types.CompletionItemKind.Property,
                    detail=f"→ TIMES: {times_attr}",
                    documentation=types.MarkupContent(
                        kind=types.MarkupKind.Markdown,
                        value=format_vedalang_attribute_hover(vedalang_attr) or "",
                    ),
                )
            )

    return types.CompletionList(is_incomplete=False, items=items)


def validate_document(
    ls: VedaLangServer, document: TextDocument
) -> list[types.Diagnostic]:
    """Validate a VedaLang document and return diagnostics."""
    diagnostics: list[types.Diagnostic] = []
    source = document.source

    try:
        parsed = yaml.safe_load(source)
    except yaml.YAMLError as e:
        line = getattr(e, "problem_mark", None)
        line_num = line.line if line else 0
        col = line.column if line else 0
        diagnostics.append(
            types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=line_num, character=col),
                    end=types.Position(line=line_num, character=col + 10),
                ),
                message=f"YAML syntax error: {e}",
                severity=types.DiagnosticSeverity.Error,
                source="vedalang",
            )
        )
        ls.symbols.pop(document.uri, None)
        ls.references.pop(document.uri, None)
        return diagnostics

    if not parsed:
        return diagnostics

    # Re-index after successful parse
    parse_and_index(ls, document)

    # Check for required 'model' key
    if "model" not in parsed:
        diagnostics.append(
            types.Diagnostic(
                range=types.Range(
                    start=types.Position(line=0, character=0),
                    end=types.Position(line=0, character=5),
                ),
                message="Missing required 'model' key",
                severity=types.DiagnosticSeverity.Error,
                source="vedalang",
            )
        )
        return diagnostics

    model = parsed.get("model", {})

    # Check required model properties
    required_props = ["name", "regions", "commodities", "processes"]
    for prop in required_props:
        if prop not in model:
            for i, line in enumerate(document.lines):
                if line.strip().startswith("model:"):
                    diagnostics.append(
                        types.Diagnostic(
                            range=types.Range(
                                start=types.Position(line=i, character=0),
                                end=types.Position(line=i, character=len(line)),
                            ),
                            message=f"Missing required property: '{prop}'",
                            severity=types.DiagnosticSeverity.Warning,
                            source="vedalang",
                        )
                    )
                    break

    # Check for deprecated 'scenarios' key
    if "scenarios" in model:
        for i, line in enumerate(document.lines):
            if line.strip().startswith("scenarios:"):
                diagnostics.append(
                    types.Diagnostic(
                        range=types.Range(
                            start=types.Position(line=i, character=0),
                            end=types.Position(line=i, character=len(line)),
                        ),
                        message="'scenarios' is deprecated. Use 'scenario_parameters'.",
                        severity=types.DiagnosticSeverity.Warning,
                        source="vedalang",
                    )
                )
                break

    # Check for duplicate commodity names
    commodity_names: dict[str, int] = {}
    for i, c in enumerate(model.get("commodities", []) or []):
        name = c.get("name")
        if name:
            if name in commodity_names:
                diagnostics.append(
                    types.Diagnostic(
                        range=find_definition_range(document, "commodity", name),
                        message=f"Duplicate commodity name: '{name}'",
                        severity=types.DiagnosticSeverity.Error,
                        source="vedalang",
                    )
                )
            else:
                commodity_names[name] = i

    # Check for duplicate process names
    process_names: dict[str, int] = {}
    for i, p in enumerate(model.get("processes", []) or []):
        name = p.get("name")
        if name:
            if name in process_names:
                diagnostics.append(
                    types.Diagnostic(
                        range=find_definition_range(document, "process", name),
                        message=f"Duplicate process name: '{name}'",
                        severity=types.DiagnosticSeverity.Error,
                        source="vedalang",
                    )
                )
            else:
                process_names[name] = i

    # Check for undefined references
    uri = document.uri
    symtab = ls.symbols.get(uri) or {}
    defs_by_kind = {
        k: set((symtab.get(k) or {}).keys())
        for k in ("commodity", "process", "set")
    }
    # Add known sets to defined sets
    defs_by_kind["set"] = defs_by_kind.get("set", set()) | set(KNOWN_SETS)

    for ref in ls.references.get(uri) or []:
        if ref.name not in defs_by_kind.get(ref.kind, set()):
            valid_symbols = sorted(defs_by_kind.get(ref.kind, set()))
            diagnostics.append(
                types.Diagnostic(
                    range=ref.range,
                    message=f"Undefined {ref.kind}: '{ref.name}'",
                    severity=types.DiagnosticSeverity.Error,
                    source="vedalang",
                    code="undefined-reference",
                    data={
                        "kind": ref.kind,
                        "undefined_name": ref.name,
                        "valid_symbols": valid_symbols,
                    },
                )
            )

    return diagnostics


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: VedaLangServer, params: types.DidOpenTextDocumentParams):
    """Validate document when opened."""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    diagnostics = validate_document(ls, doc)
    pub_params = types.PublishDiagnosticsParams(
        uri=params.text_document.uri, diagnostics=diagnostics
    )
    ls.text_document_publish_diagnostics(pub_params)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: VedaLangServer, params: types.DidChangeTextDocumentParams):
    """Validate document when changed."""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    diagnostics = validate_document(ls, doc)
    pub_params = types.PublishDiagnosticsParams(
        uri=params.text_document.uri, diagnostics=diagnostics
    )
    ls.text_document_publish_diagnostics(pub_params)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: VedaLangServer, params: types.DidSaveTextDocumentParams):
    """Validate document when saved."""
    doc = ls.workspace.get_text_document(params.text_document.uri)
    diagnostics = validate_document(ls, doc)
    pub_params = types.PublishDiagnosticsParams(
        uri=params.text_document.uri, diagnostics=diagnostics
    )
    ls.text_document_publish_diagnostics(pub_params)


@server.feature(types.TEXT_DOCUMENT_CODE_ACTION)
def code_action(
    ls: VedaLangServer, params: types.CodeActionParams
) -> list[types.CodeAction]:
    """Provide code actions (quick fixes) for diagnostics."""
    actions: list[types.CodeAction] = []
    uri = params.text_document.uri

    for diag in params.context.diagnostics:
        if diag.code != "undefined-reference":
            continue

        data = diag.data
        if not isinstance(data, dict):
            continue

        kind = data.get("kind", "symbol")
        valid_symbols = data.get("valid_symbols", [])

        if not valid_symbols:
            continue

        for sym in valid_symbols[:10]:
            edit = types.WorkspaceEdit(
                changes={
                    uri: [
                        types.TextEdit(range=diag.range, new_text=sym)
                    ]
                }
            )
            action = types.CodeAction(
                title=f"Replace with '{sym}'",
                kind=types.CodeActionKind.QuickFix,
                diagnostics=[diag],
                edit=edit,
            )
            actions.append(action)

        if len(valid_symbols) > 10:
            remaining = len(valid_symbols) - 10
            action = types.CodeAction(
                title=f"... and {remaining} more {kind}s (use autocomplete)",
                kind=types.CodeActionKind.QuickFix,
                diagnostics=[diag],
            )
            actions.append(action)

    return actions


# Import shared RES graph builder
from vedalang.viz.res_mermaid import build_res_graph  # noqa: E402


@server.feature("veda/resGraph")
def res_graph(ls: VedaLangServer, params) -> dict:
    """Return the RES graph for the given document."""
    # Handle both {uri: ...} and {textDocument: {uri: ...}} formats
    include_variants = False
    if hasattr(params, "textDocument"):
        td = params.textDocument
        uri = td.get("uri") if isinstance(td, dict) else td.uri
        include_variants = getattr(params, "includeVariants", False)
    elif hasattr(params, "uri"):
        uri = params.uri
        include_variants = getattr(params, "includeVariants", False)
    elif isinstance(params, dict):
        uri = params.get("textDocument", {}).get("uri") or params.get("uri")
        include_variants = params.get("includeVariants", False)
    else:
        return {"nodes": [], "edges": [], "error": "Invalid params: no uri found"}

    doc = ls.workspace.get_text_document(uri)
    try:
        parsed = yaml.safe_load(doc.source)
        if not parsed:
            return {"nodes": [], "edges": [], "error": "Empty document"}
        return build_res_graph(parsed, include_variants=include_variants)
    except yaml.YAMLError as e:
        return {"nodes": [], "edges": [], "error": str(e)}


def main():
    """Run the VedaLang language server."""
    import sys

    log_file = Path("/tmp/vedalang-lsp.log")
    handlers = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, mode="w"),
    ]
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
    logger = logging.getLogger(__name__)
    logger.info("VedaLang LSP starting...")
    logger.info(f"Python: {sys.executable}")
    logger.info(f"CWD: {Path.cwd()}")
    logger.info(f"Attribute master loaded: {len(ATTR_MASTER)} attributes")
    logger.info(f"Schema loaded: {bool(VEDALANG_SCHEMA)}")
    server.start_io()


if __name__ == "__main__":
    main()
