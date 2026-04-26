/* eslint-disable no-console */
/**
 * Documentation screenshot capture spec.
 *
 * Reads `screenshots.yaml` from the docs repo (mounted at
 * $DOCS_REPO_PATH inside the container, default `/docs`), captures a
 * full-page PNG for each entry into `<docs>/.tmp-captures/<id>.png`, and
 * writes a per-entry result JSON to `<docs>/.tmp-captures/results-<id>.json`
 * for the host-side post-processor to consume.
 *
 * Why per-entry result files (not a single results.json):
 * - Playwright runs tests in parallel workers. A single shared
 *   results.json read-modify-write race let workers clobber each other,
 *   silently dropping ~40% of captured entries from the consolidated list.
 *   Per-entry files have no contention.
 *
 * Why captures land in a temp dir, not directly in src/assets/:
 * - Cropping and callout rendering use `sharp`, which we keep on the host
 *   side to avoid bloating the playwright-runner image.
 * - Pixel-diff gating decides whether the new PNG actually differs enough
 *   from the committed one to be worth replacing — no point copying over
 *   identical bytes.
 *
 * Filtering: set DOCS_CAPTURE_IDS to a comma-separated list of entry IDs
 * to limit the run. Empty/unset means "every entry."
 */
import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { ensureAuthenticated } from "../fixtures/auth-fixture";
import {
  loadManifest,
  selectEntries,
  effectiveViewport,
  effectiveAuth,
  effectiveMocks,
  effectiveSettleMs,
  type MockSpec,
  type ActionSpec,
} from "./manifest";
import { getSeeder } from "./seeders";

const DOCS_REPO_PATH = process.env.DOCS_REPO_PATH || "/docs";
const TMP_DIR = path.join(DOCS_REPO_PATH, ".tmp-captures");
const BASE_URL = process.env.TEST_BASE_URL || "http://client:80";

function ensureTmpDir() {
  if (!fs.existsSync(TMP_DIR)) fs.mkdirSync(TMP_DIR, { recursive: true });
}

interface CaptureResult {
  id: string;
  status: "captured" | "skipped" | "error";
  tempPath?: string;
  finalImagePath: string;
  route: string;
  message?: string;
}

function resultPathFor(id: string): string {
  // Per-entry result file. Each test writes exactly one file under a unique
  // path, so parallel Playwright workers never contend on the same file.
  return path.join(TMP_DIR, `results-${id}.json`);
}

function writeResult(result: CaptureResult) {
  ensureTmpDir();
  fs.writeFileSync(resultPathFor(result.id), JSON.stringify(result, null, 2));
}

