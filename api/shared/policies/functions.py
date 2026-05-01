"""Function registry for policy expressions.

Each registered function provides BOTH a per-row evaluator and a SQL
compiler. Both forms must be supplied at registration so they cannot
drift. A function whose semantics cannot be expressed as a SQL literal
at request time (e.g., needs a DB lookup) cannot be registered here —
denormalize the relationship into a row field instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FunctionDef:
    """A registered policy function."""

    evaluate: Callable[[list[Any], Any, dict], bool]
    """Per-row evaluator. Args: (resolved_args, user, row) -> bool."""

    compile: Callable[[list[Any], Any, Any], bool]
    """SQL compiler. Args: (resolved_args, user, row_ctx) -> bool literal.

    Returns a Python bool because the compiler resolves these at compile
    time (no SQL CASE expressions for function calls).
    """

    arg_types: list[type]
    """Expected types of args for the validator at table create/update."""


def _has_role_evaluate(args: list, user, row: dict) -> bool:
    target = args[0]
    if target in user.role_names:
        return True
    return target in [str(r) for r in user.role_ids]


def _has_role_compile(args: list, user, row_ctx) -> bool:
    return _has_role_evaluate(args, user, row={})


FUNCTIONS: dict[str, FunctionDef] = {
    "has_role": FunctionDef(
        evaluate=_has_role_evaluate,
        compile=_has_role_compile,
        arg_types=[str],
    ),
}
