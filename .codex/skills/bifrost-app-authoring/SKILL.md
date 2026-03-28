---
name: bifrost-app-authoring
description: Design and implement Bifrost apps within the platform's frontend constraints. Use when creating or modifying `apps/*` code, planning app UX before coding, choosing Bifrost-specific component and hook patterns, or validating that an app follows the repo's supported SDK-first workflow.
---

# Bifrost App Authoring

Design the app first, then implement it within Bifrost's container and platform constraints.

## Workflow

1. Start with the UX, not code.
   - Ask what the app should feel like or what product it should resemble.
   - Turn that into concrete layout and interaction observations before coding.

2. Read the existing app surface first.
   - Inspect `styles.css`, `components/`, `_layout.tsx`, `pages/`, and `app.yaml`.
   - Match existing patterns when editing an existing app.

3. Respect Bifrost app rules.
   - imports come from `"bifrost"` or package names only
   - `_layout.tsx` uses `<Outlet />`
   - workflow hooks use UUIDs, not workflow names
   - custom CSS lives in `styles.css`
   - the app renders in a fixed-height container, so scrolling must be intentional

4. Distinguish custom UI from commodity UI.
   - Use standard components for standard settings and data forms.
   - Build custom components for the app's defining interaction model.

5. Validate through the supported workflow.
   - prefer local app file edits in `apps/{slug}/`
   - use the CLI/platform validation path, not hand-wavy visual assumptions

## Rules

- Do not skip the visual spec for a new app.
- Do not use workflow names in hooks where UUIDs are required.
- Do not assume normal full-page browser layout; Bifrost apps are embedded in a fixed-height shell.
- Do not let generic design-system defaults flatten the app's identity.

## Reference

Read [references/bifrost-app-rules.md](./references/bifrost-app-rules.md) for concrete app constraints and [references/bifrost-app-design-workflow.md](./references/bifrost-app-design-workflow.md) for the design-first process.
