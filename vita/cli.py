"""CLI for Vita: run, analyze, and explain VEDA/TIMES experiments."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from tools.cli_ui import StyledArgumentParser
from vita.handlers import (
    run_diff_command,
    run_experiment_full_command,
    run_experiment_plan_command,
    run_experiment_present_command,
    run_experiment_run_command,
    run_experiment_status_command,
    run_experiment_summarize_command,
    run_experiment_validate_brief_command,
    run_experiment_validate_interpretation_command,
    run_init_command,
    run_pipeline_command,
    run_sankey_command,
    run_times_results_command,
    run_update_command,
)
from vita.version import VITA_CLI_VERSION


def build_parser() -> argparse.ArgumentParser:
    """Build the Vita CLI parser."""
    parser = StyledArgumentParser(
        prog="vita",
        description="Vita (VEDA Insight & TIMES Analysis) CLI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VITA_CLI_VERSION}",
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

    # Experiment subcommand
    exp_parser = subparsers.add_parser(
        "experiment",
        help="Run declarative experiments from manifest files",
    )
    exp_parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        help="Path to experiment.yaml manifest (convenience mode)",
    )
    exp_parser.add_argument(
        "--out",
        type=Path,
        help="Output directory (convenience mode, default: experiments/<id>)",
    )
    exp_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (convenience mode)",
    )
    exp_subparsers = exp_parser.add_subparsers(dest="exp_command")

    # vita experiment stage
    exp_stage_parser = exp_subparsers.add_parser(
        "stage", help="Stage experiment inputs and create directory structure"
    )
    exp_stage_parser.add_argument(
        "manifest", type=Path, help="Path to experiment.yaml manifest"
    )
    exp_stage_parser.add_argument(
        "--out", type=Path, help="Output directory (default: experiments/<id>)"
    )

    # vita experiment run
    exp_run_parser = exp_subparsers.add_parser(
        "run", help="Execute pending runs and diffs"
    )
    exp_run_parser.add_argument(
        "experiment_dir", type=Path, help="Experiment directory"
    )
    exp_run_parser.add_argument(
        "--resume", action="store_true", help="Skip completed runs"
    )
    exp_run_parser.add_argument(
        "--force", action="store_true", help="Re-run everything"
    )
    exp_run_parser.add_argument("--json", action="store_true", dest="json_output")

    # vita experiment summarize
    exp_summarize_parser = exp_subparsers.add_parser(
        "summarize", help="Extract evidence summary from completed runs"
    )
    exp_summarize_parser.add_argument(
        "experiment_dir", type=Path, help="Experiment directory"
    )
    exp_summarize_parser.add_argument("--json", action="store_true", dest="json_output")

    # vita experiment validate-brief
    exp_vb_parser = exp_subparsers.add_parser(
        "validate-brief", help="Run brief validation gate"
    )
    exp_vb_parser.add_argument("experiment_dir", type=Path, help="Experiment directory")
    exp_vb_parser.add_argument("--json", action="store_true", dest="json_output")

    # vita experiment validate-interpretation
    exp_vi_parser = exp_subparsers.add_parser(
        "validate-interpretation", help="Run interpretation validation gate"
    )
    exp_vi_parser.add_argument("experiment_dir", type=Path, help="Experiment directory")
    exp_vi_parser.add_argument("--json", action="store_true", dest="json_output")

    # vita experiment present
    exp_present_parser = exp_subparsers.add_parser(
        "present", help="Regenerate HTML presentation"
    )
    exp_present_parser.add_argument(
        "experiment_dir", type=Path, help="Experiment directory"
    )

    # vita experiment status
    exp_status_parser = exp_subparsers.add_parser(
        "status", help="Show experiment lifecycle status"
    )
    exp_status_parser.add_argument(
        "experiment_dir", type=Path, help="Experiment directory"
    )
    exp_status_parser.add_argument("--json", action="store_true", dest="json_output")

    # vita init
    init_parser = subparsers.add_parser(
        "init",
        help="Bootstrap a new Vita project directory",
    )
    init_parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Target directory (default: current directory)",
    )
    init_parser.add_argument(
        "--times-src",
        type=Path,
        help="Path to TIMES source code",
    )
    init_parser.add_argument(
        "--gams-binary",
        default=None,
        help="Path to GAMS executable",
    )
    init_parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run a smoke test after initialization",
    )
    init_parser.add_argument(
        "--with-bd",
        action="store_true",
        help="Initialize beads (bd) for experiment task tracking",
    )

    subparsers.add_parser(
        "update",
        help="Refresh installed vita and vedalang tools when GitHub main is newer",
        description=(
            "Check the installed vita and vedalang tool package against GitHub "
            "main and refresh it with uv tool install --force when main is newer."
        ),
    )

    return parser


def main() -> None:
    """Run the Vita CLI entrypoint."""
    load_dotenv()
    parser = build_parser()
    argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return
    args = parser.parse_args(argv)

    if args.command == "init":
        run_init_command(args)
    elif args.command == "update":
        run_update_command(args)
    elif args.command == "run":
        run_pipeline_command(args)
    elif args.command == "results":
        run_times_results_command(args)
    elif args.command == "sankey":
        run_sankey_command(args)
    elif args.command == "diff":
        run_diff_command(args)
    elif args.command == "experiment":
        if args.exp_command == "stage":
            run_experiment_plan_command(args)
        elif args.exp_command == "run":
            run_experiment_run_command(args)
        elif args.exp_command == "summarize":
            run_experiment_summarize_command(args)
        elif args.exp_command == "validate-brief":
            run_experiment_validate_brief_command(args)
        elif args.exp_command == "validate-interpretation":
            run_experiment_validate_interpretation_command(args)
        elif args.exp_command == "present":
            run_experiment_present_command(args)
        elif args.exp_command == "status":
            run_experiment_status_command(args)
        elif args.exp_command is None and args.manifest is not None:
            # Convenience mode: vita experiment <manifest.yaml>
            run_experiment_full_command(args)
        else:
            parser.parse_args(["experiment", "--help"])


if __name__ == "__main__":
    main()
