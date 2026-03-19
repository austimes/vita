"""Extract and display TIMES results from GDX files."""

import csv
import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Group

from tools.cli_ui import data_table, message_panel, render_to_text, status_panel

from .gdx_utils import dump_symbol_csv, find_gdxdump

VALUE_COLUMNS = ("VAL", "VALUE", "LEVEL", "L")
PROCESS_COLUMNS = ("P", "PRC", "PROCESS")
YEAR_COLUMNS = (
    "ALLYEAR",
    "ALL_YEAR",
    "YEAR",
    "DATAYEAR",
    "DATA_YEAR",
    "Y",
    "YR",
    "LL",
)
VINTAGE_COLUMNS = ("T", "VINTAGE", "ALLYEAR", "YEAR", "PASTYEAR", "LL")
REGION_COLUMNS = ("R", "REG", "REGION")
TIMESLICE_COLUMNS = ("S", "TS", "TIMESLICE", "SLICE")
COMMODITY_COLUMNS = ("C", "COM", "COMMODITY")
ACTIVITY_SYMBOL_PREFERENCE = ("VAR_ACT", "PAR_ACTM", "PAR_ACT")
NEW_CAPACITY_SYMBOL_PREFERENCE = ("VAR_NCAP", "PAR_NCAPM", "PAR_NCAP")
INSTALLED_CAPACITY_SYMBOL_PREFERENCE = ("VAR_CAP", "PAR_CAPM", "PAR_NCAPM")
FLOW_SYMBOL_PREFERENCE = ("VAR_FLO", "PAR_FLO", "PAR_FLOM")
VALUE_FLOW_SYMBOL_PREFERENCE = ("VAL_FLO",)

ParsedSymbolRow = tuple[dict[str, str], float, str, str]


@dataclass
class TimesResults:
    """Container for extracted TIMES results."""

    gdx_path: Path
    objective: float | None = None
    objective_breakdown: dict[str, float] = field(default_factory=dict)
    var_act: list[dict[str, Any]] = field(default_factory=list)
    var_ncap: list[dict[str, Any]] = field(default_factory=list)
    var_cap: list[dict[str, Any]] = field(default_factory=list)
    var_flo: list[dict[str, Any]] = field(default_factory=list)
    var_flo_source: str | None = None
    val_flo: list[dict[str, Any]] = field(default_factory=list)
    val_flo_source: str | None = None
    par_pasti: list[dict[str, Any]] = field(default_factory=list)  # NCAP_PASTI input
    par_resid: list[dict[str, Any]] = field(default_factory=list)  # PRC_RESID input
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gdx_path": str(self.gdx_path),
            "objective": self.objective,
            "objective_breakdown": self.objective_breakdown,
            "var_act": self.var_act,
            "var_ncap": self.var_ncap,
            "var_cap": self.var_cap,
            "var_flo": self.var_flo,
            "var_flo_source": self.var_flo_source,
            "val_flo": self.val_flo,
            "val_flo_source": self.val_flo_source,
            "par_pasti": self.par_pasti,
            "par_resid": self.par_resid,
            "errors": self.errors,
        }


