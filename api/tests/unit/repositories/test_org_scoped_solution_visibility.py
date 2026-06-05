"""Deployed (solution-managed) entities must be VISIBLE in list() — criterion 16
says the Solution object is invisible, not the entities it deploys. But name/path
cascade get() must still resolve the _repo/ entity (solution entities resolve by
id at execution, never by name cascade), so a _repo/ name and a solution name can
coexist without MultipleResultsFound.

Regression guard for the org_scoped.py fix: the `solution_id IS NULL` filter
belongs on the name-cascade get() path, NOT on list().
"""
from __future__ import annotations

import uuid

import pytest

from src.models import Workflow
from src.models.orm.solutions import Solution
from src.repositories.org_scoped import OrgScopedRepository

pytestmark = pytest.mark.e2e


class _WfRepo(OrgScopedRepository[Workflow]):
    model = Workflow


def _wf(name: str, *, org_id, solution_id=None) -> Workflow:
    return Workflow(
        id=uuid.uuid4(),
        name=name,
        function_name="run",
        path=f"workflows/{name}.py",
        type="workflow",
        is_active=True,
        organization_id=org_id,
        solution_id=solution_id,
    )


async def test_list_includes_solution_managed_entities(db_session):
    db = db_session
    sol = Solution(id=uuid.uuid4(), slug=f"vis-{uuid.uuid4().hex[:8]}", name="VIS", organization_id=None)
    db.add(sol)
    await db.flush()

    uniq = uuid.uuid4().hex[:8]
    repo_wf = _wf(f"repo_{uniq}", org_id=None)
    sol_wf = _wf(f"deployed_{uniq}", org_id=None, solution_id=sol.id)
    db.add_all([repo_wf, sol_wf])
    await db.flush()

    repo = _WfRepo(session=db, org_id=None, user_id=None, is_superuser=True)
    names = {w.name for w in await repo.list()}
    # The deployed (solution-managed) workflow MUST appear in the listing.
    assert f"deployed_{uniq}" in names, "solution-managed entity hidden from list()"
    assert f"repo_{uniq}" in names


async def test_get_by_name_resolves_repo_not_solution(db_session):
    """A _repo/ workflow and a solution workflow can share a name; get(name=)
    resolves the _repo/ one without MultipleResultsFound."""
    db = db_session
    sol = Solution(id=uuid.uuid4(), slug=f"vis2-{uuid.uuid4().hex[:8]}", name="VIS2", organization_id=None)
    db.add(sol)
    await db.flush()

    shared = f"shared_{uuid.uuid4().hex[:8]}"
    repo_wf = _wf(shared, org_id=None)
    sol_wf = _wf(shared, org_id=None, solution_id=sol.id)
    db.add_all([repo_wf, sol_wf])
    await db.flush()

    repo = _WfRepo(session=db, org_id=None, user_id=None, is_superuser=True)
    got = await repo.get(name=shared)  # must NOT raise MultipleResultsFound
    assert got is not None
    assert got.solution_id is None, "name cascade must resolve the _repo/ entity, not the solution one"
