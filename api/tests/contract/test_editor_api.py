"""
Contract tests for editor API endpoints

Tests file operations, search, and editor-related models.
"""

import pytest
from pydantic import ValidationError
from src.models import (
    FileMetadata,
    FileType,
    FileContentRequest,
    FileContentResponse,
    SearchRequest,
    SearchResult,
    SearchResponse,
)


class TestEditorModelContracts:
    """Contract tests for editor API models"""

    def test_file_metadata_model_structure(self):
        """Test that FileMetadata model has required fields"""
        file = FileMetadata(
            path="workflows/test.py",
            name="test.py",
            type=FileType.FILE,
            size=1024,
            extension=".py",
            modified="2025-10-23T14:30:00Z",
            isReadOnly=False,
        )

        assert file.path == "workflows/test.py"
        assert file.name == "test.py"
        assert file.type == FileType.FILE
        assert file.size == 1024
        assert file.extension == ".py"
        assert file.modified == "2025-10-23T14:30:00Z"
        assert file.isReadOnly is False

    def test_file_metadata_folder_type(self):
        """Test FileMetadata for folder type"""
        folder = FileMetadata(
            path="workflows",
            name="workflows",
            type=FileType.FOLDER,
            size=None,
            extension=None,
            modified="2025-10-23T14:30:00Z",
            isReadOnly=False,
        )

        assert folder.type == FileType.FOLDER
        assert folder.size is None
        assert folder.extension is None

    def test_file_content_request_model(self):
        """Test FileContentRequest model structure"""
        request = FileContentRequest(
            path="workflows/test.py",
            content="import bifrost\n\ndef run(context):\n    pass",
            encoding="utf-8",
        )

        assert request.path == "workflows/test.py"
        assert "import bifrost" in request.content
        assert request.encoding == "utf-8"

    def test_file_content_request_default_encoding(self):
        """Test FileContentRequest uses utf-8 by default"""
        request = FileContentRequest(
            path="workflows/test.py", content="test content"
        )

        assert request.encoding == "utf-8"

    def test_file_content_response_model(self):
        """Test FileContentResponse model structure"""
        response = FileContentResponse(
            path="workflows/test.py",
            content="import bifrost",
            encoding="utf-8",
            size=14,
            etag="abc123",
            modified="2025-10-23T14:30:00Z",
        )

        assert response.path == "workflows/test.py"
        assert response.content == "import bifrost"
        assert response.encoding == "utf-8"
        assert response.size == 14
        assert response.etag == "abc123"
        assert response.modified == "2025-10-23T14:30:00Z"

    def test_search_request_model(self):
        """Test SearchRequest model structure"""
        request = SearchRequest(
            query="def run",
            case_sensitive=False,
            regex=False,
            include_pattern="**/*.py",
            max_results=100,
        )

        assert request.query == "def run"
        assert request.case_sensitive is False
        assert request.is_regex is False
        assert request.include_pattern == "**/*.py"
        assert request.max_results == 100

    def test_search_request_defaults(self):
        """Test SearchRequest default values"""
        request = SearchRequest(query="test")

        assert request.case_sensitive is False
        assert request.is_regex is False
        assert request.include_pattern == "**/*"
        assert request.max_results == 1000

    def test_search_request_validates_query_not_empty(self):
        """Test SearchRequest rejects empty query"""
        with pytest.raises(ValidationError):
            SearchRequest(query="")

    def test_search_request_validates_max_results_range(self):
        """Test SearchRequest validates max_results is within range"""
        # Valid range
        SearchRequest(query="test", max_results=1)
        SearchRequest(query="test", max_results=10000)

        # Too low
        with pytest.raises(ValidationError):
            SearchRequest(query="test", max_results=0)

        # Too high
        with pytest.raises(ValidationError):
            SearchRequest(query="test", max_results=10001)

    def test_search_result_model(self):
        """Test SearchResult model structure"""
        result = SearchResult(
            file_path="workflows/sync.py",
            line=42,
            column=15,
            match_text="def run",
            context_before="# Sync workflow",
            context_after="    context.info('Starting')",
        )

        assert result.file_path == "workflows/sync.py"
        assert result.line == 42
        assert result.column == 15
        assert result.match_text == "def run"
        assert result.context_before == "# Sync workflow"
        assert result.context_after == "    context.info('Starting')"

    def test_search_result_optional_context(self):
        """Test SearchResult with optional context fields"""
        result = SearchResult(
            file_path="workflows/sync.py",
            line=1,
            column=0,
            match_text="import",
            context_before=None,
            context_after=None,
        )

        assert result.context_before is None
        assert result.context_after is None

    def test_search_result_validates_line_number(self):
        """Test SearchResult validates line >= 1"""
        # Valid line numbers
        SearchResult(
            file_path="test.py",
            line=1,
            column=0,
            match_text="test",
        )

        # Invalid line number (must be >= 1)
        with pytest.raises(ValidationError):
            SearchResult(
                file_path="test.py",
                line=0,
                column=0,
                match_text="test",
            )

    def test_search_result_validates_column_number(self):
        """Test SearchResult validates column >= 0"""
        # Valid column numbers
        SearchResult(
            file_path="test.py",
            line=1,
            column=0,
            match_text="test",
        )

        # Invalid column number (must be >= 0)
        with pytest.raises(ValidationError):
            SearchResult(
                file_path="test.py",
                line=1,
                column=-1,
                match_text="test",
            )

    def test_search_response_model(self):
        """Test SearchResponse model structure"""
        results = [
            SearchResult(
                file_path="test1.py",
                line=10,
                column=5,
                match_text="test",
            ),
            SearchResult(
                file_path="test2.py",
                line=20,
                column=8,
                match_text="test",
            ),
        ]

        response = SearchResponse(
            query="test",
            total_matches=2,
            files_searched=50,
            results=results,
            truncated=False,
            search_time_ms=123,
        )

        assert response.query == "test"
        assert response.total_matches == 2
        assert response.files_searched == 50
        assert len(response.results) == 2
        assert response.truncated is False
        assert response.search_time_ms == 123

    def test_search_response_truncated_results(self):
        """Test SearchResponse with truncated results"""
        response = SearchResponse(
            query="test",
            total_matches=5000,
            files_searched=1000,
            results=[],  # Truncated
            truncated=True,
            search_time_ms=456,
        )

        assert response.total_matches == 5000
        assert len(response.results) == 0
        assert response.truncated is True

    def test_file_type_enum_values(self):
        """Test FileType enum has correct values"""
        assert FileType.FILE == "file"
        assert FileType.FOLDER == "folder"

        # Enum should only have these two values
        assert len(list(FileType)) == 2
