"""Tests for prompt registry versioning and immutability checks."""

from __future__ import annotations

import json
import shutil

import pytest

from vedalang.lint.prompt_registry import (
    PromptBundle,
    compute_prompt_bundle_hash,
    get_prompt_bundle,
    resolve_prompt_versions,
    verify_prompt_manifest,
)


def test_structure_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.structure.res_assessment", "v1")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_units_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.units.component_quorum", "v1")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_structure_v2_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.structure.res_assessment", "v2")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_units_v2_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.units.component_quorum", "v2")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_units_v3_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.units.component_quorum", "v3")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_units_v5_prompt_manifest_validates():
    bundle = get_prompt_bundle("llm.units.component_quorum", "v5")
    digest = compute_prompt_bundle_hash(bundle)
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["content_sha256"] == digest


def test_prompt_version_all_resolves_sorted_versions():
    versions = resolve_prompt_versions("llm.structure.res_assessment", "all")
    assert "v1" in versions
    assert "v2" in versions


def test_manifest_mismatch_raises(tmp_path):
    source_bundle = get_prompt_bundle("llm.units.component_quorum", "v1")
    copied = tmp_path / "v1"
    shutil.copytree(source_bundle.directory, copied)

    # Tamper with a historical prompt file without manifest update.
    system_file = copied / "system.txt"
    system_file.write_text(system_file.read_text(encoding="utf-8") + "\n# tampered\n")

    tampered = PromptBundle(
        check_id="llm.units.component_quorum",
        version="v1",
        directory=copied,
    )

    with pytest.raises(RuntimeError, match="hash mismatch"):
        verify_prompt_manifest(tampered)
