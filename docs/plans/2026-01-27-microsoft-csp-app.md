# Microsoft CSP Management App

## Overview

App-centric solution for managing Microsoft CSP tenants, linking them to Bifrost organizations, and granting application consent with dynamic permission selection.

---

## Phase 2: Enhanced Permission Management (Design)

### Problem Statement

The current CSP app:
- Stores tenant mappings in a custom `csp_tenant_status` table instead of using IntegrationMapping
- Hardcodes permissions in the consent workflow
- Doesn't support selecting delegated vs application permissions
- Doesn't properly set up the "Microsoft" integration for client credentials access to customer tenants

### Integration Architecture

#### Two Integrations

| Integration | OAuth Flow | Purpose |
|-------------|------------|---------|
| **Microsoft CSP** | Delegated (Authorization Code) | Partner Center API, GDAP access, listing managed tenants |
| **Microsoft** | Client Credentials | Graph, Exchange, SharePoint, Defender APIs in customer tenants |

#### Microsoft CSP Integration
- Standard OAuth with user sign-in
- Stores refresh token (long-lived with GDAP)
- Used by: `list_tenants`, consent workflows
- No `{entity_id}` templating - always hits partner tenant

#### Microsoft Integration
- Client credentials (App ID + Secret only, no user)
- Token URL: `https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token`
- No stored tokens - fetched on-demand when `integrations.get()` is called
- IntegrationMapping per customer org stores `entity_id` = customer tenant ID

#### Auto-Refresh for Templated URLs

When a token URL contains `{entity_id}`, the system automatically fetches a fresh token on each `integrations.get()` call rather than returning a stored token. This is necessary because:
1. Client credentials tokens are short-lived (1 hour for Microsoft)
2. Each customer tenant requires a different token endpoint
3. Storing tokens per-tenant creates refresh scheduling complexity

### Data Model Changes

#### IntegrationMapping (Microsoft integration)

```
organization_id: Bifrost org UUID
entity_id: Customer tenant ID (e.g., "9eb52e66-48e3-4a97-...")
entity_name: Customer name (e.g., "Covi Development")
oauth_token_id: NULL (not used - tokens fetched on-demand)
```

#### microsoft_selected_permissions (Bifrost table)

Scoped to platform org. Stores which permissions to consent when onboarding tenants.

```
api_id: "00000003-0000-0000-c000-000000000000"
api_name: "Microsoft Graph"
permission_name: "Directory.Read.All"
permission_type: "delegated" | "application"
created_at: timestamp
```

#### Supported Microsoft APIs

| API | Enterprise Application ID |
|-----|---------------------------|
| Microsoft Graph | `00000003-0000-0000-c000-000000000000` |
| Exchange Online | `00000002-0000-0ff1-ce00-000000000000` |
| SharePoint | `00000003-0000-0ff1-ce00-000000000000` |
| Windows Defender ATP | `fc780465-2017-40d4-a0c5-307022471b92` |

Future: Support adding custom APIs by enterprise application ID.

### User Flow

#### Setup Phase (one-time)
1. User navigates to Microsoft CSP app
2. Sees setup instructions for both integrations
3. Status cards show which integrations are connected
4. Once both connected → Permission selection unlocks

#### Permission Selection
1. User clicks "Configure" on Permissions card
2. Dialog fetches available permissions dynamically from Microsoft Graph
3. Two columns per API: Delegated | Application
4. User selects needed permissions, saves to table
5. Can revisit anytime to add more

#### Tenant Management
1. Only fully enabled after setup complete
2. Map tenants → Bifrost orgs (creates IntegrationMapping)
3. Consent button → runs consent workflow with selected permissions
4. Status shows consent state per tenant

### Consent Workflow (Enhanced)

When user clicks "Consent" on a tenant:

1. **Read selected permissions** from `microsoft_selected_permissions` table

2. **Grant delegated permissions** via Partner Center API:
   ```
   POST https://api.partnercenter.microsoft.com/v1/customers/{tenant_id}/applicationconsents
   {
     "applicationId": "{partner_app_id}",
     "applicationGrants": [{
       "enterpriseApplicationId": "00000003-0000-0000-c000-000000000000",
       "scope": "Directory.Read.All,User.Read.All,..."
     }]
   }
   ```

3. **Grant application permissions** via Graph API:
   - Connect to customer tenant using CSP delegated access
   - Find partner app's service principal in customer tenant
   - For each app permission, assign app role to service principal

4. **Create IntegrationMapping** for "Microsoft" integration:
   ```python
   await integrations.upsert_mapping(
       "Microsoft",
       scope=bifrost_org_id,
       entity_id=tenant_id,
       entity_name=tenant_name,
   )
   ```

