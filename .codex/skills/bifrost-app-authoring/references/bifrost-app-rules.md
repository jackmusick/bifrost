# Bifrost App Rules

## Structural Rules

- Root layout uses `<Outlet />`, not `{children}`
- App code lives under `apps/{slug}/`
- `styles.css` sits at app root
- custom components live in `components/`

## Import Rules

Use:

```ts
import { Button, useWorkflowQuery, useState } from "bifrost"
```

Everything Bifrost-provided comes from `"bifrost"`.

Do not add import statements for auto-injected local components when the platform already injects them.

## Workflow Hooks

Use UUIDs:

```ts
useWorkflowQuery("uuid-here")
```

Do not use workflow names.

## Layout Constraint

The app is rendered in a fixed-height shell. Manage scroll regions explicitly.

## Styling

- define visual identity in `styles.css`
- use `.dark` for dark mode variants
- avoid generic default styling when the app needs a distinctive interaction model

## Dependencies

- declare npm dependencies in `app.yaml`
- keep within platform limits
