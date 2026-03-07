#!/usr/bin/env python3
"""Generate a STATUS.md-friendly summary from current bd issue data."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any


def run_bd_json(args: list[str]) -> list[dict[str, Any]]:
    """Run a bd command in JSON mode and return parsed issue data."""
    result = subprocess.run(
        ["bd", *args, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown bd error"
        raise RuntimeError(f"bd {' '.join(args)} failed: {stderr}")
    return json.loads(result.stdout or "[]")


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the markdown-friendly status summary."""
    open_issues = [issue for issue in issues if issue.get("status") == "open"]
    closed_issues = [issue for issue in issues if issue.get("status") == "closed"]

    def sort_key(issue: dict[str, Any]) -> tuple[Any, ...]:
        priority = int(issue.get("priority", 9))
        return (priority, issue.get("id", ""), issue.get("title", ""))

    open_issues.sort(key=sort_key)
    closed_issues.sort(
        key=lambda issue: (
            issue.get("closed_at") or "",
            issue.get("updated_at") or "",
            issue.get("id") or "",
        )
    )

    return {
        "total": len(issues),
        "open": len(open_issues),
        "closed": len(closed_issues),
        "open_issues": open_issues,
        "recently_closed": list(reversed(closed_issues[-10:])),
    }


def render_status_sync(
    summary: dict[str, Any],
    *,
    as_of: datetime | None = None,
) -> str:
    """Render the markdown snippet printed by the script."""
    if as_of is None:
        as_of = datetime.now()

    lines = [f"# VedaLang Status Sync — {as_of.strftime('%Y-%m-%d')}", ""]
    lines.append(f"**Total issues:** {summary['total']}")
    lines.append(f"**Closed:** {summary['closed']}")
    lines.append(f"**Open:** {summary['open']}")
    lines.append("")

    open_issues = summary["open_issues"]
    if open_issues:
        lines.append("## Open Issues")
        lines.append("")
        lines.append("| Issue | Priority | Type | Description |")
        lines.append("|-------|----------|------|-------------|")
        for issue in open_issues:
            issue_id = issue.get("id", "?")
            priority = f"P{issue.get('priority', '?')}"
            issue_type = issue.get("issue_type", "?")
            title = (issue.get("title", "") or "").replace("|", "\\|")
            lines.append(f"| `{issue_id}` | {priority} | {issue_type} | {title} |")
        lines.append("")

    lines.append("## Recently Closed (last 10)")
    lines.append("")
    recently_closed = summary["recently_closed"]
    if recently_closed:
        for issue in recently_closed:
            issue_id = issue.get("id", "?")
            title = issue.get("title", "")
            lines.append(f"- `{issue_id}`: {title}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("---")
    lines.append("Copy relevant sections to docs/STATUS.md")
    return "\n".join(lines)


def main() -> None:
    issues = run_bd_json(["list", "--all"])
    summary = summarize_issues(issues)
    print(render_status_sync(summary))


if __name__ == "__main__":
    main()
