"""VedaLang Language Server using pygls."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError
from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument
from yaml.nodes import MappingNode, Node, SequenceNode

from vedalang.compiler.source_maps import attach_source_positions
from vedalang.compiler.v0_2_diagnostics import collect_v0_2_diagnostics
from vedalang.versioning import looks_like_v0_2_source

from .schema_docs import SCHEMA_FIELD_DOCS

# Load schemas and attribute data
SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "vedalang" / "schema"
VEDALANG_SCHEMA_PATH = SCHEMA_DIR / "vedalang.schema.json"


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
    path = VEDALANG_SCHEMA_PATH
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}
ATTR_MASTER = load_attribute_master()
VEDALANG_SCHEMA = load_vedalang_schema()
SCHEMA_VALIDATOR = Draft7Validator(VEDALANG_SCHEMA) if VEDALANG_SCHEMA else None
SCHEMA_MTIME = (
    VEDALANG_SCHEMA_PATH.stat().st_mtime if VEDALANG_SCHEMA_PATH.exists() else None
)


def refresh_schema_cache() -> None:
    """Reload schema/validator when the schema file changes on disk."""
    global VEDALANG_SCHEMA, SCHEMA_VALIDATOR, SCHEMA_MTIME

    if not VEDALANG_SCHEMA_PATH.exists():
        return

    current_mtime = VEDALANG_SCHEMA_PATH.stat().st_mtime
    if SCHEMA_MTIME is None or current_mtime != SCHEMA_MTIME:
        VEDALANG_SCHEMA = load_vedalang_schema()
        SCHEMA_VALIDATOR = (
            Draft7Validator(VEDALANG_SCHEMA) if VEDALANG_SCHEMA else None
        )
        SCHEMA_MTIME = current_mtime


def _resolve_schema_ref_in_root(schema_node: dict, schema_root: dict) -> dict:
    """Resolve local $ref pointers against a specific schema document."""
    current = schema_node
    while isinstance(current, dict) and "$ref" in current:
        ref = current.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            break
        pointer = [_decode_json_pointer_segment(p) for p in ref[2:].split("/")]
        target = schema_root
        for part in pointer:
            if not isinstance(target, dict) or part not in target:
                return current
            target = target[part]
        if not isinstance(target, dict):
            return current
        current = target
    return current if isinstance(current, dict) else {}

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
    "commodities",
    "technologies",
    "technology_roles",
    "stock_characterizations",
    "spatial_layers",
    "spatial_measure_sets",
    "temporal_index_series",
    "region_partitions",
    "zone_overlays",
    "sites",
    "facilities",
    "fleets",
    "opportunities",
    "networks",
    "runs",
]

# Commodity-level keywords
COMMODITY_KEYWORDS = [
    "id",
    "description",
    "kind",
    "unit",
]

TECHNOLOGY_KEYWORDS = [
    "id",
    "description",
    "provides",
    "inputs",
    "outputs",
    "performance",
    "emissions",
    "investment_cost",
    "fixed_om",
    "variable_om",
    "lifetime",
    "stock_characterization",
]

TECHNOLOGY_ROLE_KEYWORDS = [
    "id",
    "primary_service",
    "technologies",
    "transitions",
    "description",
]

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
    context: str  # e.g., "technologies.inputs", "networks.commodity"


class VedaLangServer(LanguageServer):
    """Language server for VedaLang .veda.yaml files."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostics: dict = {}
        self.symbols: dict[str, dict[str, dict[str, SymbolDef]]] = {}
        self.references: dict[str, list[SymbolRef]] = {}


server = VedaLangServer("vedalang-lsp", "v0.2.0")


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


def _decode_json_pointer_segment(segment: str) -> str:
    """Decode a JSON pointer segment."""
    return segment.replace("~1", "/").replace("~0", "~")


def _resolve_schema_ref(schema_node: dict) -> dict:
    """Resolve local $ref pointers in the loaded VedaLang schema."""
    return _resolve_schema_ref_in_root(schema_node, VEDALANG_SCHEMA)


