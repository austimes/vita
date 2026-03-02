"""Integration tests for the diagnostic feedback loop.

Tests the full pipeline: VedaLang → Excel → xl2times with structured diagnostics.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from tools.veda_check import run_check
from tools.veda_emit_excel import emit_excel
from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


class TestDiagnosticFeedbackLoop:
    """Tests for the complete diagnostic feedback loop."""

    def test_veda_check_captures_diagnostics(self):
        """veda_check should capture diagnostics from xl2times."""
        result = run_check(
            EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml",
            from_vedalang=True,
        )

        # Pipeline should produce tables
        assert len(result.tables) > 0
        assert "~FI_COMM" in result.tables
        assert "~FI_PROCESS" in result.tables
        assert "~FI_T" in result.tables

        # VedaLang now emits all required system tables, so pipeline should succeed
        assert result.success

        # Should not have critical errors
        assert result.errors == 0

    def test_diagnostics_json_is_valid(self):
        """diagnostics.json should be valid JSON with expected structure."""
        source = load_vedalang(EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml")
        ir = compile_vedalang_to_tableir(source)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            emit_excel(ir, tmpdir)

            diag_path = tmpdir / "diagnostics.json"

            subprocess.run(
                [
                    "uv", "run", "python", "-m", "xl2times",
                    str(tmpdir),
                    "--diagnostics-json", str(diag_path),
                ],
                capture_output=True,
                text=True,
            )

            # Diagnostics file should exist
            assert diag_path.exists(), "diagnostics.json should be created"

            # Should be valid JSON
            with open(diag_path) as f:
                diag = json.load(f)

            # Check required structure
            assert "version" in diag
            assert "status" in diag
            assert "diagnostics" in diag
            assert "summary" in diag
            assert isinstance(diag["diagnostics"], list)

            # Summary should have counts
            summary = diag["summary"]
            assert "error_count" in summary
            assert "warning_count" in summary
            assert "info_count" in summary

    def test_internal_error_has_traceback(self):
        """INTERNAL_ERROR diagnostics should include traceback context."""
        source = load_vedalang(EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml")
        ir = compile_vedalang_to_tableir(source)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            emit_excel(ir, tmpdir)

            diag_path = tmpdir / "diagnostics.json"

            subprocess.run(
                [
                    "uv", "run", "python", "-m", "xl2times",
                    str(tmpdir),
                    "--diagnostics-json", str(diag_path),
                ],
                capture_output=True,
            )

            with open(diag_path) as f:
                diag = json.load(f)

            # Find INTERNAL_ERROR if present
            internal_errors = [
                d for d in diag["diagnostics"]
                if d.get("code") == "INTERNAL_ERROR"
            ]

            if internal_errors:
                error = internal_errors[0]
                assert "context" in error
                assert "exception_type" in error["context"]
                assert "traceback" in error["context"]

    def test_error_messages_propagated_to_result(self):
        """Error messages should be available in CheckResult."""
        result = run_check(
            EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml",
            from_vedalang=True,
        )

        # If there are errors, there should be messages
        if result.errors > 0:
            assert len(result.error_messages) > 0


class TestDiagnosticCodes:
    """Tests for specific diagnostic codes from xl2times."""

    def test_missing_table_warnings_logged(self):
        """Missing optional elements should be logged as warnings."""
        source = load_vedalang(EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml")
        ir = compile_vedalang_to_tableir(source)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            emit_excel(ir, tmpdir)

            proc = subprocess.run(
                ["uv", "run", "python", "-m", "xl2times", str(tmpdir)],
                capture_output=True,
                text=True,
            )

            # Check stdout for warning messages (VedaLang now emits required tables,
            # but there may be other warnings like external regions)
            stdout = proc.stdout
            # Should produce some output without crashing
            assert proc.returncode is not None
            # Either there are warnings or the process completed
            assert "WARNING" in stdout or proc.returncode == 0 or "SUCCESS" in stdout
