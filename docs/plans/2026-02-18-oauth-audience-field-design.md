# OAuth Audience Field + Dialog Simplification

**Date**: 2026-02-18

## Summary

Add an optional `audience` field to OAuth provider configuration and remove the preset tabs from the OAuth connection dialog.

## Motivation

Pax8 (and other providers like Auth0) require an `audience` parameter in OAuth token requests to specify which API/resource the token is intended for. This is defined in RFC 8693 (Token Exchange) and is common in practice. Our current implementation has no way to pass extra token request parameters.

## Changes

### 1. Add `audience` field (backend)

- **ORM** (`api/src/models/orm/oauth.py`): Add `audience: Mapped[str | None] = mapped_column(String(500), default=None)` to `OAuthProvider`
- **Migration**: Alembic migration adding nullable `audience` column to `oauth_providers`
- **Pydantic contracts** (`api/src/models/contracts/oauth.py`):
  - `CreateOAuthConnectionRequest`: add `audience: str | None = Field(None, ...)`
  - `UpdateOAuthConnectionRequest`: add `audience: str | None = Field(default=None, ...)`
  - `OAuthConnectionDetail`: add `audience: str | None = None`
- **Token requests** (`api/src/services/oauth_provider.py`): All three methods accept optional `audience` param, include in payload when non-null:
  - `exchange_code_for_token()`
  - `refresh_access_token()`
  - `get_client_credentials_token()`
- **Router** (`api/src/routers/oauth_connections.py`):
  - `create_connection`: save `request.audience` to provider
  - `update_connection` repository: update audience when provided
  - `refresh` endpoint: pass `provider.audience` through to token request
  - `callback` endpoint: pass `provider.audience` through to code exchange
- **Scheduler** (`api/src/jobs/schedulers/oauth_token_refresh.py`): Pass `provider.audience` to `refresh_access_token()`

### 2. Add `audience` field (frontend)

- **Dialog** (`client/src/components/oauth/CreateOAuthConnectionDialog.tsx`): Add optional "Audience" input field
- **Type generation**: Regenerate types after API changes

### 3. Remove preset tabs from dialog

- Remove `<Tabs>` wrapper and preset selector from `CreateOAuthConnectionDialog.tsx`
- Keep `OAUTH_PROVIDER_PRESETS` in `client/src/lib/client-types.ts` (unused for now, may return)
- Show the custom provider form directly without tabs

### Not changed

- `OAuthToken` table — no changes to token storage
- SSO OAuth config (`oauth_config.py`) — separate system
- Authorization URL flow — audience is a token endpoint concept
