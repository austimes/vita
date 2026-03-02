"""Tests for VEDA table schema validation."""

from pathlib import Path

from vedalang.compiler.table_schemas import (
    VedaFieldSchema,
    VedaTableLayout,
    VedaTableSchema,
    get_all_schemas,
    load_attribute_master,
    load_veda_tags_schemas,
    validate_table_rows,
    validate_tableir,
)

PROJECT_ROOT = Path(__file__).parent.parent
VEDA_TAGS_PATH = PROJECT_ROOT / "xl2times" / "config" / "veda-tags.json"


class TestLoadVedaTagsSchemas:
    """Tests for loading schemas from veda-tags.json."""

    def test_load_veda_tags_schemas_returns_dict(self):
        """Should return a dict of schemas."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        assert isinstance(schemas, dict)
        assert len(schemas) > 0

    def test_fi_t_schema_exists(self):
        """FI_T is a common tag and should be present."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        assert "fi_t" in schemas
        schema = schemas["fi_t"]
        assert schema.tag_name == "fi_t"

    def test_fi_comm_schema_has_required_commodity_field(self):
        """FI_COMM requires commname field."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        assert "fi_comm" in schemas
        schema = schemas["fi_comm"]

        # commname (commodity) is marked remove_any_row_if_absent: true
        assert "commodity" in schema.fields
        assert schema.fields["commodity"].required
        # Required column should be in required_columns set
        assert "commodity" in schema.required_columns

    def test_canonical_header_set_correctly(self):
        """Each field should have a canonical_header (lowercase use_name)."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # attribute field should have canonical_header set
        attr_field = fi_t.fields.get("attribute")
        assert attr_field is not None
        assert attr_field.canonical_header == "attribute"

    def test_allowed_columns_includes_canonical_and_aliases(self):
        """allowed_columns contains canonical names and their aliases."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # Should have canonical names (use_name from veda-tags.json)
        # Note: veda-tags.json uses 'process' as use_name for techname
        assert "attribute" in fi_t.allowed_columns
        assert "process" in fi_t.allowed_columns  # canonical for techname
        assert "commodity" in fi_t.allowed_columns  # canonical for commname
        # Aliases ARE also allowed (xl2times accepts them)
        assert "parameter" in fi_t.allowed_columns  # alias for attribute
        assert "techname" in fi_t.allowed_columns  # alias for process

    def test_valid_values_extracted(self):
        """valid_values should be extracted from veda-tags.json."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        uc_t = schemas.get("uc_t")

        if uc_t:
            # top_check has valid_values: ["A", "I", "O", "NO"]
            top_check = uc_t.fields.get("top_check")
            if top_check:
                assert top_check.valid_values is not None
                assert "A" in top_check.valid_values
                assert "I" in top_check.valid_values

    def test_multi_valued_fields_marked(self):
        """Fields with comma-separated-list: true should be multi_valued."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        fi_comm = schemas["fi_comm"]

        # region field has comma-separated-list: true
        region_field = fi_comm.fields.get("region")
        assert region_field is not None
        assert region_field.multi_valued

    def test_query_fields_marked(self):
        """Fields with query_field: true should be marked."""
        schemas = load_veda_tags_schemas(VEDA_TAGS_PATH)
        uc_t = schemas.get("uc_t")

        if uc_t:
            # pset_pn is a query field
            pset_pn = uc_t.fields.get("pset_pn")
            if pset_pn:
                assert pset_pn.query_field


class TestManualLayouts:
    """Tests for manual layout overlays."""

    def test_fi_t_layout_applied(self):
        """FI_T should have wide layout with attributes as column headers."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        assert fi_t.layout.kind == "wide"
        assert "process" in fi_t.layout.index_fields

    def test_fi_t_allows_value_with_attribute(self):
        """FI_T should allow 'value' column when 'attribute' column is present.

        This enables long-format attribute rows (e.g., ENV_ACT) within ~FI_T.
        """
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # ~FI_T now allows value column for attribute-based rows
        assert fi_t.layout.allow_value_column is True
        assert "value" in fi_t.allowed_columns
        assert "attribute" in fi_t.allowed_columns

    def test_fi_comm_layout_applied(self):
        """FI_COMM should have wide layout."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_comm = schemas["fi_comm"]

        assert fi_comm.layout.kind == "wide"

    def test_tfm_dins_at_variant_created(self):
        """TFM_DINS-AT variant should be created with forbidden value column."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)

        if "tfm_dins-at" in schemas:
            dins_at = schemas["tfm_dins-at"]
            assert dins_at.variant == "at"
            assert dins_at.layout.allow_value_column is False
            assert "value" in dins_at.forbidden_headers

    def test_uc_t_mutually_exclusive_groups(self):
        """UC_T should have mutually exclusive query field groups."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        uc_t = schemas.get("uc_t")

        if uc_t:
            # Should have commodity query fields as mutually exclusive
            assert len(uc_t.mutually_exclusive_groups) > 0

    def test_fi_t_require_any_of_loaded(self):
        """FI_T should have require_any_of rules from constraints.yaml."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # Should have at least one require_any_of group
        assert len(fi_t.require_any_of) > 0


