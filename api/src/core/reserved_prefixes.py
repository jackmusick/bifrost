"""
Reserved S3 prefix validation.

Prevents SDK file operations from accessing platform-managed prefixes.
"""

RESERVED_PREFIXES = frozenset({"_repo", "_tmp"})


def validate_sdk_location(location: str) -> None:
    """
    Validate that an SDK file location is not a reserved prefix.

    Raises ValueError if the location starts with a reserved prefix.
    """
    normalized = location.strip("/")
    for prefix in RESERVED_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            raise ValueError(
                f"Location '{location}' is reserved for platform use. "
                f"Reserved prefixes: {', '.join(sorted(RESERVED_PREFIXES))}"
            )
