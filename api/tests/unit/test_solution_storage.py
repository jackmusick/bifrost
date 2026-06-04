"""Unit tests for SolutionStorage — S3 operations scoped to
``_solutions/{solution_id}/``.

Mirrors RepoStorage but every key is prefixed by the install's solution_id, so
two installs (and _repo/) never collide. This is the storage half of the
self-contained-world guarantee (success-criteria §3.5/§3.6).
"""
from __future__ import annotations

import uuid

from src.services.solutions.storage import SolutionStorage


def test_key_prefix() -> None:
    sid = uuid.uuid4()
    s = SolutionStorage(sid)
    assert s._key("workflows/triage.py") == f"_solutions/{sid}/workflows/triage.py"


def test_key_strips_leading_slash() -> None:
    sid = uuid.uuid4()
    s = SolutionStorage(sid)
    assert s._key("/modules/x.py") == f"_solutions/{sid}/modules/x.py"


def test_key_accepts_str_or_uuid() -> None:
    sid = uuid.uuid4()
    by_uuid = SolutionStorage(sid)
    by_str = SolutionStorage(str(sid))
    assert by_uuid._key("a.py") == by_str._key("a.py")


def test_prefix_is_isolated_per_install() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert SolutionStorage(a)._key("modules/x.py") != SolutionStorage(b)._key("modules/x.py")


def test_solution_prefix_constant() -> None:
    sid = uuid.uuid4()
    s = SolutionStorage(sid)
    assert s.prefix == f"_solutions/{sid}/"
