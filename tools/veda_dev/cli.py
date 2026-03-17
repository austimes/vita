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
        "--run",
        help="Selected run when validating VedaLang input",
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

    # eval subcommand
    eval_parser = subparsers.add_parser(
        "eval",
        help="Run and inspect llm-lint model/effort evals",
    )
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    eval_catalog = eval_subparsers.add_parser(
        "catalog",
        help="Show eval candidate matrix and dataset profiles",
    )
    eval_catalog.add_argument(
        "--dataset",
        type=Path,
        help="Optional dataset YAML path",
    )
    eval_catalog.add_argument("--json", action="store_true", dest="json_output")

    eval_run = eval_subparsers.add_parser("run", help="Run eval benchmark")
    eval_run.add_argument(
        "--profile",
        choices=["smoke", "ci", "deep"],
        default="ci",
        help="Eval profile (default: ci)",
    )
    eval_run.add_argument(
        "--prompt-version",
        default=None,
        help=(
            "Prompt version to evaluate (or 'all'). "
            "Default: latest available version per check."
        ),
    )
    eval_run.add_argument(
        "--dataset",
        type=Path,
        help="Optional dataset YAML path",
    )
    eval_run.add_argument(
        "--cache",
        type=Path,
        default=Path("tmp/evals/cache.json"),
        help=(
            "Cache path for LLM lint and judge responses "
            "(default: tmp/evals/cache.json)"
        ),
    )
    eval_run.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache reuse for LLM lint and judge responses",
    )
    eval_run.add_argument(
        "--timeout-sec",
        type=int,
        default=120,
        help="Per-request timeout in seconds (default: 120)",
    )
    eval_run.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Max parallel eval calls per candidate (default: 4)",
    )
    eval_run.add_argument(
        "--no-judge",
        action="store_true",
        help="Disable LLM-as-judge scoring",
    )
    eval_run.add_argument(
        "--judge-model",
        default="gpt-5.2",
        help="Judge model (default: gpt-5.2)",
    )
    eval_run.add_argument(
        "--judge-effort",
        choices=["none", "low", "medium", "high", "xhigh"],
        default="xhigh",
        help="Judge reasoning effort (default: xhigh)",
    )
    eval_run.add_argument(
        "--out",
        type=Path,
        help="Optional output JSON path (default: tmp/evals/<run_id>.json)",
    )
    eval_run.add_argument(
        "--progress",
        action="store_true",
        dest="progress",
        help="Print live eval progress to stderr (default for non-JSON output)",
    )
    eval_run.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable live eval progress output",
    )
    eval_run.set_defaults(progress=None)
    eval_run.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help=(
            "Print run payload JSON to stdout. A JSON artifact file is always "
            "written to --out (or default tmp/evals/<run_id>.json)."
        ),
    )

    eval_compare = eval_subparsers.add_parser(
        "compare",
        help="Compare two eval run JSON artifacts",
    )
    eval_compare.add_argument("old_run", type=Path, help="Path to old run JSON")
    eval_compare.add_argument("new_run", type=Path, help="Path to new run JSON")
    eval_compare.add_argument("--json", action="store_true", dest="json_output")

    eval_report = eval_subparsers.add_parser(
        "report",
        help="Render human-readable report from eval run JSON",
    )
    eval_report.add_argument("run", type=Path, help="Path to eval run JSON")
    eval_report.add_argument("--json", action="store_true", dest="json_output")

    args = parser.parse_args()

    if args.command == "check":
        run_check_command(args)
    elif args.command == "emit-excel":
        run_emit_excel_command(args)
    elif args.command == "pattern":
        run_pattern_command(args)
    elif args.command == "eval":
        run_eval_command(args)


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
        selected_run=args.run,
    )

    if args.json_output:
        output = {
            "dsl_version": result.dsl_version,
            "artifact_version": result.artifact_version,
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


def run_eval_command(args):
    """Run eval command family."""
    from tools.veda_dev.evals import (
        build_candidate_matrix,
        compare_runs,
        load_dataset,
        render_report,
        run_eval,
    )

    def _fmt_score(value: object, places: int = 2) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, (int, float)):
            return f"{float(value):.{places}f}"
        return str(value)

    def _format_progress(event: dict[str, object]) -> str:
        etype = str(event.get("event"))
        if etype == "start":
            return (
                "[eval] start "
                f"profile={event.get('profile')} "
                f"base_cases={event.get('base_cases')} "
                f"expanded_cases={event.get('expanded_cases')} "
                f"candidates={event.get('candidates')} "
                f"total_runs={event.get('total_runs')} "
                f"max_concurrency={event.get('max_concurrency')}"
            )
        if etype == "source_loaded":
            return (
                "[eval] source "
                f"{event.get('case_index')}/{event.get('case_total')} "
                f"case={event.get('case_id')}"
            )
        if etype == "candidate_start":
            return (
                "[eval] candidate "
                f"{event.get('candidate_index')}/{event.get('candidate_total')} "
                f"{event.get('candidate_id')}"
            )
        if etype == "row_complete":
            return (
                "[eval] row "
                f"{event.get('completed_runs')}/{event.get('total_runs')} "
                f"candidate={event.get('candidate_id')} "
                f"case={event.get('case_id')} "
                f"status={event.get('status')} "
                f"cached={event.get('cached')} "
                f"det={_fmt_score(event.get('deterministic_score'))} "
                f"label_match={event.get('label_match') or 'n/a'} "
                f"control_match={event.get('control_match') or 'n/a'} "
                f"extra={_fmt_score(event.get('additional_issues_count'), 0)} "
                f"label_f1={_fmt_score(event.get('label_f1'))} "
                f"judge={_fmt_score(event.get('judge_score'))} "
                f"quality={_fmt_score(event.get('quality_score'))} "
                f"cost=${_fmt_score(event.get('estimated_cost_usd'), 4)} "
                f"elapsed={_fmt_score(event.get('row_elapsed_sec'))}s"
            )
        if etype == "candidate_complete":
            return (
                "[eval] candidate done "
                f"{event.get('candidate_id')} "
                f"ok={event.get('ok_cases')} "
                f"skipped={event.get('skipped_cases')} "
                f"errors={event.get('error_cases')} "
                f"det={_fmt_score(event.get('deterministic_score'))} "
                f"label_match={event.get('label_match') or 'n/a'} "
                f"control_match={event.get('control_match') or 'n/a'} "
                f"extra={_fmt_score(event.get('additional_issues_count'), 0)} "
                f"label_f1={_fmt_score(event.get('label_f1'))} "
                f"label_presence={_fmt_score(event.get('label_presence_accuracy'))} "
                "label_difficulty="
                f"{_fmt_score(event.get('label_difficulty_accuracy'))} "
                f"label_family={_fmt_score(event.get('label_family_accuracy'))} "
                f"judge={_fmt_score(event.get('judge_score'))} "
                f"quality={_fmt_score(event.get('quality_score'))} "
                f"rank={_fmt_score(event.get('rank_score'))} "
                f"avg_row_elapsed={_fmt_score(event.get('avg_row_elapsed_sec'))}s "
                f"total_elapsed={_fmt_score(event.get('total_row_elapsed_sec'))}s "
                f"candidate_elapsed={_fmt_score(event.get('candidate_elapsed_sec'))}s"
            )
        if etype == "complete":
            return (
                "[eval] complete "
                f"run_id={event.get('run_id')} "
                f"top={event.get('leaderboard_top')} "
                f"elapsed={_fmt_score(event.get('run_elapsed_sec'))}s"
            )
        return f"[eval] {etype}"

    if args.eval_command == "catalog":
        dataset = load_dataset(args.dataset)
        payload = {
            "profiles": {
                name: {
                    "count": len(case_ids),
                    "cases": case_ids,
                }
                for name, case_ids in dataset.profiles.items()
            },
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "model": c.model,
                    "reasoning_effort": c.reasoning_effort,
                }
                for c in build_candidate_matrix()
            ],
            "checks_supported": [
                "llm.structure.res_assessment",
                "llm.units.component_quorum",
            ],
        }
        if args.json_output:
            print(json.dumps(payload, indent=2))
        else:
            print("Profiles:")
            for name, info in payload["profiles"].items():
                print(f"  - {name}: {info['count']} cases")
            print()
            print("Candidates:")
            for c in payload["candidates"]:
                print(f"  - {c['candidate_id']}")
        sys.exit(0)

    if args.eval_command == "run":
        emit_progress = (
            args.progress if args.progress is not None else not args.json_output
        )
        progress_callback = None
        if emit_progress:

            def progress_callback(event: dict[str, object]) -> None:
                print(_format_progress(event), file=sys.stderr, flush=True)

        run = run_eval(
            profile=args.profile,
            prompt_version=args.prompt_version,
            dataset_path=args.dataset,
            cache_path=args.cache,
            use_cache=not args.no_cache,
            timeout_sec=args.timeout_sec,
            max_concurrency=args.max_concurrency,
            no_judge=args.no_judge,
            judge_model=args.judge_model,
            judge_effort=args.judge_effort,
            progress_callback=progress_callback,
        )

        out_path = args.out
        if out_path is None:
            out_path = Path("tmp/evals") / f"{run['run_id']}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

        if args.json_output:
            print(json.dumps({"run_path": str(out_path), "run": run}, indent=2))
        else:
            print(render_report(run))
            print()
            print(f"Saved run artifact: {out_path}")
        sys.exit(0)

    if args.eval_command == "compare":
        if not args.old_run.exists() or not args.new_run.exists():
            print("Error: compare inputs must exist", file=sys.stderr)
            sys.exit(2)
        old = json.loads(args.old_run.read_text(encoding="utf-8"))
        new = json.loads(args.new_run.read_text(encoding="utf-8"))
        diff = compare_runs(old, new)
        if args.json_output:
            print(json.dumps(diff, indent=2))
        else:
            print(f"Compare: {diff['old_run_id']} -> {diff['new_run_id']}")
            for row in diff["deltas"][:20]:
                print(
                    f"  - {row['candidate_id']}: delta_rank={row['delta_rank_score']}"
                )
        sys.exit(0)

    if args.eval_command == "report":
        if not args.run.exists():
            print(f"Error: file not found: {args.run}", file=sys.stderr)
            sys.exit(2)
        run = json.loads(args.run.read_text(encoding="utf-8"))
        if args.json_output:
            print(json.dumps(run, indent=2))
        else:
            print(render_report(run))
        sys.exit(0)

    print("Usage: vedalang-dev eval {catalog|run|compare|report} ...")
    sys.exit(2)


if __name__ == "__main__":
    main()
