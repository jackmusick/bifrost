"""Unit tests for app file MCP tools."""

from src.services.mcp_server.tools.app_files import _validate_file_path


class TestValidateFilePath:
    """Tests for the _validate_file_path validation function."""

    # Valid paths
    def test_valid_root_layout(self):
        assert _validate_file_path("_layout.tsx") is None

    def test_valid_root_providers(self):
        assert _validate_file_path("_providers.tsx") is None

    def test_valid_pages(self):
        assert _validate_file_path("pages/index.tsx") is None
        assert _validate_file_path("pages/_layout.tsx") is None
        assert _validate_file_path("pages/clients/index.tsx") is None

    def test_valid_components(self):
        assert _validate_file_path("components/Button.tsx") is None
        assert _validate_file_path("components/ui/Card.tsx") is None

    def test_valid_modules(self):
        assert _validate_file_path("modules/api.ts") is None
        assert _validate_file_path("modules/services/auth.ts") is None

    def test_valid_dynamic_routes(self):
        assert _validate_file_path("pages/[id].tsx") is None
        assert _validate_file_path("pages/clients/[id]/edit.tsx") is None

    # Invalid paths
    def test_invalid_empty(self):
        error = _validate_file_path("")
        assert error is not None
        assert "empty" in error.lower()

    def test_invalid_root_file(self):
        error = _validate_file_path("main.tsx")
        assert error is not None
        assert "_layout" in error or "_providers" in error

    def test_invalid_top_dir(self):
        error = _validate_file_path("services/api.ts")
        assert error is not None
        assert "pages" in error

    def test_invalid_dynamic_in_components(self):
        error = _validate_file_path("components/[id].tsx")
        assert error is not None
        assert "Dynamic" in error

    def test_invalid_layout_in_modules(self):
        error = _validate_file_path("modules/_layout.tsx")
        assert error is not None
        assert "_layout" in error

    def test_strips_slashes(self):
        assert _validate_file_path("/pages/index.tsx/") is None
        assert _validate_file_path("/_layout.tsx") is None
