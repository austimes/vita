"""CLI for veda_run_times."""

import argparse
import json
import sys
from pathlib import Path

from .runner import find_times_source, run_times


def format_result_table(result) -> str:
    """Format result as a nice table."""
    status = "✓ PASS" if result.success else "✗ FAIL"

    lines = [
        f"Work dir: {result.work_dir}",
        "",
        "┌" + "─" * 60 + "┐",
        "│ veda_run_times results" + " " * 37 + "│",
        "├" + "─" * 60 + "┤",
        f"│ Case: {result.case}".ljust(61) + "│",
        f"│ GAMS return code: {result.return_code}".ljust(61) + "│",
    ]

    if result.model_status:
        lines.append(f"│ Model status: {result.model_status}".ljust(61) + "│")
    if result.solve_status:
        lines.append(f"│ Solve status: {result.solve_status}".ljust(61) + "│")
    if result.objective is not None:
        lines.append(f"│ Objective: {result.objective:.6g}".ljust(61) + "│")
    if result.lst_file:
        lines.append(f"│ LST: {str(result.lst_file)[:53]}".ljust(61) + "│")
    if result.gdx_files:
        gdx_str = ", ".join(f.name for f in result.gdx_files[:3])
        if len(result.gdx_files) > 3:
            gdx_str += f" (+{len(result.gdx_files) - 3} more)"
        lines.append(f"│ GDX: {gdx_str[:53]}".ljust(61) + "│")

    lines.append(f"│ Status: {status}".ljust(61) + "│")
    lines.append("└" + "─" * 60 + "┘")

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for msg in result.errors[:5]:
            lines.append(f"  - {msg[:70]}")

    if result.stderr and not result.success:
        lines.append("")
        lines.append("GAMS stderr (last 5 lines):")
        for line in result.stderr.strip().split("\n")[-5:]:
            lines.append(f"  {line[:70]}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="veda_run_times",
        description="Run TIMES models through GAMS after xl2times processing",
    )
    parser.add_argument(
        "dd_dir",
        type=Path,
        help="Directory containing DD files from xl2times",
    )
    parser.add_argument(
        "--case", "-c",
        default="scenario",
        help="Case/scenario name (default: scenario)",
    )
    parser.add_argument(
        "--times-src",
        type=Path,
        help="Path to TIMES source code (defaults to TIMES_SRC env or ~/TIMES_model)",
    )
    parser.add_argument(
        "--gams-binary",
        default="gams",
        help="Path to GAMS executable (default: gams)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory (default: create temp dir)",
    )
    parser.add_argument(
        "--solver",
        default="CBC",
        help="LP solver to use (default: CBC)",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep working directory after successful run",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if not args.dd_dir.exists():
        print(f"Error: DD directory not found: {args.dd_dir}", file=sys.stderr)
        sys.exit(2)

    if not list(args.dd_dir.glob("*.dd")):
        print(f"Error: No .dd files found in: {args.dd_dir}", file=sys.stderr)
        sys.exit(2)

    times_src = args.times_src
    if times_src is None:
        times_src = find_times_source()
        if times_src is None:
            print(
                "Error: TIMES source not found. "
                "Set TIMES_SRC env var or use --times-src",
                file=sys.stderr,
            )
            sys.exit(2)

    if args.verbose:
        print(f"Using TIMES source: {times_src}")

    result = run_times(
        dd_dir=args.dd_dir,
        case=args.case,
        times_src=times_src,
        gams_binary=args.gams_binary,
        work_dir=args.work_dir,
        solver=args.solver,
        keep_workdir=args.keep_workdir,
        verbose=args.verbose,
    )

    if args.json_output:
        output = {
            "success": result.success,
            "case": result.case,
            "work_dir": str(result.work_dir),
            "gams": {
                "command": " ".join(result.gams_command),
                "return_code": result.return_code,
            },
            "files": {
                "lst": str(result.lst_file) if result.lst_file else None,
                "gdx": [str(f) for f in result.gdx_files],
            },
            "status": {
                "model_status": result.model_status,
                "solve_status": result.solve_status,
                "objective": result.objective,
            },
            "errors": result.errors,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result_table(result))

    sys.exit(0 if result.success else 2)


if __name__ == "__main__":
    main()
