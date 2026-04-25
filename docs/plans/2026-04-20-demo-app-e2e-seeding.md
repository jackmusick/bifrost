# Demo App E2E Seeding Plan

**Date:** 2026-04-20
**Status:** Draft — for review
**Context:** Add Playwright specs that open preview and published apps as a regular org user, assert access rules visually, and verify a demo app renders the feature set we expect. Today there's no checked-in demo app and no seeding helper, so specs have nothing to navigate to.

## Problem

API e2e tests validate that `/api/applications` returns the right data given the right role. They **do not** catch:

- CSS/layout regressions in `JsxAppShell` / `JsxPageRenderer`
- Runtime errors in the dynamic module-loading path
- Routing bugs within a rendered app
- Permission-gated UI chrome (nav entries, 403 screens)
- Realtime workflow results inside a rendered app

Playwright can catch all of these, but needs a stable, deterministic demo app to run against. Apps are rows in `applications` + source files in S3 `_repo/apps/…` + compiled artifacts in S3 `_apps/{id}/preview/`. None of this exists in the test stack by default.

## Preconditions for the rendered-app user flow

For `org1_user` navigating `/apps/{slug}` to succeed:

1. `Application` row exists with that slug in `applications` table
2. Source files exist in `_repo/apps/{slug}/` (S3)
3. Compiled bundle exists in `_apps/{app_id}/preview/` (S3)
4. User's role is on the app's allow list (if `access_level == "role_based"`) — skip by using `access_level == "authenticated"` for the base demo
5. Any workflows the app invokes are registered and accessible to the user's org

## Seeding approach

**Decision: pre-built fixture + direct API POST + direct S3 upload.** Mirrors how the existing auth fixture seeds users and orgs — no CLI dependency, no git-sync simulation, all within `client/e2e/`.

### Fixture layout

```
client/e2e/fixtures/demo-app/
├── source/                    # Human-readable source, checked in
│   ├── App.tsx                # Entry point
│   ├── pages/
│   │   ├── Home.tsx           # Shows static content + workflow trigger
│   │   └── Execution.tsx      # Shows realtime workflow result
│   └── app.yaml               # App metadata (name, pages, roles)
├── compiled/                  # Pre-built, checked in (deterministic)
│   ├── App.js                 # Output of AppCompilerService on source/
│   └── pages/*.js
└── demo-app-seeder.ts         # Test helper — seeds one app per org
```

**Why compiled files checked in:** We don't want to run the real `AppCompilerService` inside Playwright setup. Pre-compiling once and committing the output means Playwright just does an S3 PUT. When the source changes, a pre-commit hook or a `scripts/rebuild-demo-app.sh` regenerates `compiled/` — that's a tractable ergonomics problem, not a per-test-run problem.

### Seeder helper (pseudocode)

```ts
// client/e2e/fixtures/demo-app-seeder.ts
export async function seedDemoApp(opts: {
  apiUrl: string;
  accessToken: string;     // platform admin
  orgId?: string;          // omit for global app; set for org-scoped demo
  slug?: string;           // default: "e2e-demo-app"
}): Promise<{ id: string; slug: string }> {
  // 1. Create Application row
  const app = await api.post("/api/applications", {
    name: "E2E Demo App",
    slug: opts.slug ?? "e2e-demo-app",
    description: "Fixture for Playwright tests — do not modify",
    access_level: "authenticated",
    repo_path: `apps/${slug}`,
    organization_id: opts.orgId,
  });

  // 2. Upload source files into _repo/apps/{slug}/ via files API
  //    (reuse whatever POST /api/files endpoint the UI uses on save)
  for (const file of readdirRecursive("fixtures/demo-app/source")) {
    await api.put(`/api/files/_repo/apps/${slug}/${file.path}`, file.content);
  }

  // 3. Upload pre-compiled files directly into _apps/{app_id}/preview/
  //    Preferred: new minimal endpoint POST /api/applications/{id}/seed-preview
  //    (test-only, guarded by BIFROST_ENVIRONMENT == "testing")
  for (const file of readdirRecursive("fixtures/demo-app/compiled")) {
    await api.post(`/api/applications/${app.id}/seed-preview`, {
      path: file.path,
      content: base64(file.content),
    });
  }

  return { id: app.id, slug: app.slug };
}
```

**Open question:** Is there already a `POST /api/applications/{id}/files` style endpoint we can use, or do we need a new test-only one? The explorer didn't confirm — verification task in the subagent plan below.

If no existing endpoint and we don't want to add a test-only one, fall back to **calling `/api/applications/{id}/publish`** (if it exists) on the source files after upload — that triggers the real compiler and the tests would run against real artifacts. Slower but higher fidelity.

### Where seeding runs

Add to `client/e2e/setup/global.setup.ts` after user+org creation:

