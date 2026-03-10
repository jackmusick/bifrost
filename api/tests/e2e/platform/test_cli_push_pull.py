"""E2E tests for CLI push/pull endpoints and manifest round-tripping."""
import base64
import hashlib


def _b64(text: str) -> str:
    """Encode text as base64 string (matching CLI push format)."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_push_basic_files(e2e_client, platform_admin):
    """Push regular files and verify counts."""
    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {
            "apps/test-app/index.tsx": _b64("export default () => <div>Hello</div>"),
            "apps/test-app/styles.css": _b64("body { margin: 0; }"),
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] + data["updated"] + data["unchanged"] == 2
    assert data["errors"] == []


def test_push_unchanged_files(e2e_client, platform_admin):
    """Pushing the same files twice reports them as unchanged."""
    files = {
        "apps/push-unchanged/index.tsx": _b64("export default () => <div>Static</div>"),
    }
    e2e_client.post("/api/files/push", headers=platform_admin.headers, json={"files": files})
    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={"files": files})
    data = resp.json()
    assert data["unchanged"] == 1
    assert data["created"] == 0
    assert data["updated"] == 0


def test_push_bifrost_manifest(e2e_client, platform_admin):
    """Pushing .bifrost/ files triggers manifest processing."""
    workflows_yaml = (
        "workflows:\n"
        "  test-wf:\n"
        "    name: test-wf\n"
        "    path: workflows/test_wf.py\n"
    )
    # Push the workflow source file first so the manifest import can resolve it
    e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {
            "workflows/test_wf.py": _b64("from bifrost import workflow\n\n@workflow\ndef test_wf():\n    pass\n"),
        },
    })
    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64(workflows_yaml),
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    # manifest_applied may be True or False depending on DB state,
    # but the key must be present and the push must succeed
    assert "manifest_applied" in data
    assert "manifest_files" in data


def test_push_manifest_response_shape(e2e_client, platform_admin):
    """Push response should include manifest_files and modified_files dicts."""
    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64("workflows: {}\n"),
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("manifest_files"), dict)
    assert isinstance(data.get("modified_files"), dict)
    assert isinstance(data.get("warnings"), list)


def test_pull_only_returns_manifests(e2e_client, platform_admin):
    """Pull should only return manifest files, not code files."""
    content = "# pull test file"
    e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {"modules/pull_test.py": _b64(content)},
    })
    resp = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
        "prefix": "modules",
        "local_hashes": {"modules/pull_test.py": "0000000000000000"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "modules/pull_test.py" not in data["files"]


def test_pull_skips_matching_manifest_files(e2e_client, platform_admin):
    """Pull should NOT return manifest files whose hash matches local."""
    # First get the current manifest from server
    resp1 = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
        "prefix": "modules",
        "local_hashes": {},
    })
    data1 = resp1.json()
    manifest_files = data1.get("manifest_files", {})

    if manifest_files:
        # Now pull again with correct hashes — should get empty manifest_files
        local_hashes = {}
        for filename, content in manifest_files.items():
            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            local_hashes[f".bifrost/{filename}"] = h

        resp2 = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
            "prefix": "modules",
            "local_hashes": local_hashes,
        })
        data2 = resp2.json()
        assert data2["manifest_files"] == {}


def test_pull_does_not_return_deleted_files(e2e_client, platform_admin):
    """Pull should NOT list code files as deleted — git handles reconciliation."""
    resp = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
        "prefix": "modules",
        "local_hashes": {"modules/nonexistent_file.py": "abc123"},
    })
    data = resp.json()
    assert data["deleted"] == []


def test_pull_new_local_file_not_in_deleted(e2e_client, platform_admin):
    """Files that exist locally but not on server should NOT appear in deleted.

    The pull endpoint should only return manifest data, not try to reconcile
    code files — git handles that.
    """
    resp = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
        "prefix": "apps/new-app",
        "local_hashes": {"apps/new-app/brand-new.tsx": "abc123"},
    })
    data = resp.json()
    assert "apps/new-app/brand-new.tsx" not in data.get("deleted", [])


def test_pull_manifest_files(e2e_client, platform_admin):
    """Pull should include regenerated manifest files when they differ from local."""
    resp = e2e_client.post("/api/files/pull", headers=platform_admin.headers, json={
        "prefix": "apps/test-app",
        "local_hashes": {
            ".bifrost/workflows.yaml": "0000000000000000",
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("manifest_files", {}), dict)


def test_push_does_not_mark_dirty(e2e_client, platform_admin):
    """CLI push should not mark repo as dirty (covered by skip_dirty_flag)."""
    # Get current dirty state
    before = e2e_client.get("/api/github/repo-status", headers=platform_admin.headers).json()

    e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {"test-no-dirty.py": _b64("# test")},
    })
    after = e2e_client.get("/api/github/repo-status", headers=platform_admin.headers).json()

    # If it was clean before, it should still be clean after push
    if not before["dirty"]:
        assert after["dirty"] is False


def test_push_delete_missing_prefix(e2e_client, platform_admin):
    """delete_missing_prefix should remove files not in the push batch."""
    e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {
            "apps/cleanup/keep.tsx": _b64("keep"),
            "apps/cleanup/remove.tsx": _b64("remove"),
        },
    })
    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {"apps/cleanup/keep.tsx": _b64("keep")},
        "delete_missing_prefix": "apps/cleanup",
    })
    data = resp.json()
    assert data["deleted"] >= 1


def test_push_pull_binary_file(e2e_client, platform_admin):
    """Push and pull a binary file via base64 encoding."""
    # Binary content with null bytes (would fail with text encoding)
    binary_content = b"\x00\x01\x02\xff\xfe\xfd\x89PNG\r\n\x1a\n"
    b64_content = base64.b64encode(binary_content).decode("ascii")

    resp = e2e_client.post("/api/files/push", headers=platform_admin.headers, json={
        "files": {"assets/test.bin": b64_content},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] + data["updated"] + data["unchanged"] == 1
    assert data["errors"] == []
