"""Watch mode dashboard TUI."""

from __future__ import annotations

import asyncio
import logging
import textwrap
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from bifrost.tui.theme import BifrostApp

logger = logging.getLogger(__name__)

_SPINNER = "\u280b\u2819\u2838\u2830\u2826\u2807"

# Column widths
_COL_TIME = 8  # HH:MM:SS
_COL_ACTION = 10  # "✗ Delete  " padded
_COL_SEP = 2  # gap between columns
_COL_USER = 12  # max username width

# Detail row indent (aligns with path column)
_DETAIL_INDENT = _COL_TIME + _COL_ACTION + _COL_SEP * 2

# Color palette
_CLR_TIME = "#6e7681"
_CLR_PATH = "#e6edf3"
_CLR_USER = "#484f58"
_CLR_DETAIL = "#484f58"  # dim for sub-rows
_CLR_ACTION = {
    "push": "#7aa2f7",
    "pull": "#9ece6a",
    "success": "#9ece6a",
    "error": "#f7768e",
    "warning": "#e0af68",
    "info": "#6e7681",
}


def _format_row(
    width: int,
    timestamp: str,
    action_color: str,
    icon: str,
    action_word: str,
    path: str,
    user: str = "",
) -> str:
    """Build a Rich-markup row with fixed columns."""
    # Compute available path width
    fixed = _COL_TIME + _COL_ACTION + _COL_SEP * 2
    if user:
        fixed += _COL_USER + _COL_SEP
    path_width = max(8, width - fixed - 4)  # 4 for padding

    # Truncate path from the left (preserve filename)
    if len(path) > path_width:
        path = "\u2026" + path[-(path_width - 1):]

    action_col = f"{icon} {action_word}"
    parts = (
        f"[{_CLR_TIME}]{timestamp:<{_COL_TIME}}[/]"
        f"{'':>{_COL_SEP}}"
        f"[{action_color}]{action_col:<{_COL_ACTION}}[/]"
        f"{'':>{_COL_SEP}}"
        f"[{_CLR_PATH}]{path:<{path_width}}[/]"
    )
    if user:
        display_user = user[:_COL_USER]
        parts += f"{'':>{_COL_SEP}}[{_CLR_USER}]{display_user}[/]"
    return parts


