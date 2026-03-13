"""Extract and display TIMES results from GDX files."""

import csv
import json
import os
import subprocess
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

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
)
VINTAGE_COLUMNS = ("T", "VINTAGE", "ALLYEAR", "YEAR", "PASTYEAR")
REGION_COLUMNS = ("R", "REG", "REGION")
TIMESLICE_COLUMNS = ("S", "TS", "TIMESLICE", "SLICE")
COMMODITY_COLUMNS = ("C", "COM", "COMMODITY")


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
            "par_pasti": self.par_pasti,
            "par_resid": self.par_resid,
            "errors": self.errors,
        }


def find_gdxdump() -> str | None:
    """Find gdxdump executable."""
    default_path = "/Library/Frameworks/GAMS.framework/Resources/gdxdump"
    if os.path.exists(default_path):
        return default_path

    env_path = os.environ.get("GDXDUMP")
    if env_path and os.path.exists(env_path):
        return env_path

    import shutil

    return shutil.which("gdxdump")


def dump_symbol_csv(gdx_path: Path, symbol: str, gdxdump: str) -> str | None:
    """Dump a symbol from GDX to CSV format."""
    cmd = [gdxdump, str(gdx_path), f"Symb={symbol}", "Format=csv", "EpsOut=0"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout
        return None
    except Exception:
        return None


def parse_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV output from gdxdump."""
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def _normalize_header(header: str | None) -> str:
    if not header:
        return ""
    return (
        header.strip()
        .strip('"')
        .replace("-", "_")
        .replace(" ", "_")
        .upper()
    )


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
        results.errors.append(
            "gdxdump not found. Set GDXDUMP env var or install GAMS."
        )
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

    # Extract VAR_ACT (process activity)
    var_act_csv = dump_symbol_csv(gdx_path, "VAR_ACT", gdxdump)
    if var_act_csv:
        for raw_row in parse_csv(var_act_csv):
            row = _normalize_row(raw_row)
            try:
                val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                if val is None:
                    continue
                if abs(val) < 1e-9:
                    continue
                process = _get_field(row, *PROCESS_COLUMNS)
                year = _get_field(row, *YEAR_COLUMNS)
                vintage = _get_field(row, *VINTAGE_COLUMNS, default=year)

                if process_filter and not any(
                    f.lower() in process.lower() for f in process_filter
                ):
                    continue
                if year_filter and year not in year_filter:
                    continue

                results.var_act.append(
                    {
                        "region": _get_field(row, *REGION_COLUMNS),
                        "vintage": vintage,
                        "year": year,
                        "process": process,
                        "timeslice": _get_field(row, *TIMESLICE_COLUMNS),
                        "level": val,
                    }
                )
            except (ValueError, KeyError):
                pass

    # Sort by level descending, limit
    results.var_act.sort(key=lambda r: abs(r["level"]), reverse=True)
    results.var_act = _apply_limit(results.var_act, limit)

    # Extract VAR_NCAP (new capacity)
    var_ncap_csv = dump_symbol_csv(gdx_path, "VAR_NCAP", gdxdump)
    if var_ncap_csv:
        for raw_row in parse_csv(var_ncap_csv):
            row = _normalize_row(raw_row)
            try:
                val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                if val is None:
                    continue
                if abs(val) < 1e-9:
                    continue
                process = _get_field(row, *PROCESS_COLUMNS)
                year = _get_field(row, *YEAR_COLUMNS)

                if process_filter and not any(
                    f.lower() in process.lower() for f in process_filter
                ):
                    continue
                if year_filter and year not in year_filter:
                    continue

                results.var_ncap.append(
                    {
                        "region": _get_field(row, *REGION_COLUMNS),
                        "year": year,
                        "process": process,
                        "level": val,
                    }
                )
            except (ValueError, KeyError):
                pass

    results.var_ncap.sort(key=lambda r: abs(r["level"]), reverse=True)
    results.var_ncap = _apply_limit(results.var_ncap, limit)

    # Extract VAR_CAP (installed capacity)
    var_cap_csv = dump_symbol_csv(gdx_path, "VAR_CAP", gdxdump)
    if var_cap_csv:
        for raw_row in parse_csv(var_cap_csv):
            row = _normalize_row(raw_row)
            try:
                val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                if val is None:
                    continue
                if abs(val) < 1e-9:
                    continue
                process = _get_field(row, *PROCESS_COLUMNS)
                year = _get_field(row, *YEAR_COLUMNS)

                if process_filter and not any(
                    f.lower() in process.lower() for f in process_filter
                ):
                    continue
                if year_filter and year not in year_filter:
                    continue

                results.var_cap.append(
                    {
                        "region": _get_field(row, *REGION_COLUMNS),
                        "year": year,
                        "process": process,
                        "level": val,
                    }
                )
            except (ValueError, KeyError):
                pass

    results.var_cap.sort(key=lambda r: (r["year"], -abs(r["level"])))
    results.var_cap = _apply_limit(results.var_cap, limit)

    # Extract VAR_FLO (commodity flows) - optional
    if include_flows:
        var_flo_csv = dump_symbol_csv(gdx_path, "VAR_FLO", gdxdump)
        if var_flo_csv:
            for raw_row in parse_csv(var_flo_csv):
                row = _normalize_row(raw_row)
                try:
                    val = _parse_float(_get_field(row, *VALUE_COLUMNS, default="0"))
                    if val is None:
                        continue
                    if abs(val) < 1e-9:
                        continue
                    process = _get_field(row, *PROCESS_COLUMNS)
                    year = _get_field(row, *YEAR_COLUMNS)

                    if process_filter and not any(
                        f.lower() in process.lower() for f in process_filter
                    ):
                        continue
                    if year_filter and year not in year_filter:
                        continue

                    results.var_flo.append(
                        {
                            "region": _get_field(row, *REGION_COLUMNS),
                            "year": year,
                            "process": process,
                            "commodity": _get_field(row, *COMMODITY_COLUMNS),
                            "timeslice": _get_field(row, *TIMESLICE_COLUMNS),
                            "level": val,
                        }
                    )
                except (ValueError, KeyError):
                    pass

        results.var_flo.sort(key=lambda r: abs(r["level"]), reverse=True)
        results.var_flo = _apply_limit(results.var_flo, limit)

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
    lines = []

    # Header
    lines.append(f"TIMES Results: {results.gdx_path}")
    lines.append("=" * 60)

    # Objective
    if results.objective is not None:
        lines.append(f"Objective value: {results.objective:.2f}")
    if results.objective_breakdown:
        breakdown = ", ".join(
            f"{k}={v:.2f}" for k, v in results.objective_breakdown.items() if v != 0
        )
        if breakdown:
            lines.append(f"  Breakdown: {breakdown}")
    lines.append("")

    # VAR_ACT
    lines.append(
        format_table(
            "Process Activity (VAR_ACT)",
            results.var_act,
            ["year", "process", "timeslice", "level"],
            limit,
        )
    )
    lines.append("")

    # VAR_NCAP
    lines.append(
        format_table(
            "New Capacity (VAR_NCAP)",
            results.var_ncap,
            ["year", "process", "level"],
            limit,
        )
    )
    lines.append("")

    # VAR_CAP
    lines.append(
        format_table(
            "Installed Capacity (VAR_CAP)",
            results.var_cap,
            ["year", "process", "level"],
            limit,
        )
    )
    lines.append("")

    # VAR_FLO (if present)
    if results.var_flo:
        lines.append(
            format_table(
                "Commodity Flows (VAR_FLO)",
                results.var_flo,
                ["year", "process", "commodity", "level"],
                limit,
            )
        )
        lines.append("")

    # PAR_PASTI (input: past investments with vintage)
    if results.par_pasti:
        lines.append(
            format_table(
                "Past Investments (PAR_PASTI)",
                results.par_pasti,
                ["vintage", "process", "capacity"],
                limit,
            )
        )
        lines.append("")

    # PAR_RESID (input: residual/stock capacity)
    if results.par_resid:
        lines.append(
            format_table(
                "Residual Capacity (PAR_RESID)",
                results.par_resid,
                ["year", "process", "capacity"],
                limit,
            )
        )
        lines.append("")

    # Errors
    if results.errors:
        lines.append("Errors:")
        for err in results.errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


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
