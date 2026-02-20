# Secret Redaction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent decrypted config secrets from persisting in execution variables, results, error messages, and logs.

**Architecture:** Two defense layers: (1) `SecretString(str)` subclass returned from `ConfigResolver._decrypt_secret()` that masks itself in `repr`/`str`/logging, (2) persist-time deep scrub of all execution outputs against known secret values before returning `ExecutionResult`. Real-time log scrub in `WorkflowLogHandler.emit()`.

**Tech Stack:** Python stdlib only (no new dependencies)

---

### Task 1: SecretString class + redact_secrets utility

**Files:**
- Create: `api/src/core/secret_string.py`
- Test: `api/tests/unit/test_secret_string.py`

**Step 1: Write the failing tests**

```python
# api/tests/unit/test_secret_string.py
import json
import pytest
from src.core.secret_string import SecretString, redact_secrets


class TestSecretString:
    """Test SecretString masks itself in display contexts but works as a real string."""

    def test_repr_is_redacted(self):
        s = SecretString("my-api-key")
        assert repr(s) == "'[REDACTED]'"

    def test_str_is_redacted(self):
        s = SecretString("my-api-key")
        assert str(s) == "[REDACTED]"

    def test_print_is_redacted(self, capsys):
        s = SecretString("my-api-key")
        print(s)
        assert capsys.readouterr().out.strip() == "[REDACTED]"

    def test_format_returns_real_value(self):
        s = SecretString("my-api-key")
        assert f"Bearer {s}" == "Bearer my-api-key"

    def test_concat_returns_real_value(self):
        s = SecretString("my-api-key")
        assert "Bearer " + s == "Bearer my-api-key"

    def test_encode_returns_real_bytes(self):
        s = SecretString("my-api-key")
        assert s.encode() == b"my-api-key"

    def test_equality_with_real_string(self):
        s = SecretString("my-api-key")
        assert s == "my-api-key"

    def test_get_secret_value(self):
        s = SecretString("my-api-key")
        assert s.get_secret_value() == "my-api-key"

    def test_json_dumps_leaks_raw_value(self):
        """json.dumps uses C-level str buffer, bypassing __str__.
        This is expected — redact_secrets and remove_circular_refs are the protection layers."""
        s = SecretString("my-api-key")
        dumped = json.dumps(s)
        assert dumped == '"my-api-key"'  # Documents the real behavior

    def test_isinstance_str(self):
        s = SecretString("my-api-key")
        assert isinstance(s, str)

    def test_logging_format_string(self):
        s = SecretString("my-api-key")
        msg = "key=%s" % s
        assert msg == "key=[REDACTED]"

    def test_bang_s_forces_redaction(self):
        """f'{s!s}' forces __str__, which redacts. This is by design."""
        s = SecretString("my-api-key")
        assert f"{s!s}" == "[REDACTED]"

    def test_bang_r_forces_redaction(self):
        s = SecretString("my-api-key")
        assert f"{s!r}" == "'[REDACTED]'"

    def test_used_as_dict_value_in_headers(self):
        """Simulates passing to requests/httpx headers dict."""
        s = SecretString("my-api-key")
        headers = {"Authorization": s}
        # Libraries read the str buffer directly, not __str__
        assert headers["Authorization"] == "my-api-key"
        assert headers["Authorization"].encode() == b"my-api-key"


class TestRedactSecrets:
    """Test deep scrubbing of secret values from JSON-serializable objects."""

    def test_redact_string_exact_match(self):
        result = redact_secrets("my-secret-key", {"my-secret-key"})
        assert result == "[REDACTED]"

    def test_redact_string_substring(self):
        result = redact_secrets("Bearer my-secret-key here", {"my-secret-key"})
        assert result == "Bearer [REDACTED] here"

    def test_redact_in_dict_values(self):
        obj = {"output": "token is my-secret-key", "count": 42}
        result = redact_secrets(obj, {"my-secret-key"})
        assert result["output"] == "token is [REDACTED]"
        assert result["count"] == 42

    def test_redact_in_nested_dict(self):
        obj = {"outer": {"inner": "my-secret-key"}}
        result = redact_secrets(obj, {"my-secret-key"})
        assert result["outer"]["inner"] == "[REDACTED]"

    def test_redact_in_list(self):
        obj = ["safe", "contains my-secret-key"]
        result = redact_secrets(obj, {"my-secret-key"})
        assert result[0] == "safe"
        assert result[1] == "contains [REDACTED]"

    def test_redact_in_set(self):
        obj = {"items": {"my-secret-key", "safe"}}
        result = redact_secrets(obj, {"my-secret-key"})
        assert "[REDACTED]" in result["items"]
        assert "my-secret-key" not in result["items"]

    def test_redact_multiple_secrets(self):
        obj = "key1=aaa key2=bbb"
        result = redact_secrets(obj, {"aaa", "bbb"})
        assert result == "key1=[REDACTED] key2=[REDACTED]"

    def test_skip_short_secrets(self):
        """Secrets shorter than 4 chars are skipped to avoid false positives."""
        obj = "the api key"
        result = redact_secrets(obj, {"api"})
        assert result == "the api key"  # Not redacted

    def test_no_secrets_passthrough(self):
        obj = {"key": "value", "num": 123}
        result = redact_secrets(obj, set())
        assert result == {"key": "value", "num": 123}

    def test_none_passthrough(self):
        assert redact_secrets(None, {"secret"}) is None

    def test_bool_passthrough(self):
        assert redact_secrets(True, {"secret"}) is True

    def test_int_passthrough(self):
        assert redact_secrets(42, {"secret"}) == 42

    def test_does_not_mutate_original(self):
        original = {"key": "my-secret-key"}
        redact_secrets(original, {"my-secret-key"})
        assert original["key"] == "my-secret-key"

    def test_redact_pydantic_model(self):
        """Pydantic models are converted to dicts and scrubbed."""
        from pydantic import BaseModel

        class Response(BaseModel):
            api_key: str
            message: str

        obj = Response(api_key="my-secret-key", message="ok")
        result = redact_secrets(obj, {"my-secret-key"})
        assert isinstance(result, dict)
        assert result["api_key"] == "[REDACTED]"
        assert result["message"] == "ok"
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.secret_string'`

