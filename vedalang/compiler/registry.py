"""VedaRegistry - Central registry for attribute/tag validation at compile time."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    pass


@dataclass
class AttributeInfo:
    """Info about a supported attribute."""

    times_name: str
    column_header: str
    description: str
    notes: str | None = None
    indexes: list[str] | None = None
    mapping: list[str] | None = None


@dataclass
class UnsupportedInfo:
    """Info about why an attribute is unsupported."""

    reason: str
    suggested_alternative: str | None = None
    implementation_notes: list[str] | None = None


@dataclass
class TagInfo:
    """Info about a supported tag."""

    tag_name: str
    description: str
    file_types: list[str]
    valid_fields: set[str] = field(default_factory=set)


@dataclass
class IndexLayout:
    """How attribute indices map to tag columns."""

    column_mappings: dict[str, str]
    other_indexes: list[str]
    other_indexes_order: list[str]


class VedaLangError(Exception):
    """Base error for VedaLang validation failures."""

    pass


class VedaRegistry:
    """Central registry for attribute/tag validation."""

    def __init__(self) -> None:
        self._attributes: dict[str, AttributeInfo] = {}
        self._attributes_lower: dict[str, str] = {}
        self._unsupported: dict[str, UnsupportedInfo] = {}
        self._unsupported_lower: dict[str, str] = {}
        self._tags: dict[str, TagInfo] = {}
        self._tags_lower: dict[str, str] = {}
        self._times_info: dict[str, dict] = {}
        self._veda_tags_raw: dict[str, dict] = {}
        self._tag_valid_fields: dict[str, set[str]] = {}
        self._column_aliases: dict[str, set[str]] = {}
        self._load_data()

    def _get_schema_path(self, filename: str) -> Path:
        """Get path to a schema file."""
        return Path(__file__).parent.parent / "schema" / filename

    def _get_xl2times_config_path(self, filename: str) -> Path:
        """Get path to an xl2times config file."""
        return Path(__file__).parent.parent.parent / "xl2times" / "config" / filename

    def _load_data(self) -> None:
        """Load all config files and build internal lookups."""
        self._load_attributes_supported()
        self._load_unsupported_overrides()
        self._load_tags_supported()
        self._load_times_info()
        self._load_veda_tags()

    def _load_attributes_supported(self) -> None:
        """Load the curated supported attributes."""
        path = self._get_schema_path("attributes-supported.yaml")
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "attributes" not in data:
            return

        for name, info in data["attributes"].items():
            attr = AttributeInfo(
                times_name=info.get("times_name", name),
                column_header=info.get("column_header", name.lower()),
                description=info.get("description", ""),
                notes=info.get("notes"),
            )
            self._attributes[name] = attr
            self._attributes_lower[name.lower()] = name

    def _load_unsupported_overrides(self) -> None:
        """Load unsupported attribute reasons."""
        path = self._get_schema_path("unsupported-overrides.yaml")
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "attributes" not in data:
            return

        for name, info in data["attributes"].items():
            unsupported = UnsupportedInfo(
                reason=info.get("reason", ""),
                suggested_alternative=info.get("suggested_alternative"),
                implementation_notes=info.get("implementation_notes"),
            )
            self._unsupported[name] = unsupported
            self._unsupported_lower[name.lower()] = name

    def _load_tags_supported(self) -> None:
        """Load the curated supported tags."""
        path = self._get_schema_path("tags-supported.yaml")
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "tags" not in data:
            return

        for name, info in data["tags"].items():
            tag = TagInfo(
                tag_name=info.get("tag_name", name),
                description=info.get("description", ""),
                file_types=info.get("file_types", []),
            )
            self._tags[name] = tag
            self._tags_lower[name.lower()] = name

    def _load_times_info(self) -> None:
        """Load times-info.json for attribute index mappings."""
        path = self._get_xl2times_config_path("times-info.json")
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        for entry in data:
            name = entry.get("name")
            if name:
                self._times_info[name] = entry
                canonical = self._attributes_lower.get(name.lower())
                if canonical and canonical in self._attributes:
                    self._attributes[canonical].indexes = entry.get("indexes")
                    self._attributes[canonical].mapping = entry.get("mapping")

    def _load_veda_tags(self) -> None:
        """Load veda-tags.json for tag valid fields."""
        path = self._get_xl2times_config_path("veda-tags.json")
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        for tag_entry in data:
            tag_name = tag_entry.get("tag_name", "")
            self._veda_tags_raw[tag_name] = tag_entry

            valid_fields: set[str] = set()
            aliases_map: dict[str, set[str]] = {}

            if "valid_fields" in tag_entry:
                for field_entry in tag_entry["valid_fields"]:
                    use_name = field_entry.get("use_name", "")
                    if use_name:
                        valid_fields.add(use_name)
                        if use_name not in aliases_map:
                            aliases_map[use_name] = set()
                        aliases_map[use_name].add(field_entry.get("name", use_name))
                        if "aliases" in field_entry:
                            aliases_map[use_name].update(field_entry["aliases"])

            self._tag_valid_fields[tag_name] = valid_fields

            canonical_tag = self._tags_lower.get(tag_name.lower())
            if canonical_tag and canonical_tag in self._tags:
                self._tags[canonical_tag].valid_fields = valid_fields

            for use_name, aliases in aliases_map.items():
                if use_name not in self._column_aliases:
                    self._column_aliases[use_name] = set()
                self._column_aliases[use_name].update(aliases)

    def is_attribute_supported(self, attr_name: str) -> bool:
        """Check if attribute is in the supported list (case-insensitive)."""
        return attr_name.lower() in self._attributes_lower

    def get_attribute_info(self, attr_name: str) -> AttributeInfo | None:
        """Get full info for a supported attribute."""
        canonical = self._attributes_lower.get(attr_name.lower())
        if canonical:
            return self._attributes.get(canonical)
        return None

    def get_unsupported_info(self, attr_name: str) -> UnsupportedInfo | None:
        """Get info about why attribute is unsupported (if documented)."""
        canonical = self._unsupported_lower.get(attr_name.lower())
        if canonical:
            return self._unsupported.get(canonical)
        return None

    def validate_attribute(self, attr_name: str) -> None:
        """Raise VedaLangError if attribute not supported."""
        if self.is_attribute_supported(attr_name):
            return

        unsupported = self.get_unsupported_info(attr_name)
        if unsupported:
            msg = f"Attribute '{attr_name}' is not supported by VedaLang.\n"
            msg += f"Reason: {unsupported.reason}"
            if unsupported.suggested_alternative:
                msg += f"\nSuggested alternative: {unsupported.suggested_alternative}"
            raise VedaLangError(msg)

        raise VedaLangError(
            f"Attribute '{attr_name}' is not in the supported attribute list."
        )

    def is_tag_supported(self, tag_name: str) -> bool:
        """Check if tag is in the supported list."""
        return tag_name.lower() in self._tags_lower

    def get_tag_info(self, tag_name: str) -> TagInfo | None:
        """Get full info for a supported tag."""
        canonical = self._tags_lower.get(tag_name.lower())
        if canonical:
            return self._tags.get(canonical)
        return None

    def _get_tag_valid_fields(self, tag_name: str) -> set[str]:
        """Get valid fields for a tag from veda-tags.json."""
        tag_lower = tag_name.lower()
        for key, fields in self._tag_valid_fields.items():
            if key.lower() == tag_lower:
                return fields
        return set()

    def _mapping_column_to_tag_field(self, mapping_col: str) -> set[str]:
        """
        Map a times-info mapping column name to possible tag field use_names.

        For example:
        - 'process' maps to {'process', 'pset_pn'}
        - 'commodity' maps to {'commodity', 'cset_cn'}
        """
        direct_mappings: dict[str, set[str]] = {
            "region": {"region"},
            "year": {"year"},
            "year2": {"year2"},
            "process": {"process", "pset_pn"},
            "commodity": {"commodity", "cset_cn"},
            "timeslice": {"timeslice"},
            "limtype": {"limtype"},
            "currency": {"currency"},
            "cg": {"cg", "other_indexes"},
            "other_indexes": {"other_indexes"},
            "uc_n": {"uc_n"},
            "side": {"side"},
            "units": {"unit"},
        }

        if mapping_col in direct_mappings:
            return direct_mappings[mapping_col]
        return {mapping_col, "other_indexes"}

    def is_attribute_compatible_with_tag(
        self, attr_name: str, tag_name: str
    ) -> bool:
        """
        Check if attribute can be set in this tag.

        Algorithm:
        1. Get attribute mapping from times-info.json (required columns)
        2. Get tag valid_fields from veda-tags.json (available columns)
        3. For each mapping column:
           - If it's 'other_indexes' -> OK (will use other_indexes column)
           - If column exists in tag's valid_fields (including aliases) -> OK
           - If tag has 'other_indexes' and this is an overflow index -> OK
           - Otherwise -> NOT compatible
        """
        attr_info = self.get_attribute_info(attr_name)
        if not attr_info:
            attr_upper = attr_name.upper()
            times_entry = self._times_info.get(attr_upper)
            if not times_entry:
                return False
            mapping = times_entry.get("mapping", [])
        else:
            mapping = attr_info.mapping or []

        if not mapping:
            return True

        tag_fields = self._get_tag_valid_fields(tag_name)
        has_other_indexes = "other_indexes" in tag_fields

        for col in mapping:
            if col == "other_indexes":
                if has_other_indexes:
                    continue
                else:
                    return False

            possible_fields = self._mapping_column_to_tag_field(col)
            if any(f in tag_fields for f in possible_fields):
                continue

            if has_other_indexes:
                continue

            return False

        return True

    def get_index_layout(
        self, attr_name: str, tag_name: str
    ) -> IndexLayout | None:
        """
        Compute how attribute indices map to tag columns.

        Returns None if attribute/tag incompatible.
        """
        if not self.is_attribute_compatible_with_tag(attr_name, tag_name):
            return None

        attr_info = self.get_attribute_info(attr_name)
        if not attr_info:
            attr_upper = attr_name.upper()
            times_entry = self._times_info.get(attr_upper)
            if not times_entry:
                return None
            indexes = times_entry.get("indexes", [])
            mapping = times_entry.get("mapping", [])
        else:
            indexes = attr_info.indexes or []
            mapping = attr_info.mapping or []

        if not indexes or not mapping:
            return IndexLayout(
                column_mappings={},
                other_indexes=[],
                other_indexes_order=[],
            )

        tag_fields = self._get_tag_valid_fields(tag_name)
        has_other_indexes = "other_indexes" in tag_fields

        column_mappings: dict[str, str] = {}
        other_indexes: list[str] = []
        other_indexes_order: list[str] = []

        for i, col in enumerate(mapping):
            idx = indexes[i] if i < len(indexes) else f"idx_{i}"

            if col == "other_indexes":
                other_indexes.append(idx)
                other_indexes_order.append(idx)
                continue

            possible_fields = self._mapping_column_to_tag_field(col)
            matched_field = None
            for f in possible_fields:
                if f in tag_fields:
                    matched_field = f
                    break

            if matched_field:
                column_mappings[idx] = matched_field
            elif has_other_indexes:
                other_indexes.append(idx)
                other_indexes_order.append(idx)
            else:
                return None

        return IndexLayout(
            column_mappings=column_mappings,
            other_indexes=other_indexes,
            other_indexes_order=other_indexes_order,
        )


_registry: VedaRegistry | None = None


def get_registry() -> VedaRegistry:
    """Get or create the singleton registry."""
    global _registry
    if _registry is None:
        _registry = VedaRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the singleton registry (for testing)."""
    global _registry
    _registry = None
