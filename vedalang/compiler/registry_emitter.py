"""Registry JSON output generation for VedaLang compiler.

Generates a machine-readable registry.json that captures all entities
in a compiled model with their identifiers, parsed components, and metadata.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from vedalang.compiler.template_resolver import ResolvedProcess
from vedalang.identity.parser import parse_process_id
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
        """Map VedaLang commodity type to kind."""
        mapping = {
            "energy": "TRADABLE",
            "material": "TRADABLE",
            "demand": "SERVICE",
            "emission": "EMISSION",
        }
        return mapping.get(commodity_type, "TRADABLE")

    def _build_commodity_id(
        self, name: str, kind: str, context: str | None = None
    ) -> str:
        """Build a full commodity ID with prefix."""
        prefix_map = {"TRADABLE": "C", "SERVICE": "S", "EMISSION": "E"}
        prefix = prefix_map.get(kind, "C")
        if kind == "SERVICE" and context:
            return f"{prefix}:{name}:{context}"
        return f"{prefix}:{name}"

    def _parse_commodity_id(self, commodity_id: str) -> tuple[str, str, str | None]:
        """Parse a commodity ID into (code, kind, context)."""
        parts = commodity_id.split(":")
        prefix = parts[0] if parts else ""

        kind_map = {"C": "TRADABLE", "S": "SERVICE", "E": "EMISSION"}
        kind = kind_map.get(prefix, "TRADABLE")

        code = parts[1] if len(parts) > 1 else commodity_id
        context = parts[2] if len(parts) > 2 else None

        return code, kind, context

    def emit_commodity(self, commodity: dict) -> CommodityRegistryEntry:
        """Create registry entry for a commodity.

        - Extract code from ID (after C:, S:, E: prefix)
        - Look up key (expanded name) from abbreviation registry
        - Include all metadata
        """
        name = commodity.get("name", "")
        commodity_type = commodity.get("type", "energy")
        kind = self._map_commodity_kind(commodity_type)

        context = None
        if kind == "SERVICE":
            context = commodity.get("context", "RES.ALL")

        full_id = self._build_commodity_id(name, kind, context)

        abbrev = self._abbrev.find_commodity_by_code(name)
        key = abbrev.key if abbrev else None

        return CommodityRegistryEntry(
            id=full_id,
            kind=kind,
            code=name,
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

        if name.startswith("P:"):
            validation = parse_process_id(name)
            if validation.valid and validation.parsed:
                parsed = validation.parsed
                return ProcessRegistryEntry(
                    id=name,
                    template=None,
                    parsed={
                        "technology": parsed.technology,
                        "role": parsed.role,
                        "geo": parsed.geo,
                        "segment": parsed.segment,
                        "variant": parsed.variant,
                        "vintage": parsed.vintage,
                    },
                    region=parsed.geo,
                    technology=parsed.technology,
                    role=parsed.role,
                    segment=parsed.segment,
                    variant=parsed.variant,
                    vintage=parsed.vintage,
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
        return ProcessRegistryEntry(
            id=resolved.veda_id,
            template=resolved.template_name,
            parsed={
                "technology": resolved.technology,
                "role": resolved.role,
                "geo": resolved.region,
                "segment": resolved.segment,
                "variant": resolved.variant,
                "vintage": resolved.vintage,
            },
            region=resolved.region,
            technology=resolved.technology,
            role=resolved.role,
            segment=resolved.segment,
            variant=resolved.variant,
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
