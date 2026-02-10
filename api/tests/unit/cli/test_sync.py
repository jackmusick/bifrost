"""Tests for bifrost sync command."""
from bifrost.sync import format_preview_summary


class TestFormatPreviewSummary:
    """Test preview output formatting."""

    def test_empty_sync(self):
        """Should report no changes when preview is empty."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [],
            "preflight": {"valid": True, "issues": []},
            "is_empty": True,
        }
        lines = format_preview_summary(preview)
        assert any("no changes" in line.lower() for line in lines)

    def test_clean_sync(self):
        """Should summarize pull/push counts without conflicts."""
        preview = {
            "to_pull": [
                {"path": "workflows/a.py", "action": "add", "display_name": "a"},
                {"path": "workflows/b.py", "action": "modify", "display_name": "b"},
            ],
            "to_push": [
                {"path": "workflows/c.py", "action": "add", "display_name": "c"},
            ],
            "conflicts": [],
            "preflight": {"valid": True, "issues": []},
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "2" in text  # 2 to pull
        assert "1" in text  # 1 to push

    def test_conflicts_shown(self):
        """Should list each conflict with path and resolve command."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [
                {
                    "path": "workflows/billing.py",
                    "display_name": "billing",
                    "entity_type": "workflow",
                },
            ],
            "preflight": {"valid": True, "issues": []},
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "workflows/billing.py" in text
        assert "--resolve" in text

    def test_preflight_errors_shown(self):
        """Should show preflight errors."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [],
            "preflight": {
                "valid": False,
                "issues": [
                    {
                        "path": "workflows/bad.py",
                        "line": 42,
                        "message": "SyntaxError: unexpected indent",
                        "severity": "error",
                        "category": "syntax",
                    },
                ],
            },
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "workflows/bad.py" in text
        assert "SyntaxError" in text
        assert "error" in text.lower()

    def test_preflight_warnings_shown(self):
        """Should show preflight warnings."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [],
            "preflight": {
                "valid": True,
                "issues": [
                    {
                        "path": "workflows/messy.py",
                        "message": "unused import",
                        "severity": "warning",
                        "category": "lint",
                    },
                ],
            },
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "workflows/messy.py" in text
        assert "unused import" in text
        assert "warning" in text.lower()
