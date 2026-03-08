"""Tests for veda_check orchestrator."""

from pathlib import Path

import yaml

from tests.test_v0_2_backend import _v0_2_backend_source
from tools.veda_check import run_check

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


def test_check_vedalang_compiles():
    """VedaLang source should compile and emit tables."""
    result = run_check(
        EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml",
        from_vedalang=True,
    )
    # These minimal examples lack system tables so xl2times fails,
    # but the compile+emit pipeline should work
    assert len(result.tables) > 0
    assert result.total_rows > 0
    assert result.dsl_version == "0.2"
    assert result.artifact_version == "1.0.0"


def test_check_tableir_emits():
    """TableIR should emit tables."""
    result = run_check(
        EXAMPLES_DIR / "tableir/tableir_minimal.yaml",
        from_tableir=True,
    )
    # Minimal example - compiles but xl2times fails (missing system tables)
    assert len(result.tables) > 0
    assert result.total_rows > 0


def test_check_invalid_source():
    """Invalid source should fail with errors."""
    # Create a temp invalid file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".veda.yaml", delete=False, mode="w") as f:
        f.write("invalid: not_a_model\n")
        tmp_path = Path(f.name)

    try:
        result = run_check(tmp_path, from_vedalang=True)
        assert not result.success
        assert result.errors > 0
    finally:
        tmp_path.unlink()


def test_check_rejects_legacy_public_process_syntax():
    """Public check entrypoint rejects legacy top-level processes syntax."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".veda.yaml", delete=False, mode="w") as f:
        f.write(
            "\n".join(
                [
                    "model:",
                    "  name: LegacyCheck",
                    "  regions: [REG1]",
                    "  commodities:",
                    "    - name: C:ELC",
                    "      type: energy",
                    "processes:",
                    "  - name: IMP_ELC",
                    "    sets: [IMP]",
                    "    outputs:",
                    "      - commodity: C:ELC",
                    "    efficiency: 1.0",
                ]
            )
            + "\n"
        )
        tmp_path = Path(f.name)

    try:
        result = run_check(tmp_path, from_vedalang=True)
        assert not result.success
        assert result.errors > 0
        assert any(
            "Additional properties are not allowed" in msg
            for msg in result.error_messages
        )
    finally:
        tmp_path.unlink()


def test_result_has_table_info():
    """Result should include table information."""
    result = run_check(
        EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml",
        from_vedalang=True,
    )
    # Should have some tables
    assert len(result.tables) >= 1


def test_check_v0_2_run_scoped_source(tmp_path):
    """Run-scoped v0.2 sources compile through veda_check."""
    src = tmp_path / "toy_v0_2.veda.yaml"
    src.write_text(yaml.safe_dump(_v0_2_backend_source()), encoding="utf-8")

    result = run_check(
        src,
        from_vedalang=True,
        selected_run="toy_states_2025",
    )

    assert result.dsl_version == "0.2"
    assert len(result.tables) > 0
    assert result.total_rows > 0