def parse_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV output from gdxdump."""
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def _normalize_header(header: str | None) -> str:
    if not header:
        return ""
    return header.strip().strip('"').replace("-", "_").replace(" ", "_").upper()


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = _normalize_header(key)
        if not normalized_key:
            continue
        normalized[normalized_key] = (value or "").strip().strip('"')
    return normalized


def _get_field(row: dict[str, str], *aliases: str, default: str = "") -> str:
    for alias in aliases:
        if alias in row:
            return row[alias]
    return default


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text.replace("d", "e").replace("D", "e"))
    except ValueError:
        return None


def _apply_limit(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None or limit <= 0:
        return rows
    return rows[:limit]


def _normalize_timeslice(row: dict[str, str], *, default: str = "") -> str:
    timeslice = _get_field(row, *TIMESLICE_COLUMNS)
    return timeslice or default


def _extract_nonzero_rows_from_symbols(
    *,
    gdx_path: Path,
    gdxdump: str,
    symbol_preference: tuple[str, ...],
    process_filter: list[str] | None,
    year_filter: list[str] | None,
) -> tuple[str | None, list[ParsedSymbolRow]]:
    """Return first preferred symbol with non-zero rows that pass filters."""
    for symbol in symbol_preference:
        symbol_csv = dump_symbol_csv(gdx_path, symbol, gdxdump)
        if not symbol_csv:
            continue

        rows: list[ParsedSymbolRow] = []
        for raw_row in parse_csv(symbol_csv):
            row = _normalize_row(raw_row)
            val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
            if val is None:
                continue
            if abs(val) < 1e-9:
                continue

            process = _get_field(row, *PROCESS_COLUMNS)
            year = _get_field(row, *YEAR_COLUMNS)

            if process_filter and not any(
                candidate.lower() in process.lower() for candidate in process_filter
            ):
                continue
            if year_filter and year not in year_filter:
                continue

            rows.append((row, val, process, year))

        if rows:
            return symbol, rows

    return None, []


def _extract_flow_rows(
    *,
    gdx_path: Path,
    gdxdump: str,
    symbol_preference: tuple[str, ...],
    process_filter: list[str] | None,
    year_filter: list[str] | None,
    limit: int | None,
    default_timeslice: str = "",
) -> tuple[str | None, list[dict[str, Any]]]:
    """Extract solved flow rows using a deterministic symbol fallback order.

    Preferred contract: use `VAR_FLO` first, then `PAR_FLO` and `PAR_FLOM`
    for tiny fixture/model shapes where solved `VAR_FLO` is empty.
    """
    symbol, source_rows = _extract_nonzero_rows_from_symbols(
        gdx_path=gdx_path,
        gdxdump=gdxdump,
        symbol_preference=symbol_preference,
        process_filter=process_filter,
        year_filter=year_filter,
    )
    if symbol is None:
        return None, []

    flow_rows = [
        {
            "region": _get_field(row, *REGION_COLUMNS),
            "year": year,
            "process": process,
            "commodity": _get_field(row, *COMMODITY_COLUMNS),
            "timeslice": _normalize_timeslice(row, default=default_timeslice),
            "level": val,
        }
        for row, val, process, year in source_rows
    ]
    flow_rows.sort(key=lambda extracted: abs(extracted["level"]), reverse=True)
    return symbol, _apply_limit(flow_rows, limit)


def extract_results(
    gdx_path: Path,
    process_filter: list[str] | None = None,
    year_filter: list[str] | None = None,
    include_flows: bool = False,
    limit: int | None = 50,
) -> TimesResults:
    """Extract results from a GDX file."""
    results = TimesResults(gdx_path=gdx_path)

    gdxdump = find_gdxdump()
    if not gdxdump:
        results.errors.append("gdxdump not found. Set GDXDUMP env var or install GAMS.")
        return results

    if not gdx_path.exists():
        results.errors.append(f"GDX file not found: {gdx_path}")
        return results

    # Extract objective value (OBJZ scalar)
    objz_csv = dump_symbol_csv(gdx_path, "OBJZ", gdxdump)
    if objz_csv:
        rows = [_normalize_row(row) for row in parse_csv(objz_csv)]
        for row in rows:
            value = _parse_float(_get_field(row, *VALUE_COLUMNS))
            if value is not None:
                results.objective = value
                break

    # Extract objective breakdown (VAR_OBJ)
    var_obj_csv = dump_symbol_csv(gdx_path, "VAR_OBJ", gdxdump)
    if var_obj_csv:
        for raw_row in parse_csv(var_obj_csv):
            row = _normalize_row(raw_row)
            component = _get_field(row, "OBV", "OBJ", "COMPONENT")
            value = _parse_float(_get_field(row, *VALUE_COLUMNS))
            if component and value is not None:
                results.objective_breakdown[component] = value

    # Extract process activity with fallback for toy-model PAR_* symbols.
    _, activity_rows = _extract_nonzero_rows_from_symbols(
        gdx_path=gdx_path,
        gdxdump=gdxdump,
        symbol_preference=ACTIVITY_SYMBOL_PREFERENCE,
        process_filter=process_filter,
        year_filter=year_filter,
    )
    for row, val, process, year in activity_rows:
        results.var_act.append(
            {
                "region": _get_field(row, *REGION_COLUMNS),
                "vintage": _get_field(row, *VINTAGE_COLUMNS, default=year),
                "year": year,
                "process": process,
                "timeslice": _get_field(row, *TIMESLICE_COLUMNS),
                "level": val,
            }
        )

    # Sort by level descending, limit
    results.var_act.sort(key=lambda r: abs(r["level"]), reverse=True)
    results.var_act = _apply_limit(results.var_act, limit)

    # Extract new capacity with fallback for toy-model PAR_* symbols.
    _, new_capacity_rows = _extract_nonzero_rows_from_symbols(
        gdx_path=gdx_path,
        gdxdump=gdxdump,
        symbol_preference=NEW_CAPACITY_SYMBOL_PREFERENCE,
        process_filter=process_filter,
        year_filter=year_filter,
    )
    for row, val, process, year in new_capacity_rows:
        results.var_ncap.append(
            {
                "region": _get_field(row, *REGION_COLUMNS),
                "year": year,
                "process": process,
                "level": val,
            }
        )

    results.var_ncap.sort(key=lambda r: abs(r["level"]), reverse=True)
    results.var_ncap = _apply_limit(results.var_ncap, limit)

    # Extract installed capacity; PAR_NCAPM is the final fallback for toy models
    # where VAR_CAP/PAR_CAPM are structurally empty.
    _, installed_capacity_rows = _extract_nonzero_rows_from_symbols(
        gdx_path=gdx_path,
        gdxdump=gdxdump,
        symbol_preference=INSTALLED_CAPACITY_SYMBOL_PREFERENCE,
        process_filter=process_filter,
        year_filter=year_filter,
    )
    for row, val, process, year in installed_capacity_rows:
        results.var_cap.append(
            {
                "region": _get_field(row, *REGION_COLUMNS),
                "year": year,
                "process": process,
                "level": val,
            }
        )

    results.var_cap.sort(key=lambda r: (r["year"], -abs(r["level"])))
    results.var_cap = _apply_limit(results.var_cap, limit)

    # Extract deterministic commodity-flow evidence - optional
    if include_flows:
        (
            results.var_flo_source,
            results.var_flo,
        ) = _extract_flow_rows(
            gdx_path=gdx_path,
            gdxdump=gdxdump,
            symbol_preference=FLOW_SYMBOL_PREFERENCE,
            process_filter=process_filter,
            year_filter=year_filter,
            limit=limit,
        )
        (
            results.val_flo_source,
            results.val_flo,
        ) = _extract_flow_rows(
            gdx_path=gdx_path,
            gdxdump=gdxdump,
            symbol_preference=VALUE_FLOW_SYMBOL_PREFERENCE,
            process_filter=process_filter,
            year_filter=year_filter,
            limit=limit,
            default_timeslice="ANNUAL",
        )

    # Extract NCAP_PASTI (past investments / existing capacity with vintage)
    # This is INPUT data (parameter), not a result variable
    par_pasti_csv = dump_symbol_csv(gdx_path, "NCAP_PASTI", gdxdump)
    if par_pasti_csv:
        for raw_row in parse_csv(par_pasti_csv):
            row = _normalize_row(raw_row)
            try:
                val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                if val is None:
                    continue
                if abs(val) < 1e-9:
                    continue
                # GDX columns: REG, ALLYEAR, PRC, Val
                process = _get_field(row, "PRC", *PROCESS_COLUMNS)
                vintage = _get_field(row, *VINTAGE_COLUMNS)
                region = _get_field(row, "REG", *REGION_COLUMNS)

                if process_filter and not any(
                    f.lower() in process.lower() for f in process_filter
                ):
                    continue
                if year_filter and vintage not in year_filter:
                    continue

                results.par_pasti.append(
                    {
                        "region": region,
                        "vintage": vintage,
                        "process": process,
                        "capacity": val,
                    }
                )
            except (ValueError, KeyError):
                pass

    results.par_pasti.sort(key=lambda r: (r.get("vintage", ""), r.get("process", "")))
    results.par_pasti = _apply_limit(results.par_pasti, limit)

    # Extract PRC_RESID (residual capacity / stock)
    # This is INPUT data (parameter), not a result variable
    par_resid_csv = dump_symbol_csv(gdx_path, "PRC_RESID", gdxdump)
    if par_resid_csv:
        for raw_row in parse_csv(par_resid_csv):
            row = _normalize_row(raw_row)
            try:
                val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                if val is None:
                    continue
                if abs(val) < 1e-9:
                    continue
                # GDX columns: REG, ALLYEAR, PRC, Val
                process = _get_field(row, "PRC", *PROCESS_COLUMNS)
                year = _get_field(row, *YEAR_COLUMNS)
                region = _get_field(row, "REG", *REGION_COLUMNS)

                if process_filter and not any(
                    f.lower() in process.lower() for f in process_filter
                ):
                    continue
                if year_filter and year not in year_filter:
                    continue

                results.par_resid.append(
                    {
                        "region": region,
                        "year": year,
                        "process": process,
                        "capacity": val,
                    }
                )
            except (ValueError, KeyError):
                pass

    results.par_resid.sort(key=lambda r: (r.get("year", ""), r.get("process", "")))
    results.par_resid = _apply_limit(results.par_resid, limit)

    return results


def format_table(
    title: str,
    rows: list[dict],
    columns: list[str],
    limit: int = 20,
) -> str:
    """Format a table for console output."""
    lines = [title, "-" * len(title)]

    if not rows:
        lines.append("(no non-zero rows)")
        return "\n".join(lines)

    display_rows = rows[:limit]

    # Calculate column widths
    widths = {}
    for col in columns:
        widths[col] = max(
            len(col), max((len(str(r.get(col, ""))) for r in display_rows), default=0)
        )

    # Header
    header = "  ".join(f"{col:{widths[col]}}" for col in columns)
    lines.append(header)
    lines.append("  ".join("-" * widths[col] for col in columns))

    # Rows
    for row in display_rows:
        vals = []
        for col in columns:
            v = row.get(col, "")
            if isinstance(v, float):
                v = f"{v:.2f}"
            vals.append(f"{str(v):{widths[col]}}")
        lines.append("  ".join(vals))

    if len(rows) > limit:
        lines.append(f"(showing {limit} of {len(rows)} rows)")

    return "\n".join(lines)


def format_results_console(results: TimesResults, limit: int = 20) -> str:
    """Format results for console display."""
    sections = []
    summary_rows = [("GDX", str(results.gdx_path))]
    if results.objective is not None:
        summary_rows.append(("Objective value", f"{results.objective:.2f}"))
    if results.objective_breakdown:
        breakdown = ", ".join(
            f"{key}={value:.2f}"
            for key, value in results.objective_breakdown.items()
            if value != 0
        )
        if breakdown:
            summary_rows.append(("Breakdown", breakdown))
    sections.append(
        status_panel(
            "TIMES Results",
            summary_rows,
            level="info",
            status=("ready", "success")
            if not results.errors
            else ("issues", "warning"),
        )
    )

    def _rows(data: list[dict[str, Any]], cols: list[str]) -> list[list[str]]:
        display_rows = data[:limit] if limit > 0 else data
        return [
            [
                (
                    f"{row.get(col, ''):.2f}"
                    if isinstance(row.get(col), float)
                    else str(row.get(col, ""))
                )
                for col in cols
            ]
            for row in display_rows
        ]

    sections.append(
        data_table(
            "Process Activity (VAR_ACT)",
            ["Year", "Process", "Timeslice", "Level"],
            _rows(results.var_act, ["year", "process", "timeslice", "level"]),
            empty_message="No non-zero rows",
        )
    )
    sections.append(
        data_table(
            "New Capacity (VAR_NCAP)",
            ["Year", "Process", "Level"],
            _rows(results.var_ncap, ["year", "process", "level"]),
            empty_message="No non-zero rows",
        )
    )
    sections.append(
        data_table(
            "Installed Capacity (VAR_CAP)",
            ["Year", "Process", "Level"],
            _rows(results.var_cap, ["year", "process", "level"]),
            empty_message="No non-zero rows",
        )
    )

    if results.var_flo:
        flow_symbol = results.var_flo_source or "VAR_FLO"
        sections.append(
            data_table(
                f"Commodity Flows ({flow_symbol})",
                ["Year", "Process", "Commodity", "Level"],
                _rows(results.var_flo, ["year", "process", "commodity", "level"]),
            )
        )

    if results.val_flo:
        value_flow_symbol = results.val_flo_source or "VAL_FLO"
        sections.append(
            data_table(
                f"Value Flows ({value_flow_symbol})",
                ["Year", "Process", "Commodity", "Level"],
                _rows(results.val_flo, ["year", "process", "commodity", "level"]),
            )
        )

    if results.par_pasti:
        sections.append(
            data_table(
                "Past Investments (PAR_PASTI)",
                ["Vintage", "Process", "Capacity"],
                _rows(results.par_pasti, ["vintage", "process", "capacity"]),
            )
        )

    if results.par_resid:
        sections.append(
            data_table(
                "Residual Capacity (PAR_RESID)",
                ["Year", "Process", "Capacity"],
                _rows(results.par_resid, ["year", "process", "capacity"]),
            )
        )

    if results.errors:
        sections.append(message_panel("Errors", results.errors, level="error"))

    return str(render_to_text(Group(*sections)))


def save_results(
    results: TimesResults,
    output_path: Path,
    format: str = "json",
) -> list[Path]:
    """Save results to file(s)."""
    created = []
    output_path = Path(output_path)

    if format == "json" or output_path.suffix == ".json":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results.to_dict(), f, indent=2)
        created.append(output_path)

    elif output_path.is_dir() or format == "csv":
        output_path.mkdir(parents=True, exist_ok=True)

        # Write summary JSON
        summary_path = output_path / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(
                {
                    "gdx_path": str(results.gdx_path),
                    "objective": results.objective,
                    "objective_breakdown": results.objective_breakdown,
                    "var_flo_source": results.var_flo_source,
                    "val_flo_source": results.val_flo_source,
                },
                f,
                indent=2,
            )
        created.append(summary_path)

        # Write CSVs for each table
        for name, rows in [
            ("var_act", results.var_act),
            ("var_ncap", results.var_ncap),
            ("var_cap", results.var_cap),
            ("var_flo", results.var_flo),
            ("val_flo", results.val_flo),
            ("par_pasti", results.par_pasti),
            ("par_resid", results.par_resid),
        ]:
            if rows:
                csv_path = output_path / f"{name}.csv"
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                created.append(csv_path)

    return created
