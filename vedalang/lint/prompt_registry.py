"""Versioned prompt registry and manifest verification for LLM lint checks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"

CHECK_PROMPT_PATHS = {
    "llm.structure.res_assessment": "res-assessment",
    "llm.units.component_quorum": "unit-check",
}


@dataclass(frozen=True)
class PromptBundle:
    check_id: str
    version: str
    directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    @property
    def system_path(self) -> Path:
        return self.directory / "system.txt"

    @property
    def user_prefix_path(self) -> Path:
        return self.directory / "user_prefix.txt"

    @property
    def response_schema_path(self) -> Path:
        return self.directory / "response_schema.json"


def _version_key(version: str) -> tuple[int, str]:
    m = re.fullmatch(r"v(\d+)", version)
    if m:
        return int(m.group(1)), version
    return -1, version


def prompt_root_for_check(check_id: str) -> Path:
    rel = CHECK_PROMPT_PATHS.get(check_id)
    if rel is None:
        raise ValueError(f"No prompt path registered for check_id '{check_id}'")
    return PROMPTS_ROOT / rel


def available_prompt_versions(check_id: str) -> list[str]:
    root = prompt_root_for_check(check_id)
    if not root.exists():
        return []
    versions = [
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and (p / "system.txt").exists()
        and (p / "user_prefix.txt").exists()
    ]
    return sorted(versions, key=_version_key)


def resolve_prompt_versions(check_id: str, requested_version: str | None) -> list[str]:
    versions = available_prompt_versions(check_id)
    if not versions:
        raise RuntimeError(f"No prompt versions found for check_id '{check_id}'")

    if requested_version is None:
        return [versions[-1]]

    if requested_version == "all":
        return versions

    if requested_version not in versions:
        raise ValueError(
            f"Unknown prompt version '{requested_version}' for {check_id}. "
            f"Available: {', '.join(versions)}"
        )
    return [requested_version]


def get_prompt_bundle(check_id: str, version: str) -> PromptBundle:
    directory = prompt_root_for_check(check_id) / version
    if not directory.exists():
        raise RuntimeError(
            f"Prompt version not found for {check_id}: {version} ({directory})"
        )
    bundle = PromptBundle(check_id=check_id, version=version, directory=directory)
    verify_prompt_manifest(bundle)
    return bundle


def _files_for_hash(bundle: PromptBundle) -> list[Path]:
    return sorted(
        [
            p
            for p in bundle.directory.iterdir()
            if p.is_file() and p.name != "manifest.json"
        ],
        key=lambda p: p.name,
    )


def compute_prompt_bundle_hash(bundle: PromptBundle) -> str:
    digest = hashlib.sha256()
    for path in _files_for_hash(bundle):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_prompt_manifest(bundle: PromptBundle) -> None:
    if not bundle.manifest_path.exists():
        raise RuntimeError(
            f"Prompt manifest missing: {bundle.manifest_path}. "
            "Prompt versions must include manifest.json with content hash."
        )
    try:
        manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid prompt manifest JSON: {bundle.manifest_path}"
        ) from exc

    expected = str(manifest.get("content_sha256", "")).strip()
    if not expected:
        raise RuntimeError(
            f"Prompt manifest missing content_sha256: {bundle.manifest_path}"
        )

    actual = compute_prompt_bundle_hash(bundle)
    if actual != expected:
        raise RuntimeError(
            f"Prompt manifest hash mismatch for {bundle.check_id}:{bundle.version}. "
            f"expected={expected} actual={actual}. "
            "Do not edit historical prompt versions in-place. "
            "Create a new version directory."
        )


def load_prompt_template(check_id: str, version: str, filename: str) -> str:
    bundle = get_prompt_bundle(check_id, version)
    path = bundle.directory / filename
    if not path.exists():
        raise RuntimeError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
