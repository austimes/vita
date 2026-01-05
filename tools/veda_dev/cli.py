"""CLI for vedalang-dev: Unified CLI for VedaLang Design Agent."""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="vedalang-dev",
        description="VedaLang Design Agent CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pipeline subcommand
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run full VedaLang -> TIMES pipeline",
    )
    pipeline_parser.add_argument(
        "input",
        type=Path,
        help="Input file or directory",
    )
    pipeline_parser.add_argument(
        "--from",
        dest="input_kind",
        choices=["vedalang", "tableir", "excel", "dd"],
        help="Input type (auto-detected if not specified)",
    )
    pipeline_parser.add_argument(
        "--case",
        "-c",
        default="scenario",
        help="Case/scenario name (default: scenario)",
    )
    pipeline_parser.add_argument(
        "--times-src",
        type=Path,
        help="Path to TIMES source code",
    )
    pipeline_parser.add_argument(
        "--gams-binary",
        default="gams",
        help="Path to GAMS executable (default: gams)",
    )
    pipeline_parser.add_argument(
        "--solver",
        default="CBC",
        help="LP solver (default: CBC)",
    )
    pipeline_parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory (default: create temp dir)",
    )
    pipeline_parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep working directory after run",
    )
    pipeline_parser.add_argument(
        "--no-solver",
        action="store_true",
        help="Stop before running TIMES solver",
    )
    pipeline_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    pipeline_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # check subcommand (wraps veda_check)
    check_parser = subparsers.add_parser(
        "check",
        help="Validate VedaLang/TableIR (wraps veda_check)",
    )
    check_parser.add_argument(
        "input",
        type=Path,
        help="Input file to validate",
    )
    check_parser.add_argument(
        "--from-vedalang",
        action="store_true",
        help="Input is VedaLang source",
    )
    check_parser.add_argument(
        "--from-tableir",
        action="store_true",
        help="Input is TableIR",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    check_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # emit-excel subcommand (wraps veda_emit_excel)
    emit_parser = subparsers.add_parser(
        "emit-excel",
        help="Emit Excel from TableIR (wraps veda_emit_excel)",
    )
    emit_parser.add_argument(
        "input",
        type=Path,
        help="TableIR YAML/JSON file",
    )
    emit_parser.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Output directory for Excel files",
    )
    emit_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip schema validation",
    )

    # run-times subcommand (wraps veda_run_times)
    run_times_parser = subparsers.add_parser(
        "run-times",
        help="Run TIMES solver (wraps veda_run_times)",
    )
    run_times_parser.add_argument(
        "dd_dir",
        type=Path,
        help="Directory containing DD files",
    )
    run_times_parser.add_argument(
        "--case",
        "-c",
        default="scenario",
        help="Case name",
    )
    run_times_parser.add_argument(
        "--times-src",
        type=Path,
        help="Path to TIMES source",
    )
    run_times_parser.add_argument(
        "--gams-binary",
        default="gams",
        help="GAMS executable",
    )
    run_times_parser.add_argument(
        "--solver",
        default="CBC",
        help="LP solver",
    )
    run_times_parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory",
    )
    run_times_parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep working directory",
    )
    run_times_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="JSON output",
    )
    run_times_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    # pattern subcommand (wraps veda_pattern)
    pattern_parser = subparsers.add_parser(
        "pattern",
        help="Pattern library utilities (wraps veda_pattern)",
    )
    pattern_subparsers = pattern_parser.add_subparsers(dest="pattern_command")

    pattern_list = pattern_subparsers.add_parser("list", help="List available patterns")
    pattern_list.add_argument("--json", action="store_true", dest="json_output")

    pattern_show = pattern_subparsers.add_parser("show", help="Show pattern details")
    pattern_show.add_argument("name", help="Pattern name")
    pattern_show.add_argument("--json", action="store_true", dest="json_output")

    args = parser.parse_args()

    if args.command == "pipeline":
        run_pipeline_command(args)
    elif args.command == "check":
        run_check_command(args)
    elif args.command == "emit-excel":
        run_emit_excel_command(args)
    elif args.command == "run-times":
        run_run_times_command(args)
    elif args.command == "pattern":
        run_pattern_command(args)


