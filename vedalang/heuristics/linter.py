"""VedaLang v0.2 heuristics linter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from vedalang.compiler.v0_2_resolution import parse_quantity
from vedalang.versioning import looks_like_v0_2_source


@dataclass
class LintIssue:
    """A heuristic lint issue found in a VedaLang model."""

    code: str
    severity: str  # "warning" | "error"
    message: str
    location: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "context": self.context,
        }


class HeuristicRule(ABC):
    """Base class for heuristic rules."""

    code: str
    description: str
    default_severity: str = "warning"

    @abstractmethod
    def apply(self, source: dict) -> list[LintIssue]:
        raise NotImplementedError


def _commodity_kind_map(source: dict[str, Any]) -> dict[str, str]:
    return {
        str(commodity.get("id")): str(commodity.get("type"))
        for commodity in source.get("commodities", []) or []
        if commodity.get("id") and commodity.get("type")
    }


def _technology_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(technology.get("id")): technology
        for technology in source.get("technologies", []) or []
        if technology.get("id")
    }


def _role_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(role.get("id")): role
        for role in source.get("technology_roles", []) or []
        if role.get("id")
    }


def _asset_sections(source: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        ("facilities", list(source.get("facilities", []) or [])),
        ("fleets", list(source.get("fleets", []) or [])),
    ]


def _service_role_ids(source: dict[str, Any]) -> set[str]:
    commodity_kinds = _commodity_kind_map(source)
    service_roles: set[str] = set()
    for role_id, role in _role_map(source).items():
        if commodity_kinds.get(role.get("primary_service")) == "service":
            service_roles.add(role_id)
    return service_roles


def _quantity_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return parse_quantity(value).value


class H001_ServiceAssetWithoutStock(HeuristicRule):
    """Service-delivering facilities/fleets usually need explicit stock."""

    code = "H001"
    description = "Service asset without stock observations"
    default_severity = "warning"

    def apply(self, source: dict) -> list[LintIssue]:
        if not looks_like_v0_2_source(source):
            return []

        issues: list[LintIssue] = []
        service_roles = _service_role_ids(source)
        for section_name, assets in _asset_sections(source):
            for index, asset in enumerate(assets):
                role_id = asset.get("technology_role")
                if role_id not in service_roles:
                    continue
                stock = asset.get("stock")
                has_items = bool((stock or {}).get("items"))
                has_new_build_limits = bool(asset.get("new_build_limits"))
                if has_items or has_new_build_limits:
                    continue
                asset_id = asset.get("id", f"{section_name}[{index}]")
                issues.append(
                    LintIssue(
                        code=self.code,
                        severity=self.default_severity,
                        message=(
                            f"{section_name[:-1].capitalize()} '{asset_id}' uses "
                            f"service role '{role_id}' but has no stock observations. "
                            "Add stock.items for existing base-year service capacity, "
                            "add new_build_limits for a greenfield build boundary, "
                            "or remove the asset until it is modeled."
                        ),
                        location=f"{section_name}[{index}].stock",
                        context={
                            "asset": asset_id,
                            "technology_role": role_id,
                            "section": section_name,
                        },
                    )
                )
        return issues


class H002_AnnualActivityStockWithoutSupply(HeuristicRule):
    """Warn when annual-activity demand stock has no installed-capacity supplier."""

    code = "H002"
    description = "Annual-activity stock without matching installed-capacity supply"
    default_severity = "warning"

    def apply(self, source: dict) -> list[LintIssue]:
        if not looks_like_v0_2_source(source):
            return []

        issues: list[LintIssue] = []
        roles = _role_map(source)
        service_roles = _service_role_ids(source)

        installed_capacity_by_service: dict[str, float] = {}
        annual_activity_by_service: dict[str, float] = {}

        for _, assets in _asset_sections(source):
            for asset in assets:
                role_id = asset.get("technology_role")
                role = roles.get(role_id)
                if role is None:
                    continue
                service_id = role.get("primary_service")
                for item in (asset.get("stock") or {}).get("items", []) or []:
                    metric = item.get("metric")
                    observed = (item.get("observed") or {}).get("value")
                    if not metric or observed is None:
                        continue
                    value = _quantity_value(observed)
                    if metric == "installed_capacity":
                        installed_capacity_by_service[service_id] = (
                            installed_capacity_by_service.get(service_id, 0.0) + value
                        )
                    elif metric == "annual_activity":
                        annual_activity_by_service[service_id] = (
                            annual_activity_by_service.get(service_id, 0.0) + value
                        )

        for section_name, assets in _asset_sections(source):
            for index, asset in enumerate(assets):
                role_id = asset.get("technology_role")
                if role_id not in service_roles:
                    continue
                service_id = roles[role_id].get("primary_service")
                annual_activity = annual_activity_by_service.get(service_id, 0.0)
                installed_capacity = installed_capacity_by_service.get(service_id, 0.0)
                if annual_activity <= 0 or installed_capacity > 0:
                    continue
                asset_id = asset.get("id", f"{section_name}[{index}]")
                issues.append(
                    LintIssue(
                        code=self.code,
                        severity=self.default_severity,
                        message=(
                            f"{section_name[:-1].capitalize()} '{asset_id}' records "
                            f"annual_activity stock for service '{service_id}' but no "
                            "matching installed-capacity stock was found on assets for "
                            "that same service. Confirm the service is intentionally "
                            "activity-only or add installed-capacity stock."
                        ),
                        location=f"{section_name}[{index}].stock",
                        context={
                            "asset": asset_id,
                            "service": service_id,
                            "annual_activity": annual_activity,
                            "installed_capacity": installed_capacity,
                        },
                    )
                )
        return issues


ALL_RULES: list[HeuristicRule] = [
    H001_ServiceAssetWithoutStock(),
    H002_AnnualActivityStockWithoutSupply(),
]


@dataclass
class HeuristicsResult:
    """Result of running all heuristic checks."""

    issues: list[LintIssue]
    checks_run: list[dict[str, str]]
    error_count: int
    warning_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "checks_run": self.checks_run,
            "summary": {
                "total_checks": len(self.checks_run),
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "issue_count": len(self.issues),
            },
        }


def get_available_checks() -> list[dict[str, str]]:
    return [{"code": rule.code, "description": rule.description} for rule in ALL_RULES]


def run_heuristics(source: dict) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for rule in ALL_RULES:
        try:
            issues.extend(rule.apply(source))
        except Exception as exc:
            issues.append(
                LintIssue(
                    code=f"{rule.code}_ERROR",
                    severity="warning",
                    message=f"Heuristic rule {rule.code} failed: {exc}",
                    context={"exception": str(exc)},
                )
            )
    return issues


def run_heuristics_detailed(source: dict) -> HeuristicsResult:
    issues = run_heuristics(source)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    return HeuristicsResult(
        issues=issues,
        checks_run=get_available_checks(),
        error_count=error_count,
        warning_count=warning_count,
    )
