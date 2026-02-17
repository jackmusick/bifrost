# HMAC-Authenticated App Embedding

**Date**: 2026-02-16
**Status**: Approved

## Problem

Bifrost apps need to be embedded in external systems (Halo PSA, Zendesk, etc.) via iframes. These systems use HMAC-signed URLs to authenticate iframe loads. Currently, all Bifrost app endpoints require JWT authentication, making embedding impossible.

## Solution

Add platform-level HMAC verification for iframe embeds. The external system signs the iframe URL with a shared secret. Bifrost verifies the signature, issues a short-lived scoped session (8-hour embed JWT), and serves the app with full workflow access via the system user.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Secret scope | Per app, multiple allowed | One app can be embedded in multiple systems (Halo prod, Halo staging). Revoking one doesn't affect others. |
| Secret ownership | Either side can generate | It's just a shared key. Admin can paste one from Halo or auto-generate in Bifrost. |
| Secret storage | Fernet-encrypted in DB | Need raw value for HMAC computation. Existing `encrypt_value()`/`decrypt_value()` in `security.py`. |
| HMAC format | Shopify-style: sign all sorted params | Sort all non-hmac query params alphabetically, join as `key=value&key=value`, HMAC-SHA256. Most standard approach, tamper-proofs all params. |
| Post-verification identity | System user (`SYSTEM_USER_ID`) | Matches existing pattern for non-human executions (webhooks, schedules, API keys). No need for a new principal type. |
| Token lifetime | 8 hours | Long enough for a work session. Re-opening the tab recomputes the HMAC and issues a fresh token. |
| Verified params | Passed as workflow input | Params like `agent_id`, `ticket_id` are available to workflows as input data. |

## Flow

```
External System (Halo)                    Bifrost
─────────────────────                    ───────
1. Agent opens custom tab
2. Compute HMAC-SHA256(secret,
   "agent_id=42&ticket_id=1001")
3. Load iframe:
   /embed/apps/{slug}?agent_id=42
   &ticket_id=1001&hmac=abc123...
                                         4. Look up embed secrets for this app
                                         5. Sort non-hmac params → "agent_id=42&ticket_id=1001"
                                         6. Verify HMAC-SHA256(secret, sorted_params) == hmac param
                                         7. If valid → issue 8-hour embed JWT
                                         8. Serve app (same render pipeline as normal apps)
                                         9. App renders, calls workflows using embed JWT
                                         10. Workflows execute as system user,
                                             verified params available as input
```

## Data Model

### New table: `app_embed_secrets`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | PK |
| `application_id` | UUID FK → applications | Which app this secret is for |
| `name` | String | Label (e.g., "Halo Production") |
| `secret_encrypted` | String | Fernet-encrypted shared secret |
| `is_active` | Boolean | Can be disabled without deleting |
| `created_at` | DateTime(timezone=True) | |
| `created_by` | UUID FK → users | Audit trail |

Multiple secrets per app for zero-downtime rotation: add new secret → update external system → deactivate old secret.

## API Surface

### Embed Secret Management (authenticated, admin only)

```
POST   /api/applications/{app_id}/embed-secrets     → Create secret (returns raw secret once)
GET    /api/applications/{app_id}/embed-secrets     → List secrets (name, id, active — no raw values)
DELETE /api/applications/{app_id}/embed-secrets/{id} → Delete secret
PATCH  /api/applications/{app_id}/embed-secrets/{id} → Toggle active status
```

### Embed Entry Point (public, HMAC-verified)

```
GET    /embed/apps/{slug}?...&hmac=...              → Verify HMAC, issue embed JWT, serve app
```

## Embed JWT

New token type (`type: "embed"`) containing:

```json
{
  "type": "embed",
  "sub": "00000000-0000-0000-0000-000000000001",
  "app_id": "<application UUID>",
  "org_id": "<app's organization UUID>",
  "verified_params": {"agent_id": "42", "ticket_id": "1001"},
  "exp": "<8 hours from now>"
}
```

The embed JWT:
- Authenticates workflow execution calls scoped to the app
- Creates an `ExecutionContext` with `SYSTEM_USER_ID` and `name="Embed"`
- Injects `verified_params` into workflow input

## HMAC Verification Logic

```python
import hmac
import hashlib

def verify_embed_hmac(query_params: dict[str, str], secret: str) -> bool:
    """Shopify-style: sign all sorted non-hmac query params."""
    received_hmac = query_params.get("hmac", "")
    remaining = {k: v for k, v in query_params.items() if k != "hmac"}
    message = "&".join(f"{k}={v}" for k, v in sorted(remaining.items()))
    expected = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_hmac)
```

Verification tries each active embed secret for the app. First match wins.

## Security Considerations

- **CSP/X-Frame-Options**: Embed endpoint must allow framing. Normal app routes keep restrictive policies.
- **Cookie scope**: Embed JWT cookie scoped to `/embed/` and `/api/` paths.
- **CSRF**: Embed requests come from cross-origin iframes; standard double-submit CSRF won't work. The embed JWT is scoped (app-specific, 8h expiry) and HttpOnly, limiting blast radius.
- **Secret rotation**: Multiple secrets per app enables zero-downtime rotation.
- **Timing attacks**: Use `hmac.compare_digest()` for constant-time comparison.

## What We're NOT Building

- No user mapping (external agent_id stays as a workflow param, not mapped to a Bifrost user)
- No per-param signing configuration (always sign all params)
- No embed-specific analytics beyond existing execution logging
- No embed-specific UI in the app builder (apps just read query params)
- No JWT refresh flow (re-open the tab for a fresh HMAC check + new token)

## References

- [Shopify HMAC verification](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant) — signs all sorted query params
- [Zendesk sidebar app auth](https://developer.zendesk.com/documentation/apps/build-an-app/building-a-server-side-app/part-5-secure-the-app/) — JWT-based alternative
- Halo PSA custom tabs — HMAC-SHA256 with iframe secret + agent ID
