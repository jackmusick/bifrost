"""Tests for CRLF line ending normalization in bifrost sync."""

import base64
import hashlib
import pathlib
from unittest.mock import patch, MagicMock

from bifrost.cli import _normalize_line_endings, _compute_local_md5s, _collect_push_files


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


class TestComputeLocalHashesCRLF:
    @patch("bifrost.cli._build_file_filter", side_effect=_mock_file_filter)
    def test_crlf_matches_lf(self, _mock_filter, tmp_path: pathlib.Path):
        text = "hello\nworld\n"
        crlf_dir = tmp_path / "crlf"
        lf_dir = tmp_path / "lf"
        crlf_dir.mkdir()
        lf_dir.mkdir()

        (crlf_dir / "file.txt").write_bytes(text.replace("\n", "\r\n").encode())
        (lf_dir / "file.txt").write_bytes(text.encode())

        crlf_hashes = _compute_local_md5s(crlf_dir, "")
        lf_hashes = _compute_local_md5s(lf_dir, "")

        assert crlf_hashes["file.txt"] == lf_hashes["file.txt"]


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


class TestManifestHashCRLF:
    def test_manifest_hash_crlf_matches_lf(self, tmp_path: pathlib.Path):
        yaml_text = "name: test\nversion: 1\n"

        crlf_dir = tmp_path / "crlf" / ".bifrost"
        lf_dir = tmp_path / "lf" / ".bifrost"
        crlf_dir.mkdir(parents=True)
        lf_dir.mkdir(parents=True)

        (crlf_dir / "test.yaml").write_bytes(yaml_text.replace("\n", "\r\n").encode())
        (lf_dir / "test.yaml").write_bytes(yaml_text.encode())

        def hash_manifest(bifrost_dir: pathlib.Path) -> dict[str, str]:
            hashes: dict[str, str] = {}
            for bf in sorted(bifrost_dir.iterdir()):
                if bf.is_file() and bf.suffix in (".yaml", ".yml"):
                    content = _normalize_line_endings(bf.read_bytes())
                    hashes[f".bifrost/{bf.name}"] = hashlib.sha256(content).hexdigest()
            return hashes

        crlf_hashes = hash_manifest(crlf_dir)
        lf_hashes = hash_manifest(lf_dir)

        assert crlf_hashes == lf_hashes
        assert ".bifrost/test.yaml" in crlf_hashes
