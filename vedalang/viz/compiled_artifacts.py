"""Compiled artifact resolver for RES query engine.

Provides cached access to TableIR and xl2times manifest artifacts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CACHE_VERSION = "1"


@dataclass
class CompiledArtifacts:
    """Resolved compiled artifacts and diagnostics."""

    status: str
    artifacts: dict[str, str] = field(default_factory=dict)
    diagnostics: list[dict[str, str]] = field(default_factory=list)
    tableir: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None


def _diagnostic(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _cache_root(workspace_root: Path) -> Path:
    return workspace_root / ".cache" / "vedalang" / "res_viewer"


def _hash_key(file_path: Path, case_name: str | None, truth: str) -> str:
    content = file_path.read_bytes()
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(CACHE_VERSION.encode("utf-8"))
    digest.update((case_name or "").encode("utf-8"))
    digest.update(truth.encode("utf-8"))
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_tableir(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _save_cache_index(index_path: Path, payload: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2) + "\n")


def _resolve_from_index(index: dict[str, Any]) -> CompiledArtifacts | None:
    artifacts = index.get("artifacts", {})
    tableir_path = Path(artifacts.get("tableir_file", ""))
    manifest_path = Path(artifacts.get("manifest_file", ""))

    tableir = _load_tableir(tableir_path) if tableir_path else None
    manifest = _load_json(manifest_path) if manifest_path else None

    if tableir is None and manifest is None:
        return None

    status = "ok" if manifest is not None else "partial"
    diagnostics = []
    if manifest is None:
        diagnostics.append(
            _diagnostic(
                "COMPILED_MANIFEST_MISSING",
                "warning",
                "Cached manifest missing; using TableIR fallback.",
            )
        )

    return CompiledArtifacts(
        status=status,
        artifacts={k: v for k, v in artifacts.items() if isinstance(v, str)},
        diagnostics=diagnostics,
        tableir=tableir,
        manifest=manifest,
    )


def resolve_compiled_artifacts(
    *,
    file_path: Path,
    workspace_root: Path,
    case_name: str | None,
    truth: str = "auto",
    use_cache: bool = True,
) -> CompiledArtifacts:
    """Resolve compiled artifacts using pipeline with cache."""
    from tools.veda_dev.pipeline import run_pipeline

    file_path = file_path.resolve()
    workspace_root = workspace_root.resolve()
    cache_root = _cache_root(workspace_root)
    cache_key = _hash_key(file_path, case_name, truth)
    cache_dir = cache_root / cache_key
    index_path = cache_dir / "index.json"

    if use_cache and index_path.exists():
        cached = _load_json(index_path)
        if cached:
            resolved = _resolve_from_index(cached)
            if resolved is not None:
                resolved.artifacts["cache_key"] = cache_key
                return resolved

    diagnostics: list[dict[str, str]] = []
    artifacts: dict[str, str] = {"cache_key": cache_key}

    work_dir = cache_dir / "work"
    if work_dir.exists():
        shutil.rmtree(work_dir)

    result = run_pipeline(
        file_path,
        input_kind="vedalang",
        no_solver=True,
        keep_workdir=True,
        work_dir=work_dir,
        verbose=False,
    )

    artifacts.update({
        "work_dir": result.work_dir,
        "tableir_file": result.artifacts.get("tableir_file", ""),
        "excel_dir": result.artifacts.get("excel_dir", ""),
        "dd_dir": result.artifacts.get("dd_dir", ""),
    })

    xl_step = result.steps.get("xl2times")
    manifest_file = ""
    if xl_step and xl_step.artifacts.get("manifest_file"):
        manifest_file = str(xl_step.artifacts["manifest_file"])
    if manifest_file:
        artifacts["manifest_file"] = manifest_file

    compile_step = result.steps.get("compile")
    if compile_step and compile_step.errors:
        for msg in compile_step.errors:
            diagnostics.append(_diagnostic("COMPILE_ERROR", "error", msg))

    if xl_step:
        for msg in xl_step.errors:
            diagnostics.append(_diagnostic("XL2TIMES_ERROR", "error", msg))
        for msg in xl_step.warnings:
            diagnostics.append(_diagnostic("XL2TIMES_WARNING", "warning", msg))

    tableir = _load_tableir(Path(artifacts.get("tableir_file", "")))
    manifest = _load_json(Path(manifest_file)) if manifest_file else None

    if manifest is not None:
        status = "ok"
    elif tableir is not None:
        status = "partial"
        diagnostics.append(
            _diagnostic(
                "COMPILED_TABLEIR_FALLBACK",
                "warning",
                "Using TableIR fallback because xl2times manifest was unavailable.",
            )
        )
    else:
        status = "error"
        diagnostics.append(
            _diagnostic(
                "COMPILED_ARTIFACTS_UNAVAILABLE",
                "error",
                "No compiled artifacts available from pipeline execution.",
            )
        )

    _save_cache_index(
        index_path,
        {
            "version": CACHE_VERSION,
            "cache_key": cache_key,
            "status": status,
            "artifacts": artifacts,
        },
    )

    return CompiledArtifacts(
        status=status,
        artifacts=artifacts,
        diagnostics=diagnostics,
        tableir=tableir,
        manifest=manifest,
    )
