"""Tests for veda_check orchestrator."""

from pathlib import Path

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


def test_result_has_table_info():
    """Result should include table information."""
    result = run_check(
        EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml",
        from_vedalang=True,
    )
    # Should have some tables
    assert len(result.tables) >= 1
