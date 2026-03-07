from pathlib import Path

from vedalang.compiler import load_vedalang, validate_vedalang
from vedalang.versioning import looks_like_legacy_source, looks_like_v0_2_source


def test_source_shape_helpers_distinguish_v0_2_from_legacy() -> None:
    legacy = {
        "model": {"name": "Legacy", "regions": ["R1"], "commodities": []},
        "roles": [],
    }
    v0_2 = {
        "dsl_version": "0.2",
        "commodities": [{"id": "service:heat", "kind": "service"}],
    }

    assert looks_like_legacy_source(legacy)
    assert not looks_like_v0_2_source(legacy)
    assert looks_like_v0_2_source(v0_2)
    assert not looks_like_legacy_source(v0_2)


def test_load_vedalang_only_injects_dsl_version_for_v0_2_files(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.veda.yaml"
    legacy_path.write_text(
        "model:\n  name: Legacy\n  regions: [R1]\n  commodities: []\nroles: []\n",
        encoding="utf-8",
    )
    v0_2_path = tmp_path / "v0_2.veda.yaml"
    v0_2_path.write_text(
        "commodities:\n  - id: service:heat\n    kind: service\n",
        encoding="utf-8",
    )

    legacy = load_vedalang(legacy_path)
    v0_2 = load_vedalang(v0_2_path)

    assert "dsl_version" not in legacy
    assert v0_2["dsl_version"] == "0.2"


def test_validate_vedalang_routes_legacy_sources_to_legacy_schema() -> None:
    legacy = {
        "model": {
            "name": "Legacy",
            "regions": ["R1"],
            "commodities": [
                {
                    "id": "secondary:electricity",
                    "type": "energy",
                    "unit": "PJ",
                }
            ],
        },
        "roles": [],
        "variants": [],
    }

    validate_vedalang(legacy)
