"""CLI for Vita: run, analyze, and explain VEDA/TIMES experiments."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from vita.handlers import (
    run_diff_command,
    run_pipeline_command,
    run_sankey_command,
    run_times_results_command,
)


def main() -> None:
    """Run the Vita CLI entrypoint."""
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="vita",
        description="Vita (VEDA Insight & TIMES Analysis) CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run full VedaLang -> TIMES pipeline",
    )
    run_parser.add_argument("input", type=Path, help="Input file or directory")
    run_parser.add_argument(
        "--from",
        dest="input_kind",
        choices=["vedalang", "tableir", "excel", "dd"],
        help="Input type (auto-detected if not specified)",
    )
    run_parser.add_argument(
        "--case",
        "-c",
        default="scenario",
        help="Case/scenario name (default: scenario)",
    )
    run_parser.add_argument(
        "--run",
        help="Selected run when compiling VedaLang input",
    )
    run_parser.add_argument(
        "--out",
        type=Path,
        help="Write structured run artifacts to this directory",
    )
    run_parser.add_argument(
        "--times-src",
        type=Path,
        help="Path to TIMES source code",
    )
    run_parser.add_argument(
        "--gams-binary",
        default="gams",
        help="Path to GAMS executable (default: gams)",
    )
    run_parser.add_argument("--solver", default="CBC", help="LP solver (default: CBC)")
    run_parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory (default: create temp dir)",
    )
    run_parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep working directory after run",
    )
    run_parser.add_argument(
        "--no-solver",
        action="store_true",
        help="Stop before running TIMES solver",
    )
    run_parser.add_argument(
        "--no-sankey",
        action="store_true",
        help="Skip Sankey diagram generation",
    )
    run_parser.add_argument(
        "--process-results-only",
        action="store_true",
        help="Skip pipeline, just process existing GDX results",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    run_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    results_parser = subparsers.add_parser(
        "results",
        help="Extract and display TIMES results from GDX",
    )
    results_parser.add_argument(
        "--run",
        dest="run_dir",
        type=Path,
        help="Run artifact directory created by vita run --out",
    )
    results_parser.add_argument(
        "--gdx",
        type=Path,
        default=Path("tmp/gams/scenario.gdx"),
        help="Path to GDX file (default: tmp/gams/scenario.gdx)",
    )
    results_parser.add_argument(
        "--process",
        action="append",
        dest="process_filter",
        help="Filter to processes containing pattern (can repeat)",
    )
    results_parser.add_argument(
        "--year",
        dest="year_filter",
        help="Filter to years (comma-separated, e.g. 2030,2040)",
    )
    results_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max rows per table (default: 20, use 0 for no limit)",
    )
    results_parser.add_argument(
        "--flows",
        action="store_true",
        help="Include VAR_FLO (commodity flows)",
    )
    results_parser.add_argument(
        "--save",
        type=Path,
        help="Save results to file/directory (JSON or CSV)",
    )
    results_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    results_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (use with --save)",
    )

    sankey_parser = subparsers.add_parser(
        "sankey",
        help="Generate Sankey diagram from TIMES results",
    )
    sankey_parser.add_argument(
        "--run",
        dest="run_dir",
        type=Path,
        help="Run artifact directory created by vita run --out",
    )
    sankey_parser.add_argument(
        "--gdx",
        type=Path,
        default=Path("tmp/gams/scenario.gdx"),
        help="Path to GDX file (default: tmp/gams/scenario.gdx)",
    )
    sankey_parser.add_argument(
        "--year",
        "-y",
        help="Year to visualize (default: first available)",
    )
    sankey_parser.add_argument(
        "--region",
        "-r",
        help="Region to visualize (default: first available)",
    )
    sankey_parser.add_argument(
        "--min-flow",
        type=float,
        default=0.01,
        help="Minimum flow value to include (default: 0.01)",
    )
    sankey_parser.add_argument(
        "--format",
        "-f",
        choices=["html", "json", "mermaid"],
        default="html",
        help="Output format (default: html)",
    )
    sankey_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file (default: stdout for json/mermaid, sankey.html for html)",
    )
    sankey_parser.add_argument(
        "--list-years",
        action="store_true",
        help="List available years and exit",
    )
    sankey_parser.add_argument(
        "--list-regions",
        action="store_true",
        help="List available regions and exit",
    )
    sankey_parser.add_argument(
        "--static",
        action="store_true",
        help="Generate static HTML (single year/region) instead of interactive",
    )

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two Vita run directories",
    )
    diff_parser.add_argument(
        "baseline_run",
        type=Path,
        help="Baseline run directory",
    )
    diff_parser.add_argument(
        "variant_run",
        type=Path,
        help="Variant run directory",
    )
    diff_parser.add_argument(
        "--focus-processes",
        action="append",
        help="Process IDs to focus on (comma-separated, can repeat)",
    )
    diff_parser.add_argument(
        "--metric",
        action="append",
        choices=[
            "objective",
            "objective_breakdown",
            "var_act",
            "var_cap",
            "var_ncap",
            "var_flo",
        ],
        help="Metric(s) to include in diff output (repeatable)",
    )
    diff_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max rows per metric in human output (default: 20)",
    )
    diff_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if args.command == "run":
        run_pipeline_command(args)
    elif args.command == "results":
        run_times_results_command(args)
    elif args.command == "sankey":
        run_sankey_command(args)
    elif args.command == "diff":
        run_diff_command(args)


if __name__ == "__main__":
    main()
