"""Template resolution for VedaLang process instances.

Resolves process instances against templates and generates VEDA process IDs.
"""

from dataclasses import dataclass, field
from typing import Any

from vedalang.identity.parser import generate_process_id


@dataclass
class ResolvedProcess:
    """A fully resolved process ready for VEDA emission."""

    veda_id: str
    instance_name: str
    template_name: str
    region: str
    technology: str
    role: str
    segment: str | None = None
    variant: str | None = None
    vintage: str | None = None

    sets: list[str] = field(default_factory=list)
    primary_commodity_group: str = ""
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    efficiency: Any = None
    investment_cost: Any | None = None
    fixed_om_cost: Any | None = None
    variable_om_cost: Any | None = None
    lifetime: Any | None = None
    availability_factor: Any | None = None
    activity_bound: dict | None = None
    cap_bound: dict | None = None
    ncap_bound: dict | None = None
    stock: Any | None = None
    existing_capacity: list[dict] | None = None
    sankey_stage: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


class TemplateResolver:
    """Resolves process instances against templates."""

    def __init__(self, templates: list[dict], regions: list[str]):
        """Initialize with templates and valid regions.

        Args:
            templates: List of process template definitions
            regions: List of valid region codes from model.regions
        """
        self._templates = {t["name"]: t for t in templates}
        self._regions = set(regions)

    def resolve(self, instance: dict) -> ResolvedProcess:
        """Resolve a process instance to a ResolvedProcess.

        Steps:
        1. Look up template by instance['template']
        2. Validate region is in model.regions
        3. If template.role == 'EUS', require instance.segment
        4. Generate VEDA ID using generate_process_id()
        5. Merge template defaults with instance overrides
        6. Return ResolvedProcess

        Args:
            instance: Process instance definition with 'template' and 'region' keys

        Returns:
            ResolvedProcess with merged attributes and generated VEDA ID

        Raises:
            ValueError: If template not found, region invalid, or EUS missing segment
        """
        template_name = instance["template"]
        region = instance["region"]

        if template_name not in self._templates:
            raise ValueError(f"Unknown template: '{template_name}'")

        if region not in self._regions:
            raise ValueError(
                f"Unknown region: '{region}'. Valid regions: {sorted(self._regions)}"
            )

        template = self._templates[template_name]
        role = template["role"]
        segment = instance.get("segment")

        if role == "EUS" and segment is None:
            raise ValueError(
                f"Template '{template_name}' has role EUS which requires a segment, "
                f"but instance '{instance['name']}' has no segment"
            )

        veda_id = generate_process_id(
            technology=template["technology"],
            role=role,
            geo=region,
            segment=segment,
            variant=instance.get("variant"),
            vintage=instance.get("vintage"),
        )

        inputs = self._normalize_flows(template, "inputs", "input")
        outputs = self._normalize_flows(template, "outputs", "output")

        merged_tags = dict(template.get("tags", {}))
        merged_tags.update(instance.get("tags", {}))

        return ResolvedProcess(
            veda_id=veda_id,
            instance_name=instance["name"],
            template_name=template_name,
            region=region,
            technology=template["technology"],
            role=role,
            segment=segment,
            variant=instance.get("variant"),
            vintage=instance.get("vintage"),
            sets=template.get("sets", []),
            primary_commodity_group=template.get("primary_commodity_group", ""),
            inputs=inputs,
            outputs=outputs,
            efficiency=self._get_override(instance, template, "efficiency"),
            investment_cost=self._get_override(instance, template, "investment_cost"),
            fixed_om_cost=self._get_override(instance, template, "fixed_om_cost"),
            variable_om_cost=self._get_override(instance, template, "variable_om_cost"),
            lifetime=self._get_override(instance, template, "lifetime"),
            availability_factor=self._get_override(
                instance, template, "availability_factor"
            ),
            activity_bound=instance.get("activity_bound"),
            cap_bound=instance.get("cap_bound"),
            ncap_bound=instance.get("ncap_bound"),
            stock=instance.get("stock"),
            existing_capacity=instance.get("existing_capacity"),
            sankey_stage=template.get("sankey_stage"),
            tags=merged_tags,
        )

    def resolve_all(self, instances: list[dict]) -> list[ResolvedProcess]:
        """Resolve all instances, collecting errors.

        Args:
            instances: List of process instance definitions

        Returns:
            List of ResolvedProcess objects

        Raises:
            ValueError: If any instance fails validation (includes all errors)
        """
        results = []
        errors = []

        for instance in instances:
            try:
                results.append(self.resolve(instance))
            except ValueError as e:
                errors.append(f"Instance '{instance.get('name', '?')}': {e}")

        if errors:
            raise ValueError("Template resolution errors:\n" + "\n".join(errors))

        return results

    def _normalize_flows(
        self, template: dict, array_key: str, single_key: str
    ) -> list[dict]:
        """Normalize template input/output flows to array format."""
        if array_key in template:
            return template[array_key]
        if single_key in template:
            return [{"commodity": template[single_key]}]
        return []

    def _get_override(
        self, instance: dict, template: dict, attr: str
    ) -> Any | None:
        """Get attribute value with instance override or template default."""
        if attr in instance:
            return instance[attr]
        return template.get(attr)