5. **Update consent status** in `csp_tenant_status` table

### App UI Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  Microsoft CSP                                        [Refresh] │
│  Manage CSP customer tenants and grant application consent.     │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐ ┌───────────────────┐ ┌─────────────────┐│
│  │ Microsoft CSP     │ │ Microsoft         │ │ Permissions     ││
│  │ ✓ Connected       │ │ ✓ Connected       │ │ 4 delegated     ││
│  │ Partner Center    │ │ Client Credentials│ │ 12 application  ││
│  │                   │ │                   │ │ [Configure]     ││
│  └───────────────────┘ └───────────────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  CSP Customers                    [Search...] [Filter ▼]        │
│  Link tenants to Bifrost organizations and manage consent.      │
│                                                                 │
│  (tenant table with current search/filter functionality)        │
└─────────────────────────────────────────────────────────────────┘
```

#### Conditional Rendering
- Neither integration connected → Show setup instructions only
- CSP connected but not Microsoft → Show warning, disable consent buttons
- Both connected but no permissions selected → Show warning on permissions card
- All ready → Full UI with tenant table

### Implementation Phases

#### Phase 2a: Platform Changes
1. Add auto-refresh token fetching when `{entity_id}` in token_url
2. Create "Microsoft" integration with client credentials OAuth setup
3. Ensure "Microsoft CSP" integration exists with delegated OAuth

#### Phase 2b: Workflows
1. `check_microsoft_setup` - Returns status of both integrations
2. `list_available_permissions` - Fetches permissions from Microsoft service principals
3. `save_selected_permissions` - Persists to table
4. `get_selected_permissions` - Reads from table
5. Update `consent_tenant` - Use selected permissions, grant both delegated and app permissions, create IntegrationMapping

#### Phase 2c: App UI
1. Refactor page with three status cards header
2. Add setup instructions when integrations missing
3. Add permissions configuration dialog
4. Update tenant table to check prerequisites before enabling consent
5. Keep existing search/filter functionality

#### Phase 2d: Cleanup
1. Migrate existing `csp_tenant_status` mappings to IntegrationMapping
2. Remove redundant `entra_tenant_id` config usage

---

## Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable dynamic Microsoft permission selection and proper integration mapping for CSP tenant consent.

**Architecture:** Two integrations (Microsoft CSP for delegated Partner Center access, Microsoft for client credentials to customer tenants), auto-refresh tokens when URL contains `{entity_id}`, permission selection stored in Bifrost tables.

**Tech Stack:** Python/FastAPI (platform), Bifrost SDK (workflows), React/TSX (app UI)

---

### Task 1: Auto-Refresh Token for Templated URLs

**Files:**
- Modify: `api/src/routers/cli.py:540-600` (SDK integrations.get endpoint)
- Modify: `api/src/services/oauth_provider.py` (OAuthProviderClient)
- Create: `api/tests/unit/routers/test_cli_auto_refresh.py`

**Step 1: Write the failing test**

Create `api/tests/unit/routers/test_cli_auto_refresh.py`:

```python
"""Tests for auto-refresh token behavior when token_url contains {entity_id}."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAutoRefreshTokenForTemplatedUrl:
    """Test that integrations.get() auto-fetches token when URL has {entity_id}."""

    @pytest.mark.asyncio
    async def test_fetches_fresh_token_when_url_has_entity_id_placeholder(self):
        """When token_url contains {entity_id}, should fetch fresh client_credentials token."""
        from src.services.oauth_provider import OAuthProviderClient

        # Mock provider with templated URL
        provider = MagicMock()
        provider.token_url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        provider.client_id = "test-client-id"
        provider.encrypted_client_secret = b"encrypted-secret"
        provider.oauth_flow_type = "client_credentials"
        provider.scopes = ["https://graph.microsoft.com/.default"]
        provider.token_url_defaults = {}

        entity_id = "customer-tenant-123"

        # Mock the token fetch
        with patch.object(
            OAuthProviderClient,
            "get_client_credentials_token",
            new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = (True, {
                "access_token": "fresh-token-123",
                "expires_at": "2026-01-27T12:00:00Z",
            })

            # Import and call the function that should trigger auto-refresh
            from src.routers.cli import should_auto_refresh_token

            result = should_auto_refresh_token(provider, entity_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_no_auto_refresh_when_url_has_no_placeholder(self):
        """When token_url has no {entity_id}, should use stored token."""
        provider = MagicMock()
        provider.token_url = "https://oauth.example.com/token"
        provider.oauth_flow_type = "client_credentials"

        from src.routers.cli import should_auto_refresh_token

        result = should_auto_refresh_token(provider, "some-entity")

        assert result is False

    @pytest.mark.asyncio
    async def test_no_auto_refresh_for_authorization_code_flow(self):
        """Authorization code flow should never auto-refresh (uses stored refresh token)."""
        provider = MagicMock()
        provider.token_url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        provider.oauth_flow_type = "authorization_code"

        from src.routers.cli import should_auto_refresh_token

        result = should_auto_refresh_token(provider, "some-entity")

        assert result is False
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/routers/test_cli_auto_refresh.py -v`
Expected: FAIL with "cannot import name 'should_auto_refresh_token'"

**Step 3: Add helper function to cli.py**

Add to `api/src/routers/cli.py` after imports (~line 50):

```python
def should_auto_refresh_token(provider: Any, entity_id: str | None) -> bool:
    """
    Determine if we should auto-fetch a fresh token instead of using stored token.

    Auto-refresh when:
    1. Token URL contains {entity_id} placeholder (per-tenant endpoint)
    2. OAuth flow is client_credentials (not authorization_code)
    3. entity_id is provided

    This enables multi-tenant client credentials where each tenant
    requires hitting a different token endpoint.
    """
    if not provider or not entity_id:
        return False

    if not provider.token_url:
        return False

    # Only auto-refresh for client_credentials flow
    if provider.oauth_flow_type != "client_credentials":
        return False

    # Check if URL has {entity_id} placeholder
    return "{entity_id}" in provider.token_url
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/routers/test_cli_auto_refresh.py -v`
Expected: PASS

**Step 5: Write integration test for full flow**

Add to `api/tests/unit/routers/test_cli_auto_refresh.py`:

```python
class TestBuildOAuthDataWithAutoRefresh:
    """Test _build_oauth_data with auto-refresh behavior."""

    @pytest.mark.asyncio
    async def test_build_oauth_data_fetches_token_for_templated_url(self):
        """_build_oauth_data should fetch fresh token when URL has {entity_id}."""
        from src.routers.cli import _build_oauth_data
        from src.services.oauth_provider import resolve_url_template

        provider = MagicMock()
        provider.token_url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        provider.client_id = "test-client-id"
        provider.encrypted_client_secret = b"encrypted"
        provider.oauth_flow_type = "client_credentials"
        provider.scopes = ["https://graph.microsoft.com/.default"]
        provider.token_url_defaults = {}
        provider.provider_name = "Microsoft"
        provider.authorization_url = None

        entity_id = "customer-tenant-456"

        # Mock decrypt_secret
        async def mock_decrypt(val):
            return "decrypted-secret"

        # Mock the OAuth client
        with patch(
            "src.routers.cli.OAuthProviderClient"
        ) as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_client_credentials_token = AsyncMock(
                return_value=(True, {
                    "access_token": "fresh-access-token",
                    "expires_at": MagicMock(isoformat=lambda: "2026-01-27T12:00:00Z"),
                })
            )
            MockClient.return_value = mock_instance

            result = await _build_oauth_data(
                provider=provider,
                token=None,  # No stored token
                entity_id=entity_id,
                resolve_url_template=resolve_url_template,
                decrypt_secret=mock_decrypt,
            )

            # Should have fetched a fresh token
            mock_instance.get_client_credentials_token.assert_called_once()
            assert result.access_token == "fresh-access-token"
            assert result.token_url == f"https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
```

**Step 6: Update _build_oauth_data to support auto-refresh**

Modify `api/src/routers/cli.py` function `_build_oauth_data` (~line 605):

```python
async def _build_oauth_data(
    provider: Any,
    token: Any,
    entity_id: str | None,
    resolve_url_template: Any,
    decrypt_secret: Any,
) -> SDKIntegrationsOAuthData:
    """Build OAuth data dict from provider and token for CLI response."""
    from src.services.oauth_provider import OAuthProviderClient

    # Decrypt client_secret
    client_secret = None
    if provider.encrypted_client_secret:
        try:
            raw = provider.encrypted_client_secret
            client_secret = await asyncio.to_thread(
                decrypt_secret, raw.decode() if isinstance(raw, bytes) else raw
            )
        except Exception:
            logger.warning("Failed to decrypt client_secret")

    # Resolve token_url with entity_id
    resolved_token_url = None
    if provider.token_url:
        if entity_id:
            resolved_token_url = resolve_url_template(
                url=provider.token_url,
                entity_id=entity_id,
                defaults=provider.token_url_defaults,
            )
        else:
            resolved_token_url = provider.token_url

    access_token = None
    refresh_token = None
    expires_at = None

    # Check if we should auto-fetch a fresh token
    if should_auto_refresh_token(provider, entity_id):
        logger.info(f"Auto-refreshing token for templated URL (entity_id={entity_id})")

        if not client_secret:
            logger.error("Cannot auto-refresh: client_secret not available")
        elif not resolved_token_url:
            logger.error("Cannot auto-refresh: token_url not resolved")
        else:
            # Fetch fresh token using client credentials
            oauth_client = OAuthProviderClient()
            scopes = " ".join(provider.scopes) if provider.scopes else ""

            success, result = await oauth_client.get_client_credentials_token(
                token_url=resolved_token_url,
                client_id=provider.client_id,
                client_secret=client_secret,
                scopes=scopes,
            )

            if success:
                access_token = result.get("access_token")
                expires_at_dt = result.get("expires_at")
                if expires_at_dt:
                    expires_at = expires_at_dt.isoformat() if hasattr(expires_at_dt, 'isoformat') else str(expires_at_dt)
                logger.info("Auto-refresh token successful")
            else:
                logger.error(f"Auto-refresh token failed: {result.get('error_description', result.get('error'))}")

    else:
        # Use stored token (existing behavior)
        if token:
            if token.encrypted_access_token:
                try:
                    raw = token.encrypted_access_token
                    access_token = await asyncio.to_thread(
                        decrypt_secret, raw.decode() if isinstance(raw, bytes) else raw
                    )
                except Exception:
                    logger.warning("Failed to decrypt access_token")

            if token.encrypted_refresh_token:
                try:
                    raw = token.encrypted_refresh_token
                    refresh_token = await asyncio.to_thread(
                        decrypt_secret, raw.decode() if isinstance(raw, bytes) else raw
                    )
                except Exception:
                    logger.warning("Failed to decrypt refresh_token")

            if token.expires_at:
                expires_at = token.expires_at.isoformat()

    return SDKIntegrationsOAuthData(
        connection_name=provider.provider_name,
        client_id=provider.client_id,
        client_secret=client_secret,
        authorization_url=provider.authorization_url,
        token_url=resolved_token_url,
        scopes=provider.scopes or [],
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
```

**Step 7: Run all tests**

Run: `./test.sh api/tests/unit/routers/test_cli_auto_refresh.py -v`
Expected: All PASS

**Step 8: Run existing CLI tests to ensure no regression**

Run: `./test.sh api/tests/unit/routers/ -v -k cli`
Expected: All PASS

**Step 9: Commit**

```bash
git add api/src/routers/cli.py api/tests/unit/routers/test_cli_auto_refresh.py
git commit -m "feat: auto-refresh tokens when token_url contains {entity_id}

For client_credentials OAuth flows with templated URLs (e.g.,
https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token),
integrations.get() now fetches a fresh token on each call instead
of returning a stored token.

This enables multi-tenant client credentials where each customer
tenant requires a different token endpoint."
```

---

### Task 2: Create check_microsoft_setup Workflow

**Files:**
- Create: `features/microsoft_csp/workflows/check_setup.py` (via Bifrost)

**Step 1: Write the workflow**

Use `mcp__bifrost__replace_content` to create the workflow:

```python
"""
Check Microsoft Setup

