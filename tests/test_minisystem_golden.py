"""Golden checks for the v0.3 MiniSystem ladder."""

from pathlib import Path

from tools.veda_check import run_check
from vedalang.compiler import (
    compile_vedalang_bundle,
    compile_vedalang_to_tableir,
    load_vedalang,
)

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "vedalang" / "examples"
MINISYSTEM_PATH = EXAMPLES_DIR / "minisystem/minisystem8.veda.yaml"


def _table_rows(tableir: dict, tag: str) -> list[dict]:
    rows: list[dict] = []
    for file_spec in tableir.get("files", []):
        for sheet in file_spec.get("sheets", []):
            for table in sheet.get("tables", []):
                if table.get("tag") == tag:
                    rows.extend(table.get("rows", []))
    return rows


def test_minisystem8_exists_and_compiles():
    assert MINISYSTEM_PATH.exists()
    source = load_vedalang(MINISYSTEM_PATH)
    bundle = compile_vedalang_bundle(
        source, validate=True, selected_run="australia_2025"
    )
    assert bundle.csir is not None
    assert bundle.cpir is not None
    assert bundle.explain is not None


def test_minisystem8_uses_multi_region_v0_2_surface():
    source = load_vedalang(MINISYSTEM_PATH)
    assert source["region_partitions"][0]["members"] == ["NEM_EAST", "NEM_SOUTH", "WA"]
    assert any(
        network["id"] == "east_south_interconnector" for network in source["networks"]
    )
    assert len(source["technology_roles"]) >= 8


def test_minisystem8_tableir_has_core_process_and_trade_rows():
    source = load_vedalang(MINISYSTEM_PATH)
    tableir = compile_vedalang_to_tableir(source)
    fi_process_rows = _table_rows(tableir, "~FI_PROCESS")
    tradelink_rows = _table_rows(tableir, "~TRADELINKS")

    assert fi_process_rows
    assert tradelink_rows


def test_minisystem8_validates_through_run_check():
    result = run_check(MINISYSTEM_PATH, from_vedalang=True)
    assert result.success
    assert result.errors == 0
