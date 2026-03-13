"""Tests for TIMES GDX result extraction helpers."""

from unittest.mock import patch

import pytest

from tools.veda_dev.times_results import extract_results


@patch("tools.veda_dev.times_results.dump_symbol_csv")
@patch("tools.veda_dev.times_results.find_gdxdump")
def test_extract_results_handles_header_variants(
    mock_find,
    mock_dump,
    tmp_path,
):
    """Extraction supports common gdxdump header variants."""
    mock_find.return_value = "/usr/bin/gdxdump"

    symbol_csv = {
        "OBJZ": '"Value"\n"1.2345D+03"',
        "VAR_OBJ": (
            '"Component","Level"\n'
            '"COST_NPV",1000\n'
            '"CARBON",234.5'
        ),
        "VAR_ACT": (
            '"REGION","YEAR","PROCESS","TIMESLICE","LEVEL"\n'
            '"R1","2030","CCGT_A","ANNUAL",80\n'
            '"R2","2040","CCGT_B","ANNUAL",0'
        ),
        "VAR_NCAP": (
            '"reg","yr","prc","value"\n'
            '"R1","2030","CCGT_A",10'
        ),
        "VAR_CAP": (
            '"R","DATAYEAR","P","L"\n'
            '"R1","2030","CCGT_A",95'
        ),
        "VAR_FLO": (
            '"Reg","Data Year","PRC","Commodity","TS","Value"\n'
            '"R1","2030","CCGT_A","ELC","ANNUAL",120'
        ),
    }

    def _mock_dump(_gdx_path, symbol, _gdxdump):
        return symbol_csv.get(symbol)

    mock_dump.side_effect = _mock_dump

    gdx_path = tmp_path / "scenario.gdx"
    gdx_path.touch()

    results = extract_results(gdx_path, include_flows=True, limit=None)

    assert not results.errors
    assert results.objective == pytest.approx(1234.5)
    assert results.objective_breakdown == {
        "COST_NPV": pytest.approx(1000.0),
        "CARBON": pytest.approx(234.5),
    }

    assert results.var_act == [
        {
            "region": "R1",
            "vintage": "2030",
            "year": "2030",
            "process": "CCGT_A",
            "timeslice": "ANNUAL",
            "level": 80.0,
        }
    ]
    assert results.var_ncap == [
        {
            "region": "R1",
            "year": "2030",
            "process": "CCGT_A",
            "level": 10.0,
        }
    ]
    assert results.var_cap == [
        {
            "region": "R1",
            "year": "2030",
            "process": "CCGT_A",
            "level": 95.0,
        }
    ]
    assert results.var_flo == [
        {
            "region": "R1",
            "year": "2030",
            "process": "CCGT_A",
            "commodity": "ELC",
            "timeslice": "ANNUAL",
            "level": 120.0,
        }
    ]


@patch("tools.veda_dev.times_results.dump_symbol_csv")
@patch("tools.veda_dev.times_results.find_gdxdump")
def test_extract_results_limit_zero_disables_truncation(
    mock_find,
    mock_dump,
    tmp_path,
):
    """limit<=0 returns full row sets for deterministic test assertions."""
    mock_find.return_value = "/usr/bin/gdxdump"

    var_act_csv = (
        '"R","ALLYEAR","P","S","Val"\n'
        '"R1","2020","P1","ANNUAL",10\n'
        '"R1","2020","P2","ANNUAL",20\n'
        '"R1","2020","P3","ANNUAL",30'
    )

    def _mock_dump(_gdx_path, symbol, _gdxdump):
        if symbol == "VAR_ACT":
            return var_act_csv
        return None

    mock_dump.side_effect = _mock_dump

    gdx_path = tmp_path / "scenario.gdx"
    gdx_path.touch()

    limited = extract_results(gdx_path, limit=2)
    unlimited = extract_results(gdx_path, limit=0)

    assert [row["process"] for row in limited.var_act] == ["P3", "P2"]
    assert [row["process"] for row in unlimited.var_act] == ["P3", "P2", "P1"]