Checks if both Microsoft CSP and Microsoft integrations are properly configured.
Returns status for each integration to drive UI state.
"""

import logging

from bifrost import workflow, integrations

logger = logging.getLogger(__name__)


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "setup"],
)
async def check_microsoft_setup() -> dict:
    """
    Check if Microsoft integrations are properly configured.

    Returns status for:
    - Microsoft CSP: Delegated OAuth for Partner Center access
    - Microsoft: Client credentials for customer tenant APIs

    Returns:
        dict with integration statuses and overall readiness
    """
    csp_status = {
        "name": "Microsoft CSP",
        "connected": False,
        "description": "Partner Center API access",
        "error": None,
    }

    microsoft_status = {
        "name": "Microsoft",
        "connected": False,
        "description": "Client credentials for customer APIs",
        "error": None,
    }

    # Check Microsoft CSP integration
    try:
        csp_integration = await integrations.get("Microsoft CSP")
        if csp_integration and csp_integration.oauth:
            # For delegated flow, we need a refresh token
            if csp_integration.oauth.refresh_token:
                csp_status["connected"] = True
            else:
                csp_status["error"] = "Not authenticated - OAuth connection required"
        else:
            csp_status["error"] = "Integration not configured"
    except Exception as e:
        csp_status["error"] = str(e)
        logger.warning(f"Failed to check Microsoft CSP integration: {e}")

    # Check Microsoft integration
    try:
        ms_integration = await integrations.get("Microsoft", scope="global")
        if ms_integration and ms_integration.oauth:
            # For client credentials, we need client_id and client_secret
            if ms_integration.oauth.client_id and ms_integration.oauth.client_secret:
                microsoft_status["connected"] = True
            else:
                microsoft_status["error"] = "Missing client credentials"
        else:
            microsoft_status["error"] = "Integration not configured"
    except Exception as e:
        microsoft_status["error"] = str(e)
        logger.warning(f"Failed to check Microsoft integration: {e}")

    # Overall readiness
    ready_for_consent = csp_status["connected"] and microsoft_status["connected"]

    return {
        "csp": csp_status,
        "microsoft": microsoft_status,
        "ready_for_consent": ready_for_consent,
    }
```

**Step 2: Test the workflow**

Execute via Bifrost UI or API to verify it returns expected structure.

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add check_microsoft_setup workflow

Checks if both Microsoft CSP and Microsoft integrations are
properly configured before allowing consent operations."
```

---

### Task 3: Create list_available_permissions Workflow

**Files:**
- Create: `features/microsoft_csp/workflows/list_permissions.py` (via Bifrost)

**Step 1: Write the workflow**

```python
"""
List Available Microsoft Permissions

