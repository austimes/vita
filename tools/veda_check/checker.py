"""Core veda_check logic."""

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from tools.veda_check.invariants import check_tableir_invariants
from tools.veda_emit_excel import emit_excel, load_tableir
from vedalang.compiler import (
    ResolutionError,
    compile_vedalang_bundle,
    load_vedalang,
)
from vedalang.versioning import CHECK_OUTPUT_VERSION, DSL_VERSION

SCHEMA_DIR = Path(__file__).parent.parent.parent / "vedalang" / "schema"


@dataclass
class CheckResult:
    """Result of a veda_check run."""
    success: bool
    source_path: Path
    tables: list[str] = field(default_factory=list)
    total_rows: int = 0
    warnings: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    manifest: dict | None = None
    diagnostics: dict | None = None
    dsl_version: str = DSL_VERSION
    artifact_version: str = CHECK_OUTPUT_VERSION


def run_check(
    input_path: Path,
    from_vedalang: bool = False,
    from_tableir: bool = False,
    project_root: Path | None = None,
    selected_cases: list[str] | None = None,
    selected_run: str | None = None,
) -> CheckResult:
    """
    Run the full validation pipeline.

    Args:
        input_path: Path to VedaLang or TableIR source
        from_vedalang: Input is VedaLang (.veda.yaml)
        from_tableir: Input is TableIR (.yaml/.json)
        project_root: Project root for running xl2times

    Returns:
        CheckResult with validation results
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent

    result = CheckResult(success=False, source_path=input_path)

    try:
        # Step 1: Get TableIR
        if from_vedalang:
            source = load_vedalang(input_path)
            bundle = compile_vedalang_bundle(
                source,
                selected_cases=selected_cases,
                selected_run=selected_run,
            )
            tableir = bundle.tableir
            result.dsl_version = source.get("dsl_version", DSL_VERSION)
        elif from_tableir:
            tableir = load_tableir(input_path)
            result.dsl_version = str(tableir.get("dsl_version", DSL_VERSION))
        else:
            raise ValueError("Must specify --from-vedalang or --from-tableir")

        # Extract table info from tableir (always available)
        for file_spec in tableir.get("files", []):
            for sheet_spec in file_spec.get("sheets", []):
                for table in sheet_spec.get("tables", []):
                    tag = table.get("tag", "unknown")
                    if tag not in result.tables:
                        result.tables.append(tag)
                    result.total_rows += len(table.get("rows", []))

        # Step 2: Check TableIR invariants (fast validation before xl2times)
        invariant_errors = check_tableir_invariants(tableir)
        if invariant_errors:
            result.errors += len(invariant_errors)
            result.error_messages.extend(invariant_errors)
            return result

        # Step 3: Emit Excel to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            emit_excel(tableir, tmpdir)

            # Step 4: Run xl2times
            manifest_path = tmpdir / "manifest.json"
            diagnostics_path = tmpdir / "diagnostics.json"
            xl2times_output_dir = tmpdir / "xl2times_output"

            proc = subprocess.run(
                [
                    "uv", "run", "python", "-m", "xl2times",
                    str(tmpdir),
                    "--output_dir", str(xl2times_output_dir),
                    "--manifest-json", str(manifest_path),
                    "--diagnostics-json", str(diagnostics_path),
                ],
                capture_output=True,
                text=True,
                cwd=project_root,
            )

            # Step 5: Parse and validate outputs (if available)
            if manifest_path.exists():
                with open(manifest_path) as f:
                    result.manifest = json.load(f)

            if diagnostics_path.exists():
                with open(diagnostics_path) as f:
                    result.diagnostics = json.load(f)

                # Count warnings and errors
                for diag in result.diagnostics.get("diagnostics", []):
                    severity = diag.get("severity", "")
                    if severity == "error":
                        result.errors += 1
                        msg = diag.get("message", "Unknown error")
                        result.error_messages.append(msg)
                    elif severity == "warning":
                        result.warnings += 1

            # Determine success - xl2times exit code 0 means success
            result.success = proc.returncode == 0 and result.errors == 0

    except jsonschema.ValidationError as e:
        result.errors += 1
        result.error_messages.append(e.message)
        result.diagnostics = {
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "SCHEMA_ERROR",
                    "message": e.message,
                }
            ]
        }
    except ResolutionError as e:
        result.errors += 1
        result.error_messages.append(f"{e.code}: {e.message}")
        result.diagnostics = {
            "diagnostics": [
                {
                    "severity": "error",
                    "code": e.code,
                    "message": e.message,
                    "object_id": e.object_id,
                }
            ]
        }
    except jsonschema.ValidationError as e:
        result.errors += 1
        result.error_messages.append(f"Schema validation: {e.message}")
    except Exception as e:
        result.errors += 1
        result.error_messages.append(str(e))

    return result