def _schema_child_for_token(schema_node: dict, token: str | int) -> dict | None:
    """Follow a schema node for one path token (property or array index)."""
    node = _resolve_schema_ref(schema_node)

    if isinstance(token, int):
        if isinstance(node.get("items"), dict):
            return node["items"]
    elif isinstance(token, str):
        props = node.get("properties")
        if (
            isinstance(props, dict)
            and token in props
            and isinstance(props[token], dict)
        ):
            return props[token]

        pattern_props = node.get("patternProperties")
        if isinstance(pattern_props, dict):
            for pattern, sub_schema in pattern_props.items():
                if re.match(pattern, token) and isinstance(sub_schema, dict):
                    return sub_schema

        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            return additional

    for branch_key in ("oneOf", "anyOf", "allOf"):
        branches = node.get(branch_key)
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            child = _schema_child_for_token(branch, token)
            if child:
                return child

    return None


def _schema_child_for_token_in_root(
    schema_node: dict,
    token: str | int,
    schema_root: dict,
) -> dict | None:
    """Follow a schema node for one token using a specific schema root."""
    node = _resolve_schema_ref_in_root(schema_node, schema_root)

    if isinstance(token, int):
        if isinstance(node.get("items"), dict):
            return node["items"]
    elif isinstance(token, str):
        props = node.get("properties")
        if (
            isinstance(props, dict)
            and token in props
            and isinstance(props[token], dict)
        ):
            return props[token]

        pattern_props = node.get("patternProperties")
        if isinstance(pattern_props, dict):
            for pattern, sub_schema in pattern_props.items():
                if re.match(pattern, token) and isinstance(sub_schema, dict):
                    return sub_schema

        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            return additional

    for branch_key in ("oneOf", "anyOf", "allOf"):
        branches = node.get(branch_key)
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            child = _schema_child_for_token_in_root(branch, token, schema_root)
            if child:
                return child

    return None


def schema_for_path(path: list[str | int]) -> dict | None:
    """Resolve the JSON Schema node for a YAML path."""
    refresh_schema_cache()
    root = VEDALANG_SCHEMA
    if not isinstance(root, dict) or not root:
        return None
    node: dict = root
    for token in path:
        child = _schema_child_for_token_in_root(node, token, root)
        if not isinstance(child, dict):
            return None
        node = child
    return _resolve_schema_ref_in_root(node, root)


def _position_in_node(node: Node, position: types.Position) -> bool:
    """Return whether the position falls inside a YAML node."""
    start = node.start_mark
    end = node.end_mark
    before_end = (
        position.line < end.line
        or (position.line == end.line and position.character <= end.column)
    )
    after_start = (
        position.line > start.line
        or (position.line == start.line and position.character >= start.column)
    )
    return after_start and before_end


def _path_at_position(
    node: Node, position: types.Position, prefix: list[str | int]
) -> list[str | int] | None:
    """Find the most specific YAML path containing the cursor position."""
    if not _position_in_node(node, position):
        return None

    if isinstance(node, MappingNode):
        # Key ranges are usually precise; check them first to avoid parent value
        # nodes swallowing positions on later sibling keys.
        for key_node, _value_node in node.value:
            key = key_node.value
            if _position_in_node(key_node, position):
                return prefix + [key]

        for key_node, value_node in node.value:
            key = key_node.value
            if _position_in_node(value_node, position):
                nested = _path_at_position(value_node, position, prefix + [key])
                return nested if nested is not None else prefix + [key]
        return prefix

    if isinstance(node, SequenceNode):
        for idx, item in enumerate(node.value):
            if _position_in_node(item, position):
                nested = _path_at_position(item, position, prefix + [idx])
                return nested if nested is not None else prefix + [idx]
        return prefix

    return prefix


def yaml_path_at_position(
    document: TextDocument, position: types.Position
) -> list[str | int]:
    """Get the YAML path at cursor location (e.g., ['variants', 0, 'kind'])."""
    try:
        root = yaml.compose(document.source)
    except yaml.YAMLError:
        return []
    if root is None:
        return []
    return _path_at_position(root, position, []) or []


