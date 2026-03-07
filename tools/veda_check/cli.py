"""CLI for veda_check."""

import argparse
import json
import sys
from pathlib import Path

from .checker import run_check


def format_result_table(result) -> str:
    """Format result as a nice table."""
    status = "✓ PASS" if result.success else "✗ FAIL"
    tables_str = ", ".join(result.tables[:5])
    if len(result.tables) > 5:
        tables_str += f" (+{len(result.tables) - 5} more)"

    lines = [
        "┌" + "─" * 50 + "┐",
        "│ veda_check results" + " " * 31 + "│",
        "├" + "─" * 50 + "┤",
        f"│ Source: {str(result.source_path)[:40]:<41}│",
        f"│ Tables: {len(result.tables)} ({tables_str[:35]})".ljust(51) + "│",
        f"│ Rows: {result.total_rows} total".ljust(51) + "│",
        f"│ Warnings: {result.warnings}".ljust(51) + "│",
        f"│ Errors: {result.errors}".ljust(51) + "│",
        f"│ Status: {status}".ljust(51) + "│",
        "└" + "─" * 50 + "┘",
    ]

    if result.error_messages:
        lines.append("")
        lines.append("Errors:")
        for msg in result.error_messages[:10]:
            lines.append(f"  - {msg[:70]}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="veda_check",
        description="Unified validation for VedaLang/TableIR models"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to source file"
    )
    parser.add_argument(
        "--from-vedalang",
        action="store_true",
        help="Input is VedaLang source (.veda.yaml)"
    )
    parser.add_argument(
        "--from-tableir",
        action="store_true",
        help="Input is TableIR (.yaml/.json)"
    )
    parser.add_argument(
        "--run",
        help="Selected v0.2 run when validating VedaLang input",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if not args.from_vedalang and not args.from_tableir:
        # Auto-detect based on extension
        if args.input.suffix == ".yaml" and ".veda" in args.input.name:
            args.from_vedalang = True
        else:
            args.from_tableir = True

    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    result = run_check(
        args.input,
        from_vedalang=args.from_vedalang,
        from_tableir=args.from_tableir,
        selected_run=args.run,
    )

    if args.json_output:
        output = {
            "dsl_version": result.dsl_version,
            "artifact_version": result.artifact_version,
            "success": result.success,
            "source": str(result.source_path),
            "tables": result.tables,
            "total_rows": result.total_rows,
            "warnings": result.warnings,
            "errors": result.errors,
            "error_messages": result.error_messages,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result_table(result))

    # Exit code: 0=success, 1=warnings only, 2=errors
    if result.errors > 0:
        sys.exit(2)
    elif result.warnings > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
