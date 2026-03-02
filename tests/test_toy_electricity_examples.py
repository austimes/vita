"""Regression checks for toy electricity example structure."""

from pathlib import Path

from vedalang.compiler import compile_vedalang_to_tableir, load_vedalang

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
TOY_ELECTRICITY_FILES = (
    "toy_sectors/toy_electricity_2ts.veda.yaml",
    "toy_sectors/toy_electricity_4ts.veda.yaml",
)


def _load_example(filename: str) -> dict:
    return load_vedalang(EXAMPLES_DIR / filename)


def test_toy_electricity_examples_separate_delivery_and_end_use_roles():
    """Both toy electricity variants keep delivery and end-use boundaries explicit."""
    for filename in TOY_ELECTRICITY_FILES:
        source = _load_example(filename)
        roles = {role["id"]: role for role in source["process_roles"]}

        delivery = roles["deliver_electricity_grid"]
        end_use = roles["provide_electricity_service"]

        assert delivery["stage"] == "distribution"
        assert delivery["required_inputs"][0]["commodity"] == "secondary:electricity"
        assert (
            delivery["required_outputs"][0]["commodity"]
            == "secondary:delivered_electricity"
        )

        assert end_use["stage"] == "end_use"
        assert (
            end_use["required_inputs"][0]["commodity"]
            == "secondary:delivered_electricity"
        )
        assert (
            end_use["required_outputs"][0]["commodity"]
            == "service:electricity_service"
        )

        # Ensure the examples still compile under hard stage/typing validations.
        compile_vedalang_to_tableir(source)


def test_toy_electricity_timeslice_variants_remain_separate_files():
    """2TS and 4TS examples keep distinct timeslice structures by design."""
    source_2ts = _load_example("toy_sectors/toy_electricity_2ts.veda.yaml")
    source_4ts = _load_example("toy_sectors/toy_electricity_4ts.veda.yaml")

    assert "season" not in source_2ts["model"]["timeslices"]
    assert set(source_2ts["model"]["timeslices"]["fractions"]) == {"D", "N"}

    assert "season" in source_4ts["model"]["timeslices"]
    assert set(source_4ts["model"]["timeslices"]["fractions"]) == {
        "SD",
        "SN",
        "WD",
        "WN",
    }


def test_toy_electricity_single_generation_role():
    """Both models use a single generate_electricity role with variant-level inputs."""
    for filename in TOY_ELECTRICITY_FILES:
        source = _load_example(filename)
        roles = {role["id"]: role for role in source["process_roles"]}

        # Single generation role, not fuel-pathway fragmented
        assert "generate_electricity" in roles
        assert "generate_electricity_gas" not in roles
        assert "generate_electricity_renewable" not in roles

        gen_role = roles["generate_electricity"]
        assert gen_role["stage"] == "conversion"
        assert gen_role["required_inputs"] == []  # variant-level inputs

        # Variants under this role
        gen_variants = [
            v for v in source["process_variants"]
            if v["role"] == "generate_electricity"
        ]
        assert len(gen_variants) == 4  # ccgt, ocgt, solar_pv, onshore_wind


def test_toy_electricity_renewable_resource_supply():
    """Renewables consume explicit resource commodities from supply roles."""
    for filename in TOY_ELECTRICITY_FILES:
        source = _load_example(filename)
        roles = {role["id"]: role for role in source["process_roles"]}

        # Resource supply roles exist at supply stage
        assert roles["supply_wind_resource"]["stage"] == "supply"
        assert roles["supply_solar_irradiance"]["stage"] == "supply"

        # Renewable variants consume resources, not zero-input
        variants = {v["id"]: v for v in source["process_variants"]}
        assert (
            variants["solar_pv"]["inputs"][0]["commodity"]
            == "resource:solar_irradiance"
        )
        assert (
            variants["onshore_wind"]["inputs"][0]["commodity"]
            == "resource:wind_resource"
        )
