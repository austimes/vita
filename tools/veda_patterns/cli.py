"""CLI for pattern expansion."""

import argparse
import sys

from .expander import PatternError, expand_pattern, get_pattern_info, list_patterns


def main():
    parser = argparse.ArgumentParser(
        prog="veda_pattern",
        description="Inspect patterns and expand supported TableIR templates",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list subcommand
    subparsers.add_parser("list", help="List available patterns")

    # info subcommand
    info_parser = subparsers.add_parser("info", help="Show pattern details")
    info_parser.add_argument("pattern", help="Pattern name")

    # expand subcommand
    expand_parser = subparsers.add_parser("expand", help="Expand a pattern")
    expand_parser.add_argument("pattern", help="Pattern name")
    expand_parser.add_argument(
        "--param",
        "-p",
        action="append",
        dest="params",
        default=[],
        metavar="KEY=VALUE",
        help="Parameter value (can be repeated)",
    )
    expand_parser.add_argument(
        "--format",
        "-f",
        choices=["tableir"],
        default="tableir",
        help="Output format (default: tableir)",
    )

    args = parser.parse_args()

    try:
        if args.command == "list":
            run_list()
        elif args.command == "info":
            run_info(args.pattern)
        elif args.command == "expand":
            run_expand(args.pattern, args.params, args.format)
    except PatternError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_list():
    """List all available patterns."""
    patterns = list_patterns()
    print("Available patterns:")
    for name in sorted(patterns):
        info = get_pattern_info(name)
        desc = info.get("description", "").split("\n")[0][:60]
        print(f"  {name}: {desc}")


def run_info(pattern_name: str):
    """Show detailed info about a pattern."""
    info = get_pattern_info(pattern_name)

    print(f"Pattern: {pattern_name}")
    print(f"Category: {info.get('category', 'unknown')}")
    print()
    print("Description:")
    print(f"  {info.get('description', 'No description')}")
    print()
    print("Parameters:")
    for param in info.get("parameters", []):
        if param.get("required"):
            req = "(required)"
        else:
            req = f"(default: {param.get('default', 'none')})"
        print(f"  - {param['name']}: {param.get('type', 'any')} {req}")
        if "description" in param:
            print(f"      {param['description']}")
    print()

    if "example" in info:
        print("Example:")
        for key, value in info["example"].items():
            print(f"  {key}: {value}")


def run_expand(pattern_name: str, params: list[str], output_format: str):
    """Expand a pattern with given parameters."""
    # Parse parameters
    parameters = {}
    for param_str in params:
        if "=" not in param_str:
            print(f"Error: Invalid parameter format: {param_str}", file=sys.stderr)
            print("Use: --param KEY=VALUE", file=sys.stderr)
            sys.exit(1)
        key, value = param_str.split("=", 1)
        # Try to parse as number
        try:
            if "." in value:
                value = float(value)
            else:
                value = int(value)
        except ValueError:
            pass  # Keep as string
        parameters[key] = value

    result = expand_pattern(pattern_name, parameters, output_format)
    print(result)


if __name__ == "__main__":
    main()
