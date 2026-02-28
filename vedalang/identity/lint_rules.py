"""Naming convention lint rules for VedaLang.

Validates that commodity and process identifiers follow the naming grammar.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from vedalang.identity.parser import (
    VALID_ROLES,
    parse_process_id,
    validate_commodity_id,
)
from vedalang.identity.registry import AbbreviationRegistry


def _identifier_value_and_path(
    item: dict[str, Any],
    *,
    base_path: str,
) -> tuple[str, str]:
    """Return identifier value + JSON path for id/name keyed objects."""
    if "id" in item:
        value = item.get("id")
        return (str(value) if value is not None else "", f"{base_path}.id")
    if "name" in item:
        value = item.get("name")
        return (str(value) if value is not None else "", f"{base_path}.name")
    return "", base_path


@dataclass
class LintDiagnostic:
    """A naming convention lint diagnostic."""

    code: str
    severity: str  # 'error' or 'warning'
    message: str
    path: str  # JSON path to the issue (e.g., "model.commodities[0].name")

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


class NamingLintRule(ABC):
    """Base class for naming lint rules."""

    code: str
    description: str

    @abstractmethod
    def check(self, model: dict) -> list[LintDiagnostic]:
        """Check the model for naming convention violations."""
        raise NotImplementedError


class N001_CommodityIDGrammar(NamingLintRule):
    """TRADABLE must start with C:, SERVICE with S:, EMISSION with E:."""

    code = "N001"
    description = "Commodity ID must match its kind prefix"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, comm in enumerate(model_data.get("commodities", [])):
            name, path = _identifier_value_and_path(
                comm,
                base_path=f"model.commodities[{i}]",
            )
            kind = self._infer_kind(comm)

            if kind is None:
                continue

            result = validate_commodity_id(name, kind, comm.get("context"))

            if not result.valid and result.error:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=result.error,
                        path=path,
                    )
                )

        return diagnostics

    def _infer_kind(self, comm: dict) -> str | None:
        """Infer commodity kind from type field."""
        comm_type = comm.get("type", "")
        kind = comm.get("kind")

        if kind:
            return kind

        type_to_kind = {
            "energy": "TRADABLE",
            "material": "TRADABLE",
            "demand": "SERVICE",
            "emission": "EMISSION",
        }
        return type_to_kind.get(comm_type)


class N002_ProcessIDGrammar(NamingLintRule):
    """Process names must parse as valid P:{TECH}:{ROLE}:{GEO}..."""

    code = "N002"
    description = "Process ID must follow P:TECH:ROLE:GEO grammar"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            result = parse_process_id(name)

            if not result.valid and result.error:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=result.error,
                        path=f"model.processes[{i}].name",
                    )
                )

        return diagnostics


class N003_UnknownTechnologyCode(NamingLintRule):
    """Technology code in process ID must exist in registry."""

    code = "N003"
    description = "Technology code must be registered"

    def __init__(self) -> None:
        self._registry = AbbreviationRegistry()

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            result = parse_process_id(name)

            if result.valid and result.parsed:
                tech_code = result.parsed.technology
                if self._registry.find_tech_by_code(tech_code) is None:
                    diagnostics.append(
                        LintDiagnostic(
                            code=self.code,
                            severity="error",
                            message=f"Unknown technology code: {tech_code}",
                            path=f"model.processes[{i}].name",
                        )
                    )

        return diagnostics


class N004_UnknownRoleCode(NamingLintRule):
    """Role code must be one of: GEN, EUS, CNV, EXT, TRD, STO, CAP, SEQ."""

    code = "N004"
    description = "Role code must be valid"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            parts = name.split(":")
            if len(parts) >= 3:
                role = parts[2]
                if role not in VALID_ROLES:
                    diagnostics.append(
                        LintDiagnostic(
                            code=self.code,
                            severity="error",
                            message=(
                                f"Unknown role code: {role}. "
                                f"Must be one of: {sorted(VALID_ROLES)}"
                            ),
                            path=f"model.processes[{i}].name",
                        )
                    )

        return diagnostics


class N005_GeoNotInRegions(NamingLintRule):
    """GEO segment in process ID must be in model.regions."""

    code = "N005"
    description = "GEO segment must be a defined region"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})
        regions = set(model_data.get("regions", []))

        if not regions:
            return diagnostics

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            result = parse_process_id(name)

            if result.valid and result.parsed:
                geo = result.parsed.geo
                base_geo = geo.split(".")[0]
                if base_geo not in regions:
                    diagnostics.append(
                        LintDiagnostic(
                            code=self.code,
                            severity="error",
                            message=(
                                f"GEO '{geo}' not in model regions: "
                                f"{sorted(regions)}"
                            ),
                            path=f"model.processes[{i}].name",
                        )
                    )

        return diagnostics


class N006_EUSRequiresSegment(NamingLintRule):
    """If role=EUS, process ID must include segment (sector.segment)."""

    code = "N006"
    description = "EUS role requires a segment"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            result = parse_process_id(name)

            is_eus_segment_error = (
                not result.valid
                and result.error
                and "EUS requires a segment" in result.error
            )
            if is_eus_segment_error:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=result.error,
                        path=f"model.processes[{i}].name",
                    )
                )

        return diagnostics


class N007_EUSMustOutputService(NamingLintRule):
    """If role=EUS, process must output at least one SERVICE commodity."""

    code = "N007"
    description = "EUS process must output a SERVICE commodity"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        commodity_kinds = {}
        for comm in model_data.get("commodities", []):
            name = comm.get("name", "")
            comm_type = comm.get("type", "")
            kind = comm.get("kind")
            if kind:
                commodity_kinds[name] = kind
            elif comm_type == "demand":
                commodity_kinds[name] = "SERVICE"

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")

            if not name.startswith("P:"):
                continue

            result = parse_process_id(name)

            if result.valid and result.parsed and result.parsed.role == "EUS":
                outputs = proc.get("outputs", [])
                has_service = any(
                    commodity_kinds.get(o.get("commodity")) == "SERVICE"
                    for o in outputs
                )
                if not has_service:
                    diagnostics.append(
                        LintDiagnostic(
                            code=self.code,
                            severity="error",
                            message=(
                                f"EUS process '{name}' must output at least "
                                "one SERVICE commodity"
                            ),
                            path=f"model.processes[{i}].outputs",
                        )
                    )

        return diagnostics


ROLE_SANKEY_MAP = {
    "GEN": {"GEN"},
    "EUS": {"END", "SRV"},
    "EXT": {"SUP"},
    "CNV": {"PRC"},
    "TRD": {"XFR", "EXP"},
}


class N008_RoleSankeyMismatch(NamingLintRule):
    """Role and sankey_stage should be consistent."""

    code = "N008"
    description = "Role and sankey_stage should be consistent"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, proc in enumerate(model_data.get("processes", [])):
            name = proc.get("name", "")
            sankey_stage = proc.get("sankey_stage")

            if not name.startswith("P:") or sankey_stage is None:
                continue

            result = parse_process_id(name)

            if result.valid and result.parsed:
                role = result.parsed.role
                expected_stages = ROLE_SANKEY_MAP.get(role, set())

                if expected_stages and sankey_stage not in expected_stages:
                    diagnostics.append(
                        LintDiagnostic(
                            code=self.code,
                            severity="warning",
                            message=(
                                f"Role '{role}' typically has sankey_stage in "
                                f"{sorted(expected_stages)}, but got '{sankey_stage}'"
                            ),
                            path=f"model.processes[{i}].sankey_stage",
                        )
                    )

        return diagnostics


class N009_ServiceInTradeLink(NamingLintRule):
    """SERVICE commodities cannot be used in trade_links."""

    code = "N009"
    description = "SERVICE commodities cannot be traded"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        service_commodities = set()
        for comm in model_data.get("commodities", []):
            name = comm.get("name", "")
            comm_type = comm.get("type", "")
            kind = comm.get("kind")

            if kind == "SERVICE" or comm_type == "demand":
                service_commodities.add(name)
            elif name.startswith("S:"):
                service_commodities.add(name)

        for i, link in enumerate(model_data.get("trade_links", [])):
            commodity = link.get("commodity", "")
            if commodity in service_commodities:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=(
                            f"SERVICE commodity '{commodity}' cannot be "
                            "used in trade_links"
                        ),
                        path=f"model.trade_links[{i}].commodity",
                    )
                )

        return diagnostics


class N010_ContextKindMismatch(NamingLintRule):
    """SERVICE requires context; TRADABLE/EMISSION must not have context."""

    code = "N010"
    description = "Context field must match commodity kind"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []
        model_data = model.get("model", {})

        for i, comm in enumerate(model_data.get("commodities", [])):
            kind = comm.get("kind")
            context = comm.get("context")
            comm_type = comm.get("type", "")

            if kind is None:
                if comm_type == "demand":
                    kind = "SERVICE"
                elif comm_type == "emission":
                    kind = "EMISSION"
                elif comm_type in ("energy", "material"):
                    kind = "TRADABLE"
                else:
                    continue

            if kind == "SERVICE" and context is None:
                name = comm.get("name", "")
                if not name.startswith("S:"):
                    continue
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message="SERVICE commodity requires 'context' field",
                        path=f"model.commodities[{i}]",
                    )
                )
            elif kind in ("TRADABLE", "EMISSION") and context is not None:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="error",
                        message=f"{kind} commodity must not have 'context' field",
                        path=f"model.commodities[{i}].context",
                    )
                )

        return diagnostics


class N011_SnakeCasePreferred(NamingLintRule):
    """Role, variant, and commodity IDs should use snake_case, not dashes."""

    code = "N011"
    description = "IDs should use snake_case (underscores, not dashes)"

    def check(self, model: dict) -> list[LintDiagnostic]:
        diagnostics = []

        # Check commodity IDs
        model_data = model.get("model", {})
        for i, comm in enumerate(model_data.get("commodities", [])):
            cid = comm.get("id", "")
            if "-" in cid:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="warning",
                        message=(
                            f"Commodity '{cid}' uses dashes. "
                            f"Prefer snake_case: '{cid.replace('-', '_')}'"
                        ),
                        path=f"model.commodities[{i}].id",
                    )
                )

        # Check process role IDs
        for i, role in enumerate(model.get("process_roles", [])):
            rid = role.get("id", "")
            if "-" in rid:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="warning",
                        message=(
                            f"Role '{rid}' uses dashes. "
                            f"Prefer snake_case: '{rid.replace('-', '_')}'"
                        ),
                        path=f"process_roles[{i}].id",
                    )
                )

        # Check process variant IDs
        for i, var in enumerate(model.get("process_variants", [])):
            vid = var.get("id", "")
            if "-" in vid:
                diagnostics.append(
                    LintDiagnostic(
                        code=self.code,
                        severity="warning",
                        message=(
                            f"Variant '{vid}' uses dashes. "
                            f"Prefer snake_case: '{vid.replace('-', '_')}'"
                        ),
                        path=f"process_variants[{i}].id",
                    )
                )

        return diagnostics


ALL_NAMING_RULES: list[NamingLintRule] = [
    N001_CommodityIDGrammar(),
    N002_ProcessIDGrammar(),
    N003_UnknownTechnologyCode(),
    N004_UnknownRoleCode(),
    N005_GeoNotInRegions(),
    N006_EUSRequiresSegment(),
    N007_EUSMustOutputService(),
    N008_RoleSankeyMismatch(),
    N009_ServiceInTradeLink(),
    N010_ContextKindMismatch(),
    N011_SnakeCasePreferred(),
]


def lint_naming_conventions(model: dict) -> list[LintDiagnostic]:
    """Run all naming convention lint rules on a model.

    Returns list of diagnostics sorted by severity (errors first).
    """
    diagnostics = []
    for rule in ALL_NAMING_RULES:
        try:
            diagnostics.extend(rule.check(model))
        except Exception as e:
            diagnostics.append(
                LintDiagnostic(
                    code=f"{rule.code}_ERROR",
                    severity="error",
                    message=f"Rule {rule.code} failed: {e}",
                    path="",
                )
            )

    return sorted(
        diagnostics, key=lambda d: (0 if d.severity == "error" else 1, d.code)
    )


def get_naming_lint_rules() -> list[dict[str, str]]:
    """Get list of all naming lint rules."""
    return [
        {"code": rule.code, "description": rule.description}
        for rule in ALL_NAMING_RULES
    ]
