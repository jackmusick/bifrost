# Bifrost Build Workflow

## Prerequisites

Check:

```bash
command -v bifrost
test -f "$HOME/.bifrost/credentials.json" && echo logged-in || echo missing-creds
test -d .bifrost && echo local-workspace || echo no-bifrost-dir
```

If local source, CLI, or credentials are missing, use `$bifrost-setup`.

## SDK-First Mode

Use this when local source and the CLI are available.

### Discovery

- Prefer local file reads over platform discovery.
- Read source files first.
- Only inspect `.bifrost/*.yaml` as a secondary discovery surface.

Practical paths:

- workflows and data providers: `features/**/workflows/*.py`, `workflows/`
- modules: `modules/*.py`
- apps: `apps/*/`
- transitional metadata: `.bifrost/*.yaml`

### Docs

Fetch once:

```bash
mkdir -p /tmp/bifrost-docs
bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt
```

Then grep locally.

### Sync Model

Current fork guidance:

- local git is the source of truth
- direct CLI sync is the normal path for userland
- in-app GitHub integration is deprecated for normal delivery

For userland:

- `features/`
- `modules/`
- `shared/`
- `helpers/`
- `workflows/`
- `apps/`
- current fork-local `.bifrost/` files when unavoidable

Use:

- `bifrost watch [path]`
- `bifrost push [path]`
- `bifrost sync [path]`

### Platform/Runtime Split

These require rebuild or rollout, not workspace sync:

- `api/`
- `client/`
- `docker-compose*.yml`
- build/deployment assets

## Transitional Manifest Rule

- Treat `.bifrost/` as generated or system-managed metadata.
- Small edits may still be required locally.
- Keep such edits minimal and expect regeneration/import to normalize them later.
- Do not open upstream PRs centered on `.bifrost/*.yaml` changes unless upstream explicitly asks for them.

## Cross-Referenced Entity Rule

Generate UUIDs before writing files:

```python
import uuid
workflow_id = str(uuid.uuid4())
form_id = str(uuid.uuid4())
agent_id = str(uuid.uuid4())
```

## Validation

- Repo tests: `./test.sh ...`
- Workflow execution: `bifrost run <file> --workflow <name> --params '{}'`
- Platform checks: `bifrost api GET /api/...`