def schema_for_key_at_position(
    document: TextDocument, position: types.Position, key: str
) -> tuple[list[str | int], dict] | tuple[None, None]:
    """Resolve schema for a key at cursor location."""
    path = yaml_path_at_position(document, position)
    if not path:
        return None, None
    if not (isinstance(path[-1], str) and path[-1] == key):
        path = [*path, key]

    schema_node = schema_for_path(path)
    if not isinstance(schema_node, dict):
        return None, None
    return path, schema_node


def enum_values_from_schema(schema_node: dict) -> list[str]:
    """Extract string enum candidates from a schema node."""
    values: list[str] = []

    node = _resolve_schema_ref(schema_node)
    enums = node.get("enum")
    if isinstance(enums, list):
        for value in enums:
            if isinstance(value, str):
                values.append(value)

    const_value = node.get("const")
    if isinstance(const_value, str):
        values.append(const_value)

    for branch_key in ("oneOf", "anyOf", "allOf"):
        branches = node.get(branch_key)
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if isinstance(branch, dict):
                values.extend(enum_values_from_schema(branch))

    deduped: list[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _schema_type_label(schema_node: dict) -> str:
    """Build a concise type label for schema hover content."""
    node = _resolve_schema_ref(schema_node)
    if isinstance(node.get("type"), str):
        return str(node["type"])
    if isinstance(node.get("type"), list):
        return " | ".join(str(t) for t in node["type"])
    if "enum" in node:
        if all(isinstance(v, str) for v in node["enum"]):
            return "string enum"
        return "enum"
    if "oneOf" in node:
        return "oneOf"
    if "anyOf" in node:
        return "anyOf"
    if "allOf" in node:
        return "allOf"
    return "unknown"


def _format_yaml_path(path: list[str | int]) -> str:
    """Format YAML path for display."""
    formatted = []
    for token in path:
        if isinstance(token, int):
            if not formatted:
                formatted.append("[]")
            else:
                formatted[-1] = f"{formatted[-1]}[]"
        else:
            formatted.append(token)
    return ".".join(formatted)


def format_schema_hover(key: str, path: list[str | int], schema_node: dict) -> str:
    """Generate context-aware hover content from JSON schema."""
    lines = [f"## VedaLang: `{key}`", ""]
    lines.append(f"**Type**: {_schema_type_label(schema_node)}")
    lines.append(f"**Used in**: `{_format_yaml_path(path[:-1])}`")

    description = _resolve_schema_ref(schema_node).get("description")
    if isinstance(description, str) and description:
        lines.extend(["", description])

    enum_values = enum_values_from_schema(schema_node)
    if enum_values:
        lines.extend(["", "**Allowed values**:"])
        lines.extend([f"- `{value}`" for value in enum_values])

    return "\n".join(lines)


def find_key_range(document: TextDocument, key: str) -> types.Range:
    """Find a key location for diagnostics fallback."""
    pattern = re.compile(rf"^(\s*-\s*|\s*){re.escape(key)}\s*:")
    for i, line in enumerate(document.lines):
        if not pattern.search(line):
            continue
        col = line.find(key)
        if col >= 0:
            return types.Range(
                start=types.Position(line=i, character=col),
                end=types.Position(line=i, character=col + len(key)),
            )
    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=0, character=1),
    )


def find_key_value_range(
    document: TextDocument, key: str, value: object
) -> types.Range:
    """Find a key/value location for schema diagnostics."""
    key_range = find_key_range(document, key)

    if not isinstance(value, (str, int, float, bool)) and value is not None:
        return key_range

    value_variants: list[str] = []
    if isinstance(value, bool):
        value_variants = ["true" if value else "false"]
    elif value is None:
        value_variants = ["null"]
    elif isinstance(value, str):
        value_variants = [value, json.dumps(value), f"'{value}'"]
    else:
        value_variants = [str(value)]

    for i, line in enumerate(document.lines):
        if ":" not in line:
            continue
        key_part, value_part = line.split(":", 1)
        normalized_key = key_part.strip().lstrip("-").strip()
        if normalized_key != key:
            continue
        for variant in value_variants:
            idx = value_part.find(variant)
            if idx >= 0:
                start = len(key_part) + 1 + idx
                end = start + len(variant)
                return types.Range(
                    start=types.Position(line=i, character=start),
                    end=types.Position(line=i, character=end),
                )
        return key_range

    return key_range


