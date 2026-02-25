"""Tests for VedaLang compiler."""

import json
from pathlib import Path

import jsonschema
import pytest

from vedalang.compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
)
from vedalang.compiler.compiler import (
    _detect_service_role_duplication,
    _normalize_commodities_for_new_syntax,
)
from vedalang.compiler.ir import build_roles

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
SCHEMA_DIR = PROJECT_ROOT / "vedalang" / "schema"


def test_compile_mini_plant():
    """Compile mini_plant.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have files
    assert "files" in tableir
    assert len(tableir["files"]) >= 1


def test_output_validates_against_tableir_schema():
    """Compiler output must be valid TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    with open(SCHEMA_DIR / "tableir.schema.json") as f:
        schema = json.load(f)

    # Should not raise
    jsonschema.validate(tableir, schema)


def test_commodities_become_fi_comm():
    """Commodities should appear in ~FI_COMM table."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM table
    comm_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_tables.append(t)

    assert len(comm_tables) >= 1
    comm_names = [r.get("commodity") for r in comm_tables[0]["rows"]]
    assert "secondary:electricity" in comm_names
    assert "primary:natural_gas" in comm_names


def test_processes_become_fi_process():
    """Processes should appear in ~FI_PROCESS table."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_PROCESS table
    proc_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    proc_tables.append(t)

    assert len(proc_tables) >= 1
    tech_names = [r.get("process") for r in proc_tables[0]["rows"]]
    # New P4 syntax: process name is {variant}_{region}
    assert "ccgt_REG1" in tech_names


def test_invalid_vedalang_rejected():
    """Invalid VedaLang should raise ValidationError."""
    invalid = {"not_a_model": True}
    with pytest.raises(jsonschema.ValidationError):
        compile_vedalang_to_tableir(invalid)


def test_process_cost_attributes():
    """Process cost attributes should appear in ~FI_T table."""
    source = {
        "model": {
            "name": "CostTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "C:GAS"}],
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                    "investment_cost": 800,
                    "fixed_om_cost": 20,
                    "variable_om_cost": 2,
                    "lifetime": 30,
                },
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:GAS"}],
                    "efficiency": 1.0,
                    "import_price": 5.0,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T table
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find the cost row for PP_CCGT (has eff, ncap_cost, ncap_fom, act_cost, ncap_tlife)
    ccgt_cost_rows = [
        r for r in fit_rows if r.get("process") == "PP_CCGT" and "eff" in r
    ]
    assert len(ccgt_cost_rows) == 1
    ccgt_row = ccgt_cost_rows[0]
    assert ccgt_row["eff"] == 0.55
    assert ccgt_row["ncap_cost"] == 800
    assert ccgt_row["ncap_fom"] == 20
    assert ccgt_row["act_cost"] == 2
    assert ccgt_row["ncap_tlife"] == 30

    # Find the cost row for IMP_NG
    imp_cost_rows = [
        r for r in fit_rows if r.get("process") == "IMP_NG" and "ire_price" in r
    ]
    assert len(imp_cost_rows) == 1
    assert imp_cost_rows[0]["ire_price"] == 5.0
    assert imp_cost_rows[0]["eff"] == 1.0


def test_demand_projection_scenario():
    """demand_projection scenario should emit to ~TFM_DINS-AT.

    Architecture/scenario separation: demand projections are scenario data,
    not model architecture. They go to separate Scen_* files to avoid
    forward-fill contamination in xl2times.

    File naming: Scen_{case}_{category}.xlsx
    Uses new P4 syntax (demands block) instead of old scenarios array.
    """
    source = {
        "model": {
            "name": "DemandTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030, 2040, 2050],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "residential_demand", "type": "service"},
            ],
        },
        "segments": {"sectors": ["RES"]},
        "process_roles": [
            {"id": "deliver_residential", "stage": "end_use",
             "required_inputs": [{"commodity": "electricity"}],
             "required_outputs": [{"commodity": "residential_demand"}]},
        ],
        "process_variants": [
            {
                "id": "residential_device",
                "role": "deliver_residential",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "residential_demand"}],
                "efficiency": 1.0,
            },
        ],
        "availability": [
            {
                "variant": "residential_device",
                "regions": ["REG1"],
                "sectors": ["RES"],
            },
        ],
        "demands": [
            {
                "commodity": "residential_demand",
                "region": "REG1",
                "sector": "RES",
                "interpolation": "interp_extrap",
                "values": {
                    "2020": 100.0,
                    "2030": 120.0,
                    "2050": 160.0,
                },
            },
        ],
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find scen_baseline_demands file with ~TFM_DINS-AT table
    demand_rows = []
    for f in tableir["files"]:
        if "scen_baseline_demands" in f["path"].lower():
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~TFM_DINS-AT":
                        demand_rows.extend(t["rows"])

    # Should have 4 rows (one per model year: 2020, 2030, 2040, 2050)
    assert len(demand_rows) == 4

    # Check years are present
    years = sorted([r["year"] for r in demand_rows])
    assert years == [2020, 2030, 2040, 2050]

    # Check values are interpolated correctly (com_proj is column header)
    values_by_year = {r["year"]: r["com_proj"] for r in demand_rows}
    assert values_by_year[2020] == 100.0
    assert values_by_year[2030] == 120.0
    assert values_by_year[2040] == 140.0  # Interpolated between 120 and 160
    assert values_by_year[2050] == 160.0


def test_demand_projection_creates_scenario_file():
    """demand_projection SHOULD create a separate scenario file.

    This is the correct architecture/scenario separation: demand
    projections are scenario data and belong in Scen_* files, not
    VT_* architecture files. Uses new P4 syntax.
    """
    source = {
        "model": {
            "name": "DemandTest",
            "regions": ["REG1"],
            "milestone_years": [2020],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "residential_demand", "type": "service"},
            ],
        },
        "segments": {"sectors": ["RES"]},
        "process_roles": [
            {
                "id": "deliver_residential",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "residential_demand"}],
            },
        ],
        "process_variants": [
            {
                "id": "residential_device",
                "role": "deliver_residential",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "residential_demand"}],
                "efficiency": 1.0,
            },
        ],
        "availability": [
            {
                "variant": "residential_device",
                "regions": ["REG1"],
                "sectors": ["RES"],
            },
        ],
        "demands": [
            {
                "commodity": "residential_demand",
                "region": "REG1",
                "sector": "RES",
                "interpolation": "interp_extrap",
                "values": {"2020": 100.0},
            },
        ],
    }
    tableir = compile_vedalang_to_tableir(source)

    # SHOULD have a scen_baseline_demands file (architecture/scenario separation)
    file_paths = [f["path"].lower() for f in tableir["files"]]
    assert any("scen_baseline_demands" in p for p in file_paths)


