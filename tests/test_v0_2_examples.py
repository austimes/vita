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
