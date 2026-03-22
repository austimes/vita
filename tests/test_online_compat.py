"""Tests for VEDA Online compatibility validation."""

import tempfile
from pathlib import Path

import pytest

from tools.veda_emit_excel import emit_excel
from vedalang.compiler.online_compat import validate_online_compat


def _make_tableir(tables: list[dict], *, path: str = "test.xlsx", sheet_name: str = "Sheet1") -> dict:
    """Helper to wrap tables in minimal TableIR structure."""
    return {
        "files": [
            {
                "path": path,
                "sheets": [{"name": sheet_name, "tables": tables}],
            }
        ]
    }


class TestScalarTagValidation:
    def test_scalar_tag_with_extra_keys_rejected(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020, "extra": "bad"}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "extra keys" in errors[0]
        assert "extra" in errors[0]

    def test_scalar_tag_wrong_type_rejected(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": "2020"}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "must be int" in errors[0]
        assert "str" in errors[0]

    def test_scalar_tag_valid_passes(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

class TestYearColumnValidation:
    def test_year_column_string_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "year": "2020"}]}
        ], path="VT_TEST_ALL_V1.xlsx")
        errors = validate_online_compat(tableir)
        assert any("'year' must be int" in e for e in errors)

    def test_year_column_null_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "year": None}]}
        ], path="VT_TEST_ALL_V1.xlsx")
        errors = validate_online_compat(tableir)
        assert any("null 'year'" in e for e in errors)

    def test_year_column_int_passes(self):
        tableir = _make_tableir([
            {"tag": "~FI_PROCESS", "rows": [{"PRC": "P1", "year": 2020}]}
        ], path="VT_TEST_ALL_V1.xlsx")
        errors = validate_online_compat(tableir)
        assert errors == []


class TestWideAttributeColumns:
    def test_generic_value_column_rejected(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "value": 100}]}
        ], path="VT_TEST_ALL_V1.xlsx")
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "'value' column" in errors[0]
        assert "wide-attribute" in errors[0]

    def test_value_column_in_dins_at_rejected(self):
        tableir = _make_tableir([
            {"tag": "~TFM_DINS-AT", "rows": [{"PRC": "P1", "value": 100}]}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "'value' column" in errors[0]

    def test_attribute_column_allowed_in_tfm_ins(self):
        tableir = _make_tableir([
            {"tag": "~TFM_INS", "rows": [{"attribute": "YRFR", "allregions": 0.25}]}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

    def test_named_columns_pass(self):
        tableir = _make_tableir([
            {"tag": "~FI_T", "rows": [{"PRC": "P1", "EFF": 0.55}]}
        ], path="VT_TEST_ALL_V1.xlsx")
        errors = validate_online_compat(tableir)
        assert errors == []


class TestUcSetsValidation:
    def test_uc_sets_trailing_colon_rejected(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"T_E": "value:"}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert len(errors) == 1
        assert "trailing colon" in errors[0]

    def test_uc_sets_empty_value_passes(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"T_E": ""}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []

    def test_uc_sets_normal_value_passes(self):
        tableir = _make_tableir([
            {"tag": "~UC_T", "uc_sets": {"R_E": "AllRegions"}, "rows": []}
        ])
        errors = validate_online_compat(tableir)
        assert errors == []


class TestEmitExcelIntegration:
    def test_emit_excel_rejects_invalid_scalar(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020, "extra": "bad"}]}
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="VEDA Online compatibility"):
                emit_excel(tableir, Path(tmpdir))

    def test_emit_excel_accepts_valid_scalar(self):
        tableir = _make_tableir([
            {"tag": "~STARTYEAR", "rows": [{"value": 2020}]}
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            created = emit_excel(tableir, Path(tmpdir))
            assert len(created) == 1


class TestVedaWorkbookContracts:
    def test_syssettings_requires_exact_filename_and_sheet(self):
        tableir = {
            "files": [
                {
                    "path": "syssettings.xlsx",
                    "sheets": [
                        {
                            "name": "SysSets",
                            "tables": [
                                {
                                    "tag": "~BOOKREGIONS_MAP",
                                    "rows": [{"bookname": "AUS", "region": "SINGLE"}],
                                },
                                {
                                    "tag": "~TIMESLICES",
                                    "rows": [{"season": "ANNUAL", "weekly": "", "daynite": ""}],
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        errors = validate_online_compat(tableir)
        assert any("SysSettings workbook path must be exactly 'SysSettings.xlsx'" in e for e in errors)
        assert any("missing required 'Region-Time Slices' sheet" in e for e in errors)

    def test_bookname_must_match_vt_filename(self):
        tableir = {
            "files": [
                {
                    "path": "SysSettings.xlsx",
                    "sheets": [
                        {
                            "name": "Region-Time Slices",
                            "tables": [
                                {
                                    "tag": "~BOOKREGIONS_MAP",
                                    "rows": [{"bookname": "AUS", "region": "SINGLE"}],
                                },
                                {
                                    "tag": "~TIMESLICES",
                                    "rows": [{"season": "ANNUAL", "weekly": "", "daynite": ""}],
                                },
                            ],
                        },
                        {
                            "name": "TimePeriods",
                            "tables": [
                                {"tag": "~STARTYEAR", "rows": [{"value": 2025}]},
                                {
                                    "tag": "~MILESTONEYEARS",
                                    "rows": [
                                        {"type": "milestoneyear", "pathway_2025_2035": 2025},
                                        {"type": "milestoneyear", "pathway_2025_2035": 2035},
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "Defaults",
                            "tables": [{"tag": "~CURRENCIES", "rows": [{"currency": "USD"}]}],
                        },
                    ],
                },
                {
                    "path": "VT_NSW_ALL_V1.xlsx",
                    "sheets": [{"name": "Processes", "tables": [{"tag": "~FI_PROCESS", "rows": []}]}],
                },
            ]
        }
        errors = validate_online_compat(tableir)
        assert any("bookname 'AUS' does not match any VT workbook filename" in e for e in errors)

    def test_timeslices_rejects_an_abbreviation(self):
        tableir = _make_tableir(
            [{"tag": "~TIMESLICES", "rows": [{"season": "AN", "weekly": "", "daynite": ""}]}]
        )
        errors = validate_online_compat(tableir)
        assert any("annual timeslice must be 'ANNUAL'" in e for e in errors)
