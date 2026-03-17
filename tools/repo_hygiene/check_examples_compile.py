"""Run-aware VedaLang example compile sweep for hygiene audits.

This check distinguishes expected run-selection diagnostics (E002 for
multi-run files compiled without --run) from true compile failures.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vedalang.compiler import ResolutionError, compile_vedalang_bundle, load_vedalang


def _is_expected_run_selection_error(exc: Exception) -> bool:
    return (
        isinstance(exc, ResolutionError)
        and exc.code == "E002"
        and exc.object_id == "runs"
        and "multiple runs defined" in exc.message
    )


def _as_failure(file_path: Path, run_id: str | None, exc: Exception) -> dict[str, Any]:
    code = getattr(exc, "code", exc.__class__.__name__)
    message = getattr(exc, "message", str(exc))
    return {
        "file": str(file_path),
        "run_id": run_id,
        "code": str(code),
        "message": str(message),
    }


def _extract_run_ids(source: dict[str, Any]) -> list[str]:
    run_ids: list[str] = []
    for run in source.get("runs") or []:
        if isinstance(run, dict):
            run_id = run.get("id")
            if isinstance(run_id, str) and run_id.strip():
                run_ids.append(run_id)
    return run_ids


def evaluate_examples(example_files: list[Path]) -> dict[str, Any]:
    file_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    expected_e002_files: list[str] = []
    checked_runs = 0

    for file_path in example_files:
        file_failures: list[dict[str, Any]] = []
        expected_e002 = False

        try:
            source = load_vedalang(file_path)
            if not isinstance(source, dict):
                raise TypeError("source is not a mapping")
        except Exception as exc:
            failure = _as_failure(file_path, None, exc)
            file_failures.append(failure)
            failures.append(failure)
            file_results.append(
                {
                    "file": str(file_path),
                    "run_ids": [],
                    "expected_e002": expected_e002,
                    "failures": file_failures,
                }
            )
            continue

        run_ids = _extract_run_ids(source)
        checked_runs += len(run_ids)

        if len(run_ids) > 1:
            try:
                compile_vedalang_bundle(source)
            except Exception as exc:
                if _is_expected_run_selection_error(exc):
                    expected_e002 = True
                    expected_e002_files.append(str(file_path))
                else:
                    failure = _as_failure(file_path, None, exc)
                    file_failures.append(failure)
                    failures.append(failure)

        runs_to_check = run_ids or [None]
        for run_id in runs_to_check:
            try:
                compile_vedalang_bundle(source, selected_run=run_id)
            except Exception as exc:
                failure = _as_failure(file_path, run_id, exc)
                file_failures.append(failure)
                failures.append(failure)

        file_results.append(
            {
                "file": str(file_path),
                "run_ids": run_ids,
                "expected_e002": expected_e002,
                "failures": file_failures,
            }
        )

    return {
        "success": not failures,
        "checked_files": len(example_files),
        "checked_runs": checked_runs,
        "expected_e002_files": expected_e002_files,
        "failures": failures,
        "results": file_results,
    }


def _collect_example_files(examples_root: Path) -> list[Path]:
    return sorted(examples_root.rglob("*.veda.yaml"))


def _print_text_report(report: dict[str, Any]) -> None:
    print(
        "Checked"
        f" {report['checked_files']} files"
        f" across {report['checked_runs']} declared runs."
    )
    print(
        "Observed expected E002 run-selection responses in"
        f" {len(report['expected_e002_files'])} multi-run files."
    )

    failures = report["failures"]
    if not failures:
        print("No true compile failures detected.")
        return

    print(f"True compile failures: {len(failures)}")
    for failure in failures:
        run_suffix = f" (run: {failure['run_id']})" if failure["run_id"] else ""
        print(
            f"- {failure['file']}{run_suffix}:"
            f" {failure['code']} {failure['message']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run-aware compile hygiene sweep for vedalang/examples, "
            "with expected E002 run-selection classification."
        )
    )
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=Path("vedalang/examples"),
        help="Root directory containing .veda.yaml examples.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    args = parser.parse_args()

    if not args.examples_root.exists():
        print(f"examples root not found: {args.examples_root}")
        return 2

    example_files = _collect_example_files(args.examples_root)
    report = evaluate_examples(example_files)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report)

    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
