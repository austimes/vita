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


def run_experiment_plan_command(args):
    """Handle 'vita experiment plan'."""
    from vita.experiment_runner import plan_experiment

    state = plan_experiment(args.manifest, args.out)
    print(f"Experiment planned: {state.experiment_id}")
    print(f"  Status: {state.status}")
    print(f"  Runs: {state.progress.runs_total}")
    print(f"  Comparisons: {state.progress.diffs_total}")


def run_experiment_run_command(args):
    """Handle 'vita experiment run'."""
    from vita.experiment_runner import run_experiment

    result = run_experiment(
        args.experiment_dir,
        resume=args.resume,
        force=args.force,
        json_output=getattr(args, "json_output", False),
    )
    if args.json_output:
        print(
            json.dumps(
                {
                    "experiment_dir": str(result.experiment_dir),
                    "status": result.state.status,
                    "success": result.success,
                    "progress": result.state.progress.__dict__,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
    else:
        print(f"Experiment: {result.state.experiment_id}")
        print(f"  Status: {result.state.status}")
        p = result.state.progress
        print(f"  Runs: {p.runs_complete}/{p.runs_total} complete")
        print(f"  Diffs: {p.diffs_complete}/{p.diffs_total} complete")
    sys.exit(0 if result.success else 2)


def run_experiment_summarize_command(args):
    """Handle 'vita experiment summarize'."""
    from vita.experiment_summary import generate_summary

    summary_path = generate_summary(args.experiment_dir)

    if getattr(args, "json_output", False):
        import json as json_mod

        print(json_mod.dumps({"summary_json": str(summary_path)}, indent=2))
    else:
        print(f"Summary generated: {summary_path}")


def run_experiment_validate_brief_command(args):
    """Handle 'vita experiment validate-brief'."""
    import json as json_mod

    from vita.experiment_manifest import load_experiment_manifest
    from vita.experiment_validation import validate_brief

    experiment_dir = args.experiment_dir.expanduser().resolve()
    manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")

    brief_path = experiment_dir / "planning" / "brief.json"
    if not brief_path.exists():
        print(f"Error: brief.json not found: {brief_path}", file=sys.stderr)
        sys.exit(2)

    brief = json_mod.loads(brief_path.read_text(encoding="utf-8"))
    result = validate_brief(brief, manifest)

    # Save validation result
    val_path = experiment_dir / "planning" / "brief.validation.json"
    result.save(val_path)

    if getattr(args, "json_output", False):
        print(json_mod.dumps(result.to_dict(), indent=2))
    else:
        if result.valid:
            print(f"Brief validation passed ({len(result.warnings)} warnings)")
        else:
            print(f"Brief validation FAILED ({len(result.errors)} errors)")
            for err in result.errors:
                print(f"  ERROR: {err}")
        for w in result.warnings:
            print(f"  WARNING: {w}")

    sys.exit(0 if result.valid else 2)


def run_experiment_validate_interpretation_command(args):
    """Handle 'vita experiment validate-interpretation'."""
    import json as json_mod

    from vita.experiment_manifest import load_experiment_manifest
    from vita.experiment_validation import validate_interpretation

    experiment_dir = args.experiment_dir.expanduser().resolve()
    manifest = load_experiment_manifest(experiment_dir / "manifest.yaml")

    interpretation_path = experiment_dir / "conclusions" / "interpretation.json"
    if not interpretation_path.exists():
        print(
            f"Error: interpretation.json not found: {interpretation_path}",
            file=sys.stderr,
        )
        sys.exit(2)

    interpretation = json_mod.loads(
        interpretation_path.read_text(encoding="utf-8")
    )

    summary_path = experiment_dir / "conclusions" / "summary.json"
    summary = {}
    if summary_path.exists():
        summary = json_mod.loads(summary_path.read_text(encoding="utf-8"))

    result = validate_interpretation(interpretation, manifest, summary)

    # Save validation result
    val_path = experiment_dir / "conclusions" / "interpretation.validation.json"
    val_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(val_path)

    if getattr(args, "json_output", False):
        print(json_mod.dumps(result.to_dict(), indent=2))
    else:
        if result.valid:
            print(
                f"Interpretation validation passed ({len(result.warnings)} warnings)"
            )
        else:
            print(
                f"Interpretation validation FAILED ({len(result.errors)} errors)"
            )
            for err in result.errors:
                print(f"  ERROR: {err}")
        for w in result.warnings:
            print(f"  WARNING: {w}")

    sys.exit(0 if result.valid else 2)


def run_experiment_present_command(args):
    """Handle 'vita experiment present'."""
    from vita.experiment_presentation import generate_presentation

    html_path = generate_presentation(args.experiment_dir)
    print(f"Presentation generated: {html_path}")


def run_experiment_status_command(args):
    """Handle 'vita experiment status'."""
    from vita.experiment_state import load_experiment_state

    state = load_experiment_state(args.experiment_dir)
    if getattr(args, "json_output", False):
        print(json.dumps(state.to_dict(), indent=2))
    else:
        print(f"Experiment: {state.experiment_id}")
        print(f"  Status: {state.status}")
        p = state.progress
        print(
            f"  Runs: {p.runs_complete}/{p.runs_total} complete, {p.runs_failed} failed"
        )
        print(f"  Diffs: {p.diffs_complete}/{p.diffs_total} complete")
        if state.completed_at:
            print(f"  Completed: {state.completed_at}")
        if state.concluded_at:
            print(f"  Concluded: {state.concluded_at}")


def run_experiment_full_command(args):
    """Handle convenience 'vita experiment <manifest.yaml>' (stage+run+summarize)."""
    from vita.experiment_runner import plan_experiment, run_experiment
    from vita.experiment_summary import generate_summary

    state = plan_experiment(args.manifest, args.out)
    print(f"Experiment staged: {state.experiment_id}")
    print(f"  Runs: {state.progress.runs_total}")
    print(f"  Comparisons: {state.progress.diffs_total}")

    result = run_experiment(
        state.experiment_dir,
        resume=False,
        force=False,
        json_output=getattr(args, "json_output", False),
    )

    if getattr(args, "json_output", False):
        print(
            json.dumps(
                {
                    "experiment_dir": str(result.experiment_dir),
                    "status": result.state.status,
                    "success": result.success,
                    "progress": result.state.progress.__dict__,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
    else:
        print(f"Experiment: {result.state.experiment_id}")
        print(f"  Status: {result.state.status}")
        p = result.state.progress
        print(f"  Runs: {p.runs_complete}/{p.runs_total} complete")
        print(f"  Diffs: {p.diffs_complete}/{p.diffs_total} complete")

    if not result.success:
        sys.exit(2)

    summary_path = generate_summary(result.experiment_dir)
    # DO NOT auto-present or auto-conclude — those require agentic artifacts
    if not getattr(args, "json_output", False):
        print(f"  Summary: {summary_path}")

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
