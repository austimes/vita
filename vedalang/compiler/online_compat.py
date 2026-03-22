"""VEDA Online compatibility validation for TableIR.

These rules catch issues that xl2times tolerates but VEDA Online rejects.
"""

from __future__ import annotations

import re

SCALAR_TAGS = {"~STARTYEAR"}

# Tags that use wide-in-attribute format (attribute names as column headers)
# These should NOT have generic 'value' column - data goes under attribute headers
WIDE_ATTRIBUTE_TAGS = {"~FI_T", "~TFM_DINS-AT"}
SYSSETTINGS_TRIGGER_TAGS = {"~BOOKREGIONS_MAP", "~TIMESLICES"}
BOOKREGION_SHEET = "Region-Time Slices"
SYSSETTINGS_FILENAME = "SysSettings.xlsx"
VT_FILENAME_RE = re.compile(r"^VT_([A-Z][A-Z0-9]*)_ALL_V1\.xlsx$")


def validate_online_compat(tableir: dict) -> list[str]:
    """Validate TableIR for VEDA Online compatibility. Returns list of errors."""
    errors = []
    book_names: set[str] = set()
    vt_files: set[str] = set()

    for file in tableir.get("files", []):
        file_path = file.get("path", "<unknown>")
        file_tags = {
            table.get("tag", "")
            for sheet in file.get("sheets", [])
            for table in sheet.get("tables", [])
        }

        if file_tags & SYSSETTINGS_TRIGGER_TAGS:
            errors.extend(_validate_syssettings_file(file, str(file_path)))
            book_names.update(_book_names_from_file(file))

        if "~FI_PROCESS" in file_tags or "~FI_T" in file_tags:
            errors.extend(_validate_vt_file(file, str(file_path)))
            vt_files.add(str(file_path))

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

                if tag == "~TIMESLICES":
                    errors.extend(_validate_timeslices(rows, loc))

                uc_sets = table.get("uc_sets", {})
                errors.extend(_validate_uc_sets(uc_sets, loc))

    errors.extend(_validate_bookname_to_vt_mapping(book_names, vt_files))
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


def _validate_syssettings_file(file_spec: dict, loc: str) -> list[str]:
    errors = []
    if file_spec.get("path") != SYSSETTINGS_FILENAME:
        errors.append(
            f"{loc}: SysSettings workbook path must be exactly '{SYSSETTINGS_FILENAME}'"
        )

    sheets = file_spec.get("sheets", [])
    by_name = {sheet.get("name"): sheet for sheet in sheets}

    region_sheet = by_name.get(BOOKREGION_SHEET)
    if region_sheet is None:
        errors.append(
            f"{loc}: missing required '{BOOKREGION_SHEET}' sheet for "
            "~BOOKREGIONS_MAP and ~TIMESLICES"
        )
    else:
        tags = {table.get("tag") for table in region_sheet.get("tables", [])}
        if "~BOOKREGIONS_MAP" not in tags:
            errors.append(f"{loc}: '{BOOKREGION_SHEET}' sheet is missing ~BOOKREGIONS_MAP")
        if "~TIMESLICES" not in tags:
            errors.append(f"{loc}: '{BOOKREGION_SHEET}' sheet is missing ~TIMESLICES")

    for sheet in sheets:
        if sheet.get("name") == BOOKREGION_SHEET:
            continue
        tags = {table.get("tag") for table in sheet.get("tables", [])}
        if "~BOOKREGIONS_MAP" in tags or "~TIMESLICES" in tags:
            errors.append(
                f"{loc}: ~BOOKREGIONS_MAP and ~TIMESLICES must appear on "
                f"'{BOOKREGION_SHEET}'"
            )

    timeperiod_sheet = by_name.get("TimePeriods")
    if timeperiod_sheet is None:
        errors.append(f"{loc}: missing required 'TimePeriods' sheet")
    else:
        tags = {table.get("tag") for table in timeperiod_sheet.get("tables", [])}
        for tag in ("~STARTYEAR", "~MILESTONEYEARS"):
            if tag not in tags:
                errors.append(f"{loc}: 'TimePeriods' sheet is missing {tag}")

    defaults_sheet = by_name.get("Defaults")
    if defaults_sheet is None:
        errors.append(f"{loc}: missing required 'Defaults' sheet")
    elif "~CURRENCIES" not in {
        table.get("tag") for table in defaults_sheet.get("tables", [])
    }:
        errors.append(f"{loc}: 'Defaults' sheet is missing ~CURRENCIES")

    return errors


def _validate_vt_file(file_spec: dict, loc: str) -> list[str]:
    if VT_FILENAME_RE.fullmatch(str(file_spec.get("path", ""))):
        return []
    return [
        f"{loc}: VT workbook path must match 'VT_<VEDA_BOOK_NAME>_ALL_V1.xlsx'"
    ]


def _validate_timeslices(rows: list[dict], loc: str) -> list[str]:
    errors = []
    for idx, row in enumerate(rows):
        season = row.get("season")
        if isinstance(season, str) and season.upper() == "AN":
            errors.append(
                f"{loc}: Row {idx} uses 'AN'; annual timeslice must be 'ANNUAL'"
            )
    return errors


def _book_names_from_file(file_spec: dict) -> set[str]:
    book_names: set[str] = set()
    for sheet in file_spec.get("sheets", []):
        for table in sheet.get("tables", []):
            if table.get("tag") != "~BOOKREGIONS_MAP":
                continue
            for row in table.get("rows", []):
                book_name = row.get("bookname")
                if isinstance(book_name, str) and book_name:
                    book_names.add(book_name)
    return book_names


def _validate_bookname_to_vt_mapping(
    book_names: set[str], vt_files: set[str]
) -> list[str]:
    errors = []
    for book_name in sorted(book_names):
        expected = f"VT_{book_name}_ALL_V1.xlsx"
        if expected not in vt_files:
            errors.append(
                f"{SYSSETTINGS_FILENAME}: ~BOOKREGIONS_MAP bookname '{book_name}' "
                f"does not match any VT workbook filename (expected '{expected}')"
            )
    return errors