class TestValidateTableRows:
    """Tests for row-level validation."""

    def test_missing_required_column_reported(self):
        """Missing required columns should be reported."""
        schema = VedaTableSchema(
            tag_name="test",
            required_columns={"required_col"},
            allowed_columns={"required_col", "other_col"},
        )

        rows = [{"other_col": "value"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "missing required column" in errors[0]
        assert "required_col" in errors[0]

    def test_required_column_present_no_error(self):
        """Present required columns should not cause errors."""
        schema = VedaTableSchema(
            tag_name="test",
            required_columns={"required_col"},
            allowed_columns={"required_col"},
        )

        rows = [{"required_col": "value"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 0

    def test_unknown_column_reported(self):
        """Unknown columns should be reported as errors."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"commodity", "process", "region"},
        )

        rows = [{"comodity": "ELC"}]  # Typo
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "unknown column 'comodity'" in errors[0]
        assert "commodity" in errors[0]  # Suggestion

    def test_invalid_enum_value_reported(self):
        """Invalid enum values should be reported."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"top_check"},
            fields={
                "top_check": VedaFieldSchema(
                    name="top_check",
                    canonical_header="top_check",
                    valid_values={"A", "I", "O"},
                ),
            },
        )

        rows = [{"top_check": "INVALID"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "invalid value 'INVALID'" in errors[0]
        assert "A, I, O" in errors[0]

    def test_valid_enum_value_no_error(self):
        """Valid enum values should not cause errors."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"top_check"},
            fields={
                "top_check": VedaFieldSchema(
                    name="top_check",
                    canonical_header="top_check",
                    valid_values={"A", "I", "O"},
                ),
            },
        )

        rows = [{"top_check": "A"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 0

    def test_forbidden_header_reported(self):
        """Forbidden headers should be reported."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"value", "process"},
            forbidden_headers={"value", "attribute"},
        )

        rows = [{"value": 100, "process": "PP"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "forbidden column 'value'" in errors[0]

    def test_value_column_blocked_when_allow_value_column_false(self):
        """'value' column should be blocked when allow_value_column=False."""
        schema = VedaTableSchema(
            tag_name="fi_t",
            allowed_columns={"region", "techname", "value"},
            layout=VedaTableLayout(
                kind="long",
                index_fields=["region", "techname"],
                allow_value_column=False,
            ),
        )

        rows = [{"region": "R1", "techname": "PP", "value": 100}]
        errors = validate_table_rows("~FI_T", rows, schema)

        assert len(errors) == 1
        assert "'value' column not allowed" in errors[0]

    def test_require_any_of_reported(self):
        """Missing require_any_of groups should be reported."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"region", "techname", "comm_in", "comm_out"},
            require_any_of=[{"comm_in", "comm_out"}],
        )

        rows = [{"region": "R1", "techname": "PP"}]  # Missing comm_in/comm_out
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "must have at least one of" in errors[0]
        assert "comm_in" in errors[0]
        assert "comm_out" in errors[0]

    def test_require_any_of_satisfied(self):
        """Rows with at least one of require_any_of should pass."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"region", "techname", "comm_in", "comm_out"},
            require_any_of=[{"comm_in", "comm_out"}],
        )

        rows = [{"region": "R1", "techname": "PP", "comm_in": "NG"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 0

    def test_mutually_exclusive_fields_reported(self):
        """Mutually exclusive fields used together should be reported."""
        schema = VedaTableSchema(
            tag_name="test",
            allowed_columns={"cset_cd", "cset_cn"},
            fields={
                "cset_cd": VedaFieldSchema(
                    name="cset_cd",
                    canonical_header="cset_cd",
                ),
                "cset_cn": VedaFieldSchema(
                    name="cset_cn",
                    canonical_header="cset_cn",
                ),
            },
            mutually_exclusive_groups=[{"cset_cd", "cset_cn"}],
        )

        rows = [{"cset_cd": "NRG", "cset_cn": "ELC"}]
        errors = validate_table_rows("~TEST", rows, schema)

        assert len(errors) == 1
        assert "mutually exclusive" in errors[0]


class TestValidateTableIR:
    """Tests for full TableIR validation."""

    def test_valid_tableir_passes(self):
        """Valid TableIR should pass validation."""
        tableir = {
            "files": [
                {
                    "path": "base/base.xlsx",
                    "sheets": [
                        {
                            "name": "Base",
                            "tables": [
                                {
                                    "tag": "~FI_COMM",
                                    "rows": [
                                        {
                                            "commodity": "ELC",
                                            "csets": "NRG",
                                            "region": "R1",
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        schemas = get_all_schemas(VEDA_TAGS_PATH)
        errors = validate_tableir(tableir, schemas)

        assert len(errors) == 0

    def test_missing_required_in_tableir_reported(self):
        """Missing required fields in TableIR should be reported with context."""
        tableir = {
            "files": [
                {
                    "path": "base/test.xlsx",
                    "sheets": [
                        {
                            "name": "TestSheet",
                            "tables": [
                                {
                                    "tag": "~FI_COMM",
                                    "rows": [
                                        {"csets": "NRG"},  # Missing commodity
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        schemas = get_all_schemas(VEDA_TAGS_PATH)
        errors = validate_tableir(tableir, schemas)

        assert len(errors) >= 1
        # Should report missing required column
        assert any("commodity" in e for e in errors)

    def test_unknown_tag_skipped(self):
        """Unknown tags should be silently skipped."""
        tableir = {
            "files": [
                {
                    "path": "base/base.xlsx",
                    "sheets": [
                        {
                            "name": "Base",
                            "tables": [
                                {
                                    "tag": "~UNKNOWN_TAG",
                                    "rows": [{"anything": "goes"}],
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        errors = validate_tableir(tableir)
        assert len(errors) == 0

    def test_multiple_errors_collected(self):
        """Multiple validation errors should all be collected."""
        tableir = {
            "files": [
                {
                    "path": "base/base.xlsx",
                    "sheets": [
                        {
                            "name": "Base",
                            "tables": [
                                {
                                    "tag": "~FI_COMM",
                                    "rows": [
                                        {"csets": "NRG"},  # Missing commodity
                                        {"csets": "MAT"},  # Missing commodity
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        schemas = get_all_schemas(VEDA_TAGS_PATH)
        errors = validate_tableir(tableir, schemas)

        # Should have errors for missing commodity in both rows
        assert len(errors) >= 2


class TestIntegrationWithCompiler:
    """Integration tests with actual compiled output."""

    def test_mini_plant_tableir_validates(self):
        """TableIR from quickstart/mini_plant.veda.yaml validates."""
        from vedalang.compiler.compiler import (
            compile_vedalang_to_tableir,
            load_vedalang,
        )
        from vedalang.compiler.table_schemas import validate_tableir

        vedalang_path = (
            Path(__file__).parent.parent
            / "vedalang"
            / "examples"
            / "quickstart/mini_plant.veda.yaml"
        )
        source = load_vedalang(vedalang_path)
        tableir = compile_vedalang_to_tableir(source)
        errors = validate_tableir(tableir)

        assert errors == [], f"Validation errors: {errors}"


class TestAttributeMaster:
    """Tests for attribute master integration."""

    def test_attribute_master_loads(self):
        """attribute-master.json should load successfully."""
        attrs = load_attribute_master()
        assert len(attrs) > 0
        assert "ACT_BND" in attrs
        assert attrs["ACT_BND"]["column_header"] == "act_bnd"

    def test_attribute_master_has_common_attributes(self):
        """Common VEDA attributes should be present."""
        attrs = load_attribute_master()
        # Use canonical VEDA attribute names (uppercase)
        expected = [
            "ACT_BND", "CAP_BND", "NCAP_BND", "ACT_COST",
            "NCAP_COST", "NCAP_FOM", "COM_PROJ", "EFF",  # COM_PROJ has alias "DEMAND"
        ]
        for name in expected:
            assert name in attrs, f"Missing expected attribute: {name}"

    def test_attribute_master_includes_aliases_in_column_headers(self):
        """column_headers should include both canonical name and aliases."""
        attrs = load_attribute_master()

        # NCAP_COST has alias INVCOST
        assert "NCAP_COST" in attrs
        headers = attrs["NCAP_COST"].get("column_headers", [])
        assert "ncap_cost" in headers
        assert "invcost" in headers

        # COM_PROJ has alias DEMAND
        assert "COM_PROJ" in attrs
        headers = attrs["COM_PROJ"].get("column_headers", [])
        assert "com_proj" in headers
        assert "demand" in headers

    def test_fi_t_has_canonical_attribute_columns_only(self):
        """FI_T allowed_columns should include ONLY canonical attribute headers."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # Check that canonical attribute columns are allowed
        assert "com_proj" in fi_t.allowed_columns  # canonical for COM_PROJ
        assert "eff" in fi_t.allowed_columns
        assert "act_bnd" in fi_t.allowed_columns
        assert "ncap_cost" in fi_t.allowed_columns

        # Aliases should NOT be in allowed_columns (canonical-only enforcement)
        assert "demand" not in fi_t.allowed_columns  # alias for com_proj
        assert "invcost" not in fi_t.allowed_columns  # alias for ncap_cost
        assert "varom" not in fi_t.allowed_columns  # alias for act_cost
        assert "fixom" not in fi_t.allowed_columns  # alias for ncap_fom
        assert "life" not in fi_t.allowed_columns  # alias for ncap_tlife

    def test_tfm_dins_at_has_attribute_columns_from_master(self):
        """TFM_DINS-AT allowed_columns should include attribute headers."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        dins_at = schemas.get("tfm_dins-at")

        if dins_at:
            assert "com_cstnet" in dins_at.allowed_columns
            assert "ncap_cost" in dins_at.allowed_columns

    def test_compiler_emitted_attributes_are_canonical_or_whitelisted(self):
        """Attributes emitted by compiler should be canonical, with some exceptions.

        Most attributes must use canonical VEDA column headers. However, 'cost'
        is an intentional exception: xl2times handles the COST -> IRE_PRICE
        transformation specially for IMP/EXP processes (populating other_indexes).
        Using the canonical 'ire_price' header would bypass this logic.
        """
        from vedalang.compiler.compiler import ATTR_TO_COLUMN

        attrs = load_attribute_master()
        # Only canonical column headers (no aliases)
        canonical_headers: set[str] = set()
        for meta in attrs.values():
            canonical = meta.get("column_header", "")
            if canonical:
                canonical_headers.add(canonical.lower())

        # 'cost' is allowed because xl2times only handles COST -> IRE_PRICE correctly
        whitelisted_aliases = {"cost"}

        # Columns the compiler emits - must all be canonical or whitelisted
        emitted_headers = {col.lower() for col in ATTR_TO_COLUMN.values()}
        # Plus other attribute columns used in compiler output
        emitted_headers.update({"com_proj", "com_cstnet"})  # canonical names

        missing = emitted_headers - canonical_headers - whitelisted_aliases
        assert not missing, f"Compiler emits non-canonical attributes: {missing}"

    def test_compiler_attr_mappings_use_valid_veda_names(self):
        """ATTR_TO_COLUMN values must be valid VEDA attribute headers.

        Most should be canonical, but 'cost' is whitelisted because xl2times
        only handles COST -> IRE_PRICE transformation correctly with the alias.
        """
        from vedalang.compiler.compiler import ATTR_TO_COLUMN

        attrs = load_attribute_master()
        # Canonical column headers
        canonical_headers: set[str] = set()
        for meta in attrs.values():
            canonical = meta.get("column_header", "")
            if canonical:
                canonical_headers.add(canonical.lower())

        # 'cost' is a whitelisted alias for xl2times compatibility
        whitelisted_aliases = {"cost"}
        valid_headers = canonical_headers | whitelisted_aliases

        for vedalang_name, column in ATTR_TO_COLUMN.items():
            assert column.lower() in valid_headers, (
                f"ATTR_TO_COLUMN['{vedalang_name}'] = '{column}' "
                f"is not a valid VEDA attribute column"
            )

    def test_alias_column_rejected_with_helpful_message(self):
        """Alias columns should be rejected with 'use canonical X' error."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # Use an alias column (demand is alias for com_proj)
        # Include eff to satisfy require_any_of constraint
        rows = [{"region": "R1", "process": "PP", "eff": 0.5, "demand": 100}]
        errors = validate_table_rows("~FI_T", rows, fi_t)

        # Should get exactly one error about the alias
        assert len(errors) == 1
        assert "'demand' is an alias column" in errors[0]
        assert "Use canonical name 'com_proj'" in errors[0]

    def test_multiple_aliases_rejected(self):
        """Multiple alias columns should each produce separate errors."""
        schemas = get_all_schemas(VEDA_TAGS_PATH)
        fi_t = schemas["fi_t"]

        # Use multiple alias columns
        # Include eff to satisfy require_any_of constraint
        rows = [
            {"region": "R1", "process": "PP", "eff": 0.5, "demand": 100, "invcost": 500}
        ]
        errors = validate_table_rows("~FI_T", rows, fi_t)

        # Should get errors for both aliases
        assert len(errors) == 2
        demand_error = [e for e in errors if "demand" in e][0]
        invcost_error = [e for e in errors if "invcost" in e][0]
        assert "Use canonical name 'com_proj'" in demand_error
        assert "Use canonical name 'ncap_cost'" in invcost_error
