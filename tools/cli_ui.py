"""Shared terminal presentation helpers for user-facing CLIs."""

from __future__ import annotations

import argparse
import difflib
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_INVALID_CHOICE_RE = re.compile(r"invalid choice: '([^']+)'")
_REQUIRED_ARGS_RE = re.compile(r"required: (.+)$")
_UNICODE_PROBE = "┌─✓→"

_LEVEL_STYLE = {
    "info": ("cyan", "bold white on cyan"),
    "success": ("green", "bold white on green"),
    "warning": ("yellow", "bold black on yellow"),
    "error": ("red", "bold white on red"),
    "muted": ("bright_black", "bold white on bright_black"),
}


@dataclass(frozen=True)
class TerminalProfile:
    """Terminal capabilities relevant to CLI presentation."""

    force_terminal: bool
    no_color: bool
    unicode: bool
    width: int


class StyledText(str):
    """String subclass that preserves the plain-text rendering."""

    def __new__(cls, plain: str, ansi: str):
        obj = super().__new__(cls, ansi)
        obj.plain = plain
        return obj


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)


def _stream_handle(stream: str):
    return sys.stderr if stream == "stderr" else sys.stdout


def _supports_unicode(handle: Any) -> bool:
    encoding = getattr(handle, "encoding", None) or "utf-8"
    try:
        _UNICODE_PROBE.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def get_terminal_profile(
    *,
    stream: str = "stdout",
    width: int = 100,
) -> TerminalProfile:
    """Detect terminal behavior for the given output stream."""
    handle = _stream_handle(stream)
    no_color = os.getenv("NO_COLOR") not in (None, "")
    force_color = os.getenv("CLICOLOR_FORCE") not in (None, "", "0")
    term = (os.getenv("TERM") or "").lower()
    is_tty = bool(getattr(handle, "isatty", lambda: False)())
    force_terminal = False if term == "dumb" else (force_color or is_tty)
    return TerminalProfile(
        force_terminal=force_terminal,
        no_color=no_color or term == "dumb",
        unicode=_supports_unicode(handle),
        width=width,
    )


def make_console(
    *,
    stream: str = "stdout",
    record: bool = False,
    width: int = 100,
) -> Console:
    """Create a Rich console honoring repository terminal defaults."""
    handle = _stream_handle(stream)
    profile = get_terminal_profile(stream=stream, width=width)
    return Console(
        file=handle,
        force_terminal=profile.force_terminal,
        no_color=profile.no_color,
        legacy_windows=False,
        color_system="truecolor"
        if profile.force_terminal and not profile.no_color
        else None,
        record=record,
        width=profile.width,
        soft_wrap=False,
    )


def render_to_text(
    renderable: RenderableType,
    *,
    stream: str = "stdout",
    width: int = 100,
) -> StyledText:
    """Render a Rich object to terminal text, optionally with ANSI styles."""
    profile = get_terminal_profile(stream=stream, width=width)
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=profile.force_terminal,
        no_color=profile.no_color,
        legacy_windows=False,
        color_system="truecolor"
        if profile.force_terminal and not profile.no_color
        else None,
        width=profile.width,
        soft_wrap=False,
    )
    console.print(renderable)
    ansi = buffer.getvalue()
    plain = strip_ansi(ansi)
    return StyledText(plain, ansi)


def print_renderable(
    renderable: RenderableType,
    *,
    stream: str = "stdout",
    width: int = 100,
) -> None:
    """Print a Rich renderable using repository defaults."""
    console = make_console(stream=stream, width=width)
    console.print(renderable)


def _panel_box(*, stream: str = "stdout"):
    profile = get_terminal_profile(stream=stream)
    return box.ROUNDED if profile.unicode else box.ASCII


def _status_badge(label: str, level: str) -> Text:
    _, badge_style = _LEVEL_STYLE[level]
    return Text.assemble((f" {label.upper()} ", badge_style))


def _section_table(
    title: str, rows: list[tuple[str, str]], *, stream: str = "stdout"
) -> Table:
    table = Table(
        box=box.SIMPLE_HEAD
        if get_terminal_profile(stream=stream).unicode
        else box.SIMPLE,
        show_header=False,
        expand=True,
        pad_edge=False,
    )
    table.add_column(style="bold")
    table.add_column(style="default", ratio=1)
    for label, value in rows:
        table.add_row(label, value)
    table.title = f"[bold]{title}[/bold]"
    return table


