"""Shared Textual theme and base app for Bifrost CLI TUI apps.

Dark theme inspired by OpenCode — near-black background, muted grays,
minimal accent color.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from textual.app import App
from textual.theme import Theme

T = TypeVar("T")

BIFROST_THEME = Theme(
    name="bifrost",
    primary="#7aa2f7",       # soft blue accent
    secondary="#9ece6a",     # muted green
    accent="#7aa2f7",        # same soft blue
    warning="#e0af68",       # muted amber
    error="#f7768e",         # soft red
    success="#9ece6a",       # muted green
    background="#0d1117",    # near-black (GitHub dark)
    surface="#161b22",       # very dark gray
    panel="#21262d",         # dark gray
    foreground="#e6edf3",    # light gray, not pure white
    dark=True,
    variables={
        "footer-background": "#161b22",
        "footer-key-foreground": "#7aa2f7",
        "footer-description-foreground": "#6e7681",
        "header-background": "#161b22",
        "border": "#30363d",
        "scrollbar-color": "#30363d",
        "scrollbar-color-hover": "#484f58",
        "scrollbar-background": "#0d1117",
    },
)


_BIFROST_BASE_CSS = """
Screen {
    background: #0d1117;
}
Header {
    background: #161b22;
    color: #e6edf3;
}
Footer {
    background: #161b22;
}
FooterKey .footer-key--key {
    color: #7aa2f7;
    background: #21262d;
}
FooterKey .footer-key--description {
    color: #6e7681;
}
"""


class BifrostApp(App[T], Generic[T]):
    """Base app with Bifrost theme pre-registered."""

    CSS = _BIFROST_BASE_CSS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.register_theme(BIFROST_THEME)
        self.theme = "bifrost"

    def action_help_quit(self) -> None:
        """Override Textual's ctrl+c confirmation screen — just exit."""
        self.exit()
