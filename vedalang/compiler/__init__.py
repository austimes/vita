"""VedaLang compiler - transforms VedaLang source to TableIR."""

from .compiler import (
    SemanticValidationError,
    compile_vedalang_to_tableir,
    load_vedalang,
    validate_cross_references,
    validate_vedalang,
)
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

__all__ = [
    "AttributeInfo",
    "IndexLayout",
    "SemanticValidationError",
    "TableValidationError",
    "TagInfo",
    "UnsupportedInfo",
    "VedaFieldSchema",
    "VedaLangError",
    "VedaRegistry",
    "VedaTableLayout",
    "VedaTableSchema",
    "compile_vedalang_to_tableir",
    "get_all_schemas",
    "get_registry",
    "load_vedalang",
    "reset_registry",
    "validate_cross_references",
    "validate_tableir",
    "validate_vedalang",
]