class _BatchRow(Static):
    """A single log row that can animate a spinner then freeze."""

    DEFAULT_CSS = """
    _BatchRow {
        height: auto;
        padding: 0 2;
    }
    """

    def __init__(self, text: str, style: str = "") -> None:
        markup = f"  [{style}]{text}[/]" if style else f"  {text}"
        super().__init__(markup)
        self._action_word = ""
        self._path = ""
        self._user = ""

    def set_spinning(self, action_word: str, path: str) -> None:
        """Store structured data for spinner updates."""
        self._action_word = action_word
        self._path = path

    def update_spinner(self, frame: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            width = self.app.size.width
        except Exception:
            width = 120
        markup = _format_row(
            width, ts, _CLR_ACTION.get("push", ""), frame, self._action_word, self._path
        )
        self.update(markup)

    def freeze(
        self,
        level: str,
        icon: str,
        action_word: str,
        path: str,
        user: str = "",
    ) -> None:
        """Finalize this row with structured columnar data."""
        ts = datetime.now().strftime("%H:%M:%S")
        color = _CLR_ACTION.get(level, "")
        try:
            width = self.app.size.width
        except Exception:
            width = 120
        markup = _format_row(width, ts, color, icon, action_word, path, user)
        self.update(markup)


class WatchApp(BifrostApp[None]):
    """Persistent watch mode dashboard with scrolling activity log."""

    CSS = """
    #activity-log {
        height: 1fr;
        margin: 0 0;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: #21262d;
        color: #6e7681;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Stop watching", priority=True),
        Binding("ctrl+q", "quit", "Stop watching", show=False, priority=True),
    ]

    def __init__(self, workspace: str, session_id: str) -> None:
        super().__init__()
        self.title = f"bifrost watch \u2014 {workspace}"
        self.sub_title = f"session {session_id[:8]}"
        self._pending = 0
        self._last_sync = "\u2014"
        self._work_coro: Coroutine[Any, Any, None] | None = None

    def set_work(self, coro: Coroutine[Any, Any, None]) -> None:
        """Set the coroutine to run as a worker when the app mounts."""
        self._work_coro = coro

    async def on_mount(self) -> None:
        if self._work_coro is not None:
            self.run_worker(self._work_coro)

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="activity-log")
        yield Static(self._format_status(), id="status-bar")
        yield Footer()

    def _format_status(self) -> str:
        return f"  Watching \u00b7 {self._pending} pending \u00b7 last sync {self._last_sync}  "

    def _update_status(self) -> None:
        try:
            self.query_one("#status-bar", Static).update(self._format_status())
        except Exception as e:
            # Status bar may not be mounted yet (early startup) — skip update
            logger.debug(f"_update_status skipped: {e}")

    def _add_row(
        self,
        level: str,
        icon: str,
        action_word: str,
        path: str,
        user: str = "",
    ) -> _BatchRow:
        """Add a finalized row to the log."""
        row = _BatchRow("")
        try:
            scroll = self.query_one("#activity-log", VerticalScroll)
            scroll.mount(row)
            scroll.scroll_end(animate=False)
        except Exception as e:
            # Scroll widget may not be mounted (early startup / shutdown) — drop the row
            logger.debug(f"_add_row could not mount: {e}")
        row.freeze(level, icon, action_word, path, user)
        return row

    def create_batch_row(self, action_word: str, path: str) -> _BatchRow:
        """Create a row with a spinner for an in-progress operation."""
        row = _BatchRow("")
        row.set_spinning(action_word, path)
        try:
            scroll = self.query_one("#activity-log", VerticalScroll)
            scroll.mount(row)
            scroll.scroll_end(animate=False)
        except Exception as e:
            # Scroll widget may not be mounted yet — return unmounted row anyway
            logger.debug(f"create_batch_row could not mount: {e}")
        return row

    async def spin_row(self, row: _BatchRow) -> None:
        """Animate a spinner on a row until cancelled."""
        try:
            i = 0
            while True:
                row.update_spinner(_SPINNER[i % len(_SPINNER)])
                i += 1
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass

    def log_push(self, filename: str) -> None:
        self._add_row("push", "\u2192", "Push", filename)

    def log_pull(self, filename: str, user: str = "") -> None:
        self._add_row("pull", "\u2190", "Pull", filename, user)

    def log_delete(self, filename: str, user: str = "") -> None:
        self._add_row("warning", "\u2717", "Delete", filename, user)

    def log_success(self, message: str) -> None:
        self._last_sync = datetime.now().strftime("%H:%M:%S")
        self._update_status()
        self._add_row("success", "\u2713", "Push", message)

    def log_error(self, message: str) -> None:
        self._add_row("error", "\u26a0", "Error", message)

    def log_error_detail(self, summary: str, detail: str) -> None:
        """Log an error with a colored gutter bar and detail sub-rows.

        Example output:
            14:32:01  ⚠ Error     workflows.yaml: HTTP 400
                               │  Manifest validation failed: workflow 'onboard'
                               │  references non-existent role 'abc-123'
        """
        self._add_row("error", "\u26a0", "Error", summary)
        self._add_detail_rows(detail, _CLR_ACTION["error"])

    def log_warning_detail(self, summary: str, detail: str) -> None:
        """Log a warning with a colored gutter bar and detail sub-rows."""
        self._add_row("warning", "\u26a0", "Warning", summary)
        self._add_detail_rows(detail, _CLR_ACTION["warning"])

    def _add_detail_rows(self, detail: str, gutter_color: str) -> None:
        """Add detail sub-rows with a colored gutter bar connecting them to the parent."""
        try:
            width = self.size.width
        except Exception:
            width = 120
        # Gutter bar sits just before the path column
        gutter_indent = " " * (_DETAIL_INDENT - 3)
        wrap_width = max(20, width - _DETAIL_INDENT - 4)
        for line in detail.splitlines():
            for wrapped in textwrap.wrap(line, width=wrap_width) or [line]:
                markup = f"  {gutter_indent}[{gutter_color}]\u2502[/]  [{_CLR_DETAIL}]{wrapped}[/]"
                row = _BatchRow(markup)
                try:
                    scroll = self.query_one("#activity-log", VerticalScroll)
                    scroll.mount(row)
                    scroll.scroll_end(animate=False)
                except Exception as e:
                    # Scroll widget may not be mounted — drop this detail row
                    logger.debug(f"_add_detail_rows could not mount: {e}")

    def log_info(self, message: str) -> None:
        self._add_row("info", "\u00b7", "Info", message)

    def set_pending(self, count: int) -> None:
        self._pending = count
        self._update_status()
