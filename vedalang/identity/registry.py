"""Abbreviation registry for VedaLang naming conventions.

All abbreviations are compiler-owned. No user-defined abbreviations allowed.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml


class CommodityKind(Enum):
    TRADABLE = "TRADABLE"
    SERVICE = "SERVICE"
    EMISSION = "EMISSION"


@dataclass(frozen=True)
class CommodityAbbrev:
    key: str
    code: str
    kind: CommodityKind


@dataclass(frozen=True)
class TechAbbrev:
    key: str
    code: str


@dataclass(frozen=True)
class RoleAbbrev:
    key: str
    code: str


class AbbreviationRegistry:
    """Registry of all compiler-owned abbreviations.

    Loads abbreviations from YAML files in the identity directory.
    Provides bidirectional lookup (key -> code, code -> key).
    """

    def __init__(self) -> None:
        self._commodities_by_key: dict[str, CommodityAbbrev] = {}
        self._commodities_by_code: dict[str, CommodityAbbrev] = {}
        self._techs_by_key: dict[str, TechAbbrev] = {}
        self._techs_by_code: dict[str, TechAbbrev] = {}
        self._roles_by_key: dict[str, RoleAbbrev] = {}
        self._roles_by_code: dict[str, RoleAbbrev] = {}

        self._load_all()

    def _load_all(self) -> None:
        """Load all registry files from the identity directory."""
        identity_dir = Path(__file__).parent

        commodity_files = [
            "commodities.tradable.yaml",
            "commodities.service.yaml",
            "commodities.emission.yaml",
        ]
        for fname in commodity_files:
            self._load_commodities(identity_dir / fname)

        self._load_technologies(identity_dir / "technologies.yaml")
        self._load_roles(identity_dir / "roles.yaml")

    def _load_commodities(self, path: Path) -> None:
        """Load commodity abbreviations from a YAML file."""
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        for entry in data.get("entries", []):
            key = entry["key"]
            code = entry["code"]
            kind = CommodityKind(entry["kind"])

            if key in self._commodities_by_key:
                raise ValueError(f"Duplicate commodity key: {key}")
            if code in self._commodities_by_code:
                existing = self._commodities_by_code[code]
                raise ValueError(
                    f"Duplicate commodity code: {code} "
                    f"(used by both '{existing.key}' and '{key}')"
                )

            abbrev = CommodityAbbrev(key=key, code=code, kind=kind)
            self._commodities_by_key[key] = abbrev
            self._commodities_by_code[code] = abbrev

    def _load_technologies(self, path: Path) -> None:
        """Load technology abbreviations from a YAML file."""
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        for entry in data.get("entries", []):
            key = entry["key"]
            code = entry["code"]

            if key in self._techs_by_key:
                raise ValueError(f"Duplicate technology key: {key}")
            if code in self._techs_by_code:
                existing = self._techs_by_code[code]
                raise ValueError(
                    f"Duplicate technology code: {code} "
                    f"(used by both '{existing.key}' and '{key}')"
                )

            abbrev = TechAbbrev(key=key, code=code)
            self._techs_by_key[key] = abbrev
            self._techs_by_code[code] = abbrev

    def _load_roles(self, path: Path) -> None:
        """Load role abbreviations from a YAML file."""
        if not path.exists():
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        for entry in data.get("entries", []):
            key = entry["key"]
            code = entry["code"]

            if key in self._roles_by_key:
                raise ValueError(f"Duplicate role key: {key}")
            if code in self._roles_by_code:
                existing = self._roles_by_code[code]
                raise ValueError(
                    f"Duplicate role code: {code} "
                    f"(used by both '{existing.key}' and '{key}')"
                )

            abbrev = RoleAbbrev(key=key, code=code)
            self._roles_by_key[key] = abbrev
            self._roles_by_code[code] = abbrev

    def find_commodity_by_key(self, key: str) -> CommodityAbbrev | None:
        """Find a commodity abbreviation by its semantic key."""
        return self._commodities_by_key.get(key)

    def find_commodity_by_code(self, code: str) -> CommodityAbbrev | None:
        """Find a commodity abbreviation by its short code."""
        return self._commodities_by_code.get(code)

    def find_tech_by_key(self, key: str) -> TechAbbrev | None:
        """Find a technology abbreviation by its semantic key."""
        return self._techs_by_key.get(key)

    def find_tech_by_code(self, code: str) -> TechAbbrev | None:
        """Find a technology abbreviation by its short code."""
        return self._techs_by_code.get(code)

    def find_role_by_key(self, key: str) -> RoleAbbrev | None:
        """Find a role abbreviation by its semantic key."""
        return self._roles_by_key.get(key)

    def find_role_by_code(self, code: str) -> RoleAbbrev | None:
        """Find a role abbreviation by its short code."""
        return self._roles_by_code.get(code)

    def all_commodities(self) -> list[CommodityAbbrev]:
        """Return all commodity abbreviations."""
        return list(self._commodities_by_key.values())

    def all_technologies(self) -> list[TechAbbrev]:
        """Return all technology abbreviations."""
        return list(self._techs_by_key.values())

    def all_roles(self) -> list[RoleAbbrev]:
        """Return all role abbreviations."""
        return list(self._roles_by_key.values())
