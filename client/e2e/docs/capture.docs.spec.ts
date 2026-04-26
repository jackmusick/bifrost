/* eslint-disable no-console */
/**
 * Documentation screenshot capture spec.
 *
 * Reads `screenshots.yaml` from the docs repo (mounted at
 * $DOCS_REPO_PATH inside the container, default `/docs`), captures a
 * full-page PNG for each entry into `<docs>/.tmp-captures/<id>.png`, and
 * writes a results JSON to `<docs>/.tmp-captures/results.json` for the
 * host-side post-processor to consume.
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
} from "./manifest";
import { getSeeder } from "./seeders";

const DOCS_REPO_PATH = process.env.DOCS_REPO_PATH || "/docs";
const TMP_DIR = path.join(DOCS_REPO_PATH, ".tmp-captures");
const RESULTS_PATH = path.join(TMP_DIR, "results.json");
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

function loadOrInitResults(): CaptureResult[] {
  if (fs.existsSync(RESULTS_PATH)) {
    try {
      return JSON.parse(fs.readFileSync(RESULTS_PATH, "utf8")) as CaptureResult[];
    } catch {
      /* fall through */
    }
  }
  return [];
}

function writeResult(result: CaptureResult) {
  ensureTmpDir();
  const all = loadOrInitResults().filter((r) => r.id !== result.id);
  all.push(result);
  fs.writeFileSync(RESULTS_PATH, JSON.stringify(all, null, 2));
}

function targetIds(): string[] | null {
  const raw = process.env.DOCS_CAPTURE_IDS;
  if (!raw) return null;
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
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
  // Clear stale results from prior runs.
  if (fs.existsSync(RESULTS_PATH)) fs.unlinkSync(RESULTS_PATH);

  const manifest = loadManifest(DOCS_REPO_PATH);
  const entries = selectEntries(manifest, targetIds());
  console.log(
    `[docs-capture] manifest has ${manifest.entries.length} entries; capturing ${entries.length}`,
  );

  for (const entry of entries) {
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

        // Run seeder (best-effort) before navigating so list/detail pages
        // have content to render.
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
        await page.waitForTimeout(500);

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
