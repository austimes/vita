from pathlib import Path

from vedalang.compiler import compile_vedalang_bundle, load_vedalang

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "vedalang" / "examples" / "v0_2"


def test_flagship_v0_2_examples_compile():
    fixtures = {
        "mini_space_heat.veda.yaml": "toy_region_2025",
        "toy_heat_network.veda.yaml": "toy_states_2025",
    }

    for file_name, run_id in fixtures.items():
        source = load_vedalang(EXAMPLES_DIR / file_name)
        bundle = compile_vedalang_bundle(
            source,
            validate=True,
            selected_run=run_id,
        )
        assert bundle.run_id == run_id
        assert bundle.csir is not None
        assert bundle.cpir is not None
        assert bundle.explain is not None
        assert bundle.tableir["dsl_version"] == "0.2"


def test_quickstart_v0_2_examples_compile():
    quickstart_dir = EXAMPLES_DIR.parent / "quickstart"
    fixtures = {
        quickstart_dir / "mini_plant.veda.yaml": "reg1_2020",
        quickstart_dir / "mini_plant_shorthand.veda.yaml": "reg1_2020",
        quickstart_dir / "mini_plant_with_costs.veda.yaml": "reg1_2020",
        quickstart_dir / "demo001_resource_supply.veda.yaml": "reg1_2005",
    }

    for path, run_id in fixtures.items():
        source = load_vedalang(path)
        bundle = compile_vedalang_bundle(
            source,
            validate=True,
            selected_run=run_id,
        )
        assert bundle.run_id == run_id
        assert bundle.csir is not None
        assert bundle.cpir is not None
        assert bundle.explain is not None
        assert bundle.tableir["dsl_version"] == "0.2"
