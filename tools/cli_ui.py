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

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

_INVALID_CHOICE_RE = re.compile(r"invalid choice: '([^']+)'")
_REQUIRED_ARGS_RE = re.compile(r"required: (.+)$")
_UNICODE_PROBE = "┌─✓→"

_LEVEL_STYLE = {
    "info": ("cyan", "INFO"),
    "success": ("green", "OK"),
    "warning": ("yellow", "WARN"),
    "error": ("red", "ERROR"),
    "muted": ("bright_black", "NOTE"),
}

_AGENT_MODE = False


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


def set_agent_mode(enabled: bool) -> None:
    """Set the active process-wide CLI agent mode."""
    global _AGENT_MODE
    _AGENT_MODE = enabled


def is_agent_mode_enabled(argv: list[str] | None = None) -> bool:
    """Return whether agent mode should be used for the current invocation."""
    if _AGENT_MODE:
        return True
    if argv is None:
        argv = sys.argv[1:]
    return "--agent-mode" in argv


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


def _plain_renderable_text(
    body: str | list[str] | RenderableType,
    *,
    stream: str = "stdout",
) -> str:
    if isinstance(body, list):
        return "\n".join(body)
    if isinstance(body, str):
        return body
    return render_to_text(body, stream=stream).plain.rstrip()


def _title_text(
    title: str,
    *,
    level: str = "info",
    status: tuple[str, str] | None = None,
    subtitle: str | None = None,
) -> Text:
    color, label = _LEVEL_STYLE[level]
    text = Text()
    if status is not None:
        text.append(f"[{status[0].upper()}] ", style=f"bold {color}")
    else:
        text.append(f"{label}: ", style=f"bold {color}")
    text.append(title, style=f"bold {color}")
    if subtitle:
        text.append(f"  {subtitle}", style="dim")
    return text


def _rows_table(rows: list[tuple[str, str]]) -> Table:
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(ratio=1)
    for label, value in rows:
        table.add_row(label, value)
    return table


def _plain_message_lines(
    title: str,
    body: str | list[str] | RenderableType,
    *,
    level: str = "info",
    subtitle: str | None = None,
    stream: str = "stdout",
) -> list[str]:
    _, label = _LEVEL_STYLE[level]
    lines = [f"{label}: {title}"]
    if subtitle:
        lines.append(f"Subtitle: {subtitle}")
    body_text = _plain_renderable_text(body, stream=stream).strip()
    if body_text:
        lines.extend(body_text.splitlines())
    return lines


def _plain_status_lines(
    title: str,
    rows: list[tuple[str, str]],
    *,
    level: str = "info",
    status: tuple[str, str] | None = None,
    footer: str | None = None,
) -> list[str]:
    _, fallback_label = _LEVEL_STYLE[level]
    prefix = status[0].upper() if status is not None else fallback_label
    lines = [f"{prefix}: {title}"]
    lines.extend(f"{label}: {value}" for label, value in rows)
    if footer:
        lines.append(footer)
    return lines


def _format_plain_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
    *,
    empty_message: str = "(no rows)",
) -> str:
    lines = [title]
    if not rows:
        lines.append(empty_message)
        return "\n".join(lines)

    widths = [len(column) for column in columns]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    header = "  ".join(
        f"{column:<{widths[index]}}" for index, column in enumerate(columns)
    )
    separator = "  ".join("-" * widths[index] for index in range(len(columns)))
    lines.extend([header, separator])
    for row in rows:
        lines.append(
            "  ".join(
                f"{str(value):<{widths[index]}}"
                for index, value in enumerate(row)
            )
        )
    return "\n".join(lines)


def message_panel(
    title: str,
    body: str | list[str] | RenderableType,
    *,
    level: str = "info",
    stream: str = "stdout",
    subtitle: str | None = None,
) -> RenderableType:
    """Build a lightweight informational section."""
    if is_agent_mode_enabled():
        return Text(
            "\n".join(
                _plain_message_lines(
                    title, body, level=level, subtitle=subtitle, stream=stream
                )
            )
        )
    normalized = _normalize_body(body)
    items: list[RenderableType] = [_title_text(title, level=level, subtitle=subtitle)]
    if isinstance(normalized, Text):
        items.append(normalized)
    else:
        items.append(normalized)
    return Group(*items)


