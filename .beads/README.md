# Beads - Repository Issue Tracking

This repository uses **Beads (`bd`)** for issue tracking.

Run `bd prime` to load the current workflow context. This checkout uses the
current Dolt-backed beads workflow rather than the older JSONL sync flow.

## Essential Commands

```bash
bd ready
bd create --title="Add user authentication" --type=task --priority=2
bd show <issue-id>
bd update <issue-id> --status in_progress
bd close <issue-id> --reason "Completed"
bd dolt push
```

## Notes

- Issue data lives under `.beads/` and is managed by `bd`
- Install git hooks with `bd hooks install` if needed
- Run `bd doctor` if the local beads setup looks unhealthy

## Learn More

- `bd prime`
- `bd quickstart`
- https://github.com/steveyegge/beads
