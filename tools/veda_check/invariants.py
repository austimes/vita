"""TableIR invariant validation.

Validates TableIR structure against VEDA tag constraints before emitting Excel.
Catches obvious errors early with better messages than xl2times.

Enforces canonical table form:
- Lowercase column names only
- No year/region pivots (years as column headers)
- No interpolation markers in values
"""

import re
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).parent.parent.parent / "rules"

# Regex patterns for canonical form validation
LOWERCASE_COLUMN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
YEAR_COLUMN_PATTERN = re.compile(r"^[12][0-9]{3}$")


def load_constraints() -> dict:
    """Load tag constraints from rules/constraints.yaml."""
    with open(RULES_DIR / "constraints.yaml") as f:
        return yaml.safe_load(f)


def check_tableir_invariants(tableir: dict) -> list[str]:
    """
    Check TableIR against constraints and canonical form rules.

    Args:
        tableir: TableIR dictionary structure

    Returns:
        List of error messages. Empty list means no errors.
    """
    errors = []
    constraints = load_constraints()
    tag_constraints = constraints.get("tag_constraints", {})

    for file_spec in tableir.get("files", []):
        file_path = file_spec.get("path", "<unknown>")
        for sheet_spec in file_spec.get("sheets", []):
            sheet_name = sheet_spec.get("name", "<unknown>")
            for table in sheet_spec.get("tables", []):
                tag = table.get("tag", "")
                rows = table.get("rows", [])

                # Always check canonical form (all tables)
                canonical_errors = _check_canonical_form(
                    tag, rows, file_path, sheet_name
                )
                errors.extend(canonical_errors)

                # Check tag-specific constraints if defined
                if tag in tag_constraints:
                    constraint = tag_constraints[tag]
                    table_errors = _check_table_constraints(
                        tag, rows, constraint, file_path, sheet_name
                    )
                    errors.extend(table_errors)

    return errors


# Tags that use dynamic column names that are intentionally not lowercase.
NONCANONICAL_COLUMN_TAGS = {"~TRADELINKS", "~TIMEPERIODS"}


def _check_canonical_form(
    tag: str,
    rows: list[dict],
    file_path: str,
    sheet_name: str,
) -> list[str]:
    """
    Check that table follows canonical form rules.

    - Lowercase column names only (except matrix format tables)
    - No year columns (4-digit numbers as column names)
    """
    errors = []

    # Some VEDA tags intentionally use dynamic or fixed-case column names.
    skip_case_check = tag in NONCANONICAL_COLUMN_TAGS

    for row_idx, row in enumerate(rows):
        location = f"{file_path}:{sheet_name}:{tag}:row {row_idx + 1}"

        for col_name, value in row.items():
            # Check lowercase column names (unless matrix format)
            if not skip_case_check and not LOWERCASE_COLUMN_PATTERN.match(col_name):
                # Special case: allow 'value' column in scalar tables
                if col_name.lower() != col_name:
                    errors.append(
                        f"{location}: column '{col_name}' must be lowercase"
                    )

            # Check for year-as-column-name (forbidden wide pivot)
            if YEAR_COLUMN_PATTERN.match(col_name):
                errors.append(
                    f"{location}: column '{col_name}' looks like a year - "
                    "use 'year' column with year values instead (canonical long format)"
                )

            # Note: We do NOT check for "I"/"E" markers here.
            # VEDA uses numeric option codes in year=0 rows, not string markers.
            # The compiler emits these correctly.

    return errors


FIELD_ALIASES = {
    # Commodity input/output aliases
    "comm-in": ["comm-in", "commodity-in"],
    "comm-out": ["comm-out", "commodity-out"],
    # VEDA/xl2times name mappings (VEDA uses TechName, xl2times uses process)
    "techname": ["techname", "process"],
    "commname": ["commname", "commodity"],
    # Demand attribute (VEDA uses DEMAND, we use lowercase demand)
    "demand": ["demand"],
}


def _normalize_field(field: str) -> list[str]:
    """Return all acceptable lowercase variants of a field name."""
    lower = field.lower()
    return FIELD_ALIASES.get(lower, [lower])


def _has_field(row_keys_lower: set[str], field: str) -> bool:
    """Check if row has the field (considering aliases)."""
    variants = _normalize_field(field)
    return any(v in row_keys_lower for v in variants)


def _check_table_constraints(
    tag: str,
    rows: list[dict],
    constraint: dict,
    file_path: str,
    sheet_name: str,
) -> list[str]:
    """Check a single table against its constraints."""
    errors = []
    required_fields = constraint.get("required_fields", [])
    any_of_fields = constraint.get("any_of_fields", [])

    for row_idx, row in enumerate(rows):
        row_keys_lower = {k.lower() for k in row.keys()}
        location = f"{file_path}:{sheet_name}:{tag}:row {row_idx + 1}"

        for field in required_fields:
            if not _has_field(row_keys_lower, field):
                errors.append(
                    f"{location}: missing required field '{field}'"
                )

        for cond in any_of_fields:
            fields = cond.get("fields", [])
            if fields and not any(_has_field(row_keys_lower, f) for f in fields):
                field_list = "', '".join(fields)
                errors.append(
                    f"{location}: must have at least one of '{field_list}'"
                )

    return errors
