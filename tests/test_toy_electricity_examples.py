from pathlib import Path

from vedalang.compiler import compile_vedalang_bundle, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"


def _load_example(filename: str) -> dict:
    return load_vedalang(EXAMPLES_DIR / filename)


def test_toy_electricity_examples_compile_as_public_network_models():
    fixtures = {
        "toy_sectors/toy_electricity_2ts.veda.yaml": "electricity_2node_2025",
        "toy_sectors/toy_electricity_4ts.veda.yaml": "electricity_4node_2025",
    }

    for filename, run_id in fixtures.items():
        source = _load_example(filename)
        bundle = compile_vedalang_bundle(source, validate=True, selected_run=run_id)
        assert bundle.run_id == run_id
        assert bundle.csir is not None
        assert bundle.cpir is not None


def test_toy_electricity_2ts_and_4ts_keep_distinct_partition_sizes():
    source_2ts = _load_example("toy_sectors/toy_electricity_2ts.veda.yaml")
    source_4ts = _load_example("toy_sectors/toy_electricity_4ts.veda.yaml")

    assert source_2ts["region_partitions"][0]["members"] == ["D", "N"]
    assert source_4ts["region_partitions"][0]["members"] == ["SD", "SN", "WD", "WN"]
    assert len(source_4ts["networks"][0]["links"]) > len(
        source_2ts["networks"][0]["links"]
    )
