"""Tests for dependency validation logic."""
import re

_PKG_NAME_RE = re.compile(r"^(@[a-z0-9-]+/)?[a-z0-9][a-z0-9._-]*$")
_VERSION_RE = re.compile(r"^\^?~?\d+(\.\d+){0,2}$")


def test_valid_package_names():
    """Standard and scoped package names pass validation."""
    assert _PKG_NAME_RE.match("recharts")
    assert _PKG_NAME_RE.match("dayjs")
    assert _PKG_NAME_RE.match("@tanstack/react-table")
    assert _PKG_NAME_RE.match("react-icons")


def test_invalid_package_names():
    """Invalid package names are rejected."""
    assert not _PKG_NAME_RE.match("")
    assert not _PKG_NAME_RE.match("UPPERCASE")
    assert not _PKG_NAME_RE.match("../path-traversal")


def test_valid_versions():
    """Semver versions with optional prefix pass."""
    assert _VERSION_RE.match("2.12")
    assert _VERSION_RE.match("^1.5.3")
    assert _VERSION_RE.match("~1.11")


def test_invalid_versions():
    """Invalid versions are rejected."""
    assert not _VERSION_RE.match("latest")
    assert not _VERSION_RE.match("*")
