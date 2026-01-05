"""VEDA Online compatibility validation for TableIR.

These rules catch issues that xl2times tolerates but VEDA Online rejects.
"""

SCALAR_TAGS = {"~STARTYEAR", "~ACTIVEPDEF"}

# Tags that use wide-in-attribute format (attribute names as column headers)
# These should NOT have generic 'value' column - data goes under attribute headers
WIDE_ATTRIBUTE_TAGS = {"~FI_T", "~TFM_DINS-AT"}


def validate_online_compat(tableir: dict) -> list[str]:
    """Validate TableIR for VEDA Online compatibility. Returns list of errors."""
    errors = []

    for file in tableir.get("files", []):
        file_path = file.get("path", "<unknown>")
        for sheet in file.get("sheets", []):
            sheet_name = sheet.get("name", "<unknown>")
            for table in sheet.get("tables", []):
                tag = table.get("tag", "")
                rows = table.get("rows", [])
                loc = f"{file_path}/{sheet_name}/{tag}"

                if tag in SCALAR_TAGS:
                    errors.extend(_validate_scalar_tag(tag, rows, loc))

                errors.extend(_validate_year_columns(tag, rows, loc))

                if tag in WIDE_ATTRIBUTE_TAGS:
                    errors.extend(_validate_no_value_column(tag, rows, loc))

                uc_sets = table.get("uc_sets", {})
                errors.extend(_validate_uc_sets(uc_sets, loc))

    return errors


def _validate_scalar_tag(tag: str, rows: list[dict], loc: str) -> list[str]:
    """Check scalar tag rows only have 'value' key with correct type."""
    errors = []
    for i, row in enumerate(rows):
        extra_keys = set(row.keys()) - {"value"}
        if extra_keys:
            errors.append(
                f"{loc}: Scalar tag row {i} has extra keys {extra_keys}, "
                f"only 'value' is allowed"
            )

        value = row.get("value")
        if tag == "~STARTYEAR" and value is not None:
            if not isinstance(value, int):
                errors.append(
                    f"{loc}: ~STARTYEAR value must be int, got {type(value).__name__}"
                )

    return errors


def _validate_year_columns(tag: str, rows: list[dict], loc: str) -> list[str]:
    """Check 'year' column values are int, not null/string."""
    errors = []
    for i, row in enumerate(rows):
        if "year" in row:
            year_val = row["year"]
            if year_val is None:
                errors.append(f"{loc}: Row {i} has null 'year' value")
            elif not isinstance(year_val, int):
                errors.append(
                    f"{loc}: Row {i} 'year' must be int, got {type(year_val).__name__}"
                )
    return errors


def _validate_no_value_column(tag: str, rows: list[dict], loc: str) -> list[str]:
    """Forbid generic 'value' column in wide-attribute format tags.

    Exception: If the row has an 'attribute' column, then 'value' is allowed
    because the row is using long-format (attribute + value) within the table.
    This is valid for tags like ~FI_T that support mixed formats.
    """
    errors = []
    for i, row in enumerate(rows):
        if "value" in row and "attribute" not in row:
            errors.append(
                f"{loc}: Row {i} has 'value' column in wide-attribute tag "
                f"(use specific attribute column names instead)"
            )
    return errors


def _validate_uc_sets(uc_sets: dict, loc: str) -> list[str]:
    """Check no trailing colons in uc_sets values."""
    errors = []
    for key, value in uc_sets.items():
        if isinstance(value, str) and value.endswith(":"):
            errors.append(
                f"{loc}: uc_sets[{key}] value '{value}' has trailing colon"
            )
    return errors
