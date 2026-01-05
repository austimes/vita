"""VEDA table schema definitions and validation.

This module defines dataclass schemas for VEDA tables, auto-generated from
xl2times veda-tags.json with manual layout overlays for tables VedaLang emits.

Key design principles:
- Canonical column names only (use_name from veda-tags.json), no aliases
- Strict validation: unknown columns are errors
- Required columns from remove_any_row_if_absent in veda-tags.json
- require_any_of rules from constraints.yaml

The schemas are used to validate TableIR before Excel emission, catching
format errors early with clear error messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Literal

import yaml

LayoutKind = Literal["long", "wide"]


@dataclass
class VedaFieldSchema:
    """Schema for a single field (column) in a VEDA table."""

    name: str  # Canonical internal name (use_name from veda-tags.json)
    canonical_header: str = ""  # The one header name to use (lowercase)
    required: bool = False  # Required per row (from remove_any_row_if_absent)
    multi_valued: bool = False  # Comma-separated list
    valid_values: set[str] | None = None  # Enum-like restriction
    query_field: bool = False  # pset_ci, cset_cd, etc.


@dataclass
class VedaTableLayout:
    """Layout rules for a VEDA table."""

    kind: LayoutKind  # "long" or "wide"
    index_fields: list[str] = field(default_factory=list)  # Row index columns
    attribute_field: str | None = None  # For long format
    value_field: str | None = None  # For long format
    allow_value_column: bool = True  # FI-style tables may disallow


@dataclass
class VedaTableSchema:
    """Complete schema for a VEDA table tag."""

    tag_name: str
    variant: str | None = None  # e.g., "AT" for ~TFM_DINS-AT
    layout: VedaTableLayout = field(
        default_factory=lambda: VedaTableLayout(kind="long", index_fields=[])
    )
    fields: dict[str, VedaFieldSchema] = field(default_factory=dict)
    # Canonical column names only (no aliases)
    allowed_columns: set[str] = field(default_factory=set)  # Known valid columns
    required_columns: set[str] = field(default_factory=set)  # Must be present
    forbidden_headers: set[str] = field(default_factory=set)  # Explicitly banned
    mutually_exclusive_groups: list[set[str]] = field(default_factory=list)
    require_any_of: list[set[str]] = field(default_factory=list)  # At least one


class TableValidationError(Exception):
    """Raised when table validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


# Default path to veda-tags.json (relative to this file)
DEFAULT_VEDA_TAGS_PATH = (
    Path(__file__).parent.parent.parent / "xl2times" / "config" / "veda-tags.json"
)

# Default path to attribute-master.json (VEDA attribute definitions)
DEFAULT_ATTRIBUTE_MASTER_PATH = (
    Path(__file__).parent.parent / "schema" / "attribute-master.json"
)


def load_veda_tags_schemas(
    veda_tags_path: Path | None = None,
) -> dict[str, VedaTableSchema]:
    """
    Load schemas from veda-tags.json using canonical column names only.

    Parses each tag entry and builds VedaTableSchema with:
    - VedaFieldSchema from valid_fields (using use_name as canonical)
    - required_columns from remove_any_row_if_absent flags
    - allowed_columns from all use_name values (no aliases)
    - valid_values from valid_values
    - multi_valued from comma-separated-list

    Args:
        veda_tags_path: Path to veda-tags.json. If None, uses default.

    Returns:
        Dict mapping normalized tag names (lowercase without ~) to schemas.
    """
    if veda_tags_path is None:
        veda_tags_path = DEFAULT_VEDA_TAGS_PATH

    with open(veda_tags_path) as f:
        veda_tags = json.load(f)

    schemas: dict[str, VedaTableSchema] = {}

    for tag_entry in veda_tags:
        tag_name = tag_entry["tag_name"]
        normalized_name = tag_name.lower()

        # Extract variant if present (e.g., "tfm_dins-at" -> base, variant)
        variant = None
        if "base_tag" in tag_entry:
            # This is a variant tag - skip for now, we'll handle base tags
            # The variant info is in mod_type
            continue

        # Build field schemas from valid_fields
        fields: dict[str, VedaFieldSchema] = {}
        allowed_columns: set[str] = set()
        required_columns: set[str] = set()

        for field_def in tag_entry.get("valid_fields", []):
            # Use use_name as the canonical column name (no aliases)
            field_name = field_def.get("use_name", field_def["name"])
            canonical_header = field_name.lower()

            # Add to allowed columns (canonical + all aliases)
            allowed_columns.add(canonical_header)
            for alias in field_def.get("aliases", []):
                allowed_columns.add(alias.lower())

            # Determine if field is required (from xl2times logic)
            required = (
                field_def.get("remove_any_row_if_absent", False)
                or field_def.get("remove_first_row_if_absent", False)
            )
            if required:
                required_columns.add(canonical_header)

            # Check for multi-valued (comma-separated)
            multi_valued = field_def.get("comma-separated-list", False)

            # Check for valid values enum
            valid_values_list = field_def.get("valid_values")
            valid_values = set(valid_values_list) if valid_values_list else None

            # Check if query field
            query_field = field_def.get("query_field", False)

            fields[field_name] = VedaFieldSchema(
                name=field_name,
                canonical_header=canonical_header,
                required=required,
                multi_valued=multi_valued,
                valid_values=valid_values,
                query_field=query_field,
            )

        schemas[normalized_name] = VedaTableSchema(
            tag_name=tag_name,
            variant=variant,
            fields=fields,
            allowed_columns=allowed_columns,
            required_columns=required_columns,
        )

    return schemas


