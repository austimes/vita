"""Schema contract tests for the v0.2 hard cut."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "vedalang" / "schema" / "vedalang.schema.json"
LEGACY_SCHEMA_PATH = (
    PROJECT_ROOT / "vedalang" / "schema" / "vedalang.legacy.schema.json"
)


def load_schema(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


EXPECTED_V0_2_TOP_LEVEL_PROPERTIES = {
    "dsl_version",
    "imports",
    "commodities",
    "technologies",
    "technology_roles",
    "stock_characterizations",
    "spatial_layers",
    "spatial_measure_sets",
    "temporal_index_series",
    "region_partitions",
    "zone_overlays",
    "sites",
    "facilities",
    "fleets",
    "opportunities",
    "networks",
    "runs",
}

LEGACY_TOP_LEVEL_PROPERTIES = {
    "model",
    "roles",
    "variants",
    "availability",
    "process_parameters",
    "demands",
    "providers",
}


class TestV0_2SchemaContract:
    """Verify the current public schema matches the v0.2 DSL surface."""

    @classmethod
    def setup_class(cls) -> None:
        cls.schema = load_schema(SCHEMA_PATH)

    def test_dsl_version_property_is_const_v0_2(self) -> None:
        dsl_version = self.schema["properties"]["dsl_version"]
        assert dsl_version["const"] == "0.2"

    def test_v0_2_top_level_properties_exist(self) -> None:
        current_properties = set(self.schema.get("properties", {}))
        missing = EXPECTED_V0_2_TOP_LEVEL_PROPERTIES - current_properties
        assert not missing, f"Missing v0.2 top-level properties: {sorted(missing)}"

    def test_legacy_top_level_properties_are_absent(self) -> None:
        current_properties = set(self.schema.get("properties", {}))
        unexpected = LEGACY_TOP_LEVEL_PROPERTIES & current_properties
        assert not unexpected, (
            "Legacy public top-level properties leaked into v0.2 schema: "
            f"{sorted(unexpected)}"
        )

    def test_current_schema_definitions_cover_v0_2_object_families(self) -> None:
        defs = self.schema.get("$defs", {})
        for definition in [
            "commodity",
            "technology",
            "technology_role",
            "stock_characterization",
            "flow_spec",
            "spatial_layer",
            "region_partition",
            "site",
            "facility",
            "fleet",
            "opportunity",
            "network",
            "run",
            "temporal_index_series",
            "zone_overlay",
        ]:
            assert definition in defs, f"Missing v0.2 definition: {definition}"

    def test_legacy_public_definitions_are_absent_from_v0_2_schema(self) -> None:
        defs = self.schema.get("$defs", {})
        for definition in [
            "process_role",
            "process_variant",
            "flow",
            "scenario_parameter",
            "timeslices",
            "timeslice_level",
            "scoping",
            "availability_entry",
            "process_parameter",
            "demand",
        ]:
            assert definition not in defs, (
                f"Legacy definition {definition} should not be present in v0.2 schema"
            )

    def test_required_fields_for_core_v0_2_objects(self) -> None:
        defs = self.schema["$defs"]
        assert defs["commodity"]["required"] == ["id", "kind"]
        assert defs["technology"]["required"] == ["id", "provides"]
        assert defs["technology_role"]["required"] == [
            "id",
            "primary_service",
            "technologies",
        ]
        assert defs["flow_spec"]["required"] == ["commodity"]
        assert defs["run"]["required"] == [
            "id",
            "base_year",
            "currency_year",
            "region_partition",
        ]

    def test_required_fields_for_spatial_and_asset_objects(self) -> None:
        defs = self.schema["$defs"]
        assert defs["site"]["required"] == ["id", "location"]
        assert defs["facility"]["required"] == ["id", "site", "technology_role"]
        assert defs["fleet"]["required"] == ["id", "technology_role", "distribution"]
        assert defs["opportunity"]["required"] == [
            "id",
            "technology",
            "siting",
            "max_new_capacity",
        ]
        assert defs["network"]["required"] == ["id", "kind", "node_basis", "links"]

    def test_commodity_kind_enum_matches_v0_2_namespaces(self) -> None:
        enum_values = self.schema["$defs"]["commodity"]["properties"]["kind"]["enum"]
        assert enum_values == [
            "primary",
            "secondary",
            "service",
            "emission",
            "material",
            "certificate",
        ]

    def test_flow_basis_stays_explicit(self) -> None:
        basis = self.schema["$defs"]["flow_spec"]["properties"]["basis"]
        assert basis["type"] == "string"
        assert basis["enum"] == ["HHV", "LHV"]


class TestLegacySchemaIsolation:
    """Verify the legacy schema remains available only for deterministic rejection."""

    @classmethod
    def setup_class(cls) -> None:
        cls.legacy_schema = load_schema(LEGACY_SCHEMA_PATH)

    def test_legacy_schema_still_recognizes_legacy_root(self) -> None:
        assert self.legacy_schema.get("required") == ["model"]

    def test_legacy_schema_retains_removed_public_surface(self) -> None:
        legacy_properties = set(self.legacy_schema.get("properties", {}))
        missing = LEGACY_TOP_LEVEL_PROPERTIES - legacy_properties
        assert not missing, (
            "Legacy compatibility schema lost expected public properties: "
            f"{sorted(missing)}"
        )

    def test_legacy_schema_retains_removed_type_definitions(self) -> None:
        defs = self.legacy_schema.get("$defs", {})
        for definition in [
            "process_role",
            "process_variant",
            "flow",
            "scenario_parameter",
            "timeslices",
            "timeslice_level",
            "scoping",
            "availability_entry",
            "process_parameter",
            "demand",
        ]:
            assert definition in defs, (
                f"Legacy compatibility schema lost definition: {definition}"
            )