def range_for_schema_error(document: TextDocument, err: ValidationError) -> types.Range:
    """Map jsonschema error path to a document range."""
    path_tokens = list(err.path)
    key = next((t for t in reversed(path_tokens) if isinstance(t, str)), None)
    if key:
        return find_key_value_range(document, key, err.instance)

    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=0, character=1),
    )


def schema_validation_diagnostics(
    document: TextDocument, parsed: dict
) -> list[types.Diagnostic]:
    """Run JSON Schema validation and return diagnostics."""
    refresh_schema_cache()
    validator = SCHEMA_VALIDATOR
    if validator is None:
        return []

    diagnostics: list[types.Diagnostic] = []
    errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.path))
    for err in errors:
        diagnostics.append(
            types.Diagnostic(
                range=range_for_schema_error(document, err),
                message=f"Schema validation: {err.message}",
                severity=types.DiagnosticSeverity.Error,
                source="vedalang-schema",
            )
        )
    return diagnostics


def find_definition_range(
    document: TextDocument, kind: str, name: str
) -> types.Range:
    """Find the line range where a definition occurs."""
    section_by_kind = {
        "commodity": "commodities",
        "technology": "technologies",
        "technology_role": "technology_roles",
        "site": "sites",
        "facility": "facilities",
        "run": "runs",
    }
    section = section_by_kind.get(kind)
    if section is None:
        return types.Range(
            start=types.Position(line=0, character=0),
            end=types.Position(line=0, character=0),
        )
    name_pattern = re.compile(rf"\b(?:id|name):\s*{re.escape(name)}\b")
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
                key = "id:" if "id:" in line else "name:"
                col = line.index(key)
                start = col + len(key)
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

    uri = document.uri

    commodity_defs: dict[str, SymbolDef] = {}
    technology_defs: dict[str, SymbolDef] = {}
    technology_role_defs: dict[str, SymbolDef] = {}
    site_defs: dict[str, SymbolDef] = {}
    facility_defs: dict[str, SymbolDef] = {}
    refs: list[SymbolRef] = []

    if not looks_like_v0_2_source(parsed):
        ls.symbols.pop(uri, None)
        ls.references.pop(uri, None)
        return parsed

    # Index commodities
    for c in parsed.get("commodities", []) or []:
        commodity_id = c.get("id") or c.get("name")
        if not commodity_id:
            continue
        rng = find_definition_range(document, "commodity", commodity_id)
        commodity_defs[commodity_id] = SymbolDef(
            kind="commodity", name=commodity_id, uri=uri, range=rng, data=c
        )

    for t in parsed.get("technologies", []) or []:
        technology_id = t.get("id")
        if not technology_id:
            continue
        rng = find_definition_range(document, "technology", technology_id)
        technology_defs[technology_id] = SymbolDef(
            kind="technology", name=technology_id, uri=uri, range=rng, data=t
        )
        for key in ("inputs", "outputs"):
            for flow in t.get(key, []) or []:
                cname = flow.get("commodity")
                if not cname:
                    continue
                refs.append(SymbolRef(
                    kind="commodity", name=cname, uri=uri,
                    range=find_reference_range(document, cname, "commodity"),
                    context=f"technology.{technology_id}.{key}.commodity"
                ))
        provides = t.get("provides")
        if provides:
            refs.append(SymbolRef(
                kind="commodity", name=provides, uri=uri,
                range=find_reference_range(document, provides, "provides"),
                context=f"technology.{technology_id}.provides"
            ))
        for emission in t.get("emissions", []) or []:
            cname = emission.get("commodity")
            if not cname:
                continue
            refs.append(SymbolRef(
                kind="commodity", name=cname, uri=uri,
                range=find_reference_range(document, cname, "commodity"),
                context=f"technology.{technology_id}.emissions.commodity"
            ))

    for role in parsed.get("technology_roles", []) or []:
        role_id = role.get("id")
        if not role_id:
            continue
        rng = find_definition_range(document, "technology_role", role_id)
        technology_role_defs[role_id] = SymbolDef(
            kind="technology_role", name=role_id, uri=uri, range=rng, data=role
        )
        primary_service = role.get("primary_service")
        if primary_service:
            refs.append(
                SymbolRef(
                    kind="commodity",
                    name=primary_service,
                    uri=uri,
                    range=find_reference_range(
                        document,
                        primary_service,
                        "primary_service",
                    ),
                    context=f"technology_role.{role_id}.primary_service",
                )
            )
        for technology_id in role.get("technologies", []) or []:
            refs.append(SymbolRef(
                kind="technology", name=technology_id, uri=uri,
                range=find_reference_range(document, technology_id, "technologies"),
                context=f"technology_role.{role_id}.technologies"
            ))

    for site in parsed.get("sites", []) or []:
        site_id = site.get("id")
        if not site_id:
            continue
        site_defs[site_id] = SymbolDef(
            kind="site",
            name=site_id,
            uri=uri,
            range=find_definition_range(document, "site", site_id),
            data=site,
        )

    for facility in parsed.get("facilities", []) or []:
        facility_id = facility.get("id")
        if not facility_id:
            continue
        facility_defs[facility_id] = SymbolDef(
            kind="facility",
            name=facility_id,
            uri=uri,
            range=find_definition_range(document, "facility", facility_id),
            data=facility,
        )
        site_id = facility.get("site")
        if site_id:
            refs.append(SymbolRef(
                kind="site", name=site_id, uri=uri,
                range=find_reference_range(document, site_id, "site"),
                context=f"facility.{facility_id}.site"
            ))
        role_id = facility.get("technology_role")
        if role_id:
            refs.append(SymbolRef(
                kind="technology_role", name=role_id, uri=uri,
                range=find_reference_range(document, role_id, "technology_role"),
                context=f"facility.{facility_id}.technology_role"
            ))
        stock = facility.get("stock", {}) or {}
        for item in stock.get("items", []) or []:
            technology_id = item.get("technology")
            if not technology_id:
                continue
            refs.append(SymbolRef(
                kind="technology", name=technology_id, uri=uri,
                range=find_reference_range(document, technology_id, "technology"),
                context=f"facility.{facility_id}.stock.technology"
            ))

    ls.symbols[uri] = {
        "commodity": commodity_defs,
        "technology": technology_defs,
        "technology_role": technology_role_defs,
        "site": site_defs,
        "facility": facility_defs,
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
    if kind := c.get("kind"):
        lines.append(f"- **Kind**: `{kind}`")
    if u := c.get("unit"):
        lines.append(f"- **Unit**: `{u}`")
    return "\n".join(lines)


def format_technology_hover(sym: SymbolDef) -> str:
    """Format hover documentation for a technology."""
    technology = sym.data or {}
    lines = [f"### Technology `{sym.name}`", ""]
    if desc := technology.get("description"):
        lines.append(desc)
        lines.append("")
    if provides := technology.get("provides"):
        lines.append(f"- **Provides**: `{provides}`")
    performance = technology.get("performance") or {}
    if performance:
        lines.append(
            f"- **Performance**: `{performance.get('kind', 'custom')}` = "
            f"`{performance.get('value')}`"
        )
    if lifetime := technology.get("lifetime"):
        lines.append(f"- **Lifetime**: `{lifetime}`")
    inputs = technology.get("inputs", []) or []
    if inputs:
        comm_names = [f.get("commodity", "?") for f in inputs]
        lines.append(f"- **Inputs**: `{', '.join(comm_names)}`")
    outputs = technology.get("outputs", []) or []
    if outputs:
        comm_names = [f.get("commodity", "?") for f in outputs]
        lines.append(f"- **Outputs**: `{', '.join(comm_names)}`")
    return "\n".join(lines)


def format_process_hover(sym: SymbolDef) -> str:
    """Backward-compatible alias for the former process hover helper."""
    return format_technology_hover(sym)


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

    technology = (symtab.get("technology") or {}).get(word)
    if technology:
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=format_technology_hover(technology),
            ),
            range=technology.range,
        )

    # Fallback: check for VedaLang attribute hover
    key = get_yaml_key_at_position(doc, params.position)
    if key:
        # Check TIMES-mapped attributes first
        if md := format_vedalang_attribute_hover(key):
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown, value=md
                )
            )
        # Prefer schema-aware docs so shared key names
        # (e.g. `kind`) are context-correct.
        schema_path, schema_node = schema_for_key_at_position(doc, params.position, key)
        if schema_path and schema_node:
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown,
                    value=format_schema_hover(key, schema_path, schema_node),
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

    for kind in ("commodity", "technology", "technology_role", "site", "facility"):
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
    if key in ("commodity", "provides", "primary_service") or (
        parent in ("inputs", "outputs", "emissions") and "commodity" in stripped
    ):
        commodities = (symtab.get("commodity") or {}).values()
        for c in commodities:
            desc = (c.data or {}).get("description", "")
            ctype = (c.data or {}).get("kind", "")
            items.append(
                types.CompletionItem(
                    label=c.name,
                    kind=types.CompletionItemKind.Variable,
                    detail=f"Commodity ({ctype})" if ctype else "Commodity",
                    documentation=desc,
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    if key == "technology" or (key == "technologies" and parent == "technology_roles"):
        technologies = (symtab.get("technology") or {}).values()
        for t in technologies:
            desc = (t.data or {}).get("description", "")
            items.append(
                types.CompletionItem(
                    label=t.name,
                    kind=types.CompletionItemKind.Function,
                    detail="Technology",
                    documentation=desc,
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    if key == "technology_role":
        roles = (symtab.get("technology_role") or {}).values()
        for role in roles:
            items.append(
                types.CompletionItem(
                    label=role.name,
                    kind=types.CompletionItemKind.Class,
                    detail="Technology role",
                    documentation=(role.data or {}).get("description", ""),
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    if key == "site":
        sites = (symtab.get("site") or {}).values()
        for site in sites:
            items.append(
                types.CompletionItem(
                    label=site.name,
                    kind=types.CompletionItemKind.Enum,
                    detail="Site",
                )
            )
        return types.CompletionList(is_incomplete=False, items=items)

    # Complete enum values directly from schema (context-aware by cursor path).
    if key:
        colon_idx = line_before.find(":")
        in_value_position = colon_idx >= 0 and pos.character > colon_idx
        if in_value_position:
            _, schema_node = schema_for_key_at_position(document, pos, key)
            if schema_node:
                enum_values = enum_values_from_schema(schema_node)
                if enum_values:
                    for enum_value in enum_values:
                        items.append(
                            types.CompletionItem(
                                label=enum_value,
                                kind=types.CompletionItemKind.EnumMember,
                                detail=f"Enum value for `{key}`",
                            )
                        )
                    return types.CompletionList(is_incomplete=False, items=items)

    # Context-based completion
    if indent == 0 or stripped == "":
        for kw in VEDALANG_KEYWORDS:
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail=f"Top-level property: {kw}",
                )
            )
    elif parent == "technologies":
        for kw in TECHNOLOGY_KEYWORDS:
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail="Technology property",
                )
            )
    elif parent == "technology_roles":
        for kw in TECHNOLOGY_ROLE_KEYWORDS:
            items.append(
                types.CompletionItem(
                    label=kw,
                    kind=types.CompletionItemKind.Property,
                    detail="Technology role property",
                )
            )
    elif parent == "commodities":
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

    diagnostics.extend(schema_validation_diagnostics(document, parsed))
    if not looks_like_v0_2_source(parsed):
        return diagnostics

    raw_diagnostics = collect_v0_2_diagnostics(parsed)
    attach_source_positions(
        raw_diagnostics,
        source=parsed,
        source_text=source,
    )
    for diag in raw_diagnostics:
        line = int(diag.get("line", 1)) - 1
        end_line = int(diag.get("end_line", line + 1)) - 1
        column = int(diag.get("column", 1)) - 1
        end_column = int(diag.get("end_column", column + 1)) - 1
        range_ = types.Range(
            start=types.Position(line=max(0, line), character=max(0, column)),
            end=types.Position(
                line=max(0, end_line),
                character=max(column + 1, end_column),
            ),
        )
        object_id = diag.get("object_id")
        code = diag.get("code")
        message = str(diag.get("message", ""))
        if code and object_id:
            rendered = f"{code} {object_id}: {message}"
        elif code:
            rendered = f"{code}: {message}"
        else:
            rendered = message
        severity = types.DiagnosticSeverity.Warning
        if str(diag.get("severity", "warning")).lower() == "error":
            severity = types.DiagnosticSeverity.Error
        diagnostics.append(
            types.Diagnostic(
                range=range_,
                message=rendered,
                severity=severity,
                source="vedalang",
                code=code,
                data=diag,
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


# Import shared RES query engine and Mermaid renderer
from vedalang.viz.query_engine import query_res_graph, response_to_mermaid  # noqa: E402


@server.feature("veda/resGraph")
def res_graph(ls: VedaLangServer, params) -> dict:
    """Return RES graph response and Mermaid for the given document."""
    # Handle both {uri: ...} and {textDocument: {uri: ...}} formats
    include_variants = False
    mode = "source"
    granularity = "role"
    lens = "system"
    commodity_view = "collapse_scope"
    regions: list[str] = []
    case_name = None
    sectors: list[str] = []
    scopes: list[str] = []
    if hasattr(params, "textDocument"):
        td = params.textDocument
        uri = td.get("uri") if isinstance(td, dict) else td.uri
        include_variants = getattr(params, "includeVariants", False)
        mode = getattr(params, "mode", mode)
        granularity = getattr(params, "granularity", granularity)
        lens = getattr(params, "lens", lens)
        commodity_view = getattr(params, "commodityView", commodity_view)
        regions = list(getattr(params, "regions", regions) or [])
        case_name = getattr(params, "case", case_name)
        sectors = list(getattr(params, "sectors", sectors) or [])
        scopes = list(getattr(params, "scopes", scopes) or [])
    elif hasattr(params, "uri"):
        uri = params.uri
        include_variants = getattr(params, "includeVariants", False)
        mode = getattr(params, "mode", mode)
        granularity = getattr(params, "granularity", granularity)
        lens = getattr(params, "lens", lens)
        commodity_view = getattr(params, "commodityView", commodity_view)
        regions = list(getattr(params, "regions", regions) or [])
        case_name = getattr(params, "case", case_name)
        sectors = list(getattr(params, "sectors", sectors) or [])
        scopes = list(getattr(params, "scopes", scopes) or [])
    elif isinstance(params, dict):
        uri = params.get("textDocument", {}).get("uri") or params.get("uri")
        include_variants = params.get("includeVariants", False)
        mode = params.get("mode", mode)
        granularity = params.get("granularity", granularity)
        lens = params.get("lens", lens)
        commodity_view = params.get("commodityView", commodity_view)
        regions = list(params.get("regions", regions) or [])
        case_name = params.get("case", case_name)
        sectors = list(params.get("sectors", sectors) or [])
        scopes = list(params.get("scopes", scopes) or [])
    else:
        return {
            "graph": {"nodes": [], "edges": []},
            "mermaid": "",
            "error": "Invalid params: no uri found",
        }

    if include_variants and granularity == "role":
        granularity = "instance"

    parsed_uri = urlparse(uri)
    file_path = unquote(parsed_uri.path) if parsed_uri.path else ""
    if not file_path:
        return {
            "graph": {"nodes": [], "edges": []},
            "mermaid": "",
            "error": "Unable to resolve file path from URI",
        }
    request = {
        "version": "1",
        "file": file_path,
        "mode": mode,
        "granularity": granularity,
        "lens": lens,
        "commodity_view": commodity_view,
        "filters": {
            "regions": regions,
            "case": case_name,
            "sectors": sectors,
            "scopes": scopes,
        },
        "compiled": {
            "truth": "auto",
            "cache": True,
            "allow_partial": True,
        },
    }
    response = query_res_graph(request)
    response["mermaid"] = response_to_mermaid(response)
    return response


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