function targetIds(): string[] | null {
  const raw = process.env.DOCS_CAPTURE_IDS;
  if (!raw) return null;
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function loadFixture(fixturePath: string): unknown {
  const abs = path.isAbsolute(fixturePath)
    ? fixturePath
    : path.join(DOCS_REPO_PATH, fixturePath);
  if (!fs.existsSync(abs)) {
    throw new Error(`fixture not found: ${abs}`);
  }
  return JSON.parse(fs.readFileSync(abs, "utf8"));
}

async function runActions(
  page: import("@playwright/test").Page,
  entryId: string,
  actions: ActionSpec[],
) {
  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    try {
      if ("click" in action) {
        await page.locator(action.click).click();
      } else if ("fill" in action) {
        await page.locator(action.fill.selector).fill(action.fill.value);
      } else if ("wait_for" in action) {
        await page.locator(action.wait_for).waitFor();
      } else if ("wait_for_hidden" in action) {
        await page.locator(action.wait_for_hidden).waitFor({ state: "hidden" });
      } else if ("wait_ms" in action) {
        await page.waitForTimeout(action.wait_ms);
      } else if ("scroll_into_view" in action) {
        await page.locator(action.scroll_into_view).scrollIntoViewIfNeeded();
      } else if ("press_key" in action) {
        await page.keyboard.press(action.press_key);
      } else {
        throw new Error(`unknown action shape: ${JSON.stringify(action)}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      throw new Error(
        `[docs-capture:${entryId}] action #${i} (${JSON.stringify(action)}) failed: ${msg}`,
      );
    }
  }
}

async function applyMocks(
  page: import("@playwright/test").Page,
  mocks: MockSpec[],
) {
  for (const mock of mocks) {
    const method = (mock.method ?? "GET").toUpperCase();
    let body: unknown;
    if (mock.body !== undefined) {
      body = mock.body;
    } else if (mock.fixture) {
      body = loadFixture(mock.fixture);
    } else {
      body = {};
    }
    const status = mock.status ?? 200;
    await page.route(mock.url, async (route) => {
      if (route.request().method().toUpperCase() !== method) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });
  }
}

const manifestPath = path.join(DOCS_REPO_PATH, "screenshots.yaml");
if (!fs.existsSync(manifestPath)) {
  test(`docs manifest is missing at ${manifestPath}`, () => {
    throw new Error(
      `Expected screenshots.yaml at ${manifestPath}. Mount the docs repo at $DOCS_REPO_PATH.`,
    );
  });
} else {
  ensureTmpDir();
  // Clear stale per-entry result files from prior runs. run-pipeline.sh
  // already wipes .tmp-captures/ between runs, but be defensive when the
  // spec is invoked directly (e.g. dev iterating on a single entry).
  for (const f of fs.readdirSync(TMP_DIR)) {
    if (f.startsWith("results-") && f.endsWith(".json")) {
      try {
        fs.unlinkSync(path.join(TMP_DIR, f));
      } catch {
        /* best-effort */
      }
    }
  }
  // Also drop the legacy aggregated file if it's still around from a
  // previous pipeline version.
  const legacy = path.join(TMP_DIR, "results.json");
  if (fs.existsSync(legacy)) {
    try {
      fs.unlinkSync(legacy);
    } catch {
      /* best-effort */
    }
  }

  const manifest = loadManifest(DOCS_REPO_PATH);
  // External entries (Azure portal, VS Code, etc.) are never captured by
  // the pipeline — even if explicitly listed in DOCS_CAPTURE_IDS — because
  // the bifrost client can't render them. Skip silently.
  const allEntries = selectEntries(manifest, targetIds()).filter(
    (e) => !e.external,
  );
  const skippedExternal = manifest.entries.filter(
    (e) => e.external,
  ).length;
  console.log(
    `[docs-capture] manifest has ${manifest.entries.length} entries (${skippedExternal} external skipped); capturing ${allEntries.length}`,
  );

  for (const entry of allEntries) {
    test(`capture ${entry.id}`, async ({ browser }) => {
      const viewport = effectiveViewport(entry, manifest);
      const authAs = effectiveAuth(entry, manifest) as
        | "platform_admin"
        | "org1_user"
        | "org2_user"
        | "unauthenticated";

      let result: CaptureResult = {
        id: entry.id,
        status: "error",
        finalImagePath: entry.image,
        route: entry.route,
      };

      try {
        const ctx =
          authAs === "unauthenticated"
            ? await browser.newContext({ viewport })
            : (
                await ensureAuthenticated(
                  browser,
                  authAs as "platform_admin" | "org1_user" | "org2_user",
                )
              ).context;
        if (authAs !== "unauthenticated") {
          // ensureAuthenticated returns a context with default viewport;
          // we want the manifest's viewport.
          await ctx.setExtraHTTPHeaders({});
        }

        const page = await ctx.newPage();
        await page.setViewportSize(viewport);

        // Stub WebAuthn (window.PublicKeyCredential + navigator.credentials)
        // before any page script runs. Headless Chromium without WebAuthn
        // flags doesn't expose these APIs, so the passkeys settings page
        // shows a "not supported" warning instead of its real UI. The stub
        // is additive — it only fills in the API surface when missing, so
        // it's a no-op in environments where real WebAuthn is present.
        //
        // Scope: only inject the stub on routes that actually surface
        // passkey UI (user-settings/security, user-settings/passkeys). The
        // login page auto-triggers passkey authentication on mount, and
        // the stub's reject message ("docs capture stub") would surface as
        // a red error banner on the captured login screenshot. Other
        // routes don't need the stub at all.
        const routePath = entry.route.split("?")[0];
        const needsWebAuthnStub =
          routePath.includes("/security") ||
          routePath.includes("/passkeys");
        if (needsWebAuthnStub) {
          await page.addInitScript(() => {
            if (typeof window.PublicKeyCredential === "undefined") {
              // @ts-expect-error stub for feature detection only
              window.PublicKeyCredential = class PublicKeyCredential {
                static isUserVerifyingPlatformAuthenticatorAvailable() {
                  return Promise.resolve(true);
                }
                static isConditionalMediationAvailable() {
                  return Promise.resolve(true);
                }
              };
            }
            if (!navigator.credentials) {
              Object.defineProperty(navigator, "credentials", {
                configurable: true,
                value: {
                  create: () =>
                    Promise.reject(new Error("docs capture stub")),
                  get: () => Promise.reject(new Error("docs capture stub")),
                },
              });
            }
          });
        }

        // Apply API mocks BEFORE navigation so initial fetches are
        // intercepted. Per-entry mocks override manifest defaults with
        // matching ${method} ${url}.
        const mocks = effectiveMocks(entry, manifest);
        if (mocks.length) {
          try {
            await applyMocks(page, mocks);
          } catch (e) {
            throw new Error(
              `[docs-capture:${entry.id}] failed to apply mocks: ${
                e instanceof Error ? e.message : String(e)
              }`,
            );
          }
        }

        // Run seeder (best-effort) before navigating so list/detail pages
        // have content to render. Seeders are useful when a page can't be
        // mocked completely (e.g., needs a real auth/CSRF round-trip).
        if (entry.seed) {
          try {
            await getSeeder(entry.seed)(page);
          } catch (e) {
            console.warn(`[docs-capture:${entry.id}] seeder failed: ${e}`);
          }
        }

        const url = `${BASE_URL}${entry.route.startsWith("/") ? entry.route : "/" + entry.route}`;
        await page.goto(url, {
          waitUntil: "domcontentloaded",
          timeout: 20000,
        });
        // Settle: wait for network idle, then a brief beat for animations.
        await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => undefined);
        await page.waitForTimeout(effectiveSettleMs(entry, manifest));

        // Per-entry actions: drive UI past what the route alone can render
        // (open dialogs, fill fields, scroll into view). Failures bubble up
        // with the entry id + action index for easy post-mortem.
        const actions = entry.capture?.actions ?? [];
        if (actions.length) {
          await runActions(page, entry.id, actions);
        }

        const tempPath = path.join(TMP_DIR, `${entry.id}.png`);
        await page.screenshot({
          path: tempPath,
          fullPage: entry.capture?.fullPage ?? true,
        });

        result = {
          id: entry.id,
          status: "captured",
          tempPath,
          finalImagePath: entry.image,
          route: entry.route,
        };

        await page.close();
        await ctx.close();
      } catch (e) {
        result = {
          id: entry.id,
          status: "error",
          finalImagePath: entry.image,
          route: entry.route,
          message: e instanceof Error ? e.message : String(e),
        };
      } finally {
        writeResult(result);
      }

      expect(result.status, result.message ?? "").toBe("captured");
    });
  }

}
