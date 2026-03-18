"""Tests for vita.experiment_validation module."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from vita.experiment_manifest import ExperimentManifest, load_experiment_manifest
from vita.experiment_validation import (
    ValidationResult,
    render_brief_md,
    validate_brief,
    validate_interpretation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_MODEL = """\
vedalang: "0.5"
id: test_model
title: Test Model
regions: [SINGLE]
time_horizon: {start: 2025, periods: [{years: 2025}]}
commodities: []
technology_roles: []
"""

_MANIFEST_DICT = {
    "schema_version": 1,
    "id": "test_experiment",
    "title": "Test Experiment",
    "question": "What happens when we change X?",
    "extensions": [{"id": "A", "question": "Sub-question A?"}],
    "baseline": {"id": "baseline", "model": "model.veda.yaml", "run": "run1"},
    "variants": [
        {
            "id": "variant_a",
            "from": "baseline",
            "hypothesis": "X increases cost",
        },
    ],
    "comparisons": [
        {
            "id": "baseline_vs_variant_a",
            "baseline": "baseline",
            "variant": "variant_a",
        },
    ],
    "analyses": [
        {
            "id": "A",
            "question": "Sub-question A?",
            "comparisons": ["baseline_vs_variant_a"],
        },
    ],
}

_LONG_TEXT = "This is a sufficiently long substantive text for validation checks."
_LONG_TEXT_32 = (
    "This text is long enough for thirty-two character minimum checks easily."
)

_CALIBRATION_VARIANT_IDS = [
    "co2_cap_loose",
    "co2_cap_mid",
    "co2_cap_tight",
    "high_gas_price",
    "high_gas_price_co2_cap_mid",
    "high_h2_price_co2_cap_mid",
]

_CALIBRATION_COMPARISON_SPECS: list[tuple[str, str, str]] = [
    ("baseline_vs_co2_cap_loose", "baseline", "co2_cap_loose"),
    ("baseline_vs_co2_cap_mid", "baseline", "co2_cap_mid"),
    ("baseline_vs_co2_cap_tight", "baseline", "co2_cap_tight"),
    ("baseline_vs_high_gas_price", "baseline", "high_gas_price"),
    (
        "baseline_vs_high_gas_price_co2_cap_mid",
        "baseline",
        "high_gas_price_co2_cap_mid",
    ),
    (
        "baseline_vs_high_h2_price_co2_cap_mid",
        "baseline",
        "high_h2_price_co2_cap_mid",
    ),
    (
        "co2_cap_mid_vs_high_gas_price_co2_cap_mid",
        "co2_cap_mid",
        "high_gas_price_co2_cap_mid",
    ),
    (
        "co2_cap_mid_vs_high_h2_price_co2_cap_mid",
        "co2_cap_mid",
        "high_h2_price_co2_cap_mid",
    ),
    (
        "high_gas_price_co2_cap_mid_vs_high_h2_price_co2_cap_mid",
        "high_gas_price_co2_cap_mid",
        "high_h2_price_co2_cap_mid",
    ),
]


def _make_manifest(tmp_path: Path) -> ExperimentManifest:
    """Write manifest + model to tmp_path and load."""
    model_path = tmp_path / "model.veda.yaml"
    model_path.write_text(_MINIMAL_MODEL)
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(_MANIFEST_DICT))
    return load_experiment_manifest(manifest_path)


def _make_valid_brief() -> dict:
    """Build a minimal valid brief dict matching _MANIFEST_DICT."""
    return {
        "schema_version": "vita-experiment-brief/v1",
        "experiment_id": "test_experiment",
        "manifest_file": "manifest.yaml",
        "created_at": "2026-03-18T12:00:00Z",
        "research": {
            "question": "What happens when we change X?",
            "scope": _LONG_TEXT,
        },
        "design_summary": {
            "approach": _LONG_TEXT,
            "variant_ids": ["variant_a"],
            "comparison_ids": ["baseline_vs_variant_a"],
        },
        "variants": [
            {
                "variant_id": "variant_a",
                "change_summary": _LONG_TEXT,
                "why_this_variant": _LONG_TEXT,
                "hypothesis": {
                    "statement": _LONG_TEXT,
                    "expected_direction": "increase",
                    "mechanism_chains": [
                        {
                            "id": "M1",
                            "cause": _LONG_TEXT,
                            "effect": _LONG_TEXT,
                            "because": _LONG_TEXT,
                        },
                    ],
                    "confirmation_criteria": [
                        {
                            "id": "C1",
                            "description": "Cost increases by more than 5%",
                            "signals": [
                                {
                                    "metric": "objective",
                                    "expected_direction": "increase",
                                },
                            ],
                        },
                    ],
                    "refutation_criteria": [
                        {
                            "id": "R1",
                            "description": "Cost stays flat or decreases",
                        },
                    ],
                },
            },
        ],
        "comparison_plan": [
            {
                "comparison_id": "baseline_vs_variant_a",
                "purpose": _LONG_TEXT,
                "metrics_of_interest": [
                    {
                        "metric": "objective",
                        "priority": "primary",
                        "why_it_matters": "Main cost indicator",
                    },
                ],
            },
        ],
        "design_reasoning_steps": [
            {
                "id": "P1",
                "kind": "question_framing",
                "statement": _LONG_TEXT,
            },
        ],
    }


def _make_calibration_manifest(tmp_path: Path) -> ExperimentManifest:
    """Write a 6-variant/9-comparison toy calibration manifest and load it."""
    model_path = tmp_path / "model.veda.yaml"
    model_path.write_text(_MINIMAL_MODEL)
    manifest_dict = {
        "schema_version": 1,
        "id": "toy_industry_calibrated",
        "title": "Toy Industry Calibrated",
        "question": "Calibration fixture for narrative validation gates",
        "baseline": {
            "id": "baseline",
            "model": "model.veda.yaml",
            "run": "single_2025",
        },
        "variants": [
            {
                "id": variant_id,
                "from": "baseline",
                "run": f"run_{variant_id}",
                "hypothesis": _LONG_TEXT,
            }
            for variant_id in _CALIBRATION_VARIANT_IDS
        ],
        "comparisons": [
            {
                "id": comp_id,
                "baseline": baseline_id,
                "variant": variant_id,
            }
            for comp_id, baseline_id, variant_id in _CALIBRATION_COMPARISON_SPECS
        ],
        "analyses": [
            {
                "id": "main",
                "question": "Calibration validation coverage",
                "comparisons": [c[0] for c in _CALIBRATION_COMPARISON_SPECS],
            }
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest_dict))
    return load_experiment_manifest(manifest_path)


def _make_calibration_brief() -> dict:
    """Build a valid brief matching the 6-variant/9-comparison fixture."""
    variants = []
    for variant_id in _CALIBRATION_VARIANT_IDS:
        variants.append(
            {
                "variant_id": variant_id,
                "change_summary": _LONG_TEXT_32,
                "why_this_variant": _LONG_TEXT_32,
                "hypothesis": {
                    "statement": _LONG_TEXT_32,
                    "expected_direction": "increase",
                    "mechanism_chains": [
                        {
                            "id": f"M_{variant_id}",
                            "cause": _LONG_TEXT_32,
                            "effect": _LONG_TEXT_32,
                            "because": _LONG_TEXT_32,
                        },
                    ],
                    "confirmation_criteria": [
                        {
                            "id": f"C_{variant_id}",
                            "description": _LONG_TEXT_32,
                            "signals": [
                                {
                                    "metric": "objective",
                                    "expected_direction": "increase",
                                }
                            ],
                        },
                    ],
                    "refutation_criteria": [
                        {
                            "id": f"R_{variant_id}",
                            "description": _LONG_TEXT_32,
                        }
                    ],
                },
            }
        )

    comparison_plan = [
        {
            "comparison_id": comp_id,
            "purpose": _LONG_TEXT_32,
            "metrics_of_interest": [
                {
                    "metric": "objective",
                    "priority": "primary",
                    "why_it_matters": _LONG_TEXT_32,
                }
            ],
        }
        for comp_id, _, _ in _CALIBRATION_COMPARISON_SPECS
    ]

    return {
        "schema_version": "vita-experiment-brief/v1",
        "experiment_id": "toy_industry_calibrated",
        "manifest_file": "manifest.yaml",
        "created_at": "2026-03-18T12:00:00Z",
        "research": {
            "question": "How does policy and stress calibration behave?",
            "scope": _LONG_TEXT_32,
        },
        "design_summary": {
            "approach": _LONG_TEXT_32,
            "variant_ids": list(_CALIBRATION_VARIANT_IDS),
            "comparison_ids": [c[0] for c in _CALIBRATION_COMPARISON_SPECS],
        },
        "variants": variants,
        "comparison_plan": comparison_plan,
        "design_reasoning_steps": [
            {
                "id": "P1",
                "kind": "question_framing",
                "statement": _LONG_TEXT_32,
            },
            {
                "id": "P2",
                "kind": "hypothesis_decomposition",
                "statement": _LONG_TEXT_32,
            },
        ],
    }


def _make_calibration_interpretation() -> dict:
    """Build a valid interpretation payload matching the calibration fixture."""
    return {
        "schema_version": "vita-experiment-interpretation/v1",
        "experiment_id": "toy_industry_calibrated",
        "comparison_interpretations": [
            {
                "comparison_id": comp_id,
                "takeaway": _LONG_TEXT_32,
            }
            for comp_id, _, _ in _CALIBRATION_COMPARISON_SPECS
        ],
    }


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict(self):
        vr = ValidationResult(artifact_kind="brief", valid=True)
        d = vr.to_dict()
        assert d["schema_version"] == "vita-experiment-validation/v1"
        assert d["artifact_kind"] == "brief"
        assert d["valid"] is True

    def test_save(self, tmp_path: Path):
        vr = ValidationResult(artifact_kind="brief", valid=False, errors=["e1"])
        out = tmp_path / "result.json"
        vr.save(out)
        assert out.exists()
        import json

        data = json.loads(out.read_text())
        assert data["valid"] is False
        assert data["errors"] == ["e1"]


# ---------------------------------------------------------------------------
# Brief validation
# ---------------------------------------------------------------------------


class TestBriefValidation:
    def test_valid_brief_passes(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        result = validate_brief(brief, manifest)
        assert result.valid, f"Expected valid, got errors: {result.errors}"
        assert result.errors == []

    def test_wrong_schema_version(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["schema_version"] = "wrong/v2"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("schema_version" in e for e in result.errors)

    def test_experiment_id_mismatch(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["experiment_id"] = "wrong_id"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("experiment_id" in e for e in result.errors)

    def test_missing_variant(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Missing variant" in e for e in result.errors)
        assert "variant_a" in result.coverage["missing_variant_ids"]

    def test_extra_variant(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        extra = copy.deepcopy(brief["variants"][0])
        extra["variant_id"] = "extra_variant"
        brief["variants"].append(extra)
        result = validate_brief(brief, manifest)
        assert any("Extra variant" in w for w in result.warnings)

    def test_missing_comparison(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["comparison_plan"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Missing comparison" in e for e in result.errors)

    def test_duplicate_mechanism_ids(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        # Add a second mechanism chain with same ID
        mc_dup = copy.deepcopy(
            brief["variants"][0]["hypothesis"]["mechanism_chains"][0]
        )
        brief["variants"][0]["hypothesis"]["mechanism_chains"].append(mc_dup)
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("Duplicate" in e and "mechanism_chains" in e for e in result.errors)

    def test_non_substantive_fields(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["research"]["scope"] = "tbd"
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("research.scope" in e for e in result.errors)

    def test_empty_mechanism_chains(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"][0]["hypothesis"]["mechanism_chains"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any("mechanism_chains must not be empty" in e for e in result.errors)

    def test_empty_confirmation_criteria(self, tmp_path: Path):
        manifest = _make_manifest(tmp_path)
        brief = _make_valid_brief()
        brief["variants"][0]["hypothesis"]["confirmation_criteria"] = []
        result = validate_brief(brief, manifest)
        assert not result.valid
        assert any(
            "confirmation_criteria must not be empty" in e
            for e in result.errors
        )


class TestToyIndustryCalibrationBriefCoverage:
    def test_full_calibration_brief_passes(self, tmp_path: Path):
        manifest = _make_calibration_manifest(tmp_path)
        brief = _make_calibration_brief()

        result = validate_brief(brief, manifest)

        assert result.valid, f"Expected valid brief, got errors: {result.errors}"
        assert result.coverage["missing_variant_ids"] == []
        assert result.coverage["missing_comparison_ids"] == []
        assert len(result.coverage["expected_variant_ids"]) == 6
        assert len(result.coverage["expected_comparison_ids"]) == 9

    def test_missing_variant_fails_for_calibration_manifest(self, tmp_path: Path):
        manifest = _make_calibration_manifest(tmp_path)
        brief = _make_calibration_brief()
        brief["variants"] = [
            item
            for item in brief["variants"]
            if item["variant_id"] != "co2_cap_tight"
        ]

        result = validate_brief(brief, manifest)

        assert not result.valid
        assert "co2_cap_tight" in result.coverage["missing_variant_ids"]
        assert any("Missing variant" in err for err in result.errors)

    def test_missing_comparison_fails_for_calibration_manifest(self, tmp_path: Path):
        manifest = _make_calibration_manifest(tmp_path)
        brief = _make_calibration_brief()
        brief["comparison_plan"] = [
            item
            for item in brief["comparison_plan"]
            if item["comparison_id"] != "baseline_vs_high_gas_price"
        ]

        result = validate_brief(brief, manifest)

        assert not result.valid
        assert "baseline_vs_high_gas_price" in result.coverage["missing_comparison_ids"]
        assert any("Missing comparison" in err for err in result.errors)


class TestToyIndustryCalibrationInterpretationCoverage:
    def test_full_calibration_interpretation_passes(self, tmp_path: Path):
        manifest = _make_calibration_manifest(tmp_path)
        interpretation = _make_calibration_interpretation()

        result = validate_interpretation(interpretation, manifest)

        assert result.valid
        assert result.coverage["missing_comparison_ids"] == []
        assert len(result.coverage["expected_comparison_ids"]) == 9

    def test_missing_comparison_fails_for_interpretation(self, tmp_path: Path):
        manifest = _make_calibration_manifest(tmp_path)
        interpretation = _make_calibration_interpretation()
        interpretation["comparison_interpretations"] = [
            item
            for item in interpretation["comparison_interpretations"]
            if item["comparison_id"] != "baseline_vs_high_gas_price"
        ]

        result = validate_interpretation(interpretation, manifest)

        assert not result.valid
        assert "baseline_vs_high_gas_price" in result.coverage["missing_comparison_ids"]
        assert any("Missing comparison interpretation" in err for err in result.errors)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderBriefMd:
    def test_brief_md_has_key_sections(self):
        brief = _make_valid_brief()
        md = render_brief_md(brief)
        assert "# Experiment Brief:" in md
        assert "## Research Question" in md
        assert "## Design Approach" in md
        assert "## Variants" in md
        assert "## Comparison Plan" in md
        assert "## Design Reasoning" in md
