"""v0.2 naming convention lint rules for VedaLang."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from vedalang.conventions import (
    is_legacy_commodity_namespace,
    split_commodity_namespace,
)
from vedalang.versioning import looks_like_v0_2_source

V0_2_COMMODITY_NAMESPACE_TO_KINDS: dict[str, frozenset[str]] = {
    "primary": frozenset({"primary"}),
    "secondary": frozenset({"secondary"}),
    "resource": frozenset({"material"}),
    "service": frozenset({"service"}),
    "emission": frozenset({"emission"}),
    "material": frozenset({"material"}),
    "certificate": frozenset({"certificate"}),
}
LEGACY_NAMESPACE_ALIASES = {"fuel", "energy"}


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
    """Commodity IDs must use canonical v0.2 namespaces."""

    code = "N001"
    description = "Commodity ID namespace must match canonical conventions"

    def __init__(self) -> None:
        self._valid_namespaces = set(V0_2_COMMODITY_NAMESPACE_TO_KINDS)
        self._namespace_to_kinds = V0_2_COMMODITY_NAMESPACE_TO_KINDS

    def check(self, source: dict) -> list[LintDiagnostic]:
        if not looks_like_v0_2_source(source):
            return []

        diagnostics: list[LintDiagnostic] = []
        for index, commodity in enumerate(source.get("commodities", []) or []):
            commodity_id = commodity.get("id", "")
            kind = commodity.get("kind")
            if not commodity_id or not isinstance(kind, str):
                continue
            namespace, _ = split_commodity_namespace(str(commodity_id))
            if namespace is None:
                continue
            path = f"commodities[{index}].id"
            if (
                is_legacy_commodity_namespace(namespace)
                or namespace in LEGACY_NAMESPACE_ALIASES
            ):
                expected = [
                    candidate
                    for candidate, allowed_kinds in self._namespace_to_kinds.items()
                    if kind in allowed_kinds
                ]
                expected_text = ", ".join(f"{candidate}:*" for candidate in expected)
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=(
                            f"Legacy commodity prefix '{namespace}:' in "
                            f"'{commodity_id}' is deprecated; use {expected_text} "
                            f"for kind '{kind}'."
                        ),
                        path=path,
                    )
                )
                continue
            if namespace not in self._valid_namespaces:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=(
                            f"Unknown commodity namespace '{namespace}' in "
                            f"'{commodity_id}'. Expected one of: "
                            f"{sorted(self._valid_namespaces)}"
                        ),
                        path=path,
                    )
                )
                continue
            expected_kinds = self._namespace_to_kinds.get(namespace, frozenset())
            if kind not in expected_kinds:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=(
                            f"Commodity '{commodity_id}' namespace '{namespace}' "
                            f"implies kind in {sorted(expected_kinds)}, but "
                            f"commodity kind is '{kind}'."
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
