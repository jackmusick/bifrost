# `.bifrost` Manifest Inventory

**Date:** 2026-03-27

## Purpose

This note records what the fork's tracked `.bifrost` manifests are still
carrying so the eventual convergence work can be deliberate.

## Current Tracked Files

- `.bifrost/agents.yaml`
- `.bifrost/apps.yaml`
- `.bifrost/integrations.yaml`
- `.bifrost/workflows.yaml`

## Entity Counts

- Workflows: `108`
- Integrations: `26`
- Agents: `2`
- Apps: `1`

## What Is Already Source-Backed

All path-bearing manifest entities currently point at real files:

- Workflows with existing source paths: `108/108`
- Agents with existing source paths: `2/2`
- Apps with existing source paths: `1/1`

Workflow path breakdown:

- `features/`: `77`
- `shared/`: `30`
- `workflows/`: `1`

The lone legacy-path workflow is:

- `workflows/sample/hello_world.py`

That means the migration risk is not orphaned files. The risk is the metadata
still living only in the manifest layer.

## Workflow Metadata Still Carried In `.bifrost/workflows.yaml`

Most frequent fields:

- `function_name`: `108`
- `id`: `108`
- `name`: `108`
- `path`: `108`
- `description`: `106`
- `type`: `86`
- `category`: `83`
- `tags`: `82`
- `timeout_seconds`: `49`
- `access_level`: `39`
- `endpoint_enabled`: `38`

In other words, workflow source files already exist, but the manifest still
holds the platform registration identity and a large amount of user-facing
metadata.

## Integration Metadata Still Carried In `.bifrost/integrations.yaml`

Most frequent fields:

- `id`: `26`
- `mappings`: `26`
- `name`: `26`
- `config_schema`: `22`
- `list_entities_data_provider_id`: `21`
- `oauth_provider`: `6`
- `default_entity_id`: `2`
- `entity_id`: `2`
- `entity_id_name`: `2`

This is the hardest part of the migration. Unlike workflows, integrations do
not have a separate entity file today. The manifest is the only place carrying
most integration registration metadata.

## Migration Implications

The safe migration order is:

1. stop teaching `.bifrost/*.yaml` as authored source-of-truth
2. inventory and preserve manifest-only metadata
3. decide where integration metadata should live long-term
4. only then remove tracked `.bifrost/*.yaml` from the fork's normal authored
   surface

## Tooling

Use the local audit helper to refresh this inventory:

```bash
python scripts/audit_manifest_inventory.py
python scripts/audit_manifest_inventory.py --markdown
```