Fetches available delegated and application permissions from Microsoft
service principals for Graph, Exchange, SharePoint, and Defender APIs.
"""

import logging

from bifrost import workflow, integrations, UserError

logger = logging.getLogger(__name__)

# Well-known Microsoft API enterprise application IDs
MICROSOFT_APIS = {
    "Microsoft Graph": "00000003-0000-0000-c000-000000000000",
    "Exchange Online": "00000002-0000-0ff1-ce00-000000000000",
    "SharePoint": "00000003-0000-0ff1-ce00-000000000000",
    "Windows Defender ATP": "fc780465-2017-40d4-a0c5-307022471b92",
}


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def list_available_permissions() -> dict:
    """
    Fetch available permissions from Microsoft APIs.

    Queries the service principal for each API to get:
    - oauth2PermissionScopes (delegated permissions)
    - appRoles (application permissions)

    Returns:
        dict with permissions grouped by API
    """
    import httpx

    # Get Microsoft CSP credentials to query our own tenant
    csp = await integrations.get("Microsoft CSP")
    if not csp or not csp.oauth or not csp.oauth.refresh_token:
        raise UserError("Microsoft CSP integration not configured")

    # Get a Graph token for our partner tenant
    from modules.microsoft.auth import get_graph_token

    access_token = await get_graph_token()

    apis = []

    async with httpx.AsyncClient() as client:
        for api_name, app_id in MICROSOFT_APIS.items():
            logger.info(f"Fetching permissions for {api_name}")

            try:
                response = await client.get(
                    f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{app_id}')",
                    params={"$select": "id,appId,displayName,appRoles,oauth2PermissionScopes"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 404:
                    logger.warning(f"Service principal not found for {api_name}")
                    continue

                response.raise_for_status()
                data = response.json()

                # Parse delegated permissions
                delegated = []
                for scope in data.get("oauth2PermissionScopes", []):
                    if scope.get("isEnabled", True):
                        delegated.append({
                            "id": scope.get("id"),
                            "name": scope.get("value"),
                            "description": scope.get("adminConsentDescription") or scope.get("userConsentDescription", ""),
                            "admin_consent_required": scope.get("type") == "Admin",
                        })

                # Parse application permissions
                application = []
                for role in data.get("appRoles", []):
                    if role.get("isEnabled", True):
                        application.append({
                            "id": role.get("id"),
                            "name": role.get("value"),
                            "description": role.get("description", ""),
                        })

                # Sort by name
                delegated.sort(key=lambda x: x["name"])
                application.sort(key=lambda x: x["name"])

                apis.append({
                    "api_id": app_id,
                    "api_name": api_name,
                    "display_name": data.get("displayName", api_name),
                    "delegated_permissions": delegated,
                    "application_permissions": application,
                })

            except Exception as e:
                logger.error(f"Failed to fetch permissions for {api_name}: {e}")
                continue

    return {
        "apis": apis,
        "api_count": len(apis),
    }
```

**Step 2: Test the workflow**

Execute to verify it returns permissions from Microsoft.

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add list_available_permissions workflow

Fetches delegated and application permissions from Microsoft
service principals for Graph, Exchange, SharePoint, and Defender."
```

---

### Task 4: Create Permission Selection Workflows

**Files:**
- Create: `features/microsoft_csp/workflows/save_permissions.py` (via Bifrost)
- Create: `features/microsoft_csp/workflows/get_permissions.py` (via Bifrost)

**Step 1: Write save_permissions workflow**

```python
"""
Save Selected Microsoft Permissions

