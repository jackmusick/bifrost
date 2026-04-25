"""Tests for CRLF line ending normalization in bifrost sync."""

import base64
import pathlib
from unittest.mock import patch, MagicMock

from bifrost.cli import _normalize_line_endings, _collect_push_files


def _mock_file_filter(*args, **kwargs):
    """Return a mock PathSpec that never matches (skips nothing)."""
    spec = MagicMock()
    spec.match_file.return_value = False
    return spec


class TestNormalizeLineEndings:
    def test_basic_crlf(self):
        assert _normalize_line_endings(b"a\r\nb\r\n") == b"a\nb\n"

    def test_no_crlf_passthrough(self):
        data = b"a\nb\n"
        assert _normalize_line_endings(data) == data

    def test_mixed_endings(self):
        data = b"line1\r\nline2\nline3\r\n"
        assert _normalize_line_endings(data) == b"line1\nline2\nline3\n"

    def test_binary_with_crlf_unchanged(self):
        data = b"\x00binary\r\ndata\r\n"
        assert _normalize_line_endings(data) == data

    def test_real_png_header(self):
        # Real PNG signature contains both \r\n and \x00
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert _normalize_line_endings(png_header) == png_header

    def test_null_byte_after_8kb_treated_as_text(self):
        # Null byte only after 8KB boundary — treated as text
        data = b"text\r\n" * 1400 + b"\x00"
        result = _normalize_line_endings(data)
        assert b"\r\n" not in result
        assert result.endswith(b"\x00")

    def test_empty_data(self):
        assert _normalize_line_endings(b"") == b""

    def test_standalone_cr_unchanged(self):
        data = b"old\rmac\rline endings\n"
        assert _normalize_line_endings(data) == data


class TestCollectFilesCRLF:
    @patch("bifrost.cli._build_file_filter", side_effect=_mock_file_filter)
    def test_crlf_matches_lf(self, _mock_filter, tmp_path: pathlib.Path):
        text = "hello\nworld\n"
        crlf_dir = tmp_path / "crlf"
        lf_dir = tmp_path / "lf"
        crlf_dir.mkdir()
        lf_dir.mkdir()

        (crlf_dir / "file.txt").write_bytes(text.replace("\n", "\r\n").encode())
        (lf_dir / "file.txt").write_bytes(text.encode())

        crlf_files, _ = _collect_push_files(crlf_dir, "")
        lf_files, _ = _collect_push_files(lf_dir, "")

        assert crlf_files["file.txt"] == lf_files["file.txt"]
        # Verify content is LF-normalized
        decoded = base64.b64decode(crlf_files["file.txt"])
        assert decoded == text.encode()