def apply_manual_layouts(schemas: dict[str, VedaTableSchema]) -> None:
    """
    Apply manual layout overlays for tables VedaLang emits.

    veda-tags.json doesn't encode layouts, so we apply them manually.
    This modifies schemas in place.

    Args:
        schemas: Dict of schemas (will be modified in place)
    """
    # ~FI_COMM - wide format, commodity definition table
    if "fi_comm" in schemas:
        schemas["fi_comm"].layout = VedaTableLayout(
            kind="wide",
            index_fields=["region", "csets", "commodity"],
            allow_value_column=True,
        )

    # ~FI_PROCESS - wide format, process definition table
    if "fi_process" in schemas:
        schemas["fi_process"].layout = VedaTableLayout(
            kind="wide",
            index_fields=["region", "process", "sets"],
            allow_value_column=True,
        )

    # ~FI_T - wide-in-attribute format where attributes are column headers
    # No generic 'value' column - data goes directly under attribute column names
    if "fi_t" in schemas:
        schemas["fi_t"].layout = VedaTableLayout(
            kind="wide",
            index_fields=["region", "process", "commodity", "year"],
            attribute_field=None,  # Attributes are column headers, not row values
            value_field=None,  # No 'value' column - data under attribute headers
            allow_value_column=True,  # ~FI_T can use 'value' for attribute-based rows (e.g., ENV_ACT)
        )
        # Add common attribute column headers that VedaLang emits
        # NOTE: Use CANONICAL attribute names from attribute-master.json.
        # xl2times now recognizes both canonical names and aliases.
        schemas["fi_t"].allowed_columns.update({
            "com_proj", "eff", "ncap_cost", "ncap_fom", "act_cost", "ncap_tlife",
            "ire_price", "act_bnd", "cap_bnd", "ncap_bnd", "share-o", "share-i",
            "commodity-in", "commodity-out", "commodity", "attribute", "value",
        })

    # ~TFM_DINS - long format
    if "tfm_dins" in schemas:
        schemas["tfm_dins"].layout = VedaTableLayout(
            kind="long",
            index_fields=["region", "process", "year"],
            attribute_field="attribute",
            value_field="value",
            allow_value_column=True,
        )
        # Create AT variant schema - attribute is NOT required because
        # the attribute name becomes the column header (e.g., com_cstnet)
        at_fields = {
            name: VedaFieldSchema(
                name=f.name,
                canonical_header=f.canonical_header,
                required=False if name == "attribute" else f.required,
                multi_valued=f.multi_valued,
                valid_values=f.valid_values.copy() if f.valid_values else None,
                query_field=f.query_field,
            )
            for name, f in schemas["tfm_dins"].fields.items()
        }
        # Build allowed columns for AT variant - include attribute names as columns
        at_allowed = schemas["tfm_dins"].allowed_columns.copy()
        at_allowed.update({
            "cset_cn", "com_cstnet",  # Commodity price columns
        })
        schemas["tfm_dins-at"] = VedaTableSchema(
            tag_name="tfm_dins-at",
            variant="at",
            layout=VedaTableLayout(
                kind="wide",
                index_fields=["region", "process", "year"],
                allow_value_column=False,
            ),
            fields=at_fields,
            allowed_columns=at_allowed,
            forbidden_headers={"value", "attribute"},
        )

    # ~TFM_INS - similar to DINS
    if "tfm_ins" in schemas:
        schemas["tfm_ins"].layout = VedaTableLayout(
            kind="long",
            index_fields=["region", "timeslice"],
            attribute_field="attribute",
            value_field="value",
            allow_value_column=True,
        )

    # ~UC_T - long format with query fields
    if "uc_t" in schemas:
        schemas["uc_t"].layout = VedaTableLayout(
            kind="long",
            index_fields=["region", "uc_n", "year"],
            value_field="value",
            allow_value_column=True,
        )
        # Mutually exclusive commodity query fields
        schemas["uc_t"].mutually_exclusive_groups.append(
            {"cset_cd", "cset_cn", "cset_set"}
        )
        # Mutually exclusive process query fields
        schemas["uc_t"].mutually_exclusive_groups.append(
            {"pset_pn", "pset_pd", "pset_set", "pset_ci", "pset_co"}
        )
        # Add columns that VedaLang emits for user constraints
        schemas["uc_t"].allowed_columns.update({
            "uc_comprd", "uc_rhs", "uc_rhsrt", "commodity", "uc_sets", "value",
            "process", "uc_act",  # Activity share constraints
        })