Saves the user's selected permissions to the microsoft_selected_permissions table.
"""

import logging
from datetime import datetime, timezone

from bifrost import workflow, tables, context, UserError

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = "microsoft_selected_permissions"


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def save_selected_permissions(
    permissions: list[dict],
) -> dict:
    """
    Save selected Microsoft permissions.

    Args:
        permissions: List of permission dicts with:
            - api_id: Enterprise application ID
            - api_name: Display name (e.g., "Microsoft Graph")
            - permission_name: Permission value (e.g., "Directory.Read.All")
            - permission_type: "delegated" or "application"

    Returns:
        Success status and count
    """
    if not permissions:
        raise UserError("permissions list is required")

    # Validate permission structure
    for perm in permissions:
        if not all(k in perm for k in ["api_id", "api_name", "permission_name", "permission_type"]):
            raise UserError(f"Invalid permission structure: {perm}")
        if perm["permission_type"] not in ["delegated", "application"]:
            raise UserError(f"Invalid permission_type: {perm['permission_type']}")

    # Get platform org scope
    org_id = context.org_id

    # Clear existing permissions and save new ones
    # First, delete all existing
    try:
        existing = await tables.query(PERMISSIONS_TABLE, scope=org_id, limit=1000)
        for doc in existing.documents:
            await tables.delete(PERMISSIONS_TABLE, doc.id, scope=org_id)
        logger.info(f"Deleted {len(existing.documents)} existing permissions")
    except Exception as e:
        logger.debug(f"No existing permissions to delete: {e}")

    # Save new permissions
    now = datetime.now(timezone.utc).isoformat()
    saved_count = 0

    for perm in permissions:
        # Create unique ID from api_id + permission_name + type
        perm_id = f"{perm['api_id']}:{perm['permission_name']}:{perm['permission_type']}"

        await tables.upsert(
            PERMISSIONS_TABLE,
            id=perm_id,
            data={
                "api_id": perm["api_id"],
                "api_name": perm["api_name"],
                "permission_name": perm["permission_name"],
                "permission_type": perm["permission_type"],
                "created_at": now,
            },
            scope=org_id,
        )
        saved_count += 1

    logger.info(f"Saved {saved_count} permissions")

    return {
        "success": True,
        "saved_count": saved_count,
    }
```

**Step 2: Write get_permissions workflow**

```python
"""
Get Selected Microsoft Permissions

