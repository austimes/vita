"""Handler functions for Vita CLI commands."""

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def run_pipeline_command(args):
    """Run the pipeline command."""
    from tools.veda_dev.pipeline import format_result_table, run_pipeline
    from tools.veda_dev.times_results import extract_results, format_results_console
    from vita.run_artifacts import emit_run_artifacts

    # Handle --process-results-only mode
    if args.process_results_only:
        work_dir = args.work_dir or Path("tmp")
        gdx_path = work_dir / "gams" / f"{args.case}.gdx"

        if not gdx_path.exists():
            print(f"Error: GDX file not found: {gdx_path}", file=sys.stderr)
            sys.exit(2)

        results = extract_results(gdx_path=gdx_path)

        if args.json_output:
            print(json.dumps(results.to_dict(), indent=2))
        else:
            print(format_results_console(results))

        sys.exit(0 if not results.errors else 2)

    if not args.input.exists():
        print(f"Error: Input not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    # Suppress verbose output when JSON is requested (to keep stdout clean)
    verbose = args.verbose and not args.json_output
    out_dir = getattr(args, "out", None)
    keep_workdir = args.keep_workdir or out_dir is not None

    result = run_pipeline(
        input_path=args.input,
        input_kind=args.input_kind,
        run_id=args.run,
        case=args.case,
        times_src=args.times_src,
        gams_binary=args.gams_binary,
        solver=args.solver,
        work_dir=args.work_dir,
        keep_workdir=keep_workdir,
        no_solver=args.no_solver,
        no_sankey=args.no_sankey,
        verbose=verbose,
    )

    if out_dir is not None:
        try:
            run_times_step = result.steps.get("run_times")
            emission = emit_run_artifacts(
                run_dir=out_dir,
                input_path=args.input,
                input_kind=args.input_kind or result.input_kind,
                case=args.case,
                selected_run_id=args.run,
                pipeline_success=result.success,
                pipeline_artifacts=result.artifacts,
                run_times_artifacts=(
                    run_times_step.artifacts if run_times_step is not None else {}
                ),
                run_times_success=(
                    run_times_step.success if run_times_step is not None else False
                ),
                run_times_skipped=(
                    run_times_step.skipped if run_times_step is not None else True
                ),
                extract_results=extract_results,
                now_utc=lambda: datetime.now(UTC),
            )

            result.artifacts["run_artifacts"] = emission.paths.to_dict()
            result.artifacts["run_dir"] = str(emission.paths.run_dir)
            result.artifacts["manifest_file"] = str(emission.paths.manifest_path)
            result.artifacts["model_source_file"] = str(
                emission.paths.source_snapshot_path
            )
            if emission.results_written:
                result.artifacts["results_file"] = str(emission.paths.results_path)
            if emission.paths.gdx_path.exists():
                result.artifacts["run_gdx_file"] = str(emission.paths.gdx_path)
            if emission.paths.lst_path.exists():
                result.artifacts["run_lst_file"] = str(emission.paths.lst_path)

            if (
                result.success
                and not args.keep_workdir
                and result.work_dir != "(cleaned up)"
            ):
                work_dir_path = Path(result.work_dir)
                if work_dir_path.exists():
                    shutil.rmtree(work_dir_path)
                result.work_dir = "(cleaned up)"
                result.artifacts["work_dir"] = result.work_dir
        except Exception as exc:
            result.success = False
            result.artifacts["run_artifact_error"] = str(exc)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result_table(result))

    sys.exit(0 if result.success else 2)


def run_times_results_command(args):
    """Run times-results command."""
    from tools.veda_dev.times_results import (
        extract_results,
        format_results_console,
        save_results,
    )
    from vita.run_artifacts import RunArtifactError, resolve_run_artifacts

    if args.run_dir and args.gdx != Path("tmp/gams/scenario.gdx"):
        print("Error: Use either --run or --gdx, not both", file=sys.stderr)
        sys.exit(2)

    gdx_path = args.gdx
    if args.run_dir:
        try:
            run_paths = resolve_run_artifacts(args.run_dir, require_solver=True)
            gdx_path = run_paths.gdx_path
        except RunArtifactError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)

    year_filter = None
    if args.year_filter:
        year_filter = [y.strip() for y in args.year_filter.split(",")]

    results = extract_results(
        gdx_path=gdx_path,
        process_filter=args.process_filter,
        year_filter=year_filter,
        include_flows=args.flows,
        limit=args.limit,
    )

    if results.errors:
        for err in results.errors:
            print(f"Error: {err}", file=sys.stderr)
        sys.exit(2)

    if args.save:
        created = save_results(results, args.save)
        if not args.quiet:
            print(f"Saved results to: {', '.join(str(p) for p in created)}")

    if not args.quiet:
        if args.json_output:
            print(json.dumps(results.to_dict(), indent=2))
        else:
            print(format_results_console(results, limit=args.limit))

    sys.exit(0)


