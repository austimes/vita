from pathlib import Path

import pytest
from jsonschema import ValidationError

from vedalang.compiler import (
    load_vedalang,
    validate_vedalang,
)
from vedalang.versioning import looks_like_supported_source


def test_source_shape_helper_detects_only_public_sources() -> None:
    legacy = {
        "model": {"name": "Legacy", "regions": ["R1"], "commodities": []},
        "roles": [],
    }
    public = {
        "dsl_version": "0.3",
        "commodities": [{"id": "heat", "type": "service"}],
    }

    assert not looks_like_supported_source(legacy)
    assert looks_like_supported_source(public)


def test_load_vedalang_only_injects_dsl_version_for_public_files(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy.veda.yaml"
    legacy_path.write_text(
        "model:\n  name: Legacy\n  regions: [R1]\n  commodities: []\nroles: []\n",
        encoding="utf-8",
    )
    public_path = tmp_path / "public.veda.yaml"
    public_path.write_text(
        "commodities:\n  - id: service:heat\n    kind: service\n",
        encoding="utf-8",
    )

    legacy = load_vedalang(legacy_path)
    public = load_vedalang(public_path)

    assert "dsl_version" not in legacy
    assert public["dsl_version"] == "0.3"


def test_validate_vedalang_rejects_legacy_sources_by_default() -> None:
    legacy = {
        "model": {
            "name": "Legacy",
            "regions": ["R1"],
            "commodities": [
                {
                    "id": "electricity",
                    "type": "energy",
                    "unit": "PJ",
                }
            ],
        },
        "roles": [],
        "variants": [],
    }

    with pytest.raises(ValidationError):
        validate_vedalang(legacy)
