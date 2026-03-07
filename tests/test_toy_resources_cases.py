from pathlib import Path

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_bundle, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
TOY_RESOURCES_PATH = (
    PROJECT_ROOT / "vedalang" / "examples" / "toy_sectors/toy_resources.veda.yaml"
)


def test_toy_resources_is_a_single_v0_2_opportunity_model():
    source = load_vedalang(TOY_RESOURCES_PATH)
    bundle = compile_vedalang_bundle(
        source,
        validate=True,
        selected_run=source["runs"][0]["id"],
    )

    assert bundle.run_id == "single_2025"
    assert len(bundle.csir["opportunities"]) == 1
    assert bundle.csir["opportunities"][0]["technology"] == "electric_haul"


def test_toy_resources_validates_end_to_end():
    result = run_check(TOY_RESOURCES_PATH, from_vedalang=True)
    assert result.success
    assert result.errors == 0