def run_diff_command(args):
    """Run the Vita run-artifact diff command."""
    from vita.diff import RunDiffError, compare_run_artifacts, format_run_diff_console

    metrics = _parse_multi_csv_args(getattr(args, "metric", None))
    focus_processes = _parse_multi_csv_args(getattr(args, "focus_processes", None))
    limit = max(int(getattr(args, "limit", 20)), 0)

    try:
        diff_payload = compare_run_artifacts(
            baseline_run_dir=args.baseline_run,
            variant_run_dir=args.variant_run,
            metrics=metrics or None,
            focus_processes=focus_processes or None,
        )
    except (RunDiffError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.json_output:
        print(json.dumps(diff_payload, indent=2))
    else:
        print(format_run_diff_console(diff_payload, limit=limit))

    sys.exit(0)


def run_sankey_command(args):
    """Run the sankey command."""
    from tools.veda_dev.sankey import (
        extract_sankey,
        extract_sankey_multi,
        get_available_regions,
        get_available_years,
    )
    from vita.run_artifacts import RunArtifactError, resolve_run_artifacts

    if args.run_dir and args.gdx != Path("tmp/gams/scenario.gdx"):
        print("Error: Use either --run or --gdx, not both", file=sys.stderr)
        sys.exit(2)

    gdx_path = args.gdx
    if args.run_dir:
        try:
            run_paths = resolve_run_artifacts(args.run_dir, require_solver=True)
            gdx_path = run_paths.gdx_path
        except RunArtifactError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)

    if not gdx_path.exists():
        print(f"Error: GDX file not found: {gdx_path}", file=sys.stderr)
        sys.exit(2)

    # Handle list options
    if args.list_years:
        years = get_available_years(gdx_path)
        if years:
            print("Available years:", ", ".join(years))
        else:
            print("No flow data found in GDX file")
        sys.exit(0)

    if args.list_regions:
        regions = get_available_regions(gdx_path)
        if regions:
            print("Available regions:", ", ".join(regions))
        else:
            print("No flow data found in GDX file")
        sys.exit(0)

    # For HTML format, use interactive mode by default (unless --static)
    use_interactive = args.format == "html" and not args.static

    if use_interactive:
        # Extract all years/regions for interactive visualization
        sankey = extract_sankey_multi(
            gdx_path=gdx_path,
            min_flow=args.min_flow,
        )

        if sankey.errors:
            for err in sankey.errors:
                print(f"Error: {err}", file=sys.stderr)
            sys.exit(2)

        if not sankey.years or not sankey.regions:
            print("Warning: No flow data found in GDX file", file=sys.stderr)
            sys.exit(1)

        output = sankey.to_html_interactive()
        output_path = args.output or Path("sankey.html")
        output_path.write_text(output)
        print(f"Saved interactive HTML to: {output_path}")
        print(f"  Years: {len(sankey.years)} ({sankey.years[0]} - {sankey.years[-1]})")
        print(f"  Regions: {len(sankey.regions)} ({', '.join(sankey.regions)})")
        print(f"Open in browser: file://{output_path.absolute()}")
        sys.exit(0)

    # Static mode: single year/region
    sankey = extract_sankey(
        gdx_path=gdx_path,
        year=args.year,
        region=args.region,
        min_flow=args.min_flow,
    )

    if sankey.errors:
        for err in sankey.errors:
            print(f"Error: {err}", file=sys.stderr)
        sys.exit(2)

    if not sankey.links:
        print("Warning: No flow data found for specified year/region", file=sys.stderr)
        sys.exit(1)

    # Generate output
    if args.format == "json":
        output = json.dumps(sankey.to_dict(), indent=2)
        if args.output:
            args.output.write_text(output)
            print(f"Saved JSON to: {args.output}")
        else:
            print(output)

    elif args.format == "mermaid":
        output = sankey.to_mermaid()
        if args.output:
            args.output.write_text(output)
            print(f"Saved Mermaid to: {args.output}")
        else:
            print(output)

    elif args.format == "html":
        output = sankey.to_html()
        output_path = args.output or Path("sankey.html")
        output_path.write_text(output)
        print(f"Saved static HTML to: {output_path}")
        print(f"Open in browser: file://{output_path.absolute()}")

    sys.exit(0)


def _parse_multi_csv_args(values: list[str] | None) -> list[str]:
    """Parse repeated/CSV CLI values into a de-duplicated ordered list."""
    if values is None:
        return []

    parsed: list[str] = []
    for raw in values:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if value not in parsed:
                parsed.append(value)
    return parsed
