from src.sdk.context import ExecutionContext


class TestCollectSecretValues:
    """Test secret collection returns only dynamic secrets."""

    def test_empty_by_default(self):
        ctx = ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
        )

        secrets = ctx._collect_secret_values()
        assert secrets == set()

    def test_returns_dynamic_secrets(self):
        ctx = ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
        )
        ctx._register_dynamic_secret("super-secret-token")
        assert ctx._collect_secret_values() == {"super-secret-token"}


class TestRegisterDynamicSecret:
    """Test dynamic secret registration on ExecutionContext."""

    def _make_ctx(self, **kwargs):
        return ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
            **kwargs,
        )

    def test_register_and_collect(self):
        ctx = self._make_ctx()
        ctx._register_dynamic_secret("super-secret-token")
        assert "super-secret-token" in ctx._collect_secret_values()

    def test_short_secret_excluded(self):
        ctx = self._make_ctx()
        ctx._register_dynamic_secret("ab")
        assert "ab" not in ctx._collect_secret_values()

    def test_none_is_noop(self):
        ctx = self._make_ctx()
        ctx._register_dynamic_secret(None)
        assert ctx._collect_secret_values() == set()

    def test_empty_string_excluded(self):
        ctx = self._make_ctx()
        ctx._register_dynamic_secret("")
        assert ctx._collect_secret_values() == set()

    def test_multiple_secrets(self):
        ctx = self._make_ctx()
        ctx._register_dynamic_secret("first-token-abc")
        ctx._register_dynamic_secret("second-token-xyz")
        secrets = ctx._collect_secret_values()
        assert "first-token-abc" in secrets
        assert "second-token-xyz" in secrets
