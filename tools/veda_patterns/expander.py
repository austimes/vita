"""Pattern expansion logic."""

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template, TemplateError

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


class PatternError(Exception):
    """Error during pattern expansion."""

    pass

def load_patterns() -> dict:
    """Load patterns from rules/patterns.yaml."""
    patterns_file = RULES_DIR / "patterns.yaml"
    if not patterns_file.exists():
        raise PatternError(f"Patterns file not found: {patterns_file}")

    with open(patterns_file) as f:
        data = yaml.safe_load(f)

    return data.get("patterns", {})


def list_patterns() -> list[str]:
    """List available pattern names."""
    return list(load_patterns().keys())


def get_pattern_info(pattern_name: str) -> dict:
    """Get full info about a pattern."""
    patterns = load_patterns()
    if pattern_name not in patterns:
        available = list(patterns.keys())
        raise PatternError(f"Unknown pattern: {pattern_name}. Available: {available}")
    return patterns[pattern_name]


def expand_pattern(
    pattern_name: str,
    parameters: dict[str, Any],
    output_format: str = "tableir",
) -> str:
    """
    Expand a pattern with given parameters.

    Args:
        pattern_name: Name of the pattern (e.g., 'add_power_plant')
        parameters: Dictionary of parameter values
        output_format: supported output format (`tableir`)

    Returns:
        Expanded YAML string

    Raises:
        PatternError: If pattern not found, missing required params, or template error
    """
    patterns = load_patterns()

    if pattern_name not in patterns:
        available = list(patterns.keys())
        raise PatternError(f"Unknown pattern: {pattern_name}. Available: {available}")

    pattern = patterns[pattern_name]

    template_key = "tableir_template"
    if output_format != "tableir":
        raise PatternError(
            f"Invalid output_format: {output_format}. Use 'tableir'."
        )
    if template_key not in pattern:
        raise PatternError(
            f"Pattern '{pattern_name}' does not have a {output_format} template"
        )

    template_str = pattern[template_key]

    # Check required parameters and apply defaults
    merged_params = {}
    for param_def in pattern.get("parameters", []):
        param_name = param_def["name"]
        is_required = param_def.get("required", False)
        default = param_def.get("default")

        if param_name in parameters:
            merged_params[param_name] = parameters[param_name]
        elif default is not None:
            merged_params[param_name] = default
        elif is_required:
            raise PatternError(
                f"Missing required parameter '{param_name}' for pattern "
                f"'{pattern_name}'"
            )

    # Also include any extra parameters passed
    for key, value in parameters.items():
        if key not in merged_params:
            merged_params[key] = value

    # Expand template
    try:
        template = Template(template_str)
        result = template.render(**merged_params)
    except TemplateError as e:
        raise PatternError(f"Template expansion error: {e}")

    return result.strip()


def expand_pattern_to_dict(
    pattern_name: str,
    parameters: dict[str, Any],
    output_format: str = "tableir",
) -> dict:
    """
    Expand a pattern and parse result to dict.

    Returns:
        Parsed YAML as dictionary
    """
    yaml_str = expand_pattern(pattern_name, parameters, output_format)
    return yaml.safe_load(yaml_str)
