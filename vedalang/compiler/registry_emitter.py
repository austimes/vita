"""Registry JSON output generation for VedaLang compiler.

Generates a machine-readable registry.json that captures all entities
in a compiled model with their identifiers, parsed components, and metadata.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from vedalang.compiler.naming import parse_process_symbol
from vedalang.compiler.template_resolver import ResolvedProcess
from vedalang.conventions import (
    commodity_namespace_enum,
    is_legacy_commodity_namespace,
    split_commodity_namespace,
)
from vedalang.identity.registry import AbbreviationRegistry


@dataclass
class CommodityRegistryEntry:
    """Registry entry for a commodity."""

    id: str
    kind: str
    code: str
    key: str | None
    context: str | None
    unit: str | None
    description: str | None
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessRegistryEntry:
    """Registry entry for a process."""

    id: str
    template: str | None
    parsed: dict[str, str | None]
    region: str
    technology: str
    role: str
    segment: str | None
    variant: str | None
    vintage: str | None
    sankey_stage: str | None
    description: str | None
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRegistry:
    """Complete registry for a compiled model."""

    model_name: str
    regions: list[str]
    commodities: list[CommodityRegistryEntry]
    processes: list[ProcessRegistryEntry]


class RegistryEmitter:
    """Generates registry.json from a compiled model."""

    def __init__(self, abbreviation_registry: AbbreviationRegistry):
        self._abbrev = abbreviation_registry

    def _map_commodity_kind(self, commodity_type: str) -> str:
        """Map VedaLang commodity type to canonical semantic kind."""
        mapping = {
            "fuel": "carrier",
            "energy": "carrier",
            "service": "service",
            "demand": "service",
            "material": "material",
            "emission": "emission",
            "money": "money",
            "other": "resource",
        }
        return mapping.get(commodity_type, "carrier")

    def _namespace_for_commodity_type(self, commodity_type: str) -> str:
        mapping = {
            "fuel": "primary",
            "energy": "secondary",
            "service": "service",
            "demand": "service",
            "material": "material",
            "emission": "emission",
            "money": "money",
            "other": "resource",
        }
        return mapping.get(commodity_type, "secondary")

    def _build_commodity_id(self, name: str, commodity_type: str) -> str:
        """Build canonical namespaced commodity ID."""
        namespace, base = split_commodity_namespace(name)
        if namespace in set(commodity_namespace_enum()):
            return name
        if namespace and is_legacy_commodity_namespace(namespace):
            if namespace == "E":
                code = base.split(":", 1)[0]
                return f"emission:{code}"
            if namespace == "S":
                code = base.split(":", 1)[0]
                return f"service:{code}"
            if namespace == "C":
                code = base.split(":", 1)[0]
                return f"secondary:{code}"
        canonical_ns = self._namespace_for_commodity_type(commodity_type)
        if not name:
            return f"{canonical_ns}:unknown"
        return f"{canonical_ns}:{name}"

    def _parse_commodity_id(self, commodity_id: str) -> tuple[str, str, str | None]:
        """Parse commodity ID into (base_code, kind, optional_context)."""
        namespace, base = split_commodity_namespace(commodity_id)
        if namespace and namespace in set(commodity_namespace_enum()):
            kind_map = {
                "primary": "carrier",
                "secondary": "carrier",
                "resource": "resource",
                "material": "material",
                "service": "service",
                "emission": "emission",
                "money": "money",
            }
            kind = kind_map.get(namespace, "carrier")
            return base, kind, None
        if namespace and is_legacy_commodity_namespace(namespace):
            parts = commodity_id.split(":")
            if namespace == "S":
                return parts[1] if len(parts) > 1 else "", "service", (
                    parts[2] if len(parts) > 2 else None
                )
            if namespace == "E":
                return parts[1] if len(parts) > 1 else "", "emission", None
            return parts[1] if len(parts) > 1 else "", "carrier", None
        return commodity_id, "carrier", None

    def _parse_legacy_process_id(self, process_id: str) -> dict[str, str | None] | None:
        parts = process_id.split(":")
        if len(parts) < 4 or parts[0] != "P":
            return None
        technology = parts[1]
        role = parts[2]
        geo = parts[3]
        segment = None
        variant = None
        vintage = None
        remaining = parts[4:]
        if role == "EUS" and remaining:
            segment = remaining[0]
            remaining = remaining[1:]
        for part in remaining:
            if part in {"EXIST", "NEW"} and vintage is None:
                vintage = part
            elif segment is None and "." in part:
                segment = part
            elif variant is None:
                variant = part
            elif vintage is None:
                vintage = part
        return {
            "technology": technology,
            "role": role,
            "geo": geo,
            "segment": segment,
            "variant": variant,
            "vintage": vintage,
            "provider_kind": None,
            "provider_id": None,
            "mode": None,
        }

    def emit_commodity(self, commodity: dict) -> CommodityRegistryEntry:
        """Create registry entry for a commodity.

        - Emit canonical namespaced IDs
        - Preserve semantic kind and optional context
        - Include all metadata
        """
        raw_name = commodity.get("id") or commodity.get("name", "")
        commodity_type = commodity.get("type", "energy")
        full_id = self._build_commodity_id(str(raw_name), str(commodity_type))
        code, parsed_kind, parsed_context = self._parse_commodity_id(full_id)
        kind = self._map_commodity_kind(str(commodity_type)) or parsed_kind
        context = commodity.get("context") or parsed_context

        abbrev = self._abbrev.find_commodity_by_code(code)
        key = abbrev.key if abbrev else None

        return CommodityRegistryEntry(
            id=full_id,
            kind=kind,
            code=code,
            key=key,
            context=context,
            unit=commodity.get("unit"),
            description=commodity.get("description"),
            tags=commodity.get("tags", {}),
        )

    def emit_process(
        self, process: dict, template: dict | None = None
    ) -> ProcessRegistryEntry:
        """Create registry entry for a process.

        For inline processes: parse the ID
        For instances: use resolved data
        """
        name = process.get("name", "")
        description = process.get("description")
        tags = process.get("tags", {})

        canonical = parse_process_symbol(name)
        if canonical:
            region = process.get("region", "SINGLE")
            return ProcessRegistryEntry(
                id=name,
                template=None,
                parsed={
                    "technology": canonical["variant_id"],
                    "role": canonical["role_id"],
                    "geo": str(region),
                    "segment": None,
                    "variant": canonical["variant_id"],
                    "vintage": None,
                    "provider_kind": canonical["provider_kind"],
                    "provider_id": canonical["provider_id"],
                    "mode": canonical["mode_id"],
                },
                region=str(region),
                technology=canonical["variant_id"],
                role=canonical["role_id"],
                segment=None,
                variant=canonical["variant_id"],
                vintage=None,
                sankey_stage=process.get("sankey_stage"),
                description=description,
                tags=tags,
            )
        if name.startswith("P:"):
            parsed = self._parse_legacy_process_id(name)
            if parsed is not None:
                return ProcessRegistryEntry(
                    id=name,
                    template=None,
                    parsed=parsed,
                    region=str(parsed["geo"]),
                    technology=str(parsed["technology"]),
                    role=str(parsed["role"]),
                    segment=parsed["segment"],
                    variant=parsed["variant"],
                    vintage=parsed["vintage"],
                    sankey_stage=process.get("sankey_stage"),
                    description=description,
                    tags=tags,
                )

        sets = process.get("sets", [])
        role = self._infer_role_from_sets(sets)
        region = process.get("region", "SINGLE")

        return ProcessRegistryEntry(
            id=name,
            template=template.get("name") if template else None,
            parsed={
                "technology": name,
                "role": role,
                "geo": region,
                "segment": None,
                "variant": None,
                "vintage": None,
            },
            region=region,
            technology=name,
            role=role,
            segment=None,
            variant=None,
            vintage=None,
            sankey_stage=process.get("sankey_stage"),
            description=description,
            tags=tags,
        )

    def _infer_role_from_sets(self, sets: list) -> str:
        """Infer role from process sets."""
        set_to_role = {
            "ELE": "GEN",
            "IMP": "EXT",
            "DMD": "EUS",
            "STO": "STO",
            "TRD": "TRD",
        }
        for s in sets:
            if s in set_to_role:
                return set_to_role[s]
        return "GEN"

    def emit_resolved_process(self, resolved: ResolvedProcess) -> ProcessRegistryEntry:
        """Create registry entry from a ResolvedProcess."""
        canonical = parse_process_symbol(resolved.veda_id)
        parsed = {
            "technology": resolved.technology,
            "role": resolved.role,
            "geo": resolved.region,
            "segment": resolved.segment,
            "variant": resolved.variant,
            "vintage": resolved.vintage,
        }
        role = resolved.role
        variant = resolved.variant
        technology = resolved.technology
        if canonical:
            parsed.update(
                {
                    "technology": canonical["variant_id"],
                    "role": canonical["role_id"],
                    "variant": canonical["variant_id"],
                    "provider_kind": canonical["provider_kind"],
                    "provider_id": canonical["provider_id"],
                    "mode": canonical["mode_id"],
                }
            )
            role = canonical["role_id"]
            variant = canonical["variant_id"]
            technology = canonical["variant_id"]
        return ProcessRegistryEntry(
            id=resolved.veda_id,
            template=resolved.template_name,
            parsed=parsed,
            region=resolved.region,
            technology=technology,
            role=role,
            segment=resolved.segment,
            variant=variant,
            vintage=resolved.vintage,
            sankey_stage=resolved.sankey_stage,
            description=None,
            tags=resolved.tags,
        )

    def emit_model(
        self, model: dict, resolved_processes: list[ResolvedProcess] | None = None
    ) -> ModelRegistry:
        """Generate full registry for a model."""
        model_data = model.get("model", model)
        model_name = model_data.get("name", "Unknown")
        regions = model_data.get("regions", [])

        commodities: list[CommodityRegistryEntry] = []
        for c in model_data.get("commodities", []):
            commodities.append(self.emit_commodity(c))

        processes: list[ProcessRegistryEntry] = []

        if resolved_processes:
            for rp in resolved_processes:
                processes.append(self.emit_resolved_process(rp))
        else:
            for p in model_data.get("processes", []):
                processes.append(self.emit_process(p))

        return ModelRegistry(
            model_name=model_name,
            regions=regions,
            commodities=commodities,
            processes=processes,
        )

    def to_json(self, registry: ModelRegistry, indent: int = 2) -> str:
        """Serialize registry to JSON string."""
        def entry_to_dict(entry):
            if hasattr(entry, "__dataclass_fields__"):
                return asdict(entry)
            return entry

        data = {
            "model_name": registry.model_name,
            "regions": registry.regions,
            "commodities": [entry_to_dict(c) for c in registry.commodities],
            "processes": [entry_to_dict(p) for p in registry.processes],
        }
        return json.dumps(data, indent=indent)