# Default path to constraints.yaml
DEFAULT_CONSTRAINTS_PATH = (
    Path(__file__).parent.parent.parent / "rules" / "constraints.yaml"
)


def apply_constraints(
    schemas: dict[str, VedaTableSchema],
    constraints_path: Path | None = None,
) -> None:
    """
    Apply require_any_of rules from constraints.yaml.

    Loads any_of_fields from constraints.yaml and adds them to schemas
    as require_any_of groups. Field names are lowercased to match
    canonical column names.

    Args:
        schemas: Dict of schemas (will be modified in place)
        constraints_path: Path to constraints.yaml. If None, uses default.
    """
    if constraints_path is None:
        constraints_path = DEFAULT_CONSTRAINTS_PATH

    if not constraints_path.exists():
        return  # No constraints file, skip

    with open(constraints_path) as f:
        constraints = yaml.safe_load(f)

    tag_constraints = constraints.get("tag_constraints", {})

    for tag_key, tag_rules in tag_constraints.items():
        # Normalize tag name (remove ~ prefix, lowercase)
        normalized_tag = tag_key.lower().lstrip("~")
        schema = schemas.get(normalized_tag)
        if not schema:
            continue

        # Add any_of_fields as require_any_of groups
        for any_of in tag_rules.get("any_of_fields", []):
            fields = any_of.get("fields", [])
            if fields:
                # Lowercase field names to match canonical column names
                schema.require_any_of.append({f.lower() for f in fields})


def load_attribute_master(
    path: Path | None = None,
) -> dict[str, dict]:
    """
    Load VEDA attribute master data.

    The attribute master defines all valid VEDA attributes with metadata
    including canonical column headers, descriptions, and type information.

    Args:
        path: Path to attribute-master.json. If None, uses default.

    Returns:
        Dict mapping uppercase VEDA attribute name -> metadata dict
        with at least a 'column_header' entry.
    """
    if path is None:
        path = DEFAULT_ATTRIBUTE_MASTER_PATH

    if not path.exists():
        return {}

    with open(path) as f:
        data = json.load(f)

    # Support either {"attributes": {...}} or just a flat dict for flexibility
    attributes = data.get("attributes", data)

    # Normalize: ensure keys are uppercase, column_header exists
    normalized: dict[str, dict] = {}
    for raw_name, meta in attributes.items():
        if raw_name.startswith("_"):
            continue  # Skip metadata fields like _comment, _source
        veda_name = raw_name.upper()
        column_header = meta.get("column_header", veda_name.lower())
        meta = {**meta, "column_header": column_header}
        normalized[veda_name] = meta

    return normalized


def _build_attribute_alias_map(
    attributes: dict[str, dict],
) -> dict[str, str]:
    """
    Build a mapping from alias column headers to their canonical names.

    Args:
        attributes: Attribute master dict (uppercase name -> metadata)

    Returns:
        Dict mapping lowercase alias -> lowercase canonical column header
    """
    alias_to_canonical: dict[str, str] = {}
    for meta in attributes.values():
        canonical = meta.get("column_header", "").lower()
        if not canonical:
            continue
        # Map all aliases to canonical
        for alias in meta.get("column_headers", []):
            alias_lower = alias.lower()
            if alias_lower != canonical:
                alias_to_canonical[alias_lower] = canonical
    return alias_to_canonical


