# Bifrost CLI Boundaries

## `bifrost api`

Use only for the Bifrost platform API.

Valid examples:

- `/api/llms.txt`
- `/api/workflows`
- `/api/executions/{id}`
- `/api/applications/{id}/validate`

Invalid examples:

- vendor API routes like HaloPSA or Pax8 endpoints
- arbitrary non-`/api/` URLs

If an endpoint is uncertain, fetch docs and grep first.

## Interactive Commands

Treat these as user-run commands when a TUI is involved:

- `bifrost sync`
- `bifrost push`
- `bifrost pull`

Do not assume an agent can safely drive them non-interactively.

## `bifrost watch`

Use for intentional workspace iteration when the user is in an SDK-first workflow.

## Testing

- Prefer `./test.sh` for repo validation.
- Use `bifrost run` for workflow execution checks.
