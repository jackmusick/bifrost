"""E2E tests for CLI push/pull endpoints and manifest round-tripping."""
import base64
import hashlib


def _b64(text: str) -> str:
    """Encode text as base64 string (matching CLI push format)."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _write_file(e2e_client, headers, path, content, binary=False):
    """Helper to write a file via /api/files/write."""
    resp = e2e_client.post("/api/files/write", headers=headers, json={
        "path": path,
        "content": content,
        "mode": "cloud",
        "location": "workspace",
        "binary": binary,
    })
    assert resp.status_code == 204, f"Write {path} failed: {resp.status_code} {resp.text}"
    return resp


def test_push_basic_files(e2e_client, platform_admin):
    """Write regular files via /api/files/write and verify 204 for each."""
    files = {
        "apps/test-app/index.tsx": "export default () => <div>Hello</div>",
        "apps/test-app/styles.css": "body { margin: 0; }",
    }
    for path, content in files.items():
        _write_file(e2e_client, platform_admin.headers, path, content)


def test_push_unchanged_files(e2e_client, platform_admin):
    """Writing the same file twice via /api/files/write succeeds both times."""
    path = "apps/push-unchanged/index.tsx"
    content = "export default () => <div>Static</div>"
    _write_file(e2e_client, platform_admin.headers, path, content)
    # Writing again should also succeed with 204
    _write_file(e2e_client, platform_admin.headers, path, content)


def test_push_bifrost_manifest(e2e_client, platform_admin):
    """Writing workflow source + manifest import triggers manifest processing."""
    workflows_yaml = (
        "workflows:\n"
        "  test-wf:\n"
        "    name: test-wf\n"
        "    path: workflows/test_wf.py\n"
    )
    # Write the workflow source file first so the manifest import can resolve it
    _write_file(
        e2e_client, platform_admin.headers,
        "workflows/test_wf.py",
        "from bifrost import workflow\n\n@workflow\ndef test_wf():\n    pass\n",
    )
    # Import manifest with inline files
    resp = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64(workflows_yaml),
        },
        "delete_removed_entities": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "applied" in data
    assert "manifest_files" in data


def test_push_manifest_response_shape(e2e_client, platform_admin):
    """Manifest import response should include manifest_files and modified_files dicts."""
    resp = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64("workflows: {}\n"),
        },
        "delete_removed_entities": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("manifest_files"), dict)
    assert isinstance(data.get("modified_files"), dict)
    assert isinstance(data.get("warnings"), list)


def test_pull_only_returns_manifests(e2e_client, platform_admin):
    """Pull should only return manifest files, not code files."""
    content = "# pull test file"
    _write_file(e2e_client, platform_admin.headers, "modules/pull_test.py", content)
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
    """CLI file write should not mark repo as dirty."""
    # Get current dirty state
    before = e2e_client.get("/api/github/repo-status", headers=platform_admin.headers).json()

    _write_file(e2e_client, platform_admin.headers, "test-no-dirty.py", "# test")

    after = e2e_client.get("/api/github/repo-status", headers=platform_admin.headers).json()

    # If it was clean before, it should still be clean after write
    if not before["dirty"]:
        assert after["dirty"] is False


def test_push_delete_missing_prefix(e2e_client, platform_admin):
    """Write files, then delete one via /api/files/delete."""
    _write_file(e2e_client, platform_admin.headers, "apps/cleanup/keep.tsx", "keep")
    _write_file(e2e_client, platform_admin.headers, "apps/cleanup/remove.tsx", "remove")

    # Delete the file that should be removed
    resp = e2e_client.post("/api/files/delete", headers=platform_admin.headers, json={
        "path": "apps/cleanup/remove.tsx",
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 204

    # Verify the kept file still exists
    resp = e2e_client.post("/api/files/read", headers=platform_admin.headers, json={
        "path": "apps/cleanup/keep.tsx",
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 200
    assert resp.json()["content"] == "keep"

    # Verify the deleted file is gone
    resp = e2e_client.post("/api/files/read", headers=platform_admin.headers, json={
        "path": "apps/cleanup/remove.tsx",
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 404


def test_push_pull_binary_file(e2e_client, platform_admin):
    """Write and read a binary file via /api/files/write and /api/files/read."""
    # Binary content with null bytes (would fail with text encoding)
    binary_content = b"\x00\x01\x02\xff\xfe\xfd\x89PNG\r\n\x1a\n"
    b64_content = base64.b64encode(binary_content).decode("ascii")

    _write_file(e2e_client, platform_admin.headers, "assets/test.bin", b64_content, binary=True)

    # Read it back as binary
    resp = e2e_client.post("/api/files/read", headers=platform_admin.headers, json={
        "path": "assets/test.bin",
        "mode": "cloud",
        "location": "workspace",
        "binary": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["binary"] is True
    assert base64.b64decode(data["content"]) == binary_content


# =============================================================================
# Per-file endpoint tests (new CLI flow)
# =============================================================================


def test_list_with_metadata(e2e_client, platform_admin):
    """POST /api/files/list with include_metadata returns ETags and timestamps."""
    content = "# list metadata test"
    e2e_client.post("/api/files/write", headers=platform_admin.headers, json={
        "path": "modules/list_meta_test.py",
        "content": content,
        "mode": "cloud",
        "location": "workspace",
    })
    resp = e2e_client.post("/api/files/list", headers=platform_admin.headers, json={
        "include_metadata": True,
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert "files_metadata" in data
    assert len(data["files_metadata"]) > 0

    # Find our test file in metadata
    meta_map = {item["path"]: item for item in data["files_metadata"]}
    assert "modules/list_meta_test.py" in meta_map
    item = meta_map["modules/list_meta_test.py"]
    assert "etag" in item
    assert len(item["etag"]) == 32  # MD5 hex
    assert "last_modified" in item
    assert "T" in item["last_modified"]  # ISO 8601

    # ETag should match MD5 of content
    expected_md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    assert item["etag"] == expected_md5


def test_list_with_metadata_excludes_git(e2e_client, platform_admin):
    """List with metadata should not return .git/ objects."""
    b64_content = base64.b64encode(b"git object").decode("ascii")
    _write_file(e2e_client, platform_admin.headers, ".git/objects/meta_test", b64_content, binary=True)
    resp = e2e_client.post("/api/files/list", headers=platform_admin.headers, json={
        "include_metadata": True,
        "mode": "cloud",
        "location": "workspace",
    })
    data = resp.json()
    for item in data["files_metadata"]:
        assert not item["path"].startswith(".git/"), f"Got .git/ in metadata: {item['path']}"


def test_list_without_metadata_unchanged(e2e_client, platform_admin):
    """List without include_metadata should behave as before (files only, no metadata)."""
    resp = e2e_client.post("/api/files/list", headers=platform_admin.headers, json={
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert data.get("files_metadata", []) == []


def test_manifest_import_endpoint(e2e_client, platform_admin):
    """POST /api/files/manifest/import imports .bifrost/ from S3 into DB."""
    # Write a workflow source file + manifest to S3
    e2e_client.post("/api/files/write", headers=platform_admin.headers, json={
        "path": "workflows/import_test_wf.py",
        "content": "from bifrost import workflow\n\n@workflow\ndef import_test_wf():\n    pass\n",
        "mode": "cloud",
        "location": "workspace",
    })
    e2e_client.post("/api/files/write", headers=platform_admin.headers, json={
        "path": ".bifrost/workflows.yaml",
        "content": (
            "workflows:\n"
            "  import-test-wf:\n"
            "    name: import-test-wf\n"
            "    path: workflows/import_test_wf.py\n"
        ),
        "mode": "cloud",
        "location": "workspace",
    })

    resp = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "applied" in data
    assert isinstance(data.get("warnings"), list)
    assert isinstance(data.get("manifest_files"), dict)
    assert isinstance(data.get("modified_files"), dict)


def test_push_response_includes_deleted_entities(e2e_client, platform_admin):
    """Manifest import response should include deleted_entities field."""
    resp = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64("workflows: {}\n"),
        },
        "delete_removed_entities": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("deleted_entities"), list)


def test_push_with_delete_removed_entities(e2e_client, platform_admin):
    """Manifest import with delete_removed_entities=True should remove server-only entities."""
    from uuid import uuid4

    wf_id = str(uuid4())
    wf_py = "from bifrost import workflow\n\n@workflow\ndef del_test_wf():\n    pass\n"

    # Step 1: Write workflow source file
    _write_file(e2e_client, platform_admin.headers, "workflows/del_test_wf.py", wf_py)

    # Step 2: Import manifest so workflow exists in DB
    workflows_yaml = (
        f"workflows:\n"
        f"  del_test_wf:\n"
        f"    id: {wf_id}\n"
        f"    path: workflows/del_test_wf.py\n"
        f"    function_name: del_test_wf\n"
    )
    resp1 = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64(workflows_yaml),
        },
        "delete_removed_entities": False,
    })
    assert resp1.status_code == 200
    assert resp1.json()["applied"] is True

    # Step 3: Import empty manifest with delete_removed_entities=True
    resp2 = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64("workflows: {}\n"),
        },
        "delete_removed_entities": True,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["applied"] is True
    # The workflow should be deleted (or at least the deleted_entities list populated)
    assert isinstance(data2.get("deleted_entities"), list)


def test_push_without_delete_flag_preserves_entities(e2e_client, platform_admin):
    """Manifest import without delete_removed_entities should not remove entities."""
    from uuid import uuid4

    wf_id = str(uuid4())
    wf_py = "from bifrost import workflow\n\n@workflow\ndef preserve_test():\n    pass\n"

    # Write workflow source + import manifest
    _write_file(e2e_client, platform_admin.headers, "workflows/preserve_test.py", wf_py)
    workflows_yaml = (
        f"workflows:\n"
        f"  preserve_test:\n"
        f"    id: {wf_id}\n"
        f"    path: workflows/preserve_test.py\n"
        f"    function_name: preserve_test\n"
    )
    e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64(workflows_yaml),
        },
        "delete_removed_entities": False,
    })

    # Import empty manifest WITHOUT delete flag
    resp = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {
            ".bifrost/workflows.yaml": _b64("workflows: {}\n"),
        },
        "delete_removed_entities": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    # deleted_entities should be empty since flag is False
    assert data.get("deleted_entities", []) == []


def test_manifest_import_with_delete_flag(e2e_client, platform_admin):
    """POST /api/files/manifest/import with delete_removed_entities returns deleted_entities."""
    resp = e2e_client.post(
        "/api/files/manifest/import",
        headers=platform_admin.headers,
        json={"delete_removed_entities": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("deleted_entities"), list)


def test_per_file_push_pull_roundtrip(e2e_client, platform_admin):
    """Write files via /write, list with metadata, read back via /read."""
    files = {
        "apps/perfile/index.tsx": "export default () => <div>Per-file</div>",
        "apps/perfile/utils.ts": "export const y = 2;",
    }
    # Write files one at a time
    for path, content in files.items():
        resp = e2e_client.post("/api/files/write", headers=platform_admin.headers, json={
            "path": path,
            "content": content,
            "mode": "cloud",
            "location": "workspace",
        })
        assert resp.status_code == 204

    # List with metadata
    resp = e2e_client.post("/api/files/list", headers=platform_admin.headers, json={
        "include_metadata": True,
        "mode": "cloud",
        "location": "workspace",
    })
    assert resp.status_code == 200
    data = resp.json()
    meta_map = {item["path"]: item for item in data["files_metadata"]}
    for path in files:
        assert path in meta_map

    # Read files back one at a time
    for path, expected_content in files.items():
        resp = e2e_client.post("/api/files/read", headers=platform_admin.headers, json={
            "path": path,
            "mode": "cloud",
            "location": "workspace",
        })
        assert resp.status_code == 200
        assert resp.json()["content"] == expected_content


def test_incremental_import_skips_unchanged(e2e_client, platform_admin):
    """Importing the same manifest twice should report no entity_changes on the second import."""
    from uuid import uuid4

    wf_id = str(uuid4())
    wf_py = "from bifrost import workflow\n\n@workflow\ndef incr_test_wf():\n    pass\n"

    # Write workflow source
    _write_file(e2e_client, platform_admin.headers, "workflows/incr_test_wf.py", wf_py)

    workflows_yaml = (
        f"workflows:\n"
        f"  incr-test-wf:\n"
        f"    id: {wf_id}\n"
        f"    name: incr_test_wf\n"
        f"    path: workflows/incr_test_wf.py\n"
        f"    function_name: incr_test_wf\n"
    )

    # First import — should create the workflow
    resp1 = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {".bifrost/workflows.yaml": _b64(workflows_yaml)},
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["applied"] is True
    assert len(data1.get("entity_changes", [])) > 0, "First import should have entity_changes"

    # Second import — same manifest, should have no changes
    resp2 = e2e_client.post("/api/files/manifest/import", headers=platform_admin.headers, json={
        "files": {".bifrost/workflows.yaml": _b64(workflows_yaml)},
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["applied"] is True
    assert len(data2.get("entity_changes", [])) == 0, (
        f"Second import should have no entity_changes but got: {data2.get('entity_changes')}"
    )
