"""Tests for the v0.3-only VedaLang Language Server."""

from lsprotocol import types

from tools.vedalang_lsp.server.schema_docs import SCHEMA_FIELD_DOCS
from tools.vedalang_lsp.server.server import (
    ATTR_MASTER,
    SEMANTIC_TO_TIMES,
    SymbolDef,
    find_definition_range,
    format_commodity_hover,
    format_process_hover,
    format_times_attribute_hover,
    format_vedalang_attribute_hover,
    get_word_at_position,
    get_yaml_key_at_position,
    parse_and_index,
    schema_for_key_at_position,
    schema_for_path,
    server,
    validate_document,
)


class MockTextDocument:
    """Mock TextDocument for testing."""

    def __init__(self, source: str, uri: str = "file:///test.veda.yaml"):
        self.source = source
        self.uri = uri
        self.lines = source.splitlines(keepends=True)
        if source and not source.endswith("\n"):
            self.lines[-1] = self.lines[-1] if self.lines else ""


SAMPLE_MODEL = """dsl_version: "0.3"
commodities:
  - id: electricity
    type: energy
    energy_form: secondary
    description: Electricity
  - id: space_heat
    type: service
    description: Useful heat
technologies:
  - id: heat_pump
    description: Electric heat pump
    provides: space_heat
    inputs:
      - commodity: electricity
    performance:
      kind: cop
      value: 3.2
    lifetime: 18 year
technology_roles:
  - id: space_heat_supply
    primary_service: space_heat
    technologies: [heat_pump]
sites:
  - id: reg1_home
    location:
      point:
        lat: -33.86
        lon: 151.21
    membership_overrides:
      region_partitions:
        reg1_partition: REG1
facilities:
  - id: reg1_heat
    site: reg1_home
    technology_role: space_heat_supply
    stock:
      items:
        - technology: heat_pump
          metric: installed_capacity
          observed:
            value: 10 kW
            year: 2025
runs:
  - id: reg1_2025
    base_year: 2025
    currency_year: 2024
    region_partition: reg1_partition
region_partitions:
  - id: reg1_partition
    layer: geo.demo
    members: [REG1]
    mapping:
      kind: constant
      value: REG1
spatial_layers:
  - id: geo.demo
    kind: polygon
    key: region_id
    geometry_file: data/regions.geojson
"""


class TestHoverFormatting:
    def test_format_vedalang_attribute_hover(self):
        content = format_vedalang_attribute_hover("efficiency")
        assert content is not None
        assert "efficiency" in content
        assert "ACT_EFF" in content

    def test_schema_field_docs_loaded(self):
        assert len(SCHEMA_FIELD_DOCS) >= 30
        assert "commodities" in SCHEMA_FIELD_DOCS
        assert "technologies" in SCHEMA_FIELD_DOCS
        assert "technology_roles" in SCHEMA_FIELD_DOCS
        assert "runs" in SCHEMA_FIELD_DOCS
        assert "model" not in SCHEMA_FIELD_DOCS
        assert "processes" not in SCHEMA_FIELD_DOCS
        assert "constraints" not in SCHEMA_FIELD_DOCS
        assert "scenario_parameters" not in SCHEMA_FIELD_DOCS
        assert "primary_commodity_group" not in SCHEMA_FIELD_DOCS
        assert "trade_links" not in SCHEMA_FIELD_DOCS

    def test_format_times_attribute_hover(self):
        if "NCAP_COST" in ATTR_MASTER:
            attr_data = ATTR_MASTER["NCAP_COST"]
            content = format_times_attribute_hover("NCAP_COST", attr_data)
            assert "NCAP_COST" in content
            assert "Indexes" in content or len(content) > 50

    def test_format_commodity_hover(self):
        sym = SymbolDef(
            kind="commodity",
            name="electricity",
            uri="file:///test.yaml",
            range=types.Range(
                start=types.Position(line=0, character=0),
                end=types.Position(line=0, character=21),
            ),
            data={
                "id": "electricity",
                "type": "energy",
                "energy_form": "secondary",
                "unit": "PJ",
                "description": "Electricity",
            },
        )
        content = format_commodity_hover(sym)
        assert "electricity" in content
        assert "energy" in content
        assert "secondary" in content
        assert "PJ" in content
        assert "Electricity" in content

    def test_format_process_hover_aliases_to_technology(self):
        sym = SymbolDef(
            kind="technology",
            name="heat_pump",
            uri="file:///test.yaml",
            range=types.Range(
                start=types.Position(line=0, character=0),
                end=types.Position(line=0, character=9),
            ),
            data={
                "id": "heat_pump",
                "description": "Electric heat pump",
                "provides": "space_heat",
                "inputs": [{"commodity": "electricity"}],
                "performance": {"kind": "cop", "value": 3.2},
                "lifetime": "18 year",
            },
        )
        content = format_process_hover(sym)
        assert "Technology `heat_pump`" in content
        assert "Electric heat pump" in content
        assert "space_heat" in content


