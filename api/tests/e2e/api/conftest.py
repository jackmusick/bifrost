"""
E2E API test configuration.

Minimal fixtures - the E2E tests build their own state sequentially.
"""

import os


# API base URL - set by test.sh --e2e
API_BASE_URL = os.environ.get("TEST_API_URL", "http://localhost:18000")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
