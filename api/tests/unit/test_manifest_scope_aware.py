"""Scope-aware manifest generation (success-criteria §5 prereq).

generate_manifest historically dumps ALL orgs' entities. A per-scope Solution
export must NOT cross-contaminate tenants: generate_manifest(db, solution_id=X)
returns only that install's solution-managed entities (workflows/forms/agents/
apps/tables), never _repo/ rows or other installs.
"""
from __future__ import annotations

import uuid

import pytest

from src.models.orm.solutions import Solution
from src.models.orm.workflows import Workflow
from src.services.manifest_generator import generate_manifest


@pytest.mark.e2e
class TestScopeAwareManifest:
    async def test_solution_filter_excludes_repo_and_other_installs(self, db_session) -> None:
        db = db_session
        sol = Solution(id=uuid.uuid4(), slug=f"man-{uuid.uuid4().hex[:8]}", name="M", organization_id=None)
        other = Solution(id=uuid.uuid4(), slug=f"oth-{uuid.uuid4().hex[:8]}", name="O", organization_id=None)
        db.add_all([sol, other])
        await db.flush()

        mine = uuid.uuid4()
        db.add_all([
            Workflow(id=mine, name=f"mine_{mine.hex[:6]}", function_name="run",
                     path=f"workflows/mine_{mine.hex[:6]}.py", type="workflow",
                     organization_id=None, solution_id=sol.id),
            Workflow(id=uuid.uuid4(), name=f"repo_{uuid.uuid4().hex[:6]}", function_name="run",
                     path=f"workflows/repo_{uuid.uuid4().hex[:6]}.py", type="workflow",
                     organization_id=None, solution_id=None),
            Workflow(id=uuid.uuid4(), name=f"other_{uuid.uuid4().hex[:6]}", function_name="run",
                     path=f"workflows/other_{uuid.uuid4().hex[:6]}.py", type="workflow",
                     organization_id=None, solution_id=other.id),
        ])
        await db.flush()

        manifest = await generate_manifest(db, solution_id=sol.id)
        wf_ids = {w.id for w in manifest.workflows.values()}
        assert wf_ids == {str(mine)}

    async def test_no_filter_keeps_legacy_all_orgs_behavior(self, db_session) -> None:
        """generate_manifest(db) with no solution_id is unchanged — includes
        _repo/ workflows (legacy full-dump behavior)."""
        db = db_session
        repo_id = uuid.uuid4()
        db.add(Workflow(
            id=repo_id, name=f"legacy_{repo_id.hex[:6]}", function_name="run",
            path=f"workflows/legacy_{repo_id.hex[:6]}.py", type="workflow",
            organization_id=None, solution_id=None,
        ))
        await db.flush()
        manifest = await generate_manifest(db)
        assert str(repo_id) in manifest.workflows