def _normalize_body(body: str | list[str] | RenderableType) -> RenderableType:
    if isinstance(body, list):
        text = Text()
        for index, line in enumerate(body):
            if index:
                text.append("\n")
            text.append(line)
        return text
    if isinstance(body, str):
        return Text.from_markup(body, justify="left")
    return body


def message_panel(
    title: str,
    body: str | list[str] | RenderableType,
    *,
    level: str = "info",
    stream: str = "stdout",
    subtitle: str | None = None,
) -> Panel:
    """Build a styled informational panel."""
    border_style, _ = _LEVEL_STYLE[level]
    panel = Panel(
        _normalize_body(body),
        title=f"[bold]{title}[/bold]",
        subtitle=subtitle,
        border_style=border_style,
        box=_panel_box(stream=stream),
        padding=(0, 1),
    )
    return panel


def status_panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    level: str = "info",
    stream: str = "stdout",
    status: tuple[str, str] | None = None,
    footer: str | None = None,
) -> Panel:
    """Build a compact panel with key/value rows."""
    content: list[RenderableType] = []
    if status is not None:
        badge_grid = Table.grid(padding=(0, 1), expand=True)
        badge_grid.add_column(no_wrap=True)
        badge_grid.add_column(ratio=1)
        badge_grid.add_row(_status_badge(status[0], status[1]), "")
        content.append(badge_grid)
    content.append(_section_table(title, rows, stream=stream))
    if footer:
        content.append(Text(footer, style="bright_black"))
    border_style, _ = _LEVEL_STYLE[level]
    return Panel(
        Group(*content),
        border_style=border_style,
        box=_panel_box(stream=stream),
        padding=(0, 1),
    )


def data_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
    *,
    stream: str = "stdout",
    empty_message: str = "(no rows)",
) -> Panel:
    """Build a tabular section for human-readable CLI output."""
    table = Table(
        box=box.MINIMAL_DOUBLE_HEAD
        if get_terminal_profile(stream=stream).unicode
        else box.SIMPLE,
        expand=True,
        show_lines=False,
        pad_edge=False,
    )
    for column in columns:
        table.add_column(column, overflow="fold")
    if rows:
        for row in rows:
            table.add_row(*row)
    else:
        table.add_row(empty_message, *[""] * (len(columns) - 1))
    return Panel(
        table,
        title=f"[bold]{title}[/bold]",
        border_style="cyan",
        box=_panel_box(stream=stream),
        padding=(0, 1),
    )


def step_log(step: str, message: str) -> str:
    """Format a verbose step log line for the active terminal."""
    text = Text.assemble(
        (f"{step.upper():>10}", "bold cyan"),
        ("  ", ""),
        (message, ""),
    )
    return str(render_to_text(text))


def print_message(
    title: str,
    body: str | list[str] | RenderableType,
    *,
    level: str = "info",
    stream: str = "stdout",
    subtitle: str | None = None,
) -> None:
    """Render and print a simple panel."""
    print_renderable(
        message_panel(title, body, level=level, stream=stream, subtitle=subtitle),
        stream=stream,
    )


