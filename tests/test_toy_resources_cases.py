from pathlib import Path

from tools.veda_check import run_check
from vedalang.compiler import compile_vedalang_bundle, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
TOY_RESOURCES_PATH = (
    PROJECT_ROOT / "vedalang" / "examples" / "toy_sectors/toy_resources.veda.yaml"
)


def test_toy_resources_is_a_single_v0_2_fleet_capped_model():
    source = load_vedalang(TOY_RESOURCES_PATH)
    bundle = compile_vedalang_bundle(
        source,
        validate=True,
        selected_run=source["runs"][0]["id"],
    )

    assert bundle.run_id == "single_2025"
    assert bundle.csir["zone_opportunities"] == []
    capped_process = next(
        process
        for process in bundle.cpir["processes"]
        if process.get("source_role_instance") == "role_instance.haul_service@SINGLE"
        and process.get("technology") == "electric_haul"
    )
    assert capped_process["max_new_capacity"]["amount"] == 12.0


def test_toy_resources_validates_end_to_end():
    result = run_check(TOY_RESOURCES_PATH, from_vedalang=True)
    assert result.success
    assert result.errors == 0
