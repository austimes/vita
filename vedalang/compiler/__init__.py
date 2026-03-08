"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    CompileBundle,
    SemanticValidationError,
    compile_vedalang_bundle,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_vedalang,
)
from .demands import DemandError, compile_demands
from .naming import NamingRegistry
from .registry import (
    AttributeInfo,
    IndexLayout,
    TagInfo,
    UnsupportedInfo,
    VedaLangError,
    VedaRegistry,
    get_registry,
    reset_registry,
)
from .table_schemas import (
    TableValidationError,
    VedaFieldSchema,
    VedaTableLayout,
    VedaTableSchema,
    get_all_schemas,
    validate_tableir,
)
from .v0_2_ast import V0_2Source, parse_v0_2_source
from .v0_2_ir import (
    ResolvedArtifacts,
    build_v0_2_artifacts,
    emit_csir,
    lower_csir_to_cpir,
)
from .v0_2_resolution import (
    V0_2ResolutionError,
    allocate_fleet_stock,
    resolve_asset_stock,
    resolve_imports,
    resolve_opportunities,
    resolve_run,
    resolve_sites,
)

__all__ = [
    "AttributeInfo",
    "CompileBundle",
    "DemandError",
    "IndexLayout",
    "NamingRegistry",
    "SemanticValidationError",
    "TableValidationError",
    "TagInfo",
    "UnsupportedInfo",
    "VedaFieldSchema",
    "VedaLangError",
    "VedaRegistry",
    "ResolvedArtifacts",
    "V0_2Source",
    "V0_2ResolutionError",
    "VedaTableLayout",
    "VedaTableSchema",
    "compile_demands",
    "compile_vedalang_bundle",
    "compile_vedalang_to_tableir",
    "build_v0_2_artifacts",
    "emit_csir",
    "get_all_schemas",
    "get_registry",
    "lower_csir_to_cpir",
    "load_vedalang",
    "allocate_fleet_stock",
    "parse_v0_2_source",
    "resolve_asset_stock",
    "resolve_imports",
    "resolve_opportunities",
    "resolve_run",
    "resolve_sites",
    "reset_registry",
    "validate_tableir",
    "validate_vedalang",
]