class StyledArgumentParser(argparse.ArgumentParser):
    """ArgumentParser with shared styled help and error output."""

    def add_subparsers(self, **kwargs):
        kwargs.setdefault("parser_class", type(self))
        return super().add_subparsers(**kwargs)

    def format_help(self) -> str:
        return str(render_to_text(self._build_help_renderable(), stream="stdout"))

    def error(self, message: str) -> None:
        usage = argparse.ArgumentParser.format_usage(self).strip()
        suggestion = self._suggestion_for_error(message)
        renderable = self._build_error_renderable(
            message=message, usage=usage, suggestion=suggestion
        )
        self.exit(2, str(render_to_text(renderable, stream="stderr")))

    def _build_help_renderable(self) -> RenderableType:
        rows: list[RenderableType] = []
        title = Text(self.prog, style="bold cyan")
        description = (self.description or "").strip()
        header = Table.grid(expand=True)
        header.add_column(ratio=1)
        header.add_row(title)
        if description:
            header.add_row(Text(description, style="default"))
        rows.append(
            Panel(
                header,
                border_style="cyan",
                box=_panel_box(stream="stdout"),
                padding=(0, 1),
            )
        )
        rows.append(
            message_panel(
                "Usage",
                argparse.ArgumentParser.format_usage(self)
                .strip()
                .replace("usage: ", ""),
                level="muted",
                stream="stdout",
            )
        )

        formatter = self._get_formatter()
        positionals: list[tuple[str, str]] = []
        options: list[tuple[str, str]] = []

        for action in self._actions:
            if action.help == argparse.SUPPRESS:
                continue
            if isinstance(action, argparse._SubParsersAction):
                rows.append(self._subcommand_panel(action))
                continue

            help_text = formatter._expand_help(action) if action.help else ""
            invocation = self._action_invocation(action)
            if action.option_strings:
                options.append((invocation, help_text))
            else:
                positionals.append((invocation, help_text))

        if positionals:
            rows.append(self._rows_panel("Arguments", positionals))
        if options:
            rows.append(self._rows_panel("Options", options))

        rows.append(
            Text(
                f"Try: {self.prog} <command> --help",
                style="bright_black",
            )
        )
        return Group(*rows)

    def _subcommand_panel(self, action: argparse._SubParsersAction) -> Panel:
        rows: list[tuple[str, str]] = []
        help_by_name = {
            choice_action.dest: choice_action.help or ""
            for choice_action in action._choices_actions
        }
        for name, parser in action.choices.items():
            if not isinstance(parser, argparse.ArgumentParser):
                continue
            summary = help_by_name.get(name) or (parser.description or "").strip()
            rows.append((name, summary))
        return self._rows_panel("Commands", rows)

    def _rows_panel(self, title: str, rows: list[tuple[str, str]]) -> Panel:
        table = Table(
            box=box.SIMPLE_HEAD
            if get_terminal_profile(stream="stdout").unicode
            else box.SIMPLE,
            show_header=False,
            expand=True,
            pad_edge=False,
        )
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(ratio=1)
        for left, right in rows:
            table.add_row(left, right)
        return Panel(
            table,
            title=f"[bold]{title}[/bold]",
            border_style="cyan",
            box=_panel_box(stream="stdout"),
            padding=(0, 1),
        )

    def _action_invocation(self, action: argparse.Action) -> str:
        formatter = self._get_formatter()
        if action.option_strings:
            if action.nargs == 0:
                return ", ".join(action.option_strings)
            default = action.metavar or action.dest.upper()
            args = formatter._format_args(action, default)
            return ", ".join(action.option_strings) + f" {args}"

        default = action.metavar or action.dest
        return formatter._format_args(action, default)

    def _build_error_renderable(
        self,
        *,
        message: str,
        usage: str,
        suggestion: str | None,
    ) -> RenderableType:
        rows: list[RenderableType] = [
            Panel(
                Group(
                    _status_badge("error", "error"),
                    Text(message, style="default"),
                ),
                title=f"[bold]{self.prog}[/bold]",
                border_style="red",
                box=_panel_box(stream="stderr"),
                padding=(0, 1),
            ),
            message_panel(
                "Usage", usage.replace("usage: ", ""), level="muted", stream="stderr"
            ),
        ]
        if suggestion:
            rows.append(
                message_panel("Hint", suggestion, level="info", stream="stderr")
            )
        return Group(*rows)

    def _suggestion_for_error(self, message: str) -> str | None:
        invalid = _INVALID_CHOICE_RE.search(message)
        if invalid:
            bad_value = invalid.group(1)
            choices = self._collect_choice_values()
            if choices:
                match = difflib.get_close_matches(
                    bad_value, choices, n=1, cutoff=0.55
                )
                if match:
                    return (
                        f"Did you mean `{match[0]}`? "
                        f"Try `{self.prog} {match[0]} --help`."
                    )
            return (
                f"Run `{self.prog} --help` to see the available commands and options."
            )

        required = _REQUIRED_ARGS_RE.search(message)
        if required:
            return (
                f"Add the required arguments listed above, or run `{self.prog} --help`."
            )

        return f"Run `{self.prog} --help` for usage details."

    def _collect_choice_values(self) -> list[str]:
        values: list[str] = []
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                values.extend(action.choices.keys())
                continue
            if not action.choices:
                continue
            for choice in action.choices:
                text = str(choice)
                if text not in values:
                    values.append(text)
        return values

    def _print_message(self, message, file=None):
        if file is not None and hasattr(file, "write"):
            file.write(message)
            return
        super()._print_message(message, file)

    def format_usage(self) -> str:
        return argparse.ArgumentParser.format_usage(self)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield self._build_help_renderable()
