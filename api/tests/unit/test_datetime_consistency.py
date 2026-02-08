"""
Static analysis tests to enforce datetime standardization.

These tests scan the codebase to ensure no timezone-aware datetime patterns
are reintroduced after standardization.
"""
from pathlib import Path


API_SRC_DIR = Path(__file__).parent.parent.parent / "src"
API_MODELS_ORM_DIR = API_SRC_DIR / "models" / "orm"


def get_python_files(directory: Path) -> list[Path]:
    """Get all Python files in a directory recursively."""
    return list(directory.rglob("*.py"))


class TestDatetimeConsistency:
    """Ensure datetime patterns are consistent across the codebase."""

    def test_no_timezone_aware_columns_in_orm(self):
        """ORM models must not use DateTime(timezone=True)."""
        violations = []

        for py_file in get_python_files(API_MODELS_ORM_DIR):
            content = py_file.read_text()
            if "DateTime(timezone=True)" in content:
                # Find line numbers
                for i, line in enumerate(content.split("\n"), 1):
                    if "DateTime(timezone=True)" in line:
                        violations.append(f"{py_file.name}:{i}")

        assert not violations, (
            "Found DateTime(timezone=True) in ORM models. "
            "Use DateTime() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_datetime_now_with_timezone_utc(self):
        """Code must not use datetime.now(timezone.utc)."""
        violations = []

        for py_file in get_python_files(API_SRC_DIR):
            content = py_file.read_text()
            if "datetime.now(timezone.utc)" in content:
                for i, line in enumerate(content.split("\n"), 1):
                    if "datetime.now(timezone.utc)" in line:
                        violations.append(f"{py_file.relative_to(API_SRC_DIR)}:{i}")

        assert not violations, (
            "Found datetime.now(timezone.utc) in source code. "
            "Use datetime.utcnow() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_bare_datetime_now(self):
        """Code must not use datetime.now() without timezone (local time)."""
        violations = []

        for py_file in get_python_files(API_SRC_DIR):
            content = py_file.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Match datetime.now() but not datetime.now(timezone.utc)
                if "datetime.now()" in line and "timezone" not in line:
                    # Skip comments
                    stripped = line.strip()
                    if not stripped.startswith("#"):
                        violations.append(f"{py_file.relative_to(API_SRC_DIR)}:{i}")

        assert not violations, (
            "Found datetime.now() (local time) in source code. "
            "Use datetime.utcnow() instead.\nViolations:\n" + "\n".join(violations)
        )

    def test_no_lambda_datetime_defaults_in_orm(self):
        """ORM models must not use lambda datetime defaults."""
        violations = []

        for py_file in get_python_files(API_MODELS_ORM_DIR):
            content = py_file.read_text()
            if "default=lambda:" in content and "datetime" in content:
                for i, line in enumerate(content.split("\n"), 1):
                    if "default=lambda:" in line and "datetime" in line:
                        violations.append(f"{py_file.name}:{i}")

        assert not violations, (
            "Found lambda datetime defaults in ORM models. "
            "Use default=datetime.utcnow instead.\nViolations:\n" + "\n".join(violations)
        )