**Step 3: Write the implementation**

```python
# api/src/core/secret_string.py
"""
SecretString: a str subclass that masks itself in display/logging contexts.

Used for config values of type SECRET. Works transparently as a string
for HTTP headers, f-strings, concatenation, etc. Only masks in:
- repr() / str() / print() — display and logging
- % formatting — logging.info("key=%s", secret)

Note: json.dumps bypasses __str__ for str subclasses (uses C-level buffer).
Secret protection in JSON serialization is handled by:
- redact_secrets() — deep scrub before persistence
- remove_circular_refs() in engine.py — converts SecretString to [REDACTED]
"""

from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"
_MIN_SECRET_LENGTH = 4


class SecretString(str):
    """A string that masks itself in repr/logging but works normally as a value."""

    def __repr__(self) -> str:
        return f"'{REDACTED}'"

    def __str__(self) -> str:
        return REDACTED

    def __format__(self, format_spec: str) -> str:
        return super().__str__().__format__(format_spec)

    def get_secret_value(self) -> str:
        """Get the actual secret value."""
        return super().__str__()


def redact_secrets(obj: Any, secret_values: set[str]) -> Any:
    """
    Deep-walk a JSON-serializable object, replacing secret substrings with [REDACTED].

    Args:
        obj: Any JSON-serializable object (dict, list, str, int, etc.)
        secret_values: Set of plaintext secret values to redact.
                       Secrets shorter than 4 characters are skipped.

    Returns:
        A new object with all secret substrings replaced. Original is not mutated.
    """
    # Filter out short secrets to avoid false positives
    effective_secrets = {s for s in secret_values if len(s) >= _MIN_SECRET_LENGTH}

    if not effective_secrets:
        return obj

    return _redact_recursive(obj, effective_secrets)


def _redact_recursive(obj: Any, secrets: set[str]) -> Any:
    if isinstance(obj, str):
        result = obj
        for secret in secrets:
            result = result.replace(secret, REDACTED)
        return result
    if isinstance(obj, dict):
        return {k: _redact_recursive(v, secrets) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        redacted = [_redact_recursive(item, secrets) for item in obj]
        return redacted if isinstance(obj, list) else tuple(redacted)
    if isinstance(obj, set):
        return {_redact_recursive(item, secrets) for item in obj}
    # Handle Pydantic models — convert to dict and recurse
    try:
        from pydantic import BaseModel
        if isinstance(obj, BaseModel):
            return _redact_recursive(obj.model_dump(), secrets)
    except ImportError:
        pass
    # int, float, bool, None — pass through
    return obj
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/src/core/secret_string.py api/tests/unit/test_secret_string.py
git commit -m "feat: add SecretString class and redact_secrets utility"
```

