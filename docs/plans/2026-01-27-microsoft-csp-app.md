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
