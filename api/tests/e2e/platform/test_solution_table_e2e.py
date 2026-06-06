"""End-to-end (live REST): deploy a Solution table, seed rows, redeploy with a
changed schema, and confirm rows are preserved (criterion 11)."""
from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from src.services.solutions.deploy import solution_entity_id

pytestmark = pytest.mark.e2e


def _create_solution(e2e_client, headers, slug: str) -> str:
    r = e2e_client.post("/api/solutions", headers=headers, json={
        "slug": slug, "name": slug.upper(), "scope": "global",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_table_deploy_preserves_rows_across_schema_change(e2e_client, platform_admin):
    headers = platform_admin.headers
    slug = f"tbl-e2e-{uuid.uuid4().hex[:8]}"
    sid = _create_solution(e2e_client, headers, slug)
    tid = str(uuid.uuid4())

    # Deploy v1 (schema with one column).
    dep = e2e_client.post(f"/api/solutions/{sid}/deploy", headers=headers, json={
        "tables": [{"id": tid, "name": f"people_{slug}", "schema": {"columns": [{"name": "email"}]}, "policies": None}],
    })
    assert dep.status_code in (200, 201), dep.text
    assert dep.json()["tables_upserted"] == 1

    # Deploy remaps the manifest id to uuid5(install_id, manifest_id); the table is
    # addressable only by the remapped id.
    real_id = str(solution_entity_id(UUID(sid), UUID(tid)))

    # Seed a runtime row via the documents API (this is NOT part of the bundle).
    doc = e2e_client.post(f"/api/tables/{real_id}/documents", headers=headers, json={
        "id": "row-1", "data": {"email": "a@x.com"},
    })
    assert doc.status_code in (200, 201), doc.text

    # Redeploy with a CHANGED schema (added column).
    dep2 = e2e_client.post(f"/api/solutions/{sid}/deploy", headers=headers, json={
        "tables": [{"id": tid, "name": f"people_{slug}", "schema": {"columns": [{"name": "email"}, {"name": "phone"}]}, "policies": None}],
    })
    assert dep2.status_code in (200, 201), dep2.text

    # Row survives the schema migration.
    got = e2e_client.get(f"/api/tables/{real_id}/documents/row-1", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["email"] == "a@x.com"


def test_solution_app_resolves_its_table_by_name(e2e_client, platform_admin):
    """Codex #15: a v2 app's useTable("name") (no per-install id) must resolve the
    app's OWN install table. The SDK sends X-Bifrost-App; the table router resolves
    the app's solution_id and finds the install's table by name. Without the header
    the name cascade excludes solution-managed tables and row ops 404."""
    headers = platform_admin.headers
    slug = f"tbln-{uuid.uuid4().hex[:8]}"
    sid = _create_solution(e2e_client, headers, slug)
    tid, app_manifest_id = str(uuid.uuid4()), str(uuid.uuid4())
    table_name = f"people_{slug}"

    dep = e2e_client.post(f"/api/solutions/{sid}/deploy", headers=headers, json={
        "tables": [{"id": tid, "name": table_name,
                    "schema": {"columns": [{"name": "email"}]}, "policies": None}],
        "apps": [{"id": app_manifest_id, "slug": f"app-{slug}", "name": "App",
                  "app_model": "standalone_v2", "dist_files": {"index.html": "<html></html>"}}],
    })
    assert dep.status_code in (200, 201), dep.text
    app_id = str(solution_entity_id(UUID(sid), UUID(app_manifest_id)))

    # WITHOUT the app header: the name cascade excludes the solution table → 404.
    no_app = e2e_client.post(
        f"/api/tables/{table_name}/documents", headers=headers,
        json={"id": "r1", "data": {"email": "a@x.com"}},
    )
    assert no_app.status_code == 404, f"expected 404 w/o app header, got {no_app.text}"

    # WITH the app header: resolves the install's own table by name → row op works.
    app_headers = {**headers, "X-Bifrost-App": app_id}
    with_app = e2e_client.post(
        f"/api/tables/{table_name}/documents", headers=app_headers,
        json={"id": "r1", "data": {"email": "a@x.com"}},
    )
    assert with_app.status_code in (200, 201), f"app-scoped row op failed: {with_app.text}"
    got = e2e_client.get(
        f"/api/tables/{table_name}/documents/r1", headers=app_headers
    )
    assert got.status_code == 200, got.text
    assert got.json()["data"]["email"] == "a@x.com"
