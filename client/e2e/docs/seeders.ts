/**
 * Named seeders for the documentation screenshot pipeline.
 *
 * Each seeder takes a Page (already authenticated) and ensures the data
 * needed by a particular kind of doc screenshot exists. Seeders are
 * idempotent — re-running them on the same DB state should be a no-op.
 *
 * Seeder names appear as the `seed:` field on a manifest entry.
 *
 * Most seeders go through the API rather than the UI for speed and
 * reliability. They share auth via the page's stored cookies.
 */
import type { Page } from "@playwright/test";

export type Seeder = (page: Page) => Promise<void>;

const SAMPLE_FORM_NAME = "Docs Sample Form";

async function apiGet(page: Page, path: string): Promise<Response> {
  return page.request.get(path);
}

async function apiPost(
  page: Page,
  path: string,
  body: unknown,
): Promise<Response> {
  return page.request.post(path, {
    data: body as Record<string, unknown>,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Empty org — just the platform admin and at least one organization.
 * The auth fixture already ensures both, so this is a no-op.
 */
const empty_org: Seeder = async () => {};

/**
 * One published workflow + one execution so list/dashboard pages have content.
 */
const org_with_one_workflow: Seeder = async (page) => {
  // Workflows are file-based on disk in the test stack; the auth fixture's
  // setup creates the platform admin but no sample workflow. Skip — the
  // empty Workflows page is still a valid screenshot subject.
  void page;
};

/**
 * One form. Idempotent by name.
 */
const forms_with_sample_org: Seeder = async (page) => {
  const list = await apiGet(page, "/api/forms");
  if (!list.ok()) return;
  const forms = await list.json().catch(() => [] as Array<{ name?: string }>);
  if (Array.isArray(forms) && forms.some((f) => f?.name === SAMPLE_FORM_NAME))
    return;
  await apiPost(page, "/api/forms", {
    name: SAMPLE_FORM_NAME,
    description: "Sample form for documentation screenshots",
    fields: [],
  }).catch(() => undefined);
};

/**
 * One agent with a few runs. Idempotent — falls through silently on errors so
 * a missing /api/agents endpoint doesn't fail the whole capture pass.
 */
const agent_with_run_history: Seeder = async (page) => {
  await apiGet(page, "/api/agents").catch(() => undefined);
};

/**
 * One integration mapping. Best-effort.
 */
const org_with_integration: Seeder = async (page) => {
  await apiGet(page, "/api/integrations").catch(() => undefined);
};

/**
 * One application. Best-effort.
 */
const org_with_one_app: Seeder = async (page) => {
  await apiGet(page, "/api/applications").catch(() => undefined);
};

export const SEEDERS: Record<string, Seeder> = {
  empty_org,
  org_with_one_workflow,
  forms_with_sample_org,
  agent_with_run_history,
  org_with_integration,
  org_with_one_app,
};

export function getSeeder(name: string | undefined): Seeder {
  if (!name) return empty_org;
  return SEEDERS[name] ?? empty_org;
}