def run_pipeline_command(args):
    """Run the pipeline command."""
    from .pipeline import format_result_table, run_pipeline

    if not args.input.exists():
        print(f"Error: Input not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    # Suppress verbose output when JSON is requested (to keep stdout clean)
    verbose = args.verbose and not args.json_output

    result = run_pipeline(
        input_path=args.input,
        input_kind=args.input_kind,
        case=args.case,
        times_src=args.times_src,
        gams_binary=args.gams_binary,
        solver=args.solver,
        work_dir=args.work_dir,
        keep_workdir=args.keep_workdir,
        no_solver=args.no_solver,
        verbose=verbose,
    )

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result_table(result))

    sys.exit(0 if result.success else 2)


def run_check_command(args):
    """Run the check command (wraps veda_check)."""
    from tools.veda_check.checker import run_check
    from tools.veda_check.cli import format_result_table

    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    result = run_check(
        args.input,
        from_vedalang=args.from_vedalang,
        from_tableir=args.from_tableir,
    )

    if args.json_output:
        output = {
            "success": result.success,
            "source": str(result.source_path),
            "tables": result.tables,
            "total_rows": result.total_rows,
            "warnings": result.warnings,
            "errors": result.errors,
            "error_messages": result.error_messages,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result_table(result))

    if result.errors > 0:
        sys.exit(2)
    elif result.warnings > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def run_emit_excel_command(args):
    """Run emit-excel command (wraps veda_emit_excel)."""
    from tools.veda_emit_excel import emit_excel, load_tableir

    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        tableir = load_tableir(args.input)
        created = emit_excel(tableir, args.out, validate=not args.no_validate)

        print(f"Created {len(created)} Excel file(s):")
        for path in created:
            print(f"  {path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_run_times_command(args):
    """Run run-times command (wraps veda_run_times)."""
    from tools.veda_run_times.cli import format_result_table
    from tools.veda_run_times.runner import find_times_source, run_times

    if not args.dd_dir.exists():
        print(f"Error: DD directory not found: {args.dd_dir}", file=sys.stderr)
        sys.exit(2)

    times_src = args.times_src
    if times_src is None:
        times_src = find_times_source()
        if times_src is None:
            print(
                "Error: TIMES source not found. Set TIMES_SRC or use --times-src",
                file=sys.stderr,
            )
            sys.exit(2)

    result = run_times(
        dd_dir=args.dd_dir,
        case=args.case,
        times_src=times_src,
        gams_binary=args.gams_binary,
        solver=args.solver,
        work_dir=args.work_dir,
        keep_workdir=args.keep_workdir,
        verbose=args.verbose,
    )

    if args.json_output:
        output = {
            "success": result.success,
            "case": result.case,
            "work_dir": str(result.work_dir),
            "gams_return_code": result.return_code,
            "model_status": result.model_status,
            "solve_status": result.solve_status,
            "objective": result.objective,
            "errors": result.errors,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result_table(result))

    sys.exit(0 if result.success else 2)


def run_pattern_command(args):
    """Run pattern command (wraps veda_pattern)."""
    try:
        from tools.veda_patterns import list_patterns, show_pattern
    except ImportError:
        print("Error: veda_patterns module not available", file=sys.stderr)
        sys.exit(1)

    if args.pattern_command == "list":
        patterns = list_patterns()
        if args.json_output:
            print(json.dumps(patterns, indent=2))
        else:
            print("Available patterns:")
            for p in patterns:
                print(f"  - {p}")
    elif args.pattern_command == "show":
        pattern = show_pattern(args.name)
        if args.json_output:
            print(json.dumps(pattern, indent=2))
        else:
            print(f"Pattern: {args.name}")
            print(json.dumps(pattern, indent=2))
    else:
        print("Usage: vedalang-dev pattern {list|show} ...")
        sys.exit(1)


if __name__ == "__main__":
    main()
