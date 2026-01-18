"""Unit tests for app code files router."""

import pytest
from fastapi import HTTPException

from src.routers.app_code_files import validate_file_path


class TestValidateFilePath:
    """Tests for the validate_file_path function."""

    # ==========================================================================
    # Valid paths
    # ==========================================================================

    def test_valid_root_layout(self):
        """Root _layout is valid."""
        validate_file_path("_layout")

    def test_valid_root_providers(self):
        """Root _providers is valid."""
        validate_file_path("_providers")

    def test_valid_pages_index(self):
        """pages/index is valid."""
        validate_file_path("pages/index")

    def test_valid_pages_layout(self):
        """pages/_layout is valid."""
        validate_file_path("pages/_layout")

    def test_valid_pages_nested(self):
        """Nested pages are valid."""
        validate_file_path("pages/clients/index")
        validate_file_path("pages/clients/_layout")

    def test_valid_pages_dynamic(self):
        """Dynamic route segments in pages are valid."""
        validate_file_path("pages/clients/[id]")
        validate_file_path("pages/clients/[id]/edit")

    def test_valid_components_file(self):
        """Component files are valid."""
        validate_file_path("components/Button")
        validate_file_path("components/ClientCard")

    def test_valid_components_nested(self):
        """Nested component folders are valid."""
        validate_file_path("components/ui/Button")
        validate_file_path("components/forms/ClientForm")

    def test_valid_modules_file(self):
        """Module files are valid."""
        validate_file_path("modules/api")
        validate_file_path("modules/utils")

    def test_valid_modules_nested(self):
        """Nested module folders are valid."""
        validate_file_path("modules/services/api")
        validate_file_path("modules/hooks/useAuth")

    def test_valid_path_with_underscores(self):
        """Paths with underscores are valid."""
        validate_file_path("components/my_component")
        validate_file_path("modules/api_client")

    def test_valid_path_with_hyphens(self):
        """Paths with hyphens are valid."""
        validate_file_path("components/my-component")
        validate_file_path("modules/api-client")

    # ==========================================================================
    # Invalid paths - empty/malformed
    # ==========================================================================

    def test_invalid_empty_path(self):
        """Empty path is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("")
        assert exc_info.value.status_code == 400
        assert "cannot be empty" in exc_info.value.detail

    def test_invalid_double_slashes(self):
        """Double slashes are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("pages//index")
        assert exc_info.value.status_code == 400
        assert "empty segments" in exc_info.value.detail

    # ==========================================================================
    # Invalid paths - root level
    # ==========================================================================

    def test_invalid_root_arbitrary_file(self):
        """Arbitrary files at root are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("main")
        assert exc_info.value.status_code == 400
        assert "_layout" in exc_info.value.detail
        assert "_providers" in exc_info.value.detail

    def test_invalid_root_index(self):
        """index at root is rejected (must be in pages/)."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("index")
        assert exc_info.value.status_code == 400

    # ==========================================================================
    # Invalid paths - wrong top directory
    # ==========================================================================

    def test_invalid_top_dir(self):
        """Invalid top-level directories are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("services/api")
        assert exc_info.value.status_code == 400
        assert "pages" in exc_info.value.detail
        assert "components" in exc_info.value.detail
        assert "modules" in exc_info.value.detail

    def test_invalid_top_dir_utils(self):
        """utils/ directory is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("utils/helpers")
        assert exc_info.value.status_code == 400

    # ==========================================================================
    # Invalid paths - dynamic segments outside pages/
    # ==========================================================================

    def test_invalid_dynamic_in_components(self):
        """Dynamic segments in components/ are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("components/[id]")
        assert exc_info.value.status_code == 400
        assert "Dynamic segments" in exc_info.value.detail
        assert "pages/" in exc_info.value.detail

    def test_invalid_dynamic_in_modules(self):
        """Dynamic segments in modules/ are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("modules/[id]/utils")
        assert exc_info.value.status_code == 400
        assert "Dynamic segments" in exc_info.value.detail

    # ==========================================================================
    # Invalid paths - _layout outside pages/
    # ==========================================================================

    def test_invalid_layout_in_components(self):
        """_layout in components/ is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("components/_layout")
        assert exc_info.value.status_code == 400
        assert "_layout" in exc_info.value.detail
        assert "pages/" in exc_info.value.detail

    def test_invalid_layout_in_modules(self):
        """_layout in modules/ is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("modules/_layout")
        assert exc_info.value.status_code == 400

    # ==========================================================================
    # Invalid paths - special characters
    # ==========================================================================

    def test_invalid_special_chars(self):
        """Paths with special characters are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("components/my.component")
        assert exc_info.value.status_code == 400
        assert "Invalid path segment" in exc_info.value.detail

    def test_invalid_spaces(self):
        """Paths with spaces are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_path("components/my component")
        assert exc_info.value.status_code == 400
        assert "Invalid path segment" in exc_info.value.detail

    # ==========================================================================
    # Edge cases
    # ==========================================================================

    def test_strips_leading_slash(self):
        """Leading slashes are stripped."""
        validate_file_path("/pages/index")

    def test_strips_trailing_slash(self):
        """Trailing slashes are stripped."""
        validate_file_path("pages/index/")

    def test_valid_deeply_nested(self):
        """Deeply nested paths are valid."""
        validate_file_path("components/ui/forms/fields/TextInput")
        validate_file_path("modules/services/auth/providers/oauth")
        validate_file_path("pages/admin/users/[id]/settings/profile")
