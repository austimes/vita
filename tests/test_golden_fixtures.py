"""Golden fixture regression tests.

Validates that all VedaLang example fixtures pass through the full pipeline.
This is the primary guardrail preventing regression during schema evolution.
"""

from pathlib import Path

import pytest

from tools.veda_check import run_check

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


SKIP_XL2TIMES_VALIDATION = {
    "feature_demos/example_with_constraints.veda.yaml",
}


def get_vedalang_fixtures() -> list[Path]:
    """Find all .veda.yaml files in examples directory."""
    fixtures = sorted(EXAMPLES_DIR.rglob("*.veda.yaml"))
    fixtures = [
        f
        for f in fixtures
        if str(f.relative_to(EXAMPLES_DIR)) not in SKIP_XL2TIMES_VALIDATION
    ]
    if not fixtures:
        pytest.skip("No VedaLang fixtures found")
    return fixtures


def get_tableir_fixtures() -> list[Path]:
    """Find all valid TableIR fixtures (excluding invalid ones)."""
    all_yaml = sorted((EXAMPLES_DIR / "tableir").glob("tableir_*.yaml"))
    return [f for f in all_yaml if "invalid" not in f.name]


@pytest.mark.parametrize(
    "fixture_path",
    get_vedalang_fixtures(),
    ids=lambda p: p.name
)
def test_vedalang_fixture_compiles(fixture_path: Path):
    """Each VedaLang fixture must compile and emit tables without errors."""
    result = run_check(fixture_path, from_vedalang=True)

    assert len(result.tables) > 0, f"No tables emitted from {fixture_path.name}"
    assert result.total_rows > 0, f"No rows emitted from {fixture_path.name}"
    assert result.errors == 0, (
        f"{fixture_path.name} had {result.errors} errors:\n"
        + "\n".join(f"  - {msg}" for msg in result.error_messages)
    )


@pytest.mark.parametrize(
    "fixture_path",
    get_tableir_fixtures(),
    ids=lambda p: p.name
)
def test_tableir_fixture_emits(fixture_path: Path):
    """Each valid TableIR fixture must emit tables.

    Note: TableIR fixtures are for emitter testing, not full xl2times validation.
    They may be intentionally minimal and lack system tables.
    """
    result = run_check(fixture_path, from_tableir=True)

    assert len(result.tables) > 0, f"No tables emitted from {fixture_path.name}"
    assert result.total_rows > 0, f"No rows emitted from {fixture_path.name}"


def test_invalid_tableir_fails():
    """Invalid TableIR should fail schema validation."""
    invalid_path = EXAMPLES_DIR / "tableir/tableir_invalid.yaml"
    if not invalid_path.exists():
        pytest.skip("tableir/tableir_invalid.yaml not found")

    result = run_check(invalid_path, from_tableir=True)
    assert not result.success or result.errors > 0, (
        "tableir/tableir_invalid.yaml should have failed but passed"
    )


class TestFixtureInventory:
    """Meta-tests ensuring we have expected fixtures."""

    def test_has_vedalang_fixtures(self):
        """Ensure at least one VedaLang fixture exists."""
        fixtures = list(EXAMPLES_DIR.rglob("*.veda.yaml"))
        assert len(fixtures) >= 1, "Expected at least one .veda.yaml fixture"

    def test_mini_plant_exists(self):
        """The canonical mini_plant fixture must exist."""
        mini_plant = EXAMPLES_DIR / "quickstart/mini_plant.veda.yaml"
        assert mini_plant.exists(), (
            "quickstart/mini_plant.veda.yaml is the canonical fixture"
        )
