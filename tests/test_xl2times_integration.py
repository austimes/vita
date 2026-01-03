"""Integration tests for xl2times processing of VEDA fixtures."""

import json
import subprocess
import tempfile
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "MiniVEDA2"
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


@pytest.fixture(scope="module")
def ensure_fixture():
    """Ensure the MiniVEDA2 fixture exists before running tests."""
    if not FIXTURE_PATH.exists():
        create_script = PROJECT_ROOT / "fixtures" / "create_miniveda2.py"
        if create_script.exists():
            result = subprocess.run(
                ["uv", "run", "python", str(create_script)],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )
            if result.returncode != 0:
                pytest.skip(f"Failed to create fixture: {result.stderr}")
        else:
            pytest.skip("MiniVEDA2 fixture not found and create script missing")


@pytest.mark.skipif(
    not (PROJECT_ROOT / "xl2times").exists(),
    reason="xl2times submodule not available",
)
class TestXl2timesIntegration:
    """Tests for xl2times integration with VEDA fixtures."""

    def test_xl2times_processes_miniveda2(self, ensure_fixture):
        """Run xl2times on MiniVEDA2 and validate outputs against schemas."""
        if not FIXTURE_PATH.exists():
            pytest.skip("MiniVEDA2 fixture not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            manifest_path = tmpdir / "manifest.json"
            diagnostics_path = tmpdir / "diagnostics.json"

            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "xl2times",
                    str(FIXTURE_PATH),
                    "--manifest-json",
                    str(manifest_path),
                    "--diagnostics-json",
                    str(diagnostics_path),
                ],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )

            # Check outputs were created
            assert manifest_path.exists(), (
                f"Manifest not created. returncode={result.returncode}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
            assert diagnostics_path.exists(), (
                f"Diagnostics not created. returncode={result.returncode}\n"
                f"stderr: {result.stderr}"
            )

            # Validate manifest against schema
            manifest_schema_path = SCHEMA_DIR / "manifest.schema.json"
            assert manifest_schema_path.exists(), "Manifest schema not found"

            with open(manifest_schema_path) as f:
                manifest_schema = json.load(f)
            with open(manifest_path) as f:
                manifest = json.load(f)

            jsonschema.validate(manifest, manifest_schema)

            # Validate diagnostics against schema
            diag_schema_path = SCHEMA_DIR / "diagnostics.schema.json"
            assert diag_schema_path.exists(), "Diagnostics schema not found"

            with open(diag_schema_path) as f:
                diag_schema = json.load(f)
            with open(diagnostics_path) as f:
                diagnostics = json.load(f)

            jsonschema.validate(diagnostics, diag_schema)

            # Check no errors in diagnostics
            errors = [
                d
                for d in diagnostics.get("diagnostics", [])
                if d.get("severity") == "error"
            ]
            assert len(errors) == 0, f"xl2times reported errors: {errors}"

    def test_xl2times_produces_tables(self, ensure_fixture):
        """Verify xl2times produces expected output tables."""
        if not FIXTURE_PATH.exists():
            pytest.skip("MiniVEDA2 fixture not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            manifest_path = tmpdir / "manifest.json"

            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "xl2times",
                    str(FIXTURE_PATH),
                    "--manifest-json",
                    str(manifest_path),
                ],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )

            assert result.returncode == 0, f"xl2times failed: {result.stderr}"

            with open(manifest_path) as f:
                manifest = json.load(f)

            # Check that we have inputs and tables
            assert len(manifest.get("inputs", [])) > 0, "No inputs in manifest"
            assert len(manifest.get("tables", [])) > 0, "No tables in manifest"

            # Check for expected table tags
            tags = {t["tag"] for t in manifest["tables"]}
            expected_tags = {"~FI_T", "~FI_Process", "~FI_Comm"}
            found_expected = expected_tags & tags
            assert len(found_expected) > 0, (
                f"None of the expected tags found. Got: {tags}"
            )