# Cached alias map (lazy initialization)
_cached_alias_map: dict[str, str] | None = None


def get_attribute_alias_map() -> dict[str, str]:
    """Get cached alias-to-canonical map, building if needed."""
    global _cached_alias_map
    if _cached_alias_map is None:
        attrs = load_attribute_master()
        _cached_alias_map = _build_attribute_alias_map(attrs)
    return _cached_alias_map


def apply_attribute_columns(
    schemas: dict[str, VedaTableSchema],
    attribute_master_path: Path | None = None,
) -> None:
    """
    Extend allowed_columns of attribute-wide tables using the attribute master.

    FI_T and TFM_DINS-AT tables allow attribute names as column headers
    (e.g., "eff", "ncap_cost", "com_cstnet"). This function loads
    only CANONICAL attribute column names from the attribute master and adds
    them as allowed columns for these tables.

    CANONICAL-ONLY: Aliases (e.g., "demand", "invcost", "varom") are NOT
    included in allowed_columns. The validator will reject alias columns
    with a helpful error message suggesting the canonical name.

    Args:
        schemas: Dict of schemas (will be modified in place)
        attribute_master_path: Path to attribute-master.json. If None, uses default.
    """
    attributes = load_attribute_master(attribute_master_path)
    if not attributes:
        return

    # CANONICAL column headers ONLY (no aliases)
    # Uses column_header (singular) - the canonical name
    canonical_headers: set[str] = set()
    for meta in attributes.values():
        canonical = meta.get("column_header", "")
        if canonical:
            canonical_headers.add(canonical.lower())

    # ~FI_T: process/demand attributes as columns, no 'value' column
    if "fi_t" in schemas:
        schemas["fi_t"].allowed_columns.update(canonical_headers)

    # ~TFM_DINS-AT: scenario attributes as columns
    if "tfm_dins-at" in schemas:
        schemas["tfm_dins-at"].allowed_columns.update(canonical_headers)

    # ~UC_T: user constraint tables may also use attribute columns
    if "uc_t" in schemas:
        schemas["uc_t"].allowed_columns.update(canonical_headers)


def get_all_schemas(veda_tags_path: Path | None = None) -> dict[str, VedaTableSchema]:
    """
    Load all VEDA table schemas with manual overlays applied.

    Args:
        veda_tags_path: Optional path to veda-tags.json

    Returns:
        Dict mapping normalized tag names to schemas
    """
    schemas = load_veda_tags_schemas(veda_tags_path)
    apply_manual_layouts(schemas)
    apply_attribute_columns(schemas)
    apply_constraints(schemas)
    return schemas


def _normalize_tag(tag: str) -> str:
    """Normalize a tag name to lowercase without leading ~."""
    return tag.lower().lstrip("~")


def _suggest_column(unknown: str, known: set[str]) -> str:
    """Suggest a similar column name if one exists."""
    lower_known = [k.lower() for k in known]
    matches = get_close_matches(unknown.lower(), lower_known, n=1, cutoff=0.6)
    if matches:
        # Find original case
        for k in known:
            if k.lower() == matches[0]:
                return f" Did you mean '{k}'?"
    return ""