```ts
await seedDemoApp({ apiUrl, accessToken: platformAdmin.accessToken });
await seedDemoApp({ apiUrl, accessToken: platformAdmin.accessToken, orgId: org1.id, slug: "e2e-demo-app-org1" });
```

Result: one global app (authenticated access — both org users can open it) and one org-scoped app (only `org1_user` can see it — gives us cross-org access tests).

Credentials file gets app IDs appended for reuse across specs:
```json
{
  "platform_admin": {...},
  "org1_user": {...},
  "demo_apps": {
    "global": { "id": "...", "slug": "e2e-demo-app" },
    "org1": { "id": "...", "slug": "e2e-demo-app-org1" }
  }
}
```

## What the demo app should contain

Minimum for milestone 1 (access + basic render):
- One page with a heading ("Demo App") and a paragraph with known text
- One button that invokes a pre-registered workflow `demo_workflow`
- Asserts: heading visible, button exists, click → navigates

Milestone 2 extensions (feature coverage):
- A table component (exercises the `/api/tables/*` surface)
- A chart component (exercises the chart renderer)
- A link to a second page (exercises app-internal routing)
- Workflow button that streams results (exercises `useExecutionStream` inside an app)
- An auth-gated page (visible only to specific role — exercises app-level RBAC)

The demo workflow is minimal Python that sleeps 2s, logs 5 lines, returns `{ "greeting": "hello" }`. It lives in `client/e2e/fixtures/demo-app/workflows/demo_workflow.py` and gets seeded the same way as the app files.

## Playwright specs to add

1. `apps-access.user.spec.ts` — 4 tests
   - `org1_user` sees global app in nav, can open it, sees heading
   - `org1_user` sees org1-scoped app, can open it
   - `org2_user` does NOT see org1-scoped app in nav, direct navigation → 403 or redirect
   - Unauth → redirected to login

2. `apps-features.admin.spec.ts` — milestone 2
   - Opens demo app, asserts each feature component renders (heading, table, chart)
   - Clicks workflow button, asserts log lines stream in, asserts final result shows

3. `apps-preview.admin.spec.ts` — preview path
   - Admin opens app in editor/preview mode, edits a source file, sees updated preview

Preview is separate from published because the transports differ (preview reads from editor state, published reads compiled bundle from S3).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Compiled bundle goes stale vs source | `scripts/rebuild-demo-app.sh` + a CI check that fails if `compiled/` doesn't match source |
| Seeding is slow (uploads many files) | Seeding runs once in `global.setup.ts`, not per test |
| App IDs aren't stable across runs | Use slugs in specs, not IDs; slugs are deterministic from the seeder |
| App compile logic changes and bundle format shifts | Accept occasional rebuilds of `compiled/` — `AppCompilerService` changes are rare |
| S3 state persists between test runs | `./test.sh stack reset` wipes MinIO, so seeding runs fresh each time |

## Effort estimate

- **Seeder + pre-built fixture + one `apps-access.user.spec.ts` (milestone 1):** ~1.5 days
  - 0.5d: build the fixture (source + compiled + app.yaml)
  - 0.5d: write seeder, confirm upload path works (may need new test-only endpoint)
  - 0.5d: write 4-test access spec, stabilize
- **Feature-coverage milestone 2:** ~2 days on top
- **Preview spec:** ~0.5 day

Total to cover the user's two asks: ~4 days end-to-end.

## Open questions

1. **Is there an existing endpoint that uploads files into `_apps/{id}/preview/`?** If yes, use it. If no, do we add a test-only `POST /api/applications/{id}/seed-preview` guarded by env check, or do we invoke the real compiler via `POST /api/applications/{id}/publish` (slower, higher fidelity)?
2. **Does the demo workflow need to be in a specific location in `_repo/`?** I think `workflows/demo_workflow.py` — need to confirm the registry path.
3. **For org-scoped apps with role-based access**, the seeder will need to also create a `Role`, assign it to `org1_user`, and attach it to the app. That adds ~30 lines to the seeder — worth it for the cross-org access test.
4. **`access_level="role_based"` vs `access_level="authenticated"` behavior in nav** — does the UI filter nav by role even when access is "authenticated"? If the nav always shows authenticated apps, the "org2_user shouldn't see org1 app in nav" test won't hold for authenticated-level apps. Verify the nav filter logic before finalizing the matrix.

## Decision points for reviewer

- [ ] Pre-built bundle approach OK, or prefer real compiler via publish endpoint?
- [ ] New test-only `POST /api/applications/{id}/seed-preview` endpoint OK, or find/reuse existing?
- [ ] Milestone split (access spec first, features later) OK, or do both at once?
- [ ] Does the demo app need to be org-aware (seeded per-org), or is one global demo enough for milestone 1?
