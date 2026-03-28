---
name: bifrost-integration-authoring
description: Add or update a Bifrost vendor integration using the established repo pattern. Use when implementing a new `modules/{vendor}.py` client, integration-backed data providers, sync workflows, integration config schema, or the accompanying tests and manifest wiring for first-class vendor support.
---

# Bifrost Integration Authoring

Follow the repo's repeated first-class vendor pattern instead of inventing a one-off structure for each integration.

## Workflow

1. Classify the integration work.
   - Client/auth and normalization live in `modules/{vendor}.py`.
   - org-picker data providers live in `features/{vendor}/workflows/data_providers.py`.
   - sync and mapping flows live in `features/{vendor}/workflows/sync_*.py`.

2. Keep the client thin and focused.
   - Use async `httpx`.
   - Centralize auth handling.
   - Provide normalized list/entity helpers.
   - Prefer a `get_client(scope: str | None = None)` pattern when config-backed auth is needed.

3. Build sync flows around Bifrost org mapping.
   - List vendor entities.
   - match or create Bifrost organizations.
   - upsert `IntegrationMapping`.

4. Update integration metadata only as needed for this fork.
   - `.bifrost/integrations.yaml` for integration entry and config schema.
   - `.bifrost/workflows.yaml` for workflow/data provider metadata.
   - Keep `.bifrost/` edits tactical and minimal.

5. Add tests with the repo pattern.
   - config contract tests
   - sorting/normalization tests
   - sync behavior tests
   - choose unit vs E2E using `$bifrost-test-authoring`

## Rules

- Prefer normalized vendor helpers over spreading API shape handling across workflows.
- Keep vendor-specific API quirks inside the module client layer.
- Avoid teaching `.bifrost/` as the canonical source of truth.
- Keep tests aligned with the repo's unit/E2E split.

## Reference

Read [references/bifrost-integration-pattern.md](./references/bifrost-integration-pattern.md) for the concrete file layout and [references/bifrost-integration-checklist.md](./references/bifrost-integration-checklist.md) before editing.
