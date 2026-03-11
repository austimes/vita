"""Naming convention lint rules for the active VedaLang DSL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from vedalang.versioning import looks_like_v0_2_source


@dataclass
class LintDiagnostic:
    """A naming convention lint diagnostic."""

    code: str
    severity: str
    message: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


class NamingLintRule(ABC):
    code: str
    description: str

    @abstractmethod
    def check(self, source: dict) -> list[LintDiagnostic]:
        raise NotImplementedError


class N001_CommodityIDGrammar(NamingLintRule):
    """Commodity IDs must use bare authored names."""

    code = "N001"
    description = "Commodity IDs must not use lowered namespace prefixes"

    def check(self, source: dict) -> list[LintDiagnostic]:
        if not looks_like_v0_2_source(source):
            return []

        diagnostics: list[LintDiagnostic] = []
        for index, commodity in enumerate(source.get("commodities", []) or []):
            commodity_id = commodity.get("id", "")
            if not commodity_id:
                continue
            path = f"commodities[{index}].id"
            if ":" in str(commodity_id):
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=(
                            f"Commodity '{commodity_id}' uses a lowered namespace "
                            "prefix. In v0.3 authored commodity IDs must be bare "
                            "names; move the ontology into `type` and `energy_form`."
                        ),
                        path=path,
                    )
                )
        return diagnostics


class N011_SnakeCasePreferred(NamingLintRule):
    """Top-level v0.2 object IDs should prefer snake_case."""

    code = "N011"
    description = "IDs should use snake_case (underscores, not dashes)"

    def check(self, source: dict) -> list[LintDiagnostic]:
        if not looks_like_v0_2_source(source):
            return []

        diagnostics: list[LintDiagnostic] = []
        sections = (
            "technologies",
            "technology_roles",
            "stock_characterizations",
            "spatial_layers",
            "spatial_measure_sets",
            "temporal_index_series",
            "region_partitions",
            "zone_overlays",
            "sites",
            "facilities",
            "fleets",
            "opportunities",
            "networks",
            "runs",
        )
        for section in sections:
            for index, item in enumerate(source.get(section, []) or []):
                identifier = item.get("id", "")
                if "-" not in str(identifier):
                    continue
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="warning",
                        message=(
                            f"{section[:-1].replace('_', ' ')} '{identifier}' uses "
                            f"dashes. Prefer snake_case: "
                            f"'{str(identifier).replace('-', '_')}'"
                        ),
                        path=f"{section}[{index}].id",
                    )
                )
        return diagnostics


ALL_NAMING_RULES: list[NamingLintRule] = [
    N001_CommodityIDGrammar(),
    N011_SnakeCasePreferred(),
]


def lint_naming_conventions(source: dict) -> list[LintDiagnostic]:
    diagnostics: list[LintDiagnostic] = []
    for rule in ALL_NAMING_RULES:
        try:
            diagnostics.extend(rule.check(source))
        except Exception as exc:
            diagnostics.append(
                LintDiagnostic(
                    code=f"{rule.code}_ERROR",
                    severity="error",
                    message=f"Rule {rule.code} failed: {exc}",
                    path="",
                )
            )
    return sorted(
        diagnostics,
        key=lambda diag: (diag.severity != "error", diag.code, diag.path),
    )
