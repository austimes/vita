"""Tests for vita.experiment_manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from vita.experiment_manifest import (
    ExperimentManifestError,
    load_experiment_manifest,
    validate_manifest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_MANIFEST = """\
schema_version: 1
id: test-exp
title: Test Experiment
question: Does it work?

baseline:
  id: base
  model: model.veda.yaml
  run: default

variants:
  - id: variant-a
    from: base
    hypothesis: "Changing nothing should still work"

comparisons:
  - id: base-vs-a
    baseline: base
    variant: variant-a

analyses:
  - id: main
    question: "Is variant-a different?"
    comparisons: [base-vs-a]
"""


def _write_manifest(tmp_path: Path, content: str, *, create_model: bool = True) -> Path:
    manifest_path = tmp_path / "experiment.yaml"
    manifest_path.write_text(content, encoding="utf-8")
    if create_model:
        (tmp_path / "model.veda.yaml").write_text("# stub", encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# Valid manifest loading
# ---------------------------------------------------------------------------


class TestLoadValidManifest:
    def test_minimal_manifest(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)

        assert m.schema_version == 1
        assert m.id == "test-exp"
        assert m.title == "Test Experiment"
        assert m.question == "Does it work?"
        assert m.manifest_path == path.resolve()

    def test_baseline_parsed(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)

        assert m.baseline.id == "base"
        assert m.baseline.run == "default"
        assert m.baseline.model == (tmp_path / "model.veda.yaml").resolve()
        assert m.baseline.case == "scenario"  # default

    def test_variant_inherits_from_baseline(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)

        va = m.variants[0]
        assert va.id == "variant-a"
        assert va.model == m.baseline.model
        assert va.run == m.baseline.run
        assert va.from_case == "base"
        assert va.hypothesis == "Changing nothing should still work"

    def test_all_cases(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        cases = m.all_cases()
        assert len(cases) == 2
        assert cases[0].id == "base"
        assert cases[1].id == "variant-a"

    def test_get_case(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        assert m.get_case("base").id == "base"
        assert m.get_case("variant-a").id == "variant-a"

    def test_get_comparison(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        comp = m.get_comparison("base-vs-a")
        assert comp.baseline == "base"
        assert comp.variant == "variant-a"

    def test_defaults_populated(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        assert m.defaults.case == "scenario"
        assert m.defaults.no_sankey is False
        assert "objective" in m.defaults.metrics
        assert m.defaults.checks.require_pipeline_success is True
        assert m.defaults.checks.require_solver_status == ["optimal"]

    def test_extensions_parsed(self, tmp_path: Path) -> None:
        content = _MINIMAL_MANIFEST + """\
extensions:
  - id: A
    question: "Sub-question A"
"""
        path = _write_manifest(tmp_path, content)
        m = load_experiment_manifest(path)
        assert len(m.extensions) == 1
        assert m.extensions[0].id == "A"
        assert m.extensions[0].question == "Sub-question A"


# ---------------------------------------------------------------------------
# Variant inheritance
# ---------------------------------------------------------------------------


class TestVariantInheritance:
    def test_variant_overrides_model(self, tmp_path: Path) -> None:
        (tmp_path / "other.veda.yaml").write_text("# stub", encoding="utf-8")
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: v1
    from: base
    model: other.veda.yaml
"""
        path = _write_manifest(tmp_path, content)
        m = load_experiment_manifest(path)
        assert m.variants[0].model == (tmp_path / "other.veda.yaml").resolve()
        assert m.variants[0].run == "default"  # inherited

    def test_variant_overrides_run(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: v1
    from: base
    run: alt-run
"""
        path = _write_manifest(tmp_path, content)
        m = load_experiment_manifest(path)
        assert m.variants[0].model == m.baseline.model  # inherited
        assert m.variants[0].run == "alt-run"

    def test_variant_without_from_requires_model_run(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: v1
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="Missing required field"):
            load_experiment_manifest(path)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_relative_to_manifest(self, tmp_path: Path) -> None:
        subdir = tmp_path / "experiments"
        subdir.mkdir()
        (subdir / "my_model.veda.yaml").write_text("# stub", encoding="utf-8")
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: my_model.veda.yaml
  run: default
"""
        manifest_path = subdir / "experiment.yaml"
        manifest_path.write_text(content, encoding="utf-8")
        m = load_experiment_manifest(manifest_path)
        assert m.baseline.model == (subdir / "my_model.veda.yaml").resolve()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_missing_required_top_level(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="Missing required field"):
            load_experiment_manifest(path)

    def test_unsupported_schema_version(self, tmp_path: Path) -> None:
        content = """\
schema_version: 99
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="Unsupported schema_version"):
            load_experiment_manifest(path)

    def test_rejects_tableir_model_path(self, tmp_path: Path) -> None:
        (tmp_path / "model.tableir.yaml").write_text("files: []\n", encoding="utf-8")
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.tableir.yaml
  run: default
"""
        path = _write_manifest(tmp_path, content, create_model=False)
        with pytest.raises(ExperimentManifestError, match="not TableIR"):
            load_experiment_manifest(path)

    def test_rejects_non_veda_model_extension(self, tmp_path: Path) -> None:
        (tmp_path / "model.yaml").write_text("foo: bar\n", encoding="utf-8")
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.yaml
  run: default
"""
        path = _write_manifest(tmp_path, content, create_model=False)
        with pytest.raises(ExperimentManifestError, match="must end with"):
            load_experiment_manifest(path)

    def test_invalid_case_reference_in_comparison(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
comparisons:
  - id: bad
    baseline: base
    variant: nonexistent
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="unknown variant case"):
            load_experiment_manifest(path)

    def test_invalid_comparison_reference_in_analysis(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
analyses:
  - id: a1
    question: Q
    comparisons: [nonexistent]
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="unknown comparison"):
            load_experiment_manifest(path)

    def test_invalid_from_reference(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: v1
    from: nonexistent
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="unknown 'from' case"):
            load_experiment_manifest(path)

    def test_duplicate_case_ids(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: base
    from: base
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="Duplicate case ID"):
            load_experiment_manifest(path)

    def test_duplicate_comparison_ids(self, tmp_path: Path) -> None:
        content = """\
schema_version: 1
id: test
title: T
question: Q
baseline:
  id: base
  model: model.veda.yaml
  run: default
variants:
  - id: v1
    from: base
comparisons:
  - id: dup
    baseline: base
    variant: v1
  - id: dup
    baseline: base
    variant: v1
"""
        path = _write_manifest(tmp_path, content)
        with pytest.raises(ExperimentManifestError, match="Duplicate comparison ID"):
            load_experiment_manifest(path)

    def test_manifest_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ExperimentManifestError, match="not found"):
            load_experiment_manifest(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text(": : :\n  - [", encoding="utf-8")
        with pytest.raises(ExperimentManifestError, match="Invalid YAML"):
            load_experiment_manifest(path)

    def test_get_case_unknown(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        with pytest.raises(ExperimentManifestError, match="Unknown case ID"):
            m.get_case("nonexistent")

    def test_get_comparison_unknown(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        with pytest.raises(ExperimentManifestError, match="Unknown comparison ID"):
            m.get_comparison("nonexistent")


# ---------------------------------------------------------------------------
# Validation warnings
# ---------------------------------------------------------------------------


class TestValidateManifest:
    def test_warns_missing_model_path(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST, create_model=False)
        m = load_experiment_manifest(path)
        warnings = validate_manifest(m)
        assert any("does not exist" in w for w in warnings)

    def test_no_warnings_when_model_exists(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_experiment_manifest(path)
        warnings = validate_manifest(m)
        assert warnings == []
