"""
File path resolution for the unified Files SDK.

All file operations (`read`, `write`, `list`, `delete`, `exists`, `signed-url`)
resolve their S3 keys through `resolve_s3_key()` here. One source of truth.

Layout:
    {location}/{scope}/{path}

Reserved (managed) locations:
    workspace -> _repo/{path}            (unscoped — platform codebase)
    uploads   -> uploads/{scope}/{path}  (form upload bucket)
    temp      -> _tmp/{scope}/{path}

Freeform (user-defined) locations:
    {name}    -> {name}/{scope}/{path}

`workspace` is the only unscoped location — it's conceptually a git repo
shared across orgs. Everything else requires scope. Scope semantics
(default-from-execution-context vs explicit override) are enforced upstream
in `bifrost._context.resolve_scope`.

Form-submission paths under `uploads/` are produced by `api/src/routers/forms.py`
as `{form_id}/{uuid}/{filename}` *relative to the location*; the resolver
prepends `uploads/{scope}/`. Existing form-upload references in storage that
predate this change live at `uploads/{form_id}/{uuid}/{filename}` (no scope
segment) and remain readable only via direct S3 access — they are not
addressable through the resolver.
"""

from __future__ import annotations

import re

WORKSPACE_PREFIX = "_repo/"
TEMP_PREFIX = "_tmp/"
UPLOADS_PREFIX = "uploads/"

RESERVED_LOCATION_NAMES: frozenset[str] = frozenset({
    "workspace",
    "uploads",
    "temp",
    "_repo",
    "_tmp",
    "_apps",
})

_FREEFORM_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def validate_location_name(location: str) -> None:
    """Validate that `location` is a recognized reserved name or a legal freeform name.

    Reserved direct prefix names (`_repo`, `_tmp`, `_apps`) are rejected as locations
    so users can't bypass the `{location}/{scope}/` layout by addressing the underlying
    bucket prefix directly.
    """
    if location in ("workspace", "uploads", "temp"):
        return
    if location in ("_repo", "_tmp", "_apps"):
        raise ValueError(
            f"Invalid location: '{location}' is a reserved bucket prefix; "
            "use 'workspace', 'temp', or 'uploads' instead."
        )
    if not _FREEFORM_NAME_RE.match(location):
        raise ValueError(
            f"Invalid location name: '{location}' must match {_FREEFORM_NAME_RE.pattern}"
        )


def _validate_path(path: str) -> None:
    if ".." in path.split("/"):
        raise ValueError(f"Invalid path: path traversal not allowed: {path}")
    if path.startswith("/"):
        raise ValueError(f"Invalid path: must be relative: {path}")


def resolve_s3_key(location: str, scope: str | None, path: str) -> str:
    """Resolve `(location, scope, path)` to an S3 key.

    Raises:
        ValueError: invalid location name, traversal in path, or missing scope
            for a scoped location.
    """
    validate_location_name(location)
    _validate_path(path)

    clean_path = path.lstrip("/")

    if location == "workspace":
        return f"{WORKSPACE_PREFIX}{clean_path}"

    if scope is None or scope == "":
        raise ValueError(
            f"Scope is required for location '{location}'."
        )

    if location == "uploads":
        return f"{UPLOADS_PREFIX}{scope}/{clean_path}"
    if location == "temp":
        return f"{TEMP_PREFIX}{scope}/{clean_path}"

    return f"{location}/{scope}/{clean_path}"
