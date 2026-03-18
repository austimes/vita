from pathlib import Path

from vedalang.compiler import compile_vedalang_bundle, load_vedalang

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "vedalang" / "examples"
FEATURE_DEMOS_DIR = EXAMPLES_ROOT / "feature_demos"


def test_flagship_public_examples_compile():
    fixtures = {
        EXAMPLES_ROOT / "quickstart" / "mini_space_heat.veda.yaml": "toy_region_2025",
        FEATURE_DEMOS_DIR / "toy_heat_network.veda.yaml": "toy_states_2025",
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
        assert bundle.tableir["dsl_version"] == "0.3"


def test_quickstart_public_examples_compile():
    quickstart_dir = EXAMPLES_ROOT / "quickstart"
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
        assert bundle.tableir["dsl_version"] == "0.3"


def test_ported_example_catalog_compiles():
    example_dir = EXAMPLES_ROOT
    fixtures = {
        example_dir
        / "design_challenges/dc1_thermal_from_patterns.veda.yaml": "reg1_2020",
        example_dir / "design_challenges/dc2_thermal_renewable.veda.yaml": "reg1_2020",
        example_dir / "design_challenges/dc3_with_emissions.veda.yaml": "single_2025",
        example_dir / "design_challenges/dc4_co2_price_scenario.veda.yaml": "reg1_2025",
        example_dir / "design_challenges/dc5_two_regions.veda.yaml": "two_regions_2020",
        example_dir
        / "feature_demos/article6_abated_lng_assessment.veda.yaml": "article6_2025",
        example_dir / "feature_demos/example_with_bounds.veda.yaml": "reg1_2025",
        example_dir / "feature_demos/example_with_constraints.veda.yaml": "reg1_2025",
        example_dir / "feature_demos/example_with_demand.veda.yaml": "reg1_2020",
        example_dir
        / "feature_demos/example_with_facilities.veda.yaml": "au_states_2025",
        example_dir
        / "feature_demos/example_with_lng_ccs_option.veda.yaml": "single_2025",
        example_dir / "feature_demos/example_with_timeslices.veda.yaml": "reg1_2020",
        example_dir
        / "feature_demos/example_with_trade.veda.yaml": "trade_regions_2025",
        example_dir / "toy_sectors/toy_agriculture.veda.yaml": "single_2025",
        example_dir / "toy_sectors/toy_buildings.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_electricity_2ts.veda.yaml": "electricity_2node_2025",
        example_dir
        / "toy_sectors/toy_electricity_4ts.veda.yaml": "electricity_4node_2025",
        example_dir / "toy_sectors/toy_industry.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_industry_switch_base.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_industry_switch_cap_loose.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_industry_switch_cap_mid.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_industry_switch_cap_tight.veda.yaml": "single_2025",
        example_dir
        / "toy_sectors/toy_industry_switch_high_gas_price.veda.yaml": "single_2025",
        (
            example_dir
            / "toy_sectors/toy_industry_switch_high_gas_price_cap_mid.veda.yaml"
        ): "single_2025",
        (
            example_dir
            / "toy_sectors/toy_industry_switch_high_h2_price_cap_mid.veda.yaml"
        ): "single_2025",
        example_dir / "toy_sectors/toy_integrated_6sector.veda.yaml": "integrated_2025",
        example_dir / "toy_sectors/toy_resources.veda.yaml": "single_2025",
        example_dir / "toy_sectors/toy_transport.veda.yaml": "single_2025",
        example_dir / "minisystem/minisystem1.veda.yaml": "single_2020",
        example_dir / "minisystem/minisystem2.veda.yaml": "single_2020",
        example_dir / "minisystem/minisystem3.veda.yaml": "single_2025",
        example_dir / "minisystem/minisystem4.veda.yaml": "single_2025",
        example_dir / "minisystem/minisystem5.veda.yaml": "single_2025",
        example_dir / "minisystem/minisystem6.veda.yaml": "single_2020",
        example_dir / "minisystem/minisystem7.veda.yaml": "north_south_2025",
        example_dir / "minisystem/minisystem8.veda.yaml": "australia_2025",
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
        assert bundle.tableir["dsl_version"] == "0.3"