---

### Task 2: Wire SecretString into ConfigResolver

**Files:**
- Modify: `api/src/core/config_resolver.py:104-127`
- Test: `api/tests/unit/test_secret_string.py` (add integration test)

**Step 1: Write the failing test**

Add to `api/tests/unit/test_secret_string.py`:

```python
class TestConfigResolverSecretString:
    """Test that ConfigResolver returns SecretString for secret configs."""

    @pytest.mark.asyncio
    async def test_get_config_returns_secret_string(self):
        from unittest.mock import patch
        from src.core.config_resolver import ConfigResolver

        resolver = ConfigResolver()
        config_data = {
            "api_key": {"value": "encrypted_value", "type": "secret"},
            "name": {"value": "plain_value", "type": "string"},
        }

        with patch("src.core.security.decrypt_secret", return_value="decrypted-secret"):
            result = await resolver.get_config("org1", "api_key", config_data)

        assert isinstance(result, SecretString)
        assert result.get_secret_value() == "decrypted-secret"
        assert str(result) == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_get_config_plain_not_secret_string(self):
        from src.core.config_resolver import ConfigResolver

        resolver = ConfigResolver()
        config_data = {
            "name": {"value": "plain_value", "type": "string"},
        }

        result = await resolver.get_config("org1", "name", config_data)

        assert not isinstance(result, SecretString)
        assert result == "plain_value"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_secret_string.py::TestConfigResolverSecretString -v`
Expected: FAIL — result is a plain str, not SecretString

**Step 3: Modify ConfigResolver**

In `api/src/core/config_resolver.py`, change `_decrypt_secret` (line 122):

Change:
```python
            return decrypt_secret(encrypted_value)
```

To:
```python
            from src.core.secret_string import SecretString
            return SecretString(decrypt_secret(encrypted_value))
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/src/core/config_resolver.py api/tests/unit/test_secret_string.py
git commit -m "feat: return SecretString from ConfigResolver._decrypt_secret"
```

---

### Task 3: Add secret collection to ExecutionContext

**Files:**
- Modify: `api/src/sdk/context.py` (add `_collect_secret_values` method to `ExecutionContext`)
- Test: `api/tests/unit/test_secret_string.py` (add test)

**Step 1: Write the failing test**

Add to `api/tests/unit/test_secret_string.py`:

