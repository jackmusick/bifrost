"""E2E (live REST + DB read): DELETE /api/solutions/{id} removes the install and
everything it owns via DB cascade, sweeps S3 artifacts, and NEVER touches a git
repo (git-connected installs are deletable too)."""
from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from sqlalchemy import select

from src.models.orm.solutions import Solution as SolutionORM
from src.models.orm.workflows import Workflow

pytestmark = pytest.mark.e2e


def _create_solution(e2e_client, headers, slug: str) -> str:
    r = e2e_client.post("/api/solutions", headers=headers, json={
        "slug": slug, "name": slug.upper(), "scope": "global",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def test_delete_removes_install_and_owned_entities(e2e_client, platform_admin, db_session):
    headers = platform_admin.headers
    slug = f"del-e2e-{uuid.uuid4().hex[:8]}"
    sid = _create_solution(e2e_client, headers, slug)

    wf_id = str(uuid.uuid4())
    dep = e2e_client.post(f"/api/solutions/{sid}/deploy", headers=headers, json={
        "python_files": {
            "workflows/w.py": (
                "from bifrost import workflow\n\n"
                "@workflow\n"
                "async def go():\n"
                "    return 1\n"
            ),
        },
        "workflows": [{
            "id": wf_id, "name": f"go_{slug}", "function_name": "go",
            "path": "workflows/w.py", "type": "workflow",
        }],
        "config_schemas": [{
            "id": str(uuid.uuid4()), "key": "API_KEY", "type": "secret",
            "required": True, "description": "needed", "position": 0,
        }],
    })
    assert dep.status_code == 200, dep.text

    r = e2e_client.delete(f"/api/solutions/{sid}", headers=headers)
    assert r.status_code in (200, 204), r.text
    body = r.json()
    assert body["solution_id"] == sid
    assert body["workflows_deleted"] >= 1
    assert body["configs_deleted"] >= 1

    # The install is gone.
    g = e2e_client.get(f"/api/solutions/{sid}", headers=headers)
    assert g.status_code == 404, g.text

    # Cascade removed the owned workflow row.
    rows = (
        await db_session.execute(
            select(Workflow).where(Workflow.solution_id == UUID(sid))
        )
    ).scalars().all()
    assert rows == [], f"expected cascade to remove owned workflows, got {len(rows)}"


def test_delete_missing_is_404(e2e_client, platform_admin):
    headers = platform_admin.headers
    r = e2e_client.delete(f"/api/solutions/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404, r.text


async def test_delete_git_connected_allowed(e2e_client, platform_admin, db_session):
    """git-connected installs ARE deletable from the API (unlike deploy/zip-install
    which refuse them). The upstream repo is external — nothing is asserted about it
    because the endpoint never touches a git repo."""
    headers = platform_admin.headers
    sid = uuid.uuid4()
    db_session.add(SolutionORM(
        id=sid,
        slug=f"del-git-{uuid.uuid4().hex[:8]}",
        name="GIT",
        organization_id=None,
        git_connected=True,
        git_repo_url="https://example.com/repo.git",
    ))
    await db_session.commit()

    r = e2e_client.delete(f"/api/solutions/{sid}", headers=headers)
    assert r.status_code in (200, 204), r.text

    g = e2e_client.get(f"/api/solutions/{sid}", headers=headers)
    assert g.status_code == 404, g.text