Retrieves the currently selected permissions from the table.
"""

import logging

from bifrost import workflow, tables, context

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = "microsoft_selected_permissions"


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def get_selected_permissions() -> dict:
    """
    Get currently selected Microsoft permissions.

    Returns:
        dict with permissions grouped by API and type
    """
    org_id = context.org_id

    try:
        result = await tables.query(PERMISSIONS_TABLE, scope=org_id, limit=1000)
        permissions = [doc.data for doc in result.documents]
    except Exception as e:
        logger.debug(f"No permissions table yet: {e}")
        permissions = []

    # Group by API
    by_api = {}
    for perm in permissions:
        api_name = perm.get("api_name", "Unknown")
        if api_name not in by_api:
            by_api[api_name] = {
                "api_id": perm.get("api_id"),
                "api_name": api_name,
                "delegated": [],
                "application": [],
            }

        perm_type = perm.get("permission_type", "delegated")
        by_api[api_name][perm_type].append(perm.get("permission_name"))

    # Count totals
    delegated_count = sum(len(api["delegated"]) for api in by_api.values())
    application_count = sum(len(api["application"]) for api in by_api.values())

    return {
        "permissions": list(by_api.values()),
        "delegated_count": delegated_count,
        "application_count": application_count,
        "total_count": delegated_count + application_count,
    }
```

**Step 3: Test both workflows**

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add permission selection workflows

- save_selected_permissions: persist user's chosen permissions
- get_selected_permissions: retrieve current selections grouped by API"
```

---

### Task 5: Update consent_tenant Workflow

**Files:**
- Modify: `features/microsoft_csp/workflows/consent_tenant.py` (via Bifrost)

**Step 1: Update to use selected permissions and create IntegrationMapping**

Replace the workflow content to:
1. Read from `microsoft_selected_permissions` table
2. Grant delegated permissions via Partner Center
3. Grant application permissions via Graph API
4. Create IntegrationMapping for "Microsoft" integration

(Full code provided in design doc - this is a significant rewrite of the existing workflow)

**Step 2: Test with a development tenant**

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: update consent_tenant to use selected permissions

- Reads permissions from microsoft_selected_permissions table
- Grants both delegated and application permissions
- Creates IntegrationMapping for Microsoft integration"
```

---

### Task 6: Update App UI with Status Cards

**Files:**
- Modify: `pages/index.tsx` in app `e5a46185-b467-4666-8eea-5a95d52a91d2` (via Bifrost)

**Step 1: Add status cards header**

Update the app to include:
1. Three status cards (Microsoft CSP, Microsoft, Permissions)
2. Conditional rendering based on setup state
3. Keep existing tenant table and search/filter

**Step 2: Test in browser**

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add status cards to Microsoft CSP app

Shows connection status for Microsoft CSP and Microsoft integrations,
plus permission count with Configure button."
```

---

### Task 7: Add Permission Configuration Dialog

**Files:**
- Modify: `pages/index.tsx` in app (via Bifrost)

**Step 1: Add dialog component**

Add a dialog that:
1. Fetches available permissions via `list_available_permissions`
2. Shows current selections from `get_selected_permissions`
3. Allows toggling permissions per API
4. Saves via `save_selected_permissions`

**Step 2: Test permission selection flow**

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add permission configuration dialog

Allows selecting delegated and application permissions for
Graph, Exchange, SharePoint, and Defender APIs."
```

---

### Task 8: Update link_tenant to Create IntegrationMapping

**Files:**
- Modify: `features/microsoft_csp/workflows/link_tenant.py` (via Bifrost)

**Step 1: Update to use integrations.upsert_mapping**

Add call to create/update IntegrationMapping when linking tenant to org.

**Step 2: Test linking flow**

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: create IntegrationMapping when linking tenant

Ensures Microsoft integration mapping exists for customer org,
enabling integrations.get('Microsoft') to resolve tenant ID."
```

---

### Technical Notes

#### Fetching Available Permissions

Query each API's service principal in your tenant:
```
GET /servicePrincipals(appId='{enterprise_app_id}')?$select=appRoles,oauth2PermissionScopes
```

- `appRoles` = Application permissions
- `oauth2PermissionScopes` = Delegated permissions

#### Permission Types

**Delegated permissions** (oauth2PermissionScopes):
- Granted via Partner Center applicationconsents API
- Act on behalf of signed-in user
- Limited by user's own permissions + GDAP roles

**Application permissions** (appRoles):
- Granted via Graph API app role assignments
- Act as the application itself
- Full access within granted scope (no user context)

---

## Phase 1: Basic CSP App (Completed)

## Architecture

### App Structure

```
App: microsoft-csp (slug: microsoft-csp)
├── _layout.tsx              # Simple layout wrapper
├── pages/
│   └── index.tsx            # Main tenants list with mapping/consent UI
└── components/
    └── TenantRow.tsx        # Single tenant row with actions
```

### Backend Structure

```
features/microsoft_csp/
├── __init__.py
└── workflows/
    ├── __init__.py
    ├── list_tenants.py      # List CSP tenants with status
    ├── consent_tenant.py    # Grant consent to a tenant
    ├── link_tenant.py       # Link CSP tenant → Bifrost org
    └── refresh_status.py    # Refresh consent status
```

### Existing Modules (Keep)

```
modules/microsoft/
├── __init__.py
├── auth.py                  # FIXED: now uses integrations.get()
├── csp.py                   # Partner Center client (updated - see notes below)
└── graph.py                 # Graph client (already good)
```

**Note on `csp.py` changes:**
- Removed `get_application_consents()` - endpoint doesn't exist in Partner Center API
- Removed `update_consent()` - was using non-existent endpoint
- Updated `grant_consent()` to treat HTTP 409 (already exists) as success
- `delete_consent()` should be removed (depends on removed methods)

## Data Model

**Table: `csp_tenant_status`** (scoped to provider org, NOT app)

| Field | Type | Description |
|-------|------|-------------|
| tenant_id | string | Primary key (Entra tenant ID) |
| tenant_name | string | Company name from Partner Center |
| domain | string | Primary domain |
| customer_id | string | Partner Center customer ID |
| bifrost_org_id | string? | Linked Bifrost organization ID |
| bifrost_org_name | string? | Denormalized org name for display |
| consent_status | enum | `none` \| `granted` \| `failed` |
| consent_error | string? | Error message if failed |
| consented_at | datetime? | When consent was granted |
| updated_at | datetime | Last status update |

## UI Design

Main page displays a table:

| CSP Customer | Tenant ID | Bifrost Organization | Status | Actions |
|--------------|-----------|---------------------|--------|---------|
| jlkfin.com | 6f37c786-... | [JLK Financial ×] ▼ | ✓ Consented | 🔄 |
| Wilson Kehoe... | ce6a2c98-... | [Wilson Kehoe... ×] ▼ | ⚠ Failed | 🔄 Retry |
| New Client LLC | abc123-... | Select org... ▼ | — Not consented | ▶ Consent |

### Row States

- **Not linked**: Dropdown shows "Select org...", consent button disabled
- **Linked, no consent**: Dropdown shows org, "Consent" button enabled
- **Linked, consented**: Green checkmark, refresh button only
- **Linked, failed**: Red warning with error tooltip, "Retry" button

### Actions (all inline, no dialogs)

- **Link dropdown change** → `link_csp_tenant` → updates row
- **Consent button** → `consent_csp_tenant` → spinner → status update
- **Refresh button** → `refresh_csp_status` → re-checks consent

## Workflows

### 1. `list_csp_tenants`

Main data source for the UI.

```python
@workflow(category="Microsoft CSP")
async def list_csp_tenants() -> dict:
    """List all CSP tenants with their current status."""
    # 1. Fetch customers from Partner Center
    # 2. Query csp_tenant_status table
    # 3. Merge and return combined list
```

### 2. `link_csp_tenant`

Link a CSP tenant to a Bifrost organization.

```python
@workflow(category="Microsoft CSP")
async def link_csp_tenant(tenant_id: str, org_id: str, org_name: str) -> dict:
    """Link CSP tenant to Bifrost org."""
    # 1. Update csp_tenant_status table
    # 2. Store entra_tenant_id in org config (for Graph API)
    # 3. Return updated status
```

### 3. `consent_csp_tenant`

Grant application consent (silent operation).

```python
@workflow(category="Microsoft CSP")
async def consent_csp_tenant(tenant_id: str) -> dict:
    """Grant partner app consent to tenant."""
    # 1. Call Partner Center consent API
    # 2. Update status to granted/failed
    # 3. Return new status
```

### 4. `refresh_csp_status`

Re-check consent status for a tenant.

```python
@workflow(category="Microsoft CSP")
async def refresh_csp_status(tenant_id: str) -> dict:
    """Refresh consent status from Partner Center."""
    # 1. Query existing consents
    # 2. Update table
    # 3. Return current status
```

## Auth Fix

**Current (broken):**
```python
from bifrost import oauth  # doesn't exist
oauth_config = await oauth.get("Microsoft_GDAP")
```

**Fixed:**
```python
from bifrost import integrations

integration = await integrations.get("Microsoft CSP")
client_id = integration.oauth.client_id
client_secret = integration.oauth.client_secret
refresh_token = integration.oauth.refresh_token
```

## Files to Delete

- `workflows/microsoft/test_list_customers.py`
- `workflows/microsoft/__init__.py`
- `features/microsoft_graph/link_tenant/workflow.py`
- `features/microsoft_graph/link_tenant/__init__.py`
- `features/microsoft_graph/__init__.py`
- `shared/microsoft/data_providers.py`

## Implementation Order

1. Fix `modules/microsoft/auth.py` to use `integrations.get()`
2. Create `features/microsoft_csp/` with workflows
3. Test `list_csp_tenants` workflow
4. Test `consent_csp_tenant` against Covi Development tenant
5. Create the app with UI
6. Delete old files

## Progress

### Completed

- [x] Fix `modules/microsoft/auth.py` to use `integrations.get("Microsoft CSP")` instead of non-existent `oauth.get()`
- [x] Create `features/microsoft_csp/` directory structure
- [x] Create `list_tenants.py` workflow - **Working** (lists 60 tenants from Partner Center)
- [x] Create `consent_tenant.py` workflow - **Working** (successfully grants consent)
- [x] Create `link_tenant.py` workflow - Created, needs testing
- [x] Create `refresh_status.py` workflow - Created, needs testing
- [x] Fix `modules/microsoft/csp.py`:
  - [x] Remove `get_application_consents()` (endpoint doesn't exist)
  - [x] Remove `update_consent()` (was using non-existent endpoint)
  - [x] Update `grant_consent()` to treat 409 (already exists) as success
- [x] Create `csp_tenant_status` table (scoped to provider org)
- [x] Create Microsoft CSP app (slug: `microsoft-csp`)

### TODO

- [x] Test `link_csp_tenant` workflow - **Working**
- [x] Test `refresh_csp_status` workflow - **Working**
- [x] Build app UI (`pages/index.tsx` with tenant table) - **Complete**
- [x] Remove `delete_consent()` method from `csp.py`
- [x] Delete old files:
  - [x] `workflows/microsoft/test_list_customers.py`
  - [x] `features/microsoft_graph/link_tenant/workflow.py`
- [x] Fix datetime bug in `publish_app` MCP tool
- [x] Update MCP app schema documentation (no imports, use workflow IDs, use Outlet)
- [x] Update Platform Assistant system prompt with code-based app building guidance
- [x] Update bifrost-integrations-docs with code-based app documentation