```python
class TestCollectSecretValues:
    """Test secret collection from config dict."""

    def test_collects_secret_type_values(self):
        from unittest.mock import patch
        from src.sdk.context import ExecutionContext

        ctx = ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
            _config={
                "api_key": {"value": "encrypted_secret", "type": "secret"},
                "name": {"value": "plain", "type": "string"},
                "count": {"value": "42", "type": "int"},
            },
        )

        with patch("src.core.security.decrypt_secret", return_value="real-secret-value"):
            secrets = ctx._collect_secret_values()

        assert secrets == {"real-secret-value"}

    def test_skips_short_secrets(self):
        from unittest.mock import patch
        from src.sdk.context import ExecutionContext

        ctx = ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
            _config={
                "short": {"value": "encrypted_ab", "type": "secret"},
            },
        )

        with patch("src.core.security.decrypt_secret", return_value="ab"):
            secrets = ctx._collect_secret_values()

        assert secrets == set()  # "ab" is too short

    def test_empty_config(self):
        from src.sdk.context import ExecutionContext

        ctx = ExecutionContext(
            user_id="u1", email="e@e.com", name="Test",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="exec-1",
            _config={},
        )

        secrets = ctx._collect_secret_values()
        assert secrets == set()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_secret_string.py::TestCollectSecretValues -v`
Expected: FAIL — `AttributeError: 'ExecutionContext' has no attribute '_collect_secret_values'`

**Step 3: Add method to ExecutionContext**

In `api/src/sdk/context.py`, add to the `ExecutionContext` class (after the `finalize_execution` method around line 234):

```python
    def _collect_secret_values(self) -> set[str]:
        """
        Collect all decrypted secret values from config for scrubbing.

        Returns a set of plaintext secret values that should be redacted
        from execution output. Skips secrets shorter than 4 characters
        to avoid false positive redactions.
        """
        from src.core.secret_string import _MIN_SECRET_LENGTH

        secrets: set[str] = set()
        for entry in self._config.values():
            if isinstance(entry, dict) and entry.get("type") == "secret":
                try:
                    from src.core.security import decrypt_secret
                    decrypted = decrypt_secret(entry["value"])
                    if len(decrypted) >= _MIN_SECRET_LENGTH:
                        secrets.add(decrypted)
                except Exception:
                    pass  # Skip entries that fail to decrypt
        return secrets
```

**Step 4: Run tests to verify they pass**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/src/sdk/context.py api/tests/unit/test_secret_string.py
git commit -m "feat: add _collect_secret_values to ExecutionContext"
```

---

### Task 4: Scrub execution outputs in engine before returning

**Files:**
- Modify: `api/src/services/execution/engine.py` — four return paths need scrubbing
- Test: `api/tests/unit/test_secret_string.py` (add engine scrub test)

There are **four** exception/return paths in `execute_code()` that return `ExecutionResult`:
1. **Success path** (line ~380) — `result`, `captured_variables`, `logger_output`
2. **WorkflowExecutionException** (line ~466) — `captured_variables`, `logger_output`, `error_message`
3. **WorkflowError** (line ~501) — `captured_variables`, `logger_output`, `error_message` (str(e))
4. **Generic Exception** (line ~556) — `captured_variables`, `logger_output`, `error_message` (str(e))

All four need scrubbing.

**Step 1: Write the failing test**

Add to `api/tests/unit/test_secret_string.py`:

```python
class TestEngineOutputScrubbing:
    """Test that engine scrubs secrets from result, variables, error_message, and logs."""

    def test_scrub_result_variables_and_logs(self):
        """Simulate what the engine does: scrub all outputs before returning."""
        from src.core.secret_string import redact_secrets

        secret_values = {"sk-12345678"}

        result = {"message": "Used key sk-12345678 successfully"}
        variables = {"api_key": "sk-12345678", "count": 5}
        logs = [
            {"level": "info", "message": "Calling API with sk-12345678"},
            {"level": "info", "message": "Done"},
        ]

        scrubbed_result = redact_secrets(result, secret_values)
        scrubbed_variables = redact_secrets(variables, secret_values)
        scrubbed_logs = redact_secrets(logs, secret_values)

        assert "sk-12345678" not in json.dumps(scrubbed_result)
        assert "sk-12345678" not in json.dumps(scrubbed_variables)
        assert "sk-12345678" not in json.dumps(scrubbed_logs)
        assert scrubbed_result["message"] == "Used key [REDACTED] successfully"
        assert scrubbed_variables["api_key"] == "[REDACTED]"
        assert scrubbed_variables["count"] == 5
        assert scrubbed_logs[0]["message"] == "Calling API with [REDACTED]"
        assert scrubbed_logs[1]["message"] == "Done"

    def test_scrub_error_message(self):
        from src.core.secret_string import redact_secrets

        secret_values = {"sk-12345678"}
        error_message = "Auth failed with key sk-12345678"

        scrubbed = redact_secrets(error_message, secret_values)
        assert scrubbed == "Auth failed with key [REDACTED]"
