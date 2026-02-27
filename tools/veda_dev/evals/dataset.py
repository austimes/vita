"""Dataset loading and profile expansion for llm-lint evals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    check_id: str
    category: str
    engine: str
    source: str
    component: str | None
    expected: dict[str, Any]


@dataclass(frozen=True)
class EvalDataset:
    version: int
    profiles: dict[str, list[str]]
    cases: dict[str, EvalCase]


def default_dataset_path() -> Path:
    return Path(__file__).resolve().parent / "datasets" / "llm_lint_cases.yaml"


def load_dataset(path: Path | None = None) -> EvalDataset:
    resolved = path or default_dataset_path()
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))

    version = int(raw.get("version", 1))
    profiles = {
        str(name): [str(case_id) for case_id in (case_ids or [])]
        for name, case_ids in (raw.get("profiles", {}) or {}).items()
    }

    cases: dict[str, EvalCase] = {}
    for case_id, payload in (raw.get("cases", {}) or {}).items():
        source = str(payload.get("source", ""))
        if not source:
            raise ValueError(f"Case {case_id} missing source")
        cases[str(case_id)] = EvalCase(
            case_id=str(case_id),
            check_id=str(payload.get("check_id", "")),
            category=str(payload.get("category", "")),
            engine=str(payload.get("engine", "")),
            source=source,
            component=payload.get("component"),
            expected=dict(payload.get("expected") or {}),
        )

    _validate_profile_counts(profiles)
    return EvalDataset(version=version, profiles=profiles, cases=cases)


def _validate_profile_counts(profiles: dict[str, list[str]]) -> None:
    expected = {"smoke": 5, "ci": 10, "deep": 30}
    for profile, size in expected.items():
        actual = len(profiles.get(profile, []))
        if actual != size:
            raise ValueError(
                f"Profile '{profile}' expected {size} cases but found {actual}"
            )


def cases_for_profile(dataset: EvalDataset, profile: str) -> list[EvalCase]:
    if profile not in dataset.profiles:
        allowed = ", ".join(sorted(dataset.profiles.keys()))
        raise ValueError(f"Unknown profile '{profile}'. Available: {allowed}")

    result: list[EvalCase] = []
    for case_id in dataset.profiles[profile]:
        case = dataset.cases.get(case_id)
        if case is None:
            raise ValueError(f"Profile '{profile}' references missing case '{case_id}'")
        result.append(case)
    return result
