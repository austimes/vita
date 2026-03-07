from datetime import datetime

import pytest

from tools import sync_status


def test_summarize_issues_counts_open_and_closed():
    issues = [
        {
            "id": "vedalang-b",
            "title": "Closed item",
            "status": "closed",
            "priority": 2,
            "issue_type": "task",
            "closed_at": "2026-03-07T03:00:00Z",
        },
        {
            "id": "vedalang-a",
            "title": "Open item",
            "status": "open",
            "priority": 1,
            "issue_type": "epic",
        },
    ]

    summary = sync_status.summarize_issues(issues)

    assert summary["total"] == 2
    assert summary["open"] == 1
    assert summary["closed"] == 1
    assert [issue["id"] for issue in summary["open_issues"]] == ["vedalang-a"]
    assert [issue["id"] for issue in summary["recently_closed"]] == ["vedalang-b"]


def test_render_status_sync_includes_open_issue_table():
    summary = {
        "total": 2,
        "open": 1,
        "closed": 1,
        "open_issues": [
            {
                "id": "vedalang-a",
                "title": "Open issue",
                "priority": 1,
                "issue_type": "task",
            }
        ],
        "recently_closed": [
            {
                "id": "vedalang-b",
                "title": "Closed issue",
            }
        ],
    }

    rendered = sync_status.render_status_sync(
        summary,
        as_of=datetime(2026, 3, 7),
    )

    assert "**Open:** 1" in rendered
    assert "| `vedalang-a` | P1 | task | Open issue |" in rendered
    assert "- `vedalang-b`: Closed issue" in rendered


def test_run_bd_json_raises_on_failure(monkeypatch):
    class Result:
        returncode = 2
        stdout = ""
        stderr = "bad things"

    monkeypatch.setattr(sync_status.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="bad things"):
        sync_status.run_bd_json(["list", "--all"])
