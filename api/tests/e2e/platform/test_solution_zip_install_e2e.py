"""E2E: drag-and-drop ZIP install of a Solution (Tasks 11+12).

* PREVIEW (``POST /api/solutions/install/preview``) parses the workspace and
  reports its entities + config declarations without persisting anything.
* INSTALL (``POST /api/solutions/install``) deploys the bundle AND applies the
  provided config VALUES atomically under the per-install write lock — so the
  install never exists without its just-entered secret. We prove atomicity by
  reading ``/entities`` afterward: the required secret's ``value_set`` is True
  and it is NOT in ``required_configs_unset``.
"""
from __future__ import annotations

import io
import uuid
import zipfile

import pytest

pytestmark = pytest.mark.e2e


def _make_zip(slug: str, version: str | None = None) -> bytes:
    """A minimal Solution workspace zip: descriptor + a workflow (manifest +
    source) + a required secret config declaration.

    Entity ids are STABLE per slug (uuid5), mirroring a real workspace: the
    ``.bifrost/*.yaml`` manifests keep their ids across versions, so a v2 zip
    of the same Solution carries the same manifest UUIDs as v1."""
    wf_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}/workflows/main"))
    cfg_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}/configs/API_KEY"))
    descriptor = f"slug: {slug}\nname: {slug.upper()}\nscope: global\n"
    if version is not None:
        descriptor += f"version: '{version}'\n"
    files = {
        "bifrost.solution.yaml": descriptor,
        ".bifrost/workflows.yaml": (
            "workflows:\n"
            f"  {wf_id}:\n"
            f"    id: {wf_id}\n"
            "    name: main\n"
            "    function_name: run\n"
            "    path: workflows/main.py\n"
        ),
        ".bifrost/configs.yaml": (
            "configs:\n"
            "  API_KEY:\n"
            f"    id: {cfg_id}\n"
            "    key: API_KEY\n"
            "    type: secret\n"
            "    required: true\n"
            "    description: needed\n"
            "    position: 0\n"
        ),
        "workflows/main.py": "def run(sdk):\n    return 'ok'\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


async def test_zip_install_atomic_deploy_and_values(e2e_client, platform_admin):
    headers = platform_admin.headers
    # httpx sets the multipart Content-Type itself; the auth headers carry an
    # application/json Content-Type that would otherwise override it and make the
    # server fail to parse the upload — strip it for the multipart requests.
    upload_headers = {
        k: v for k, v in headers.items() if k.lower() != "content-type"
    }
    slug = f"zip-e2e-{uuid.uuid4().hex[:8]}"
    data = _make_zip(slug)

    # PREVIEW: parse-only, nothing persisted.
    pv = e2e_client.post(
        "/api/solutions/install/preview",
        headers=upload_headers,
        files={"file": (f"{slug}.zip", data, "application/zip")},
    )
    assert pv.status_code == 200, pv.text
    body = pv.json()
    assert body["slug"] == slug
    assert len(body["workflows"]) == 1
    assert any(c["key"] == "API_KEY" for c in body["config_schemas"])

    # INSTALL: deploy + apply the secret value atomically.
    inst = e2e_client.post(
        "/api/solutions/install",
        headers=upload_headers,
        files={"file": (f"{slug}.zip", data, "application/zip")},
        data={"config_values": '{"API_KEY": "sk_x"}'},
    )
    assert inst.status_code in (200, 201), inst.text
    sid = inst.json()["id"]

    # The deployed workflow landed and the secret VALUE is set (atomic with deploy).
    ent = e2e_client.get(f"/api/solutions/{sid}/entities", headers=headers)
    assert ent.status_code == 200, ent.text
    entities = ent.json()
    assert len(entities["workflows"]) >= 1, "workflow should have deployed"

    api_key = next((c for c in entities["configs"] if c["key"] == "API_KEY"), None)
    assert api_key is not None, "API_KEY declaration should be present"
    assert api_key["value_set"] is True, "the provided secret value should be set"
    assert "API_KEY" not in entities["required_configs_unset"], (
        "a provided required value must not be reported as unset"
    )


async def test_zip_install_refused_into_git_connected_install(e2e_client, platform_admin):
    """A zip POSTed for a slug+scope that already has a git-connected install
    must be refused with 409 — auto-pull is that install's only writer."""
    headers = platform_admin.headers
    upload_headers = {
        k: v for k, v in headers.items() if k.lower() != "content-type"
    }
    slug = f"zip-gc-{uuid.uuid4().hex[:8]}"

    # Create a git-connected global install for this slug first.
    create = e2e_client.post("/api/solutions", headers=headers, json={
        "slug": slug,
        "name": slug.upper(),
        "scope": "global",
        "git_connected": True,
        "git_repo_url": "https://example.com/repo.git",
    })
    assert create.status_code in (200, 201), create.text

    # A zip for the same slug+scope resolves to that connected install → refused.
    inst = e2e_client.post(
        "/api/solutions/install",
        headers=upload_headers,
        files={"file": (f"{slug}.zip", _make_zip(slug), "application/zip")},
        data={"config_values": "{}"},
    )
    assert inst.status_code == 409, inst.text
    assert "git-connected" in inst.json()["detail"]


async def test_zip_install_upgrade_and_downgrade_gate(e2e_client, platform_admin):
    """Versioned zip install (Task 20):

    * install v1 → install v2 (same slug+scope) is an UPGRADE of the SAME
      install (no second install row); version + upgraded_from_version recorded.
    * an older zip (v0.9) → 409 with the downgrade detail.
    * the same older zip with ?force=true → succeeds and records the downgrade.
    """
    headers = platform_admin.headers
    upload_headers = {
        k: v for k, v in headers.items() if k.lower() != "content-type"
    }
    slug = f"zip-ver-{uuid.uuid4().hex[:8]}"

    def _install(version: str, force: bool = False):
        url = "/api/solutions/install" + ("?force=true" if force else "")
        return e2e_client.post(
            url,
            headers=upload_headers,
            files={"file": (f"{slug}.zip", _make_zip(slug, version), "application/zip")},
            data={"config_values": "{}"},
        )

    # Install v1.0.0.
    v1 = _install("1.0.0")
    assert v1.status_code in (200, 201), v1.text
    sid = v1.json()["id"]
    assert v1.json()["version"] == "1.0.0"

    # Install v1.1.0 for the same slug+scope → SAME install id, version updated.
    v2 = _install("1.1.0")
    assert v2.status_code in (200, 201), v2.text
    assert v2.json()["id"] == sid, "upgrade must not create a second install"
    assert v2.json()["version"] == "1.1.0"
    assert v2.json()["upgraded_from_version"] == "1.0.0"

    # An older zip is refused with the downgrade detail.
    down = _install("0.9.0")
    assert down.status_code == 409, down.text
    detail = down.json()["detail"]
    assert "0.9.0" in detail and "1.1.0" in detail and "force" in detail

    # Same zip, ?force=true → succeeds and records the downgrade.
    forced = _install("0.9.0", force=True)
    assert forced.status_code in (200, 201), forced.text
    assert forced.json()["id"] == sid
    assert forced.json()["version"] == "0.9.0"
    assert forced.json()["upgraded_from_version"] == "1.1.0"
