"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    PublicDSLContractError,
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
    validate_public_dsl_contract,
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

__all__ = [
    "AttributeInfo",
    "DemandError",
    "IndexLayout",
    "NamingRegistry",
    "PublicDSLContractError",
    "SemanticValidationError",
    "TableValidationError",
    "TagInfo",
    "UnsupportedInfo",
    "VedaFieldSchema",
    "VedaLangError",
    "VedaRegistry",
    "V0_2Source",
    "VedaTableLayout",
    "VedaTableSchema",
    "compile_demands",
    "compile_vedalang_to_tableir",
    "get_all_schemas",
    "get_registry",
    "load_vedalang",
    "parse_v0_2_source",
    "reset_registry",
    "validate_public_dsl_contract",
    "validate_cross_references",
    "validate_tableir",
    "validate_vedalang",
]
