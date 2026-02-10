"""Tests for reserved prefix validation."""
import pytest


def test_repo_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_repo")


def test_repo_slash_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_repo/something")


def test_tmp_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_tmp")


def test_regular_location_accepted():
    from src.core.reserved_prefixes import validate_sdk_location
    # Should not raise
    validate_sdk_location("uploads")
    validate_sdk_location("exports")
    validate_sdk_location("my-custom-folder")
    validate_sdk_location("data/subfolder")


def test_empty_string_accepted():
    """Empty string = root of bucket (workspace), should be fine."""
    from src.core.reserved_prefixes import validate_sdk_location
    validate_sdk_location("")


def test_workspace_legacy_accepted():
    """Legacy 'workspace' location should still work."""
    from src.core.reserved_prefixes import validate_sdk_location
    validate_sdk_location("workspace")
