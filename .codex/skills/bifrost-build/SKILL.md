---
name: bifrost-build
description: Build or modify Bifrost workflows, forms, agents, and related userland artifacts using the repo's supported development flow. Use when deciding between local SDK-first work and remote-only work, choosing the right authored surface, fetching platform docs, or avoiding deprecated GitHub/manifest habits while implementing Bifrost features.
---

# Bifrost Build

Use local source and the Bifrost CLI first when they are available. Treat `.bifrost/` as discovery or transitional metadata, not the default authored surface.

## Workflow

1. Check prerequisites.
   - Confirm local source, CLI access, and credentials are available.
   - If not, use `$bifrost-setup` first.

2. Choose the development mode.
   - If local source and CLI are available, use SDK-first mode.
   - If only remote access is available, use platform/API-oriented guidance.

3. Fetch platform docs once per session if needed.
   - Cache `/api/llms.txt` locally and grep it rather than re-fetching for every question.

4. Choose the authored surface carefully.
   - Prefer source files in `features/`, `modules/`, `shared/`, `helpers/`, `workflows/`, and `apps/`.
   - Use `.bifrost/*.yaml` only when the current local sync path still requires tactical updates.

5. Respect the post-GitHub workflow.
   - Local git is canonical for source control.
   - Use direct CLI sync flows for userland changes.
   - Treat in-app GitHub integration as deprecated for day-to-day work in this fork.

6. Separate userland changes from platform/runtime changes.
   - Userland changes sync through `bifrost watch`, `bifrost push`, or `bifrost sync`.
   - Platform changes under `api/`, `client/`, or image/build files require rebuild or rollout, not workspace sync.

## Rules

- Do not teach manual `.bifrost/*.yaml` authoring as the default workflow.
- Do not use `bifrost api` as a proxy for third-party vendor APIs.
- Do not run interactive CLI flows on the user's behalf when they require a TUI.
- Generate UUIDs before writing cross-referenced entities.
- Use `$bifrost-app-authoring` for app-specific design and implementation details.

## Reference

Read [references/bifrost-build-workflow.md](./references/bifrost-build-workflow.md) for the detailed build workflow and [references/bifrost-cli-boundaries.md](./references/bifrost-cli-boundaries.md) for command boundaries.