def test_process_capacity_bounds():
    """Process bounds should emit rows with limtype column."""
    source = {
        "model": {
            "name": "BoundsTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                    "cap_bound": {"up": 10.0},
                    "ncap_bound": {"up": 2.0, "lo": 0.5},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find bound rows
    bound_rows = [r for r in fit_rows if "limtype" in r]
    assert len(bound_rows) == 3  # cap_bnd UP, ncap_bnd UP, ncap_bnd LO

    # Check cap_bnd upper bound
    cap_up = [r for r in bound_rows if r.get("cap_bnd") == 10.0]
    assert len(cap_up) == 1
    assert cap_up[0]["limtype"] == "UP"
    assert cap_up[0]["process"] == "PP_CCGT"

    # Check ncap_bnd upper bound
    ncap_up = [r for r in bound_rows if r.get("ncap_bnd") == 2.0]
    assert len(ncap_up) == 1
    assert ncap_up[0]["limtype"] == "UP"

    # Check ncap_bnd lower bound
    ncap_lo = [r for r in bound_rows if r.get("ncap_bnd") == 0.5]
    assert len(ncap_lo) == 1
    assert ncap_lo[0]["limtype"] == "LO"


def test_process_activity_bound():
    """Activity bounds should emit rows with act_bnd column."""
    source = {
        "model": {
            "name": "ActBoundTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
            ],
            "processes": [
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:GAS"}],
                    "efficiency": 1.0,
                    "activity_bound": {"up": 500.0, "fx": 100.0},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Find activity bound rows
    act_rows = [r for r in fit_rows if "act_bnd" in r]
    assert len(act_rows) == 2

    # Check UP bound
    act_up = [r for r in act_rows if r["limtype"] == "UP"]
    assert len(act_up) == 1
    assert act_up[0]["act_bnd"] == 500.0

    # Check FX bound
    act_fx = [r for r in act_rows if r["limtype"] == "FX"]
    assert len(act_fx) == 1
    assert act_fx[0]["act_bnd"] == 100.0


def test_compile_example_with_bounds():
    """Compile example_with_bounds.veda.yaml to TableIR (new P4 syntax)."""
    source = load_vedalang(EXAMPLES_DIR / "example_with_bounds.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # New P4 syntax emits bounds via ~TFM_INS, not ~FI_T
    tfm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TFM_INS":
                    tfm_rows.extend(t["rows"])

    # Check that bounds are present (as TFM_INS attribute rows)
    bound_attrs = ("CAP_BND", "NCAP_BND", "ACT_BND")
    bound_rows = [
        r for r in tfm_rows if r.get("attribute") in bound_attrs
    ]
    assert len(bound_rows) >= 4  # Multiple bounds across processes and years


def test_compile_timeslices():
    """Timeslices should emit ~TIMESLICES and ~TFM_INS (YRFR) tables."""
    source = {
        "model": {
            "name": "TimesliceTest",
            "regions": ["REG1"],
            "timeslices": {
                "season": [
                    {"code": "S", "name": "Summer"},
                    {"code": "W", "name": "Winter"},
                ],
                "daynite": [
                    {"code": "D", "name": "Day"},
                    {"code": "N", "name": "Night"},
                ],
                "fractions": {
                    "SD": 0.25,
                    "SN": 0.23,
                    "WD": 0.27,
                    "WN": 0.25,
                },
            },
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TIMESLICES table
    timeslice_tables = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TIMESLICES":
                    timeslice_tables.append(t)

    assert len(timeslice_tables) == 1
    ts_rows = timeslice_tables[0]["rows"]

    # Ragged table format: independent columns, NOT cross-product
    # xl2times extracts unique values per column and creates cross-product itself
    # With 2 seasons and 2 daynites, we emit 2 rows (max column length)
    assert len(ts_rows) == 2

    # Check that unique level codes are present in rows
    seasons_in_rows = {r["season"] for r in ts_rows if r["season"]}
    assert seasons_in_rows == {"S", "W"}

    daynites_in_rows = {r["daynite"] for r in ts_rows if r["daynite"]}
    assert daynites_in_rows == {"D", "N"}

    # Each row should have weekly column (empty for this test)
    for row in ts_rows:
        assert "weekly" in row
        assert row["weekly"] == ""


def test_compile_timeslices_yrfr():
    """Timeslice fractions should emit ~TFM_INS rows with attribute=YRFR."""
    source = {
        "model": {
            "name": "TimesliceYRFRTest",
            "regions": ["REG1"],
            "timeslices": {
                "season": [{"code": "S"}, {"code": "W"}],
                "daynite": [{"code": "D"}, {"code": "N"}],
                "fractions": {
                    "SD": 0.25,
                    "SN": 0.23,
                    "WD": 0.27,
                    "WN": 0.25,
                },
            },
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP_CCGT", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 0.55,
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TFM_INS table in syssettings
    tfm_ins_rows = []
    for f in tableir["files"]:
        if "syssettings" in f["path"].lower():
            for s in f["sheets"]:
                for t in s["tables"]:
                    if t["tag"] == "~TFM_INS":
                        tfm_ins_rows.extend(t["rows"])

    # Should have 4 YRFR rows
    yrfr_rows = [r for r in tfm_ins_rows if r.get("attribute") == "YRFR"]
    assert len(yrfr_rows) == 4

    # Check values
    by_ts = {r["timeslice"]: r["allregions"] for r in yrfr_rows}
    assert by_ts["SD"] == 0.25
    assert by_ts["SN"] == 0.23
    assert by_ts["WD"] == 0.27
    assert by_ts["WN"] == 0.25


def test_compile_example_with_timeslices():
    """Compile example_with_timeslices.veda.yaml to TableIR."""
    source = load_vedalang(EXAMPLES_DIR / "example_with_timeslices.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have timeslice table with ragged columns (NOT cross-product)
    has_timeslices = False
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TIMESLICES":
                    has_timeslices = True
                    # Ragged table: max(len(seasons), len(daynites)) rows
                    # With 2 seasons and 2 daynites, we get 2 rows
                    assert len(t["rows"]) == 2

    assert has_timeslices


def test_default_annual_timeslice_when_not_defined():
    """Models without explicit timeslices get default ANNUAL timeslice."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have default ANNUAL timeslice
    found_ts = False
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TIMESLICES":
                    found_ts = True
                    assert len(t["rows"]) == 1
                    assert t["rows"][0]["season"] == "AN"
    assert found_ts


def test_compile_trade_links():
    """Trade links should emit ~TRADELINKS tables (matrix format with auto-naming).

    Matrix structure:
    - First column is commodity name, value is origin (FROM) region
    - Other columns are destination (TO) regions
    - Cell value is 1 for auto-naming (VEDA generates process names)

    Bilateral trades produce rows in BOTH directions (REG1→REG2 and REG2→REG1).
    Unidirectional trades produce only one row (origin→destination).
    """
    source = {
        "model": {
            "name": "TradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
                {"name": "C:GAS", "type": "fuel"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:ELC",
                    "bidirectional": True,
                },
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:GAS",
                    "bidirectional": False,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~TRADELINKS tables and sheet names
    tradelinks_tables = []
    sheet_names = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~TRADELINKS":
                    tradelinks_tables.append(t)
                    sheet_names.append(s["name"])

    # Should have 2 sheets with Excel-safe names.
    assert len(tradelinks_tables) == 2
    assert "Bi_C_ELC" in sheet_names
    assert "Uni_C_GAS" in sheet_names

    # Check bidirectional ELC link (2 rows for both directions, auto-naming)
    bi_elc_idx = sheet_names.index("Bi_C_ELC")
    elc_rows = tradelinks_tables[bi_elc_idx]["rows"]
    assert len(elc_rows) == 2  # Both directions: REG1→REG2 and REG2→REG1
    origins = {row["C:ELC"] for row in elc_rows}
    assert origins == {"REG1", "REG2"}  # Both regions as origins
    for row in elc_rows:
        for key, val in row.items():
            if key != "C:ELC":  # Skip origin column
                assert val == 1  # Auto-naming marker

    # Check unidirectional NG link (1 row, only forward direction)
    uni_ng_idx = sheet_names.index("Uni_C_GAS")
    ng_rows = tradelinks_tables[uni_ng_idx]["rows"]
    assert len(ng_rows) == 1
    assert ng_rows[0]["C:GAS"] == "REG1"  # Origin
    assert ng_rows[0]["REG2"] == 1  # Auto-naming marker


def test_trade_links_file_path():
    """Trade links should be in suppxls/trades directory."""
    source = {
        "model": {
            "name": "TestModel",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "trade_links": [
                {"origin": "REG1", "destination": "REG2", "commodity": "C:ELC"},
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file path (in suppxls/trades)
    trade_files = [
        f["path"] for f in tableir["files"] if f["path"].startswith("suppxls/trades/")
    ]
    assert len(trade_files) == 1
    assert trade_files[0] == "suppxls/trades/scentrade__trade_links.xlsx"


def test_no_trade_links_when_not_defined():
    """Models without trade_links should not emit trade file."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have trade file
    for f in tableir["files"]:
        assert "trade" not in f["path"].lower()
        for s in f["sheets"]:
            for t in s["tables"]:
                assert t["tag"] != "~TRADELINKS"


def test_compile_example_with_trade():
    """Compile example_with_trade.veda.yaml to TableIR.

    Trade processes are auto-generated by VEDA/xl2times from ~TRADELINKS.
    Trade attributes (efficiency) are set via ~TFM_INS tables.
    """
    source = load_vedalang(EXAMPLES_DIR / "example_with_trade.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should have trade links files in suppxls/trades
    # ~TRADELINKS file + ~TFM_INS file for efficiency (emitted as EFF)
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("suppxls/trades/")
    ]
    assert len(trade_files) == 2  # trade_links.xlsx + trade_attrs.xlsx

    # Find the trade links file
    tradelinks_file = next(f for f in trade_files if "trade_links" in f["path"].lower())

    # Should have ~TRADELINKS tables (2 sheets for 2 commodities, both bidirectional)
    tradelinks_tables = []
    for s in tradelinks_file["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~TRADELINKS":
                tradelinks_tables.append(t)
    assert len(tradelinks_tables) == 2


def test_trade_link_efficiency():
    """Trade links with efficiency emit EFF via TFM_INS.

    xl2times transforms EFF on IRE processes to IRE_FLO internally.
    """
    source = {
        "model": {
            "name": "TradeEffTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:ELC",
                    "bidirectional": True,
                    "efficiency": 0.95,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade files - trade_links.xlsx + trade_attrs.xlsx
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("suppxls/trades/")
    ]
    assert len(trade_files) == 2  # trade_links.xlsx + trade_attrs.xlsx

    # Find ~TRADELINKS file
    tradelinks_file = next(f for f in trade_files if "trade_links" in f["path"].lower())
    tradelinks_tables = []
    for s in tradelinks_file["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~TRADELINKS":
                tradelinks_tables.append(t)
    assert len(tradelinks_tables) == 1

    # Bilateral trade should produce 2 rows (both directions)
    rows = tradelinks_tables[0]["rows"]
    assert len(rows) == 2  # REG1→REG2 and REG2→REG1

    # Check auto-naming: cells contain 1, not process names
    for row in rows:
        for key, val in row.items():
            if key != "C:ELC":  # Skip commodity column (value is origin region)
                assert val == 1  # Auto-naming marker

    # Check both directions are present
    origins = {row["C:ELC"] for row in rows}
    assert origins == {"REG1", "REG2"}

    # Find ~TFM_INS file with EFF rows
    attrs_file = next(f for f in trade_files if "trade_attrs" in f["path"].lower())
    tfm_tables = []
    for s in attrs_file["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~TFM_INS":
                tfm_tables.append(t)
    assert len(tfm_tables) == 1

    # Should have 2 EFF rows (one per direction for bilateral)
    eff_rows = [r for r in tfm_tables[0]["rows"] if r.get("attribute") == "EFF"]
    assert len(eff_rows) == 2

    # Check EFF row structure
    for row in eff_rows:
        assert row["attribute"] == "EFF"
        assert row["value"] == 0.95
        assert row["pset_pn"] == "TB_C:ELC_*,TU_C:ELC_*"
        assert row["region"] in {"REG1", "REG2"}


def test_trade_link_no_efficiency():
    """Trade links without efficiency should not emit ~FI_T rows."""
    source = {
        "model": {
            "name": "TradeNoEffTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:ELC",
                    "bidirectional": True,
                    # No efficiency specified
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade file
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("suppxls/trades/")
    ]
    assert len(trade_files) == 1

    # Should NOT have ~FI_T tables (only TradeLinks sheet)
    fit_tables = []
    for s in trade_files[0]["sheets"]:
        for t in s["tables"]:
            if t["tag"] == "~FI_T":
                fit_tables.append(t)

    assert len(fit_tables) == 0


def test_trade_links_emit_tradelinks_only():
    """Trade links should emit only ~TRADELINKS tables (no ~FI_PROCESS).

    Trade processes are auto-generated by VEDA/xl2times from ~TRADELINKS.
    This avoids PCG conflicts that occur when both ~TRADELINKS and explicit
    ~FI_PROCESS declarations exist for the same trades.
    """
    source = {
        "model": {
            "name": "TradeExplicitTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy", "unit": "PJ"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:ELC",
                    "bidirectional": True,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find all ~FI_PROCESS rows
    process_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_PROCESS":
                    process_rows.extend(t["rows"])

    # Trade processes should NOT be in ~FI_PROCESS (auto-generated by xl2times)
    trade_proc_rows = [
        r for r in process_rows if r.get("process", "").startswith("TRADE_")
    ]
    assert len(trade_proc_rows) == 0

    # Should NOT have trade topology in ~FI_T either
    topology_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    topology_rows.extend(t["rows"])

    trade_topo_rows = [
        r for r in topology_rows if r.get("process", "").startswith("TRADE_")
    ]
    assert len(trade_topo_rows) == 0

    # Should have ~TRADELINKS with auto-naming (1s in matrix)
    trade_files = [
        f for f in tableir["files"] if f["path"].startswith("suppxls/trades/")
    ]
    assert len(trade_files) >= 1

    tradelinks_file = [f for f in trade_files if "trade_links" in f["path"].lower()][0]
    for sheet in tradelinks_file["sheets"]:
        for table in sheet["tables"]:
            if table["tag"] == "~TRADELINKS":
                # Check cells contain 1 (auto-naming), not explicit process names
                for row in table["rows"]:
                    for key, val in row.items():
                        if key != "C:ELC":  # Skip the origin column
                            assert val == 1


def test_trade_links_unidirectional():
    """Unidirectional trade should have only one direction in matrix."""
    source = {
        "model": {
            "name": "TradeUniTest",
            "regions": ["REG1", "REG2"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "C:ELC",
                    "bidirectional": False,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find trade links file
    trade_files = [
        f for f in tableir["files"] if "trade_links" in f["path"].lower()
    ]
    assert len(trade_files) == 1

    # Check ~TRADELINKS uses Uni_ sheet name and has only one row (one direction)
    for sheet in trade_files[0]["sheets"]:
        assert sheet["name"].startswith("Uni_")
        for table in sheet["tables"]:
            if table["tag"] == "~TRADELINKS":
                # Unidirectional: only one row (REG1→REG2)
                rows = table["rows"]
                assert len(rows) == 1
                assert rows[0]["C:ELC"] == "REG1"  # Origin
                assert rows[0]["REG2"] == 1  # Auto-naming marker


# =============================================================================
# User Constraint Tests
# =============================================================================


def test_emission_cap_constraint():
    """emission_cap constraint should emit ~UC_T rows with UC_COMPRD and UC_RHSRT."""
    source = {
        "model": {
            "name": "EmissionCapTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030, 2040],
            "commodities": [
                {"name": "E:CO2", "type": "emission"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 0.55,
                },
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "E:CO2",
                    "limit": 100,
                    "limtype": "up",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T table
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have rows for 3 years (2020, 2030, 2040)
    # Each year: 1 uc_comprd row + 1 uc_rhsrt row = 2 rows
    assert len(uc_rows) == 6

    # Check uc_comprd rows (VedaOnline format: attribute as column header)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    assert len(comprd_rows) == 3
    for row in comprd_rows:
        assert row["uc_n"] == "CO2_CAP"
        assert row["commodity"] == "E:CO2"
        assert row["side"] == "LHS"
        assert row["uc_comprd"] == 1

    # Check uc_rhsrt rows (VedaOnline format: attribute as column header)
    rhs_rows = [r for r in uc_rows if "uc_rhsrt" in r]
    assert len(rhs_rows) == 3
    for row in rhs_rows:
        assert row["uc_n"] == "CO2_CAP"
        assert row["limtype"] == "UP"
        assert row["uc_rhsrt"] == 100


def test_emission_cap_with_year_trajectory():
    """emission_cap with years dict should interpolate values."""
    source = {
        "model": {
            "name": "EmissionCapTrajectoryTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030, 2040, 2050],
            "commodities": [
                {"name": "E:CO2", "type": "emission"},
            ],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "constraints": [
                {
                    "name": "CO2_BUDGET",
                    "type": "emission_cap",
                    "commodity": "E:CO2",
                    "years": {
                        "2020": 100,
                        "2040": 50,
                    },
                    "interpolation": "interp_extrap",
                    "limtype": "up",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check RHS values are interpolated (VedaOnline format: uc_rhsrt as column header)
    rhs_rows = [r for r in uc_rows if "uc_rhsrt" in r]
    by_year = {r["year"]: r["uc_rhsrt"] for r in rhs_rows}

    assert by_year[2020] == 100
    assert by_year[2030] == 75  # Interpolated
    assert by_year[2040] == 50


def test_activity_share_minimum():
    """activity_share with minimum_share should emit LO constraint."""
    source = {
        "model": {
            "name": "ActivityShareTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_WIND", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                },
                {
                    "name": "PP_SOLAR",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                },
                {
                    "name": "PP_CCGT", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 0.55,
                },
            ],
            "constraints": [
                {
                    "name": "REN_TARGET",
                    "type": "activity_share",
                    "commodity": "C:ELC",
                    "processes": ["PP_WIND", "PP_SOLAR"],
                    "minimum_share": 0.30,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have rows for 2 years (2020, 2030):
    # Each year: 2 uc_act (PP_WIND, PP_SOLAR) + 1 uc_comprd + 1 uc_rhsrt = 4 rows
    # Total: 8 rows
    assert len(uc_rows) == 8

    # Check uc_act rows (VedaOnline format: coefficient = 1 for target processes)
    act_rows = [r for r in uc_rows if "uc_act" in r]
    assert len(act_rows) == 4  # 2 processes × 2 years
    processes = {r["process"] for r in act_rows}
    assert processes == {"PP_WIND", "PP_SOLAR"}
    for row in act_rows:
        assert row["uc_act"] == 1
        assert row["side"] == "LHS"

    # Check uc_comprd rows (VedaOnline format: coefficient = -share)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    assert len(comprd_rows) == 2  # 1 per year
    for row in comprd_rows:
        assert row["commodity"] == "C:ELC"
        assert row["uc_comprd"] == -0.30
        assert row["side"] == "LHS"

    # Check uc_rhsrt rows (VedaOnline format: RHS = 0, limtype = LO)
    rhs_rows = [r for r in uc_rows if "uc_rhsrt" in r]
    assert len(rhs_rows) == 2  # 1 per year
    for row in rhs_rows:
        assert row["uc_rhsrt"] == 0
        assert row["limtype"] == "LO"


def test_activity_share_maximum():
    """activity_share with maximum_share should emit UP constraint."""
    source = {
        "model": {
            "name": "ActivityShareMaxTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP_COAL", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 0.40,
                },
                {
                    "name": "PP_CCGT", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 0.55,
                },
            ],
            "constraints": [
                {
                    "name": "COAL_LIMIT",
                    "type": "activity_share",
                    "commodity": "C:ELC",
                    "processes": ["PP_COAL"],
                    "maximum_share": 0.20,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check uc_rhsrt has limtype = UP (VedaOnline format) - 2 years
    rhs_rows = [r for r in uc_rows if "uc_rhsrt" in r]
    assert len(rhs_rows) == 2
    for row in rhs_rows:
        assert row["limtype"] == "UP"

    # Check uc_comprd has -0.20 (VedaOnline format)
    comprd_rows = [r for r in uc_rows if "uc_comprd" in r]
    for row in comprd_rows:
        assert row["uc_comprd"] == -0.20


def test_activity_share_both_min_max():
    """activity_share with both min and max should emit two constraints."""
    source = {
        "model": {
            "name": "ActivityShareBothTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "PP_WIND", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                },
            ],
            "constraints": [
                {
                    "name": "WIND_BAND",
                    "type": "activity_share",
                    "commodity": "C:ELC",
                    "processes": ["PP_WIND"],
                    "minimum_share": 0.20,
                    "maximum_share": 0.40,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Should have 2 constraints (WIND_BAND_LO and WIND_BAND_UP)
    uc_names = {r["uc_n"] for r in uc_rows}
    assert uc_names == {"WIND_BAND_LO", "WIND_BAND_UP"}

    # Check LO constraint (VedaOnline format) - 2 years
    lo_rhs = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_LO" and "uc_rhsrt" in r
    ]
    assert len(lo_rhs) == 2  # 1 per year
    for row in lo_rhs:
        assert row["limtype"] == "LO"

    lo_comprd = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_LO" and "uc_comprd" in r
    ]
    for row in lo_comprd:
        assert row["uc_comprd"] == -0.20

    # Check UP constraint (VedaOnline format) - 2 years
    up_rhs = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_UP" and "uc_rhsrt" in r
    ]
    assert len(up_rhs) == 2  # 1 per year
    for row in up_rhs:
        assert row["limtype"] == "UP"

    up_comprd = [
        r
        for r in uc_rows
        if r["uc_n"] == "WIND_BAND_UP" and "uc_comprd" in r
    ]
    for row in up_comprd:
        assert row["uc_comprd"] == -0.40


def test_constraint_file_path():
    """Constraints should be emitted to SuppXLS/Scen_{case}_policies.xlsx.

    Constraints default to category 'policies' and are co-located in the
    Scen_{case}_{category}.xlsx file for that category.
    """
    source = {
        "model": {
            "name": "ConstraintFileTest",
            "regions": ["REG1"],
            "commodities": [{"name": "E:CO2", "type": "emission"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "E:CO2",
                    "limit": 100,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find constraint file path - constraints go to scen_baseline_policies.xlsx
    constraint_files = [
        f["path"] for f in tableir["files"] if "policies" in f["path"].lower()
    ]
    assert len(constraint_files) == 1
    assert constraint_files[0] == "suppxls/scen_baseline_policies.xlsx"


# =============================================================================
# Primary Commodity Group (PCG) Tests
# =============================================================================


def test_pcg_missing_raises_validation_error():
    """Process without primary_commodity_group should raise ValidationError.

    NOTE: This test uses legacy 'processes' syntax which is deprecated.
    The new P4 syntax uses process_roles/variants/availability instead.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_pcg_invalid_value_raises_validation_error():
    """Process with invalid primary_commodity_group should raise ValidationError.

    NOTE: Legacy 'processes' syntax is deprecated in P4.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_pcg_explicit_nrgo():
    """Explicit primary_commodity_group=NRGO should compile correctly.

    NOTE: Legacy 'processes' syntax is deprecated in P4.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_pcg_explicit_demo():
    """Explicit primary_commodity_group=DEMO should compile correctly.

    NOTE: Legacy 'processes' syntax is deprecated in P4.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_pcg_always_emitted():
    """primarycg column may be empty in new P4 syntax (compiler-owned).

    NOTE: The new P4 syntax uses process_roles/variants, and primarycg
    inference is compiler-owned. We no longer require user-specified PCG.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " - P4 uses compiler-owned PCG inference"
    )


def test_no_constraints_when_not_defined():
    """Models without constraints should not emit UC file."""
    source = load_vedalang(EXAMPLES_DIR / "mini_plant.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)

    # Should NOT have UC file
    for f in tableir["files"]:
        assert "UC_Constraints" not in f["path"]
        for s in f["sheets"]:
            for t in s["tables"]:
                assert t["tag"] != "~UC_T"


def test_emission_cap_lower_bound():
    """emission_cap with limtype='lo' should set LO limit."""
    source = {
        "model": {
            "name": "EmissionMinTest",
            "regions": ["REG1"],
            "commodities": [{"name": "E:CO2", "type": "emission"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "constraints": [
                {
                    "name": "CO2_MIN",
                    "type": "emission_cap",
                    "commodity": "E:CO2",
                    "limit": 50,
                    "limtype": "lo",
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T rows
    uc_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_rows.extend(t["rows"])

    # Check limtype is LO (VedaOnline format)
    rhs_rows = [r for r in uc_rows if "uc_rhsrt" in r]
    assert all(r["limtype"] == "LO" for r in rhs_rows)


def test_uc_table_has_uc_sets_metadata():
    """~UC_T tables should include uc_sets metadata for xl2times processing."""
    source = {
        "model": {
            "name": "UCSetTest",
            "regions": ["REG1"],
            "commodities": [{"name": "E:CO2", "type": "emission"}],
            "processes": [
                {
                    "name": "PP", "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "efficiency": 1.0,
                }
            ],
            "constraints": [
                {
                    "name": "CO2_CAP",
                    "type": "emission_cap",
                    "commodity": "E:CO2",
                    "limit": 100,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~UC_T table and check it has uc_sets
    uc_table = None
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~UC_T":
                    uc_table = t
                    break

    assert uc_table is not None, "Should have ~UC_T table"
    assert "uc_sets" in uc_table, "~UC_T table should have uc_sets"
    assert "R_E" in uc_table["uc_sets"], "Should have R_E scope"
    assert "T_E" in uc_table["uc_sets"], "Should have T_E scope"
    assert uc_table["uc_sets"]["R_E"] == "AllRegions"
    assert uc_table["uc_sets"]["T_E"] == ""


# =============================================================================
# Semantic Cross-Reference Validation Tests
# =============================================================================


def test_unknown_commodity_in_process_input():
    """Unknown commodity in process inputs should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadInputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "NG_MISSING"}],
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "NG_MISSING" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)
    assert "inputs[0]" in str(exc_info.value)


def test_unknown_commodity_in_process_output():
    """Unknown commodity in process outputs should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadOutputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "C:GAS"}],
                    "outputs": [{"commodity": "ELC1"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "ELC1" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)
    assert "outputs[0]" in str(exc_info.value)


def test_unknown_commodity_suggests_similar():
    """Unknown commodity should suggest similar commodity name."""
    source = {
        "model": {
            "name": "SuggestTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:EL"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "Did you mean 'C:ELC'" in str(exc_info.value)


def test_unknown_process_in_constraint():
    """Unknown process in constraint should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadConstraintTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
            "constraints": [
                {
                    "name": "REN_TARGET",
                    "type": "activity_share",
                    "commodity": "C:ELC",
                    "processes": ["PP_WIND_MISSING"],
                    "minimum_share": 0.30,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "PP_WIND_MISSING" in str(exc_info.value)
    assert "REN_TARGET" in str(exc_info.value)


def test_unknown_region_in_trade_link():
    """Unknown region in trade_link should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadTradeTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG3_MISSING",
                    "commodity": "C:ELC",
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "REG3_MISSING" in str(exc_info.value)
    assert "destination" in str(exc_info.value)


def test_unknown_commodity_in_trade_link():
    """Unknown commodity in trade_link should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadTradeCommTest",
            "regions": ["REG1", "REG2"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
            "trade_links": [
                {
                    "origin": "REG1",
                    "destination": "REG2",
                    "commodity": "GAS_MISSING",
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "GAS_MISSING" in str(exc_info.value)


def test_demand_projection_wrong_commodity_type():
    """demand_projection targeting non-demand commodity should raise error."""
    source = {
        "model": {
            "name": "BadDemandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
            ],
            "processes": [
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:GAS"}],
                    "efficiency": 1.0,
                },
            ],
            "scenarios": [
                {
                    "name": "BaseDemand",
                    "type": "demand_projection",
                    "commodity": "C:GAS",
                    "interpolation": "interp_extrap",
                    "values": {"2020": 100.0},
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "demand_projection" in str(exc_info.value)
    assert "BaseDemand" in str(exc_info.value)
    assert "C:GAS" in str(exc_info.value)
    assert "fuel" in str(exc_info.value)


def test_commodity_price_wrong_commodity_type():
    """commodity_price targeting demand commodity should raise error.

    NOTE: Legacy 'processes' syntax with 'context' field is deprecated.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_unit_warning_for_unusual_activity_unit():
    """Non-energy activity_unit should generate warning."""
    model = {
        "name": "UnitWarningTest",
        "regions": ["REG1"],
        "commodities": [{"name": "C:ELC", "type": "energy"}],
        "processes": [
            {
                "name": "PP_CCGT",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "activity_unit": "kg",
                "outputs": [{"commodity": "C:ELC"}],
                "efficiency": 0.55,
            },
        ],
    }
    errors, warnings = validate_cross_references(model)
    assert len(errors) == 0
    assert len(warnings) == 1
    assert "kg" in warnings[0]
    assert "PP_CCGT" in warnings[0]
    assert "activity_unit" in warnings[0]


def test_unit_warning_for_unusual_capacity_unit():
    """Non-power capacity_unit should generate warning."""
    model = {
        "name": "CapUnitWarningTest",
        "regions": ["REG1"],
        "commodities": [{"name": "C:ELC", "type": "energy"}],
        "processes": [
            {
                "name": "PP_CCGT",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "capacity_unit": "Mt",
                "outputs": [{"commodity": "C:ELC"}],
                "efficiency": 0.55,
            },
        ],
    }
    errors, warnings = validate_cross_references(model)
    assert len(errors) == 0
    assert len(warnings) == 1
    assert "Mt" in warnings[0]
    assert "capacity_unit" in warnings[0]


def test_strict_unit_policy_rejects_unrecognized_activity_unit():
    """Strict mode should fail on unrecognized process activity unit."""
    model = {
        "name": "StrictUnitPolicy",
        "regions": ["REG1"],
        "unit_policy": {"mode": "strict"},
        "commodities": [{"name": "C:ELC", "type": "energy"}],
        "processes": [
            {
                "name": "PP_CCGT",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "activity_unit": "kg",
                "outputs": [{"commodity": "C:ELC"}],
                "efficiency": 0.55,
            },
        ],
    }
    errors, warnings = validate_cross_references(model)
    assert len(errors) == 1
    assert len(warnings) == 0
    assert "activity_unit" in errors[0]
    assert "kg" in errors[0]


def test_strict_unit_policy_rejects_fake_unit_transform_process():
    """Strict policy should reject same-commodity pass-through unit transformers."""
    model = {
        "name": "NoUnitTransformers",
        "regions": ["REG1"],
        "unit_policy": {
            "mode": "strict",
            "forbid_unit_transform_processes": True,
        },
        "commodities": [{"name": "C:ELC", "type": "energy"}],
        "processes": [
            {
                "name": "fake_twh_to_pj",
                "sets": ["ELE"],
                "primary_commodity_group": "NRGO",
                "inputs": [{"commodity": "C:ELC"}],
                "outputs": [{"commodity": "C:ELC"}],
            },
        ],
    }
    errors, _ = validate_cross_references(model)
    assert any("unit-only transformation" in e for e in errors)


def test_strict_unit_policy_requires_basis_for_energy_mass_process():
    """Strict mode should require HHV/LHV basis on energy<->mass pathways."""
    model = {
        "name": "BasisRequired",
        "regions": ["REG1"],
        "unit_policy": {"mode": "strict", "energy_basis": "HHV"},
        "commodities": [
            {"name": "C:GAS", "type": "fuel", "unit": "PJ"},
            {"name": "C:H2", "type": "material", "unit": "Mt"},
        ],
        "processes": [
            {
                "name": "h2_production",
                "sets": ["IND"],
                "primary_commodity_group": "MATO",
                "inputs": [{"commodity": "C:GAS"}],
                "outputs": [{"commodity": "C:H2"}],
                "efficiency": 0.7,
            }
        ],
    }
    errors, _ = validate_cross_references(model)
    assert any("has no basis" in e for e in errors)


def test_l1_emission_namespace_flow_error_in_cross_refs():
    """Namespace emission commodities are rejected in process inputs/outputs."""
    model = {
        "name": "EmissionFlowError",
        "regions": ["REG1"],
        "commodities": [
            {"id": "primary:natural_gas", "type": "fuel"},
            {"id": "service:heat", "type": "service"},
            {"id": "emission:co2", "type": "emission"},
        ],
        "processes": [
            {
                "name": "bad_proc",
                "outputs": [{"commodity": "emission:co2"}],
            }
        ],
    }

    errors, _ = validate_cross_references(model)
    assert any("L1/L4 violation" in err for err in errors)


def test_l5_warns_for_ambiguous_unnamespaced_co2():
    """Ambiguous bare CO2 references should produce migration warning."""
    model = {
        "name": "AmbiguousCo2Warning",
        "regions": ["REG1"],
        "commodities": [
            {"id": "co2", "type": "emission"},
        ],
    }

    errors, warnings = validate_cross_references(model)
    assert errors == []
    assert any("Did you mean 'emission:co2'" in warning for warning in warnings)


def test_multiple_errors_collected():
    """Multiple errors should be collected, not fail-fast."""
    source = {
        "model": {
            "name": "MultiErrorTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "MISSING1"}],
                    "outputs": [{"commodity": "MISSING2"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "MISSING1" in str(exc_info.value)
    assert "MISSING2" in str(exc_info.value)
    assert len(exc_info.value.errors) == 2


def test_all_examples_pass_semantic_validation():
    """All example files should pass semantic validation.

    Note: Template-based examples (minisystem*.veda.yaml) are skipped because
    template resolution is not yet implemented in the compiler.
    """
    example_files = list(EXAMPLES_DIR.glob("*.veda.yaml"))
    assert len(example_files) > 0, "Should have example files"

    for example_file in example_files:
        # Skip template-based examples - template resolution not yet implemented
        if example_file.name.startswith("minisystem"):
            continue
        source = load_vedalang(example_file)
        tableir = compile_vedalang_to_tableir(source)
        assert "files" in tableir, f"Failed for {example_file.name}"


# =============================================================================
# Time-Varying Process Attributes Tests
# =============================================================================


def test_time_varying_investment_cost():
    """Time-varying investment_cost should emit year-indexed rows."""
    source = {
        "model": {
            "name": "TimeVaryTest",
            "regions": ["REG1"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "SolarPV",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 1.0,
                    "investment_cost": {
                        "values": {"2020": 1000, "2030": 600, "2050": 300},
                    },
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows for SolarPV
    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(
                        r for r in t["rows"] if r.get("process") == "SolarPV"
                    )

    # Should have rows with year column for ncap_cost
    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    assert len(ncap_cost_rows) == 4  # year=0 (interp) + 3 data years

    # Check interpolation row (year=0)
    interp_row = [r for r in ncap_cost_rows if r["year"] == 0][0]
    assert interp_row["ncap_cost"] == 3  # interp_extrap code

    # Check data rows
    years_values = {r["year"]: r["ncap_cost"] for r in ncap_cost_rows if r["year"] > 0}
    assert years_values[2020] == 1000
    assert years_values[2030] == 600
    assert years_values[2050] == 300


def test_time_varying_efficiency():
    """Time-varying efficiency should emit year-indexed rows."""
    source = {
        "model": {
            "name": "TimeVaryTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "C:GAS"}],
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": {
                        "values": {"2020": 0.55, "2030": 0.60, "2050": 0.65},
                        "interpolation": "interp_extrap",
                    },
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "CCGT")

    # Should have rows with year column for eff
    eff_rows = [r for r in fit_rows if "eff" in r and "year" in r]
    assert len(eff_rows) == 4  # year=0 + 3 data years

    years_values = {r["year"]: r["eff"] for r in eff_rows if r["year"] > 0}
    assert years_values[2020] == 0.55
    assert years_values[2030] == 0.60
    assert years_values[2050] == 0.65


def test_time_varying_mixed_with_scalar():
    """Time-varying and scalar attributes can coexist."""
    source = {
        "model": {
            "name": "MixedTest",
            "regions": ["REG1"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "Wind",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 1.0,
                    "investment_cost": {"values": {"2020": 1500, "2030": 1000}},
                    "lifetime": 25,  # Scalar
                    "fixed_om_cost": 30,  # Scalar
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "Wind")

    # Should have year-indexed ncap_cost rows
    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    assert len(ncap_cost_rows) == 3  # year=0 + 2 data years

    # Should have a row with scalar ncap_tlife and ncap_fom (merged)
    scalar_rows = [r for r in fit_rows if "ncap_tlife" in r or "ncap_fom" in r]
    assert len(scalar_rows) >= 1
    # At least one row should have both
    row_with_both = [r for r in scalar_rows if "ncap_tlife" in r and "ncap_fom" in r]
    assert len(row_with_both) >= 1
    assert row_with_both[0]["ncap_tlife"] == 25
    assert row_with_both[0]["ncap_fom"] == 30


def test_time_varying_no_interpolation():
    """Interpolation mode 'none' should not emit year=0 row."""
    source = {
        "model": {
            "name": "NoInterpTest",
            "regions": ["REG1"],
            "commodities": [{"name": "C:ELC", "type": "energy"}],
            "processes": [
                {
                    "name": "Coal",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.40,
                    "investment_cost": {
                        "values": {"2020": 2000, "2030": 2100},
                        "interpolation": "none",
                    },
                }
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    fit_rows = []
    for f in tableir["files"]:
        for s in f.get("sheets", []):
            for t in s.get("tables", []):
                if t["tag"] == "~FI_T":
                    fit_rows.extend(r for r in t["rows"] if r.get("process") == "Coal")

    ncap_cost_rows = [r for r in fit_rows if "ncap_cost" in r and "year" in r]
    # Should only have 2 rows (no year=0 for interpolation)
    assert len(ncap_cost_rows) == 2
    years = [r["year"] for r in ncap_cost_rows]
    assert 0 not in years
    assert 2020 in years
    assert 2030 in years


# =============================================================================
# Ergonomic Features Tests
# =============================================================================


def test_single_input_string_shorthand():
    """Single input can be specified as string instead of array."""
    source = {
        "model": {
            "name": "ShorthandInputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "C:GAS",  # Shorthand instead of inputs array
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have input row for NG
    input_rows = [r for r in fit_rows if r.get("commodity-in") == "C:GAS"]
    assert len(input_rows) == 1
    assert input_rows[0]["process"] == "PP_CCGT"


def test_single_output_string_shorthand():
    """Single output can be specified as string instead of array."""
    source = {
        "model": {
            "name": "ShorthandOutputTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "C:GAS"}],
                    "output": "C:ELC",  # Shorthand instead of outputs array
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have output row for ELC
    output_rows = [r for r in fit_rows if r.get("commodity-out") == "C:ELC"]
    assert len(output_rows) >= 1


def test_both_input_output_shorthand():
    """Both input and output can use string shorthand."""
    source = {
        "model": {
            "name": "BothShorthandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "C:GAS",  # Shorthand
                    "output": "C:ELC",  # Shorthand
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # Should have both input and output
    input_rows = [r for r in fit_rows if r.get("commodity-in") == "C:GAS"]
    output_rows = [r for r in fit_rows if r.get("commodity-out") == "C:ELC"]
    assert len(input_rows) == 1
    assert len(output_rows) >= 1


def test_default_commodity_units_energy():
    """Energy commodities default to PJ unit."""
    source = {
        "model": {
            "name": "DefaultUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},  # No unit specified
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "C:ELC",
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # ELC should have default unit PJ
    elc_row = [r for r in comm_rows if r["commodity"] == "C:ELC"][0]
    assert elc_row["unit"] == "PJ"


def test_default_commodity_units_emission():
    """Emission commodities default to Mt unit."""
    source = {
        "model": {
            "name": "EmissionUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "E:CO2", "type": "emission"},  # No unit specified
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "C:ELC",
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # CO2 should have default unit Mt
    co2_row = [r for r in comm_rows if r["commodity"] == "E:CO2"][0]
    assert co2_row["unit"] == "Mt"


def test_default_commodity_units_demand():
    """Service commodities default to PJ unit (new P4 syntax)."""
    source = {
        "model": {
            "name": "DemandUnitTest",
            "regions": ["REG1"],
            "milestone_years": [2020],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "residential_demand", "type": "service"},  # No unit specified
            ],
        },
        "segments": {"sectors": ["RES"]},
        "process_roles": [
            {
                "id": "deliver_residential",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "residential_demand"}],
            },
        ],
        "process_variants": [
            {
                "id": "residential_device",
                "role": "deliver_residential",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "residential_demand"}],
                "efficiency": 1.0,
            },
        ],
        "availability": [
            {
                "variant": "residential_device",
                "regions": ["REG1"],
                "sectors": ["RES"],
            },
        ],
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # residential_demand should have default unit PJ
    rsd_row = [
        r for r in comm_rows if r["commodity"] == "residential_demand"
    ][0]
    assert rsd_row["unit"] == "PJ"


def test_default_commodity_units_material():
    """TRADABLE commodities default to PJ unit.

    Note: With the new naming convention, there is no separate
    'material' kind. TRADABLE is used for all physical flow
    commodities. If you need Mt units for material commodities
    (like H2), specify the unit explicitly.
    """
    source = {
        "model": {
            "name": "MaterialUnitTest",
            "regions": ["REG1"],
            "commodities": [
                # Explicit Mt for material
                {"name": "C:H2", "type": "fuel", "unit": "Mt"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_ELYZ",
                    "sets": ["ELE"],
                    "primary_commodity_group": "MATO",
                    "input": "C:ELC",
                    "output": "C:H2",
                    "efficiency": 0.70,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # H2 with explicit Mt unit should have Mt
    h2_row = [r for r in comm_rows if r["commodity"] == "C:H2"][0]
    assert h2_row["unit"] == "Mt"


def test_explicit_unit_overrides_default():
    """Explicitly specified unit should override default."""
    source = {
        "model": {
            "name": "ExplicitUnitTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy", "unit": "TWh"},  # Explicit unit
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "output": "C:ELC",
                    "efficiency": 0.55,
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_COMM rows
    comm_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_COMM":
                    comm_rows.extend(t["rows"])

    # ELC should have explicit unit TWh
    elc_row = [r for r in comm_rows if r["commodity"] == "C:ELC"][0]
    assert elc_row["unit"] == "TWh"


def test_shorthand_validation_unknown_commodity():
    """Unknown commodity in shorthand syntax should raise SemanticValidationError."""
    source = {
        "model": {
            "name": "BadShorthandTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "input": "MISSING_NG",  # Unknown commodity in shorthand
                    "output": "C:ELC",
                    "efficiency": 0.55,
                },
            ],
        }
    }
    with pytest.raises(SemanticValidationError) as exc_info:
        compile_vedalang_to_tableir(source)
    assert "MISSING_NG" in str(exc_info.value)
    assert "PP_CCGT" in str(exc_info.value)


def test_prc_capact_emitted_for_gw_pj_units():
    """Compiler emits PRC_CAPACT when capacity unit differs from activity unit.

    When TCAP=GW and TACT=PJ, the conversion factor (31.536 PJ/GW/year) must be
    emitted so TIMES knows how much activity 1 unit of capacity can produce.
    Without this, TIMES defaults to PRC_CAPACT=1, causing infeasibility.
    See issue vedalang-rkf.
    """
    source = {
        "model": {
            "name": "Cap2ActTest",
            "regions": ["R1"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"name": "C:ELC", "type": "energy", "unit": "PJ"},
            ],
            "processes": [
                {
                    "name": "PP_TEST",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.5,
                },
            ],
        }
    }

    tableir = compile_vedalang_to_tableir(source)

    # Find the ~FI_T table rows
    fi_t_rows = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == "~FI_T":
                    fi_t_rows.extend(table.get("rows", []))

    # Find the efficiency row for PP_TEST
    eff_row = None
    for row in fi_t_rows:
        if row.get("process") == "PP_TEST" and "eff" in row:
            eff_row = row
            break

    assert eff_row is not None, "Could not find efficiency row for PP_TEST"
    assert "prc_capact" in eff_row, (
        "PRC_CAPACT should be emitted when TCAP=GW and TACT=PJ"
    )
    assert eff_row["prc_capact"] == 31.536, (
        f"PRC_CAPACT should be 31.536, got {eff_row.get('prc_capact')}"
    )


def test_new_syntax_variant_units_emit_tact_tcap_and_prc_capact():
    """P4 variants should emit authored tact/tcap and computed PRC_CAPACT."""
    source = _base_new_syntax_source()
    source["process_variants"][0]["activity_unit"] = "TWh"
    source["process_variants"][0]["capacity_unit"] = "GW"

    tableir = compile_vedalang_to_tableir(source)

    fi_process_rows = []
    fi_t_rows = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == "~FI_PROCESS":
                    fi_process_rows.extend(table.get("rows", []))
                if table.get("tag") == "~FI_T":
                    fi_t_rows.extend(table.get("rows", []))

    heat_pump_rows = [r for r in fi_process_rows if "heat_pump" in r.get("process", "")]
    assert heat_pump_rows
    assert all(r["tact"] == "TWh" for r in heat_pump_rows)
    assert all(r["tcap"] == "GW" for r in heat_pump_rows)

    eff_rows = [
        r
        for r in fi_t_rows
        if "heat_pump" in r.get("process", "") and "eff" in r
    ]
    assert eff_rows
    assert eff_rows[0].get("prc_capact") == 8.76


def test_explicit_cost_attribute_names():
    """Explicit cost attribute names should map correctly.

    Explicit names (preferred):
    - investment_cost → ncap_cost (NCAP_COST)
    - fixed_om_cost → ncap_fom (NCAP_FOM)
    - variable_om_cost → act_cost (ACT_COST)
    - import_price → ire_price (IRE_PRICE)
    - lifetime → ncap_tlife (NCAP_TLIFE)
    """
    source = {
        "model": {
            "name": "ExplicitCostTest",
            "regions": ["REG1"],
            "commodities": [
                {"name": "C:GAS", "type": "fuel"},
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "IMP_NG",
                    "sets": ["IMP"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:GAS"}],
                    "efficiency": 1.0,
                    "import_price": 5.0,  # Explicit name for IRE_PRICE
                },
                {
                    "name": "PP_CCGT",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "inputs": [{"commodity": "C:GAS"}],
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 0.55,
                    "investment_cost": 800,    # Explicit name for NCAP_COST
                    "fixed_om_cost": 20,       # Explicit name for NCAP_FOM
                    "variable_om_cost": 2,     # Explicit name for ACT_COST
                    "lifetime": 30,            # Explicit name for NCAP_TLIFE
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T table
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # IMP_NG should have ire_price from import_price
    imp_rows = [r for r in fit_rows if r.get("process") == "IMP_NG" and "eff" in r]
    assert len(imp_rows) == 1
    assert imp_rows[0]["ire_price"] == 5.0

    # PP_CCGT should have all explicit cost columns
    ccgt_rows = [r for r in fit_rows if r.get("process") == "PP_CCGT" and "eff" in r]
    assert len(ccgt_rows) == 1
    ccgt = ccgt_rows[0]
    assert ccgt["ncap_cost"] == 800      # investment_cost
    assert ccgt["ncap_fom"] == 20        # fixed_om_cost
    assert ccgt["act_cost"] == 2         # variable_om_cost
    assert ccgt["ncap_tlife"] == 30      # lifetime


def test_existing_capacity_emits_ncap_pasti():
    """existing_capacity should emit NCAP_PASTI rows in ~TFM_INS table.

    Unlike 'stock' (PRC_RESID) which decays linearly, existing_capacity uses
    NCAP_PASTI with vintage years for proper economic life tracking.

    NOTE: Legacy 'processes' syntax with 'context' field is deprecated.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_existing_capacity_vs_stock():
    """existing_capacity and stock can coexist but emit different attributes.

    NOTE: Legacy 'processes' syntax with 'context' field is deprecated.
    """
    pytest.skip(
        "Legacy 'processes' syntax is deprecated"
        " in P4 - use process_roles/variants"
    )


def test_bounds_expand_to_all_milestone_years():
    """Bounds should be expanded to explicit rows for all milestone years.

    Per VedaLang design principle: never rely on TIMES implicit interpolation.
    Bounds (ACT_BND, CAP_BND, NCAP_BND) are period-indexed and should have
    explicit values for each milestone year.
    """
    source = {
        "model": {
            "name": "BoundExpansionTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030, 2040],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_TEST",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 1.0,
                    "cap_bound": {"up": 100.0},
                    "ncap_bound": {"up": 10.0, "lo": 1.0},
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows with bounds
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # cap_bound: up should be expanded to 3 rows (one per milestone year)
    cap_up = [r for r in fit_rows if r.get("cap_bnd") == 100.0]
    assert len(cap_up) == 3, f"Expected 3 cap_bnd rows, got {len(cap_up)}"
    cap_years = sorted(r["year"] for r in cap_up)
    assert cap_years == [2020, 2030, 2040]

    # ncap_bound: up should be expanded to 3 rows
    ncap_up = [r for r in fit_rows if r.get("ncap_bnd") == 10.0]
    assert len(ncap_up) == 3
    ncap_up_years = sorted(r["year"] for r in ncap_up)
    assert ncap_up_years == [2020, 2030, 2040]

    # ncap_bound: lo should be expanded to 3 rows
    ncap_lo = [r for r in fit_rows if r.get("ncap_bnd") == 1.0]
    assert len(ncap_lo) == 3
    ncap_lo_years = sorted(r["year"] for r in ncap_lo)
    assert ncap_lo_years == [2020, 2030, 2040]


def test_stock_expands_to_all_milestone_years():
    """Stock (PRC_RESID) should be expanded to explicit rows for all years.

    Per VedaLang design principle: PRC_RESID has surprising default behavior
    (linear decay over TLIFE), so scalar stock values must be expanded.
    """
    source = {
        "model": {
            "name": "StockExpansionTest",
            "regions": ["REG1"],
            "milestone_years": [2020, 2030],
            "commodities": [
                {"name": "C:ELC", "type": "energy"},
            ],
            "processes": [
                {
                    "name": "PP_EXIST",
                    "sets": ["ELE"],
                    "primary_commodity_group": "NRGO",
                    "outputs": [{"commodity": "C:ELC"}],
                    "efficiency": 1.0,
                    "stock": 50.0,  # Existing capacity
                },
            ],
        }
    }
    tableir = compile_vedalang_to_tableir(source)

    # Find ~FI_T rows with prc_resid
    fit_rows = []
    for f in tableir["files"]:
        for s in f["sheets"]:
            for t in s["tables"]:
                if t["tag"] == "~FI_T":
                    fit_rows.extend(t["rows"])

    # stock should be expanded to 2 rows (one per milestone year)
    resid_rows = [r for r in fit_rows if "prc_resid" in r]
    assert len(resid_rows) == 2, f"Expected 2 prc_resid rows, got {len(resid_rows)}"

    years = sorted(r["year"] for r in resid_rows)
    assert years == [2020, 2030]

    # All rows should have the same value
    assert all(r["prc_resid"] == 50.0 for r in resid_rows)


def _base_new_syntax_source() -> dict:
    return {
        "model": {
            "name": "InvariantTest",
            "regions": ["REG1"],
            "milestone_years": [2020],
            "commodities": [
                {"id": "electricity", "type": "energy"},
                {"id": "space_heat", "type": "service"},
                {"id": "emission:co2", "type": "emission"},
            ],
            "constraints": [
                {
                    "name": "co2_cap",
                    "type": "emission_cap",
                    "commodity": "emission:co2",
                    "limit": 100.0,
                }
            ],
        },
        "segments": {"sectors": ["RES"]},
        "process_roles": [
            {
                "id": "provide_space_heat",
                "stage": "end_use",
                "required_inputs": [{"commodity": "electricity"}],
                "required_outputs": [{"commodity": "space_heat"}],
            }
        ],
        "process_variants": [
            {
                "id": "heat_pump",
                "role": "provide_space_heat",
                "inputs": [{"commodity": "electricity"}],
                "outputs": [{"commodity": "space_heat"}],
                "kind": "device",
                "efficiency": 1.0,
                "emission_factors": {"emission:co2": 0.0},
            }
        ],
        "availability": [
            {
                "variant": "heat_pump",
                "regions": ["REG1"],
                "sectors": ["RES"],
            }
        ],
        "demands": [
            {
                "commodity": "space_heat",
                "region": "REG1",
                "sector": "RES",
                "values": {"2020": 10.0},
            }
        ],
    }


def test_new_syntax_structural_invariants_valid_model_compiles():
    source = _base_new_syntax_source()
    tableir = compile_vedalang_to_tableir(source)
    assert "files" in tableir


def test_new_syntax_invalid_commodity_type_is_deterministic_error():
    source = _base_new_syntax_source()
    source["model"]["commodities"][0]["type"] = "invalid_type"

    with pytest.raises(Exception, match=r"\[E_COMMODITY_TYPE_ENUM\]"):
        compile_vedalang_to_tableir(source, validate=False)


def test_new_syntax_demand_must_reference_service_commodity():
    source = _base_new_syntax_source()
    source["demands"][0]["commodity"] = "electricity"

    with pytest.raises(Exception, match=r"\[E_DEMAND_COMMODITY_TYPE\]"):
        compile_vedalang_to_tableir(source)


def test_new_syntax_emission_constraints_require_emission_commodity():
    source = _base_new_syntax_source()
    source["model"]["constraints"][0]["commodity"] = "electricity"

    with pytest.raises(Exception, match=r"\[E_EMISSION_COMMODITY_TYPE\]"):
        compile_vedalang_to_tableir(source)


def test_new_syntax_role_primary_output_invariant_enforced():
    source = _base_new_syntax_source()
    source["process_roles"][0]["required_outputs"] = [
        {"commodity": "space_heat"},
        {"commodity": "electricity"},
    ]

    with pytest.raises(Exception, match=r"\[E_ROLE_PRIMARY_OUTPUT\]"):
        compile_vedalang_to_tableir(source)


def test_new_syntax_stage_enum_violation_reports_structural_code():
    source = _base_new_syntax_source()
    source["process_roles"][0]["stage"] = "invalid_stage"

    with pytest.raises(Exception, match=r"\[E_STAGE_ENUM\]"):
        compile_vedalang_to_tableir(source, validate=False)


def test_new_syntax_rejects_emission_namespace_in_outputs():
    source = _base_new_syntax_source()
    source["process_variants"][0]["outputs"].append({"commodity": "emission:co2"})

    with pytest.raises(Exception, match=r"\[E_EMISSION_NAMESPACE_FLOW\]"):
        compile_vedalang_to_tableir(source)


def test_new_syntax_requires_emission_namespace_in_emission_factors():
    source = _base_new_syntax_source()
    source["process_variants"][0]["emission_factors"] = {"material:co2": 0.01}

    with pytest.raises(Exception, match=r"\[E_EMISSION_FACTOR_NAMESPACE\]"):
        compile_vedalang_to_tableir(source)


def test_new_syntax_negative_emission_factor_warns_without_documentation():
    source = _base_new_syntax_source()
    source["process_variants"][0]["emission_factors"] = {"emission:co2": -1.0}

    tableir = compile_vedalang_to_tableir(source)
    warnings = tableir["convention_diagnostics"]["warnings"]
    assert any(w["code"] == "W_NEGATIVE_EMISSION_DOC" for w in warnings)


def test_new_syntax_detects_duplicate_service_roles_with_merge_hint():
    source = _base_new_syntax_source()
    source["model"]["commodities"].append({"id": "gas", "type": "fuel"})
    source["process_roles"].append(
        {
            "id": "heat_from_gas",
            "stage": "end_use",
            "required_inputs": [{"commodity": "gas"}],
            "required_outputs": [{"commodity": "space_heat"}],
        }
    )
    source["process_variants"].append(
        {
            "id": "gas_heater",
            "role": "heat_from_gas",
            "inputs": [{"commodity": "gas"}],
            "outputs": [{"commodity": "space_heat"}],
            "kind": "device",
            "efficiency": 0.9,
        }
    )
    source["availability"].append(
        {
            "variant": "gas_heater",
            "regions": ["REG1"],
            "sectors": ["RES"],
        }
    )

    with pytest.raises(Exception) as exc:
        compile_vedalang_to_tableir(source)

    message = str(exc.value)
    assert "[E1_DUPLICATE_SERVICE_ROLES]" in message
    assert "provide_space_heat" in message
    assert "heat_from_gas" in message


def test_new_syntax_w1_detects_identical_io_split_across_roles():
    source = _base_new_syntax_source()
    source["process_roles"].append(
        {
            "id": "space_heat_with_alt_grid",
            "stage": "end_use",
            "required_inputs": [{"commodity": "electricity"}],
            "required_outputs": [{"commodity": "space_heat"}],
        }
    )

    commodities = _normalize_commodities_for_new_syntax(source["model"]["commodities"])
    roles = build_roles(source, commodities)
    errors, warnings = _detect_service_role_duplication(roles, commodities)

    assert any(e["code"] == "E1_DUPLICATE_SERVICE_ROLES" for e in errors)
    assert any(w["code"] == "W1_SPLIT_IDENTICAL_IO_ROLES" for w in warnings)


def test_new_syntax_w2_warning_is_machine_readable_and_non_blocking():
    source = _base_new_syntax_source()
    source["process_roles"][0]["id"] = "space_heat_from_electricity"
    source["process_variants"][0]["role"] = "space_heat_from_electricity"

    tableir = compile_vedalang_to_tableir(source)
    warnings = tableir["convention_diagnostics"]["warnings"]

    assert any(w["code"] == "W2_FUEL_PATHWAY_ROLE_NAME" for w in warnings)


def test_new_syntax_false_positive_guard_different_service_outputs():
    source = _base_new_syntax_source()
    source["model"]["commodities"].append({"id": "water_heat", "type": "service"})
    source["process_roles"].append(
        {
            "id": "provide_water_heat",
            "stage": "end_use",
            "required_inputs": [{"commodity": "electricity"}],
            "required_outputs": [{"commodity": "water_heat"}],
        }
    )
    source["process_variants"].append(
        {
            "id": "electric_boiler",
            "role": "provide_water_heat",
            "inputs": [{"commodity": "electricity"}],
            "outputs": [{"commodity": "water_heat"}],
            "kind": "device",
            "efficiency": 0.95,
        }
    )
    source["availability"].append(
        {
            "variant": "electric_boiler",
            "regions": ["REG1"],
            "sectors": ["RES"],
        }
    )

    tableir = compile_vedalang_to_tableir(source)
    warnings = tableir["convention_diagnostics"]["warnings"]
    assert "convention_diagnostics" in tableir
    assert all(w["code"] != "W1_SPLIT_IDENTICAL_IO_ROLES" for w in warnings)


def test_toy_agriculture_uses_service_role_and_sink_sequestration_conventions():
    source = load_vedalang(EXAMPLES_DIR / "toy_agriculture.veda.yaml")

    commodity_types = {
        commodity["id"]: commodity["type"]
        for commodity in source["model"]["commodities"]
    }
    assert commodity_types["material:ag_inputs"] == "material"
    assert commodity_types["service:agricultural_output"] == "service"
    assert commodity_types["emission:co2e"] == "emission"

    roles = {role["id"]: role for role in source["process_roles"]}
    assert set(roles) == {"supply_ag_inputs", "provide_ag_output", "remove_co2"}
    assert roles["supply_ag_inputs"]["stage"] == "supply"
    assert roles["provide_ag_output"]["stage"] == "end_use"
    assert roles["provide_ag_output"]["required_inputs"] == [
        {"commodity": "material:ag_inputs"}
    ]
    assert roles["remove_co2"]["stage"] == "sink"
    assert roles["remove_co2"]["required_inputs"] == []
    assert roles["remove_co2"]["required_outputs"] == []

    variant_roles = {
        variant["id"]: variant["role"]
        for variant in source["process_variants"]
    }
    assert variant_roles["primary_supply"] == "supply_ag_inputs"
    assert variant_roles["traditional_baseline"] == "provide_ag_output"
    assert variant_roles["traditional_with_feed_additives"] == "provide_ag_output"
    assert variant_roles["traditional_with_improved_manure"] == "provide_ag_output"
    assert variant_roles["soil_carbon"] == "remove_co2"
    assert variant_roles["reforestation"] == "remove_co2"


def test_toy_agriculture_example_compiles_after_refactor():
    source = load_vedalang(EXAMPLES_DIR / "toy_agriculture.veda.yaml")
    tableir = compile_vedalang_to_tableir(source)
    assert "files" in tableir

def test_toy_buildings_uses_service_role_and_case_demand_override_conventions():
    source = load_vedalang(EXAMPLES_DIR / "toy_buildings.veda.yaml")

    roles = {role["id"]: role for role in source["process_roles"]}
    assert "provide_space_heat" in roles
    assert roles["provide_space_heat"]["stage"] == "end_use"
    assert roles["provide_space_heat"]["required_inputs"] == []
    assert {"commodity": "service:space_heat"} in (
        roles["provide_space_heat"]["required_outputs"]
    )

    # No fuel-pathway or intermediate carrier roles
    assert "heat_from_gas" not in roles
    assert "heat_from_electricity" not in roles
    assert "reduce_heat_demand" not in roles
    assert "convert_gas_to_delivered_heat" not in roles
    assert "convert_electricity_to_delivered_heat" not in roles

    # Variants use variant-level inputs
    variants = {v["id"]: v for v in source["process_variants"]}
    assert variants["gas_heater"]["role"] == "provide_space_heat"
    assert variants["gas_heater"]["inputs"] == [{"commodity": "primary:natural_gas"}]
    assert variants["heat_pump"]["role"] == "provide_space_heat"
    assert variants["heat_pump"]["inputs"] == [{"commodity": "secondary:electricity"}]
    assert "space_heat_delivery" not in variants

    cases = {case["name"]: case for case in source["model"]["cases"]}
    assert "baseline" in cases
    assert cases["baseline"]["is_baseline"] is True
    assert "retrofit_policy" in cases

    demand_overrides = cases["retrofit_policy"]["demand_overrides"]
    assert len(demand_overrides) == 1
    assert demand_overrides[0]["commodity"] == "service:space_heat"
    assert demand_overrides[0]["sector"] == "RES"

def test_toy_industry_uses_variant_level_inputs():
    source = load_vedalang(EXAMPLES_DIR / "toy_industry.veda.yaml")

    roles = {role["id"]: role for role in source["process_roles"]}
    assert "provide_industrial_heat" in roles
    assert roles["provide_industrial_heat"]["stage"] == "end_use"
    assert roles["provide_industrial_heat"]["required_inputs"] == []
    assert roles["provide_industrial_heat"]["required_outputs"] == [
        {"commodity": "service:industrial_heat"},
    ]

    assert "convert_gas_to_industrial_heat" not in roles
    assert "convert_electricity_to_industrial_heat" not in roles
    assert "convert_hydrogen_to_industrial_heat" not in roles

    variants = {
        variant["id"]: variant
        for variant in source["process_variants"]
    }
    assert variants["gas_boiler"]["role"] == "provide_industrial_heat"
    assert variants["gas_boiler"]["inputs"] == [{"commodity": "primary:natural_gas"}]
    assert variants["electric_heater"]["role"] == "provide_industrial_heat"
    assert variants["electric_heater"]["inputs"] == [
        {"commodity": "secondary:electricity"}
    ]
    assert variants["h2_boiler"]["role"] == "provide_industrial_heat"
    assert variants["h2_boiler"]["inputs"] == [{"commodity": "secondary:hydrogen"}]
    assert "industrial_heat_delivery" not in variants

def test_toy_transport_uses_service_role_with_pathway_variants():
    source = load_vedalang(EXAMPLES_DIR / "toy_transport.veda.yaml")

    roles = {role["id"]: role for role in source["process_roles"]}
    assert "provide_passenger_km" in roles
    assert roles["provide_passenger_km"]["stage"] == "end_use"
    assert roles["provide_passenger_km"]["required_inputs"] == []
    assert roles["provide_passenger_km"]["required_outputs"] == [
        {"commodity": "service:passenger_km"},
    ]

    # No intermediate conversion roles
    assert "convert_petrol_to_mobility" not in roles
    assert "convert_electricity_to_mobility" not in roles

    variants = {v["id"]: v for v in source["process_variants"]}
    assert variants["ice_car"]["role"] == "provide_passenger_km"
    assert variants["ice_car"]["inputs"] == [{"commodity": "primary:petrol"}]
    assert variants["ev_car"]["role"] == "provide_passenger_km"
    assert variants["ev_car"]["inputs"] == [{"commodity": "secondary:electricity"}]
    assert "passenger_service_delivery" not in variants

def test_toy_resources_uses_service_role_with_case_overlays():
    source = load_vedalang(EXAMPLES_DIR / "toy_resources.veda.yaml")

    roles = {role["id"]: role for role in source["process_roles"]}
    assert "provide_haul_work" in roles
    assert roles["provide_haul_work"]["stage"] == "end_use"
    assert roles["provide_haul_work"]["required_inputs"] == []
    assert roles["provide_haul_work"]["required_outputs"] == [
        {"commodity": "service:haul_work"}
    ]

    # No fuel-pathway conversion roles — all variants under one service role
    assert "convert_diesel_to_haul_energy" not in roles
    assert "convert_electricity_to_haul_energy" not in roles
    assert "convert_biodiesel_to_haul_energy" not in roles

    variants = {
        variant["id"]: variant["role"]
        for variant in source["process_variants"]
    }
    assert variants["diesel_haul"] == "provide_haul_work"
    assert variants["electric_haul"] == "provide_haul_work"
    assert variants["biodiesel_haul"] == "provide_haul_work"

    cases = {case["name"]: case for case in source["model"]["cases"]}
    assert cases["ref"]["is_baseline"] is True
    assert "co2cap" in cases
    assert "force_shift" in cases

def test_toy_refactored_examples_compile_under_new_invariants():
    for filename in (
        "toy_buildings.veda.yaml",
        "toy_industry.veda.yaml",
        "toy_transport.veda.yaml",
        "toy_resources.veda.yaml",
    ):
        source = load_vedalang(EXAMPLES_DIR / filename)
        tableir = compile_vedalang_to_tableir(source)
        assert "files" in tableir

def test_new_syntax_end_use_requires_physical_input():
    source = _base_new_syntax_source()
    source["process_roles"][0]["required_inputs"] = []
    source["process_variants"][0]["inputs"] = []
    source["process_variants"][0].pop("kind")

    with pytest.raises(Exception, match=r"\[E_END_USE_PHYSICAL_INPUT\]"):
        compile_vedalang_to_tableir(source)

def test_new_syntax_end_use_zero_input_explicit_kind_still_errors():
    source = _base_new_syntax_source()
    source["process_roles"][0]["required_inputs"] = []
    source["process_variants"][0]["inputs"] = []
    source["process_variants"][0]["kind"] = "device"

    with pytest.raises(Exception, match=r"\[E_END_USE_PHYSICAL_INPUT\]"):
        compile_vedalang_to_tableir(source)