def validate_table_rows(
    tag: str,
    rows: list[dict],
    schema: VedaTableSchema,
) -> list[str]:
    """
    Validate table rows against a schema using canonical column names.

    Checks:
    - Unknown columns (canonical names only, no aliases)
    - Required columns are present in each row
    - require_any_of groups have at least one column present
    - Forbidden headers are not used
    - Enum values are valid
    - Mutually exclusive fields aren't both present

    Args:
        tag: The VEDA tag name (for error messages)
        rows: List of row dicts
        schema: The table schema

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    if not rows:
        return errors

    # Get all columns used in the table (normalized to lowercase)
    all_columns: set[str] = set()
    for row in rows:
        all_columns.update(k.lower() for k in row.keys())

    # Enforce layout-level prohibition on a generic 'value' column
    if not schema.layout.allow_value_column:
        if "value" in all_columns:
            errors.append(
                f"{tag}: 'value' column not allowed - use attribute columns instead"
            )

    # Check for forbidden headers
    for col in all_columns:
        if col in schema.forbidden_headers:
            errors.append(
                f"{tag}: forbidden column '{col}' not allowed in this table variant"
            )

    # Check for unknown columns (canonical names only - strict by default)
    # Alias columns get a specific "use canonical X" error message
    alias_map = get_attribute_alias_map()
    if schema.allowed_columns:
        for col in all_columns:
            if col not in schema.allowed_columns:
                # Check if this is a known alias
                canonical = alias_map.get(col)
                if canonical:
                    errors.append(
                        f"{tag}: '{col}' is an alias column. "
                        f"Use canonical name '{canonical}' instead."
                    )
                else:
                    hint = _suggest_column(col, schema.allowed_columns)
                    errors.append(f"{tag}: unknown column '{col}'.{hint}")

    # Validate each row
    for i, row in enumerate(rows):
        row_id = _format_row_id(row, schema.layout.index_fields, i)
        row_keys_lower = {k.lower() for k in row.keys()}

        # Check required columns (from schema.required_columns)
        missing = schema.required_columns - row_keys_lower
        for col in sorted(missing):
            errors.append(f"{tag} {row_id}: missing required column '{col}'")

        # Check require_any_of groups (at least one must be present)
        for group in schema.require_any_of:
            present = group & row_keys_lower
            if not present:
                group_str = ", ".join(sorted(group))
                errors.append(
                    f"{tag} {row_id}: must have at least one of [{group_str}]"
                )

        # Check enum values
        for field_name, field_schema in schema.fields.items():
            if field_schema.valid_values:
                canonical = field_schema.canonical_header
                # Find the value if present (case-insensitive key lookup)
                value = None
                for k, v in row.items():
                    if k.lower() == canonical:
                        value = v
                        break

                if value is not None and value not in field_schema.valid_values:
                    valid_str = ", ".join(sorted(field_schema.valid_values))
                    errors.append(
                        f"{tag} {row_id}: invalid value '{value}' for '{field_name}'. "
                        f"Must be one of: {valid_str}"
                    )

        # Check mutually exclusive groups
        for group in schema.mutually_exclusive_groups:
            present = []
            for field_name in group:
                if field_name in schema.fields:
                    canonical = schema.fields[field_name].canonical_header
                    if canonical in row_keys_lower:
                        present.append(field_name)
            if len(present) > 1:
                errors.append(
                    f"{tag} {row_id}: mutually exclusive fields present: "
                    f"{', '.join(sorted(present))}"
                )

    return errors


def _format_row_id(row: dict, index_fields: list[str], row_num: int) -> str:
    """Format a row identifier for error messages."""
    parts = [f"row {row_num + 1}"]
    for fld in index_fields:
        if fld in row:
            parts.append(f"{fld}={row[fld]}")
    return f"({', '.join(parts)})"


def validate_tableir(
    tableir: dict,
    schemas: dict[str, VedaTableSchema] | None = None,
) -> list[str]:
    """
    Validate TableIR against VEDA schemas using canonical column names.

    Iterates through all files/sheets/tables in the TableIR structure
    and validates each table against its schema. Validation is strict:
    only canonical column names are allowed (no aliases).

    Args:
        tableir: TableIR dict with files/sheets/tables structure
        schemas: Optional pre-loaded schemas. If None, loads from default path.

    Returns:
        List of error messages (empty if valid)
    """
    if schemas is None:
        schemas = get_all_schemas()

    errors: list[str] = []

    for file_def in tableir.get("files", []):
        file_path = file_def.get("path", "<unknown>")
        for sheet_def in file_def.get("sheets", []):
            sheet_name = sheet_def.get("name", "<unknown>")
            for table_def in sheet_def.get("tables", []):
                tag = table_def.get("tag", "")
                rows = table_def.get("rows", [])

                if not tag:
                    continue

                normalized_tag = _normalize_tag(tag)
                schema = schemas.get(normalized_tag)

                if schema is None:
                    # Unknown tag - not an error, just skip
                    continue

                table_errors = validate_table_rows(
                    tag,
                    rows,
                    schema,
                )
                for err in table_errors:
                    errors.append(f"{file_path}/{sheet_name}: {err}")

    return errors


# Singleton for loaded schemas (lazy initialization)
_cached_schemas: dict[str, VedaTableSchema] | None = None


def get_cached_schemas() -> dict[str, VedaTableSchema]:
    """Get cached schemas, loading if needed."""
    global _cached_schemas
    if _cached_schemas is None:
        _cached_schemas = get_all_schemas()
    return _cached_schemas