class TestWordExtraction:
    def test_get_word_at_position(self):
        doc = MockTextDocument("  performance: 3.2")
        pos = types.Position(line=0, character=5)
        assert get_word_at_position(doc, pos) == "performance"

    def test_get_yaml_key_at_position(self):
        doc = MockTextDocument("  provides: service:space_heat")
        pos = types.Position(line=0, character=5)
        assert get_yaml_key_at_position(doc, pos) == "provides"


class TestSchemaLookup:
    def test_schema_for_path_resolves_public_arrays(self):
        node = schema_for_path(["technologies", 0, "inputs", 0, "commodity"])
        assert node is not None

    def test_schema_for_key_at_position_uses_public_schema(self):
        doc = MockTextDocument(SAMPLE_MODEL)
        line = next(i for i, text in enumerate(doc.lines) if "provides:" in text)
        pos = types.Position(line=line, character=4)
        schema_path, schema_node = schema_for_key_at_position(doc, pos, "provides")
        assert schema_path is not None
        assert schema_node is not None


class TestIndexingAndDiagnostics:
    def test_parse_and_index_collects_public_symbols(self):
        doc = MockTextDocument(SAMPLE_MODEL)
        parsed = parse_and_index(server, doc)
        assert parsed is not None

        symtab = server.symbols[doc.uri]
        assert "electricity" in symtab["commodity"]
        assert "heat_pump" in symtab["technology"]
        assert "space_heat_supply" in symtab["technology_role"]
        assert "reg1_home" in symtab["site"]
        assert "reg1_heat" in symtab["facility"]

        refs = server.references[doc.uri]
        assert any(
            ref.kind == "commodity" and ref.name == "electricity"
            for ref in refs
        )
        assert any(ref.kind == "technology" and ref.name == "heat_pump" for ref in refs)

    def test_find_definition_range_supports_public_ids(self):
        doc = MockTextDocument(SAMPLE_MODEL)
        rng = find_definition_range(doc, "technology", "heat_pump")
        assert rng.start.line >= 0
        assert rng.end.character > rng.start.character

    def test_validate_document_accepts_valid_public_source(self):
        doc = MockTextDocument(SAMPLE_MODEL)
        diagnostics = validate_document(server, doc)
        errors = [
            d for d in diagnostics if d.severity == types.DiagnosticSeverity.Error
        ]
        assert errors == []

    def test_validate_document_rejects_legacy_source(self):
        legacy = MockTextDocument(
            "model:\n  name: Legacy\n  regions: [R1]\n  commodities: []\nroles: []\n"
        )
        diagnostics = validate_document(server, legacy)
        assert diagnostics
        assert all(d.source == "vedalang-schema" for d in diagnostics)
        assert all("Schema validation:" in d.message for d in diagnostics)

    def test_validate_document_surfaces_public_semantic_errors(self):
        invalid = MockTextDocument(
            """dsl_version: "0.3"
commodities:
  - id: electricity
    type: energy
    energy_form: secondary
technologies:
  - id: bad_tech
    provides: electricity
technology_roles:
  - id: bad_role
    primary_service: electricity
    technologies: [bad_tech]
runs:
  - id: reg1
    base_year: 2025
    currency_year: 2024
    region_partition: reg1_partition
region_partitions:
  - id: reg1_partition
    layer: geo.demo
    members: [REG1]
    mapping:
      kind: constant
      value: REG1
spatial_layers:
  - id: geo.demo
    kind: polygon
    key: region_id
    geometry_file: data/regions.geojson
"""
        )
        diagnostics = validate_document(server, invalid)
        assert any(d.code == "E004" for d in diagnostics)


def test_semantic_to_times_mapping_still_exposes_core_attributes():
    assert SEMANTIC_TO_TIMES["efficiency"] == "ACT_EFF"
    assert SEMANTIC_TO_TIMES["investment_cost"] == "NCAP_COST"