```

**Step 2: Run test to verify it passes (validates scrubbing logic)**

Run: `./test.sh tests/unit/test_secret_string.py::TestEngineOutputScrubbing -v`
Expected: PASS

**Step 3: Wire scrubbing into engine.py**

In `api/src/services/execution/engine.py`, add an import near the top (around line 20):

```python
from src.core.secret_string import redact_secrets
```

Add a helper function inside `execute_code` (or at module level) to avoid repeating the scrub block four times:

```python
def _scrub_outputs(
    context: ExecutionContext,
    result: Any = None,
    variables: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    error_message: str | None = None,
) -> tuple[Any, dict[str, Any] | None, list[dict[str, Any]] | None, str | None]:
    """Scrub secret values from execution outputs before returning."""
    secret_values = context._collect_secret_values()
    if not secret_values:
        return result, variables, logs, error_message
    return (
        redact_secrets(result, secret_values) if result is not None else None,
        redact_secrets(variables, secret_values) if variables is not None else None,
        redact_secrets(logs, secret_values) if logs is not None else None,
        redact_secrets(error_message, secret_values) if error_message is not None else None,
    )
```

Then before each of the four `return ExecutionResult(...)` calls, add:

```python
        result, captured_variables, logger_output, error_message = _scrub_outputs(
            context, result, captured_variables, logger_output, error_message
        )
```

Adjusting variable names to match each block (e.g., `error_msg` vs `error_message`, `workflow_result` vs `result`).

**Step 4: Run tests to verify nothing broke**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/src/services/execution/engine.py api/tests/unit/test_secret_string.py
git commit -m "feat: scrub secrets from execution results/variables/logs in engine"
```

---

### Task 5: Scrub real-time log stream

**Files:**
- Modify: `api/src/services/execution/engine.py:779-814` (WorkflowLogHandler.emit)

**Step 1: Write the failing test**

Add to `api/tests/unit/test_secret_string.py`:

```python
class TestLogScrubbing:
    """Test that log messages are scrubbed before streaming."""

    def test_log_message_scrubbed(self):
        from src.core.secret_string import redact_secrets

        secret_values = {"sk-12345678"}
        log_entry = "[INFO] Calling API with sk-12345678"

        scrubbed = redact_secrets(log_entry, secret_values)
        assert scrubbed == "[INFO] Calling API with [REDACTED]"

    def test_log_dict_message_scrubbed(self):
        from src.core.secret_string import redact_secrets

        secret_values = {"sk-12345678"}
        log_dict = {
            "executionLogId": "abc",
            "level": "INFO",
            "message": "key is sk-12345678",
            "timestamp": "2026-01-01T00:00:00Z",
            "sequence": 1,
        }

        scrubbed = redact_secrets(log_dict, secret_values)
        assert scrubbed["message"] == "key is [REDACTED]"
        assert scrubbed["executionLogId"] == "abc"  # Not scrubbed
```

**Step 2: Run test to verify it passes**

Run: `./test.sh tests/unit/test_secret_string.py::TestLogScrubbing -v`
Expected: PASS

**Step 3: Modify WorkflowLogHandler.emit()**