def status_panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    level: str = "info",
    stream: str = "stdout",
    status: tuple[str, str] | None = None,
    footer: str | None = None,
) -> RenderableType:
    """Build a compact status section."""
    if is_agent_mode_enabled():
        return Text(
            "\n".join(
                _plain_status_lines(
                    title, rows, level=level, status=status, footer=footer
                )
            )
        )
    items: list[RenderableType] = [_title_text(title, level=level, status=status)]
    items.append(_rows_table(rows))
    if footer:
        items.append(Text(footer, style="bright_black"))
    return Group(*items)


def data_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
    *,
    stream: str = "stdout",
    empty_message: str = "(no rows)",
) -> RenderableType:
    """Build a tabular section for human-readable CLI output."""
    if is_agent_mode_enabled():
        return Text(
            _format_plain_table(
                title,
                columns,
                rows,
                empty_message=empty_message,
            )
        )

    table = Table(
        box=None,
        expand=True,
        show_lines=False,
        pad_edge=False,
        header_style="bold cyan",
    )
    for column in columns:
        table.add_column(column, overflow="fold")
    if rows:
        for row in rows:
            table.add_row(*row)
    else:
        table.add_row(empty_message, *[""] * (len(columns) - 1))

    return Group(Text(title, style="bold cyan"), table)


def step_log(step: str, message: str) -> str:
    """Format a verbose step log line for the active terminal."""
    if is_agent_mode_enabled():
        return f"{step.upper():>10}  {message}"
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
    """Render and print a simple message block."""
    if is_agent_mode_enabled():
        handle = _stream_handle(stream)
        lines = _plain_message_lines(
            title, body, level=level, subtitle=subtitle, stream=stream
        )
        handle.write("\n".join(lines) + "\n")
        return
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
        if is_agent_mode_enabled():
            return argparse.ArgumentParser.format_help(self)
        return str(render_to_text(self._build_help_renderable(), stream="stdout"))

    def error(self, message: str) -> None:
        usage = argparse.ArgumentParser.format_usage(self).strip()
        suggestion = self._suggestion_for_error(message)
        if is_agent_mode_enabled():
            text = f"{usage}\n{self.prog}: error: {message}\n"
            if suggestion:
                text += f"hint: {suggestion}\n"
            self.exit(2, text)
        renderable = self._build_error_renderable(
            message=message, usage=usage, suggestion=suggestion
        )
        self.exit(2, str(render_to_text(renderable, stream="stderr")))

    def _build_help_renderable(self) -> RenderableType:
        rows: list[RenderableType] = []
        rows.append(Text(self.prog, style="bold cyan"))
        description = (self.description or "").strip()
        if description:
            rows.append(Text(description, style="default"))
        rows.append(Text(""))
        rows.append(Text("Usage", style="bold"))
        rows.append(
            Text(
                "  "
                + argparse.ArgumentParser.format_usage(self)
                .strip()
                .replace("usage: ", "")
            )
        )

        formatter = self._get_formatter()
        positionals: list[tuple[str, str]] = []
        options: list[tuple[str, str]] = []

        for action in self._actions:
            if action.help == argparse.SUPPRESS:
                continue
            if isinstance(action, argparse._SubParsersAction):
                rows.extend(self._subcommand_section(action))
                continue

            help_text = formatter._expand_help(action) if action.help else ""
            invocation = self._action_invocation(action)
            if action.option_strings:
                options.append((invocation, help_text))
            else:
                positionals.append((invocation, help_text))

        if positionals:
            rows.extend(self._rows_section("Arguments", positionals))
        if options:
            rows.extend(self._rows_section("Options", options))

        rows.append(Text(f"Try: {self.prog} <command> --help", style="bright_black"))
        return Group(*rows)

    def _subcommand_section(
        self, action: argparse._SubParsersAction
    ) -> list[RenderableType]:
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
        return self._rows_section("Commands", rows)

    def _rows_section(
        self, title: str, rows: list[tuple[str, str]]
    ) -> list[RenderableType]:
        table = Table(
            box=None,
            show_header=False,
            expand=True,
            pad_edge=False,
        )
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(ratio=1)
        for left, right in rows:
            table.add_row(left, right)
        return [Text(""), Text(title, style="bold"), table]

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
            _title_text("CLI Error", level="error", status=("error", "error")),
            Text(message),
            Text(""),
            Text("Usage", style="bold"),
            Text(f"  {usage.replace('usage: ', '')}", style="default"),
        ]
        if suggestion:
            rows.extend([Text(""), Text(f"Hint: {suggestion}", style="cyan")])
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
        if is_agent_mode_enabled():
            yield Text(argparse.ArgumentParser.format_help(self))
            return
        yield self._build_help_renderable()
