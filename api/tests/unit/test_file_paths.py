"""Unit tests for shared/file_paths.py — the single source of truth for S3 key resolution."""

import pytest

from shared.file_paths import resolve_s3_key, validate_location_name


class TestReservedLocations:
    def test_workspace_unscoped(self):
        assert resolve_s3_key("workspace", None, "demo/hello.pdf") == "_repo/demo/hello.pdf"

    def test_workspace_ignores_scope(self):
        # Workspace is the codebase — scope is intentionally ignored.
        assert resolve_s3_key("workspace", "org-a", "x.txt") == "_repo/x.txt"

    def test_uploads_scoped(self):
        assert resolve_s3_key("uploads", "org-a", "form_id/uuid/file.pdf") == "uploads/org-a/form_id/uuid/file.pdf"

    def test_temp_scoped(self):
        assert resolve_s3_key("temp", "org-a", "scratch.bin") == "_tmp/org-a/scratch.bin"


class TestFreeformLocations:
    def test_simple_freeform(self):
        assert resolve_s3_key("reports", "org-a", "q1.pdf") == "reports/org-a/q1.pdf"

    def test_freeform_with_hyphens(self):
        assert resolve_s3_key("customer-data", "org-a", "x.csv") == "customer-data/org-a/x.csv"

    def test_freeform_with_digits(self):
        assert resolve_s3_key("exports2", "org-a", "x.zip") == "exports2/org-a/x.zip"


class TestScopeRequirement:
    @pytest.mark.parametrize("location", ["uploads", "temp", "reports"])
    def test_missing_scope_rejected(self, location):
        with pytest.raises(ValueError, match="Scope is required"):
            resolve_s3_key(location, None, "x.txt")

    @pytest.mark.parametrize("location", ["uploads", "temp", "reports"])
    def test_empty_scope_rejected(self, location):
        with pytest.raises(ValueError, match="Scope is required"):
            resolve_s3_key(location, "", "x.txt")


class TestPathValidation:
    @pytest.mark.parametrize("bad_path", ["../etc/passwd", "a/../b", "../../x"])
    def test_traversal_rejected(self, bad_path):
        with pytest.raises(ValueError, match="path traversal"):
            resolve_s3_key("workspace", None, bad_path)

    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError, match="must be relative"):
            resolve_s3_key("workspace", None, "/etc/passwd")

    def test_subdirectory_paths(self):
        assert resolve_s3_key("temp", "org-a", "sub/file.txt") == "_tmp/org-a/sub/file.txt"

    def test_dotdot_in_filename_allowed(self):
        # ".." as a path segment is rejected; ".." in a filename is fine.
        assert resolve_s3_key("workspace", None, "file..bak") == "_repo/file..bak"


class TestLocationNameValidation:
    @pytest.mark.parametrize("reserved", ["_repo", "_tmp", "_apps"])
    def test_reserved_prefix_names_rejected(self, reserved):
        with pytest.raises(ValueError, match="reserved bucket prefix"):
            validate_location_name(reserved)

    @pytest.mark.parametrize("bad", ["UPPER", "with spaces", "with/slash", "_leading", "with_underscore"])
    def test_freeform_regex_enforced(self, bad):
        with pytest.raises(ValueError, match="must match"):
            validate_location_name(bad)

    @pytest.mark.parametrize("good", ["workspace", "uploads", "temp", "reports", "exports", "customer-data", "v2", "a"])
    def test_valid_names_accepted(self, good):
        # Should not raise.
        validate_location_name(good)


class TestResolverConsistency:
    """Round-trip-style sanity: every (location, path) deterministically maps to one key."""

    def test_idempotent(self):
        a = resolve_s3_key("uploads", "org-a", "f.pdf")
        b = resolve_s3_key("uploads", "org-a", "f.pdf")
        assert a == b

    def test_distinct_scopes_distinct_keys(self):
        # Verified for a scoped location.
        a = resolve_s3_key("temp", "org-a", "f.pdf")
        b = resolve_s3_key("temp", "org-b", "f.pdf")
        assert a != b

    def test_distinct_locations_distinct_keys(self):
        a = resolve_s3_key("temp", "org-a", "f.pdf")
        b = resolve_s3_key("reports", "org-a", "f.pdf")
        assert a != b