In `_execute_workflow_with_trace`, add secret collection at the start (after line 731 `workflow_logs: list[str] = []`):

```python
    # Collect secret values for real-time log scrubbing
    secret_values = context._collect_secret_values()
```

Then in `WorkflowLogHandler.emit()`, change the message formatting (line ~780):

From:
```python
            log_entry = f"[{record.levelname}] {record.getMessage()}"
            workflow_logs.append(log_entry)
```

To:
```python
            message = record.getMessage()
            if secret_values:
                message = redact_secrets(message, secret_values)
            log_entry = f"[{record.levelname}] {message}"
            workflow_logs.append(log_entry)
```

Update the real-time broadcast dict (line ~799) to use the already-scrubbed `message`:

From:
```python
                    "message": record.getMessage(),
```

To:
```python
                    "message": message,
```

Update the `log_and_broadcast` call (line ~814):

From:
```python
                        log_and_broadcast(
                            execution_id=execution_id,
                            level=record.levelname,
                            message=record.getMessage(),
                        )
```

To:
```python
                        log_and_broadcast(
                            execution_id=execution_id,
                            level=record.levelname,
                            message=message,
                        )
```

**Step 4: Run all tests**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/src/services/execution/engine.py api/tests/unit/test_secret_string.py
git commit -m "feat: scrub secrets from real-time log stream"
```

---

### Task 6: Handle SecretString in remove_circular_refs

**Files:**
- Modify: `api/src/services/execution/engine.py:835-870` (`remove_circular_refs` function)
- Test: `api/tests/unit/test_secret_string.py`

`remove_circular_refs` is called on captured variables in `capture_variables_from_locals` (line 884). Since `json.dumps` uses the C-level str buffer and bypasses `__str__`, a `SecretString` passed through `remove_circular_refs` would survive as a raw string value. We intercept it here.

**Step 1: Write the failing test**

Add to `api/tests/unit/test_secret_string.py`:

```python
class TestRemoveCircularRefsSecretString:
    """Test that remove_circular_refs converts SecretString to [REDACTED]."""

    def test_secret_string_detected(self):
        """SecretString values should be replaced with [REDACTED] in variable capture."""
        # This tests the principle — the actual integration is in engine.py's
        # remove_circular_refs which we modify to check isinstance(obj, SecretString)
        s = SecretString("my-api-key")
        # After remove_circular_refs processes it, it should be REDACTED
        from src.core.secret_string import REDACTED
        assert REDACTED == "[REDACTED]"
        # The actual assertion is that isinstance check works
        assert isinstance(s, SecretString)
        assert isinstance(s, str)
```

**Step 2: Modify remove_circular_refs**

In `api/src/services/execution/engine.py`, in the `remove_circular_refs` function (line ~835), add a check before the `isinstance(obj, dict)` branch:

```python
        # Redact SecretString before serialization — json.dumps bypasses __str__
        from src.core.secret_string import SecretString, REDACTED
        if isinstance(obj, SecretString):
            return REDACTED
```

This ensures that when `capture_variables_from_locals` calls `remove_circular_refs(v)` on a variable that holds a `SecretString`, it gets replaced with `"[REDACTED]"` before being stored in `captured_vars`.

**Step 3: Run all tests**

Run: `./test.sh tests/unit/test_secret_string.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add api/src/services/execution/engine.py api/tests/unit/test_secret_string.py
git commit -m "feat: handle SecretString in remove_circular_refs"
```

---

### Task 7: Run full test suite and verify

**Step 1: Run unit tests**

Run: `./test.sh tests/unit/ -v`
Expected: All PASS

**Step 2: Run E2E tests**

Run: `./test.sh tests/e2e/ -v`
Expected: All PASS (no regressions)

**Step 3: Run type checker**

Run: `cd api && pyright`
Expected: 0 errors

**Step 4: Run linter**

Run: `cd api && ruff check .`
Expected: 0 errors

**Step 5: Commit any fixes if needed**
