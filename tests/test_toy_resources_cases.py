"""Regression tests for toy_resources case overlays."""

from pathlib import Path

import pytest

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
TOY_RESOURCES_PATH = PROJECT_ROOT / "vedalang" / "examples" / "toy_resources.veda.yaml"


def test_toy_resources_has_ref_co2cap_force_shift_cases():
    """toy_resources should define all expected policy cases in one source."""
    source = load_vedalang(TOY_RESOURCES_PATH)
    tableir = compile_vedalang_to_tableir(source)

    case_names = [case["name"] for case in tableir["cases"]]
    assert case_names == ["ref", "co2cap", "force_shift"]

    ref_case = next(case for case in tableir["cases"] if case["name"] == "ref")
    assert ref_case["is_baseline"] is True


@pytest.mark.parametrize("case_name", ["ref", "co2cap", "force_shift"])
def test_toy_resources_each_case_validates(case_name: str):
    """Each toy_resources case should compile and pass xl2times validation."""
    result = run_check(
        TOY_RESOURCES_PATH,
        from_vedalang=True,
        selected_cases=[case_name],
    )

    assert result.errors == 0, (
        f"toy_resources case '{case_name}' had {result.errors} errors:\n"
        + "\n".join(f"  - {msg}" for msg in result.error_messages)
    )
    assert result.success, f"toy_resources case '{case_name}' should validate"
