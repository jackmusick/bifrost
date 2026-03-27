# Source-Backed Integration Definition Model

**Date:** 2026-03-27

## Goal

Converge the fork toward upstream's repo model without inventing a brand-new
entity system.

The platform already externalizes several entity types into source-backed
definitions:

- workflows / tools / data providers: Python decorators
- forms: `.form.yaml`
- agents: `.agent.yaml`
- apps: app directory + `app.yaml`

Integrations are the main remaining entity type whose portable definition still
mostly lives in `.bifrost/integrations.yaml`.

## Recommendation

Add a dedicated source-backed integration definition file and treat
`.bifrost/integrations.yaml` as generated export only.

Target layout:

```text
integrations/
  dnsfilter/
    integration.yaml
```

This matches the existing platform pattern better than keeping integrations as a
special case inside generated manifest YAML.

## What Belongs In `integration.yaml`

Portable definition only:

- `id`
- `name`
- `entity_id`
- `entity_id_name`
- `list_entities_data_provider_id`
- `config_schema`
- `oauth_provider`

The `oauth_provider` block may contain structural defaults such as:

- `provider_name`
- `display_name`
- `oauth_flow_type`
- `authorization_url`
- `token_url`
- `token_url_defaults`
- `scopes`
- `redirect_uri`
- `client_id` only as a sentinel like `__NEEDS_SETUP__`

## What Does Not Belong In `integration.yaml`

Runtime or environment-specific state should remain DB-backed:

- mappings
- config values
- secrets
- OAuth tokens
- org-specific overrides

## Why This Fits Upstream

This follows the model already visible in platform code:

- source/decorator metadata is indexed into DB
- forms and agents are file-backed and indexed into DB
- repo sync regenerates `.bifrost/*.yaml` from DB state
- direct editing of `.bifrost/` is blocked because it is system-generated

So the clean move is not to make `.bifrost/integrations.yaml` more important.
It is to give integrations a real source-backed home like the other entity
types already have.

## Pilot Scope

Pilot integration: `DNSFilter`

Why:

- simple config schema
- no OAuth provider block
- still exercises `list_entities_data_provider_id`

Pilot file:

- `integrations/dnsfilter/integration.yaml`

Pilot helper code:

- `api/bifrost/integration_definition.py`

Pilot validation:

- `api/tests/unit/sdk/test_integration_definition.py`

## Migration Strategy

1. Define and validate source-backed integration files.
2. Pilot one low-complexity integration.
3. Add an integration indexer / serializer path when ready.
4. Dual-write DB state and integration files during migration.
5. Only after that, stop treating `.bifrost/integrations.yaml` as authored
   source.

## Non-Goals For The Pilot

- no runtime import path change yet
- no manifest import rewrite yet
- no automatic DB sync from `integrations/*/integration.yaml` yet
- no deletion of `.bifrost/integrations.yaml` yet

The pilot exists to prove the source-backed file shape before changing platform
behavior.
