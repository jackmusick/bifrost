/**
 * Read and validate the docs screenshot manifest from the mounted docs repo.
 *
 * The same shape is enforced by the Zod schema in
 * `bifrost-integrations-docs/scripts/manifest/schema.mjs`. We don't import
 * Zod here to keep the playwright-runner image lean — light validation
 * inside the capture spec is enough; the docs repo's `npm run lint:manifest`
 * is where strict validation happens.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import yaml from "js-yaml";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Callout extends Rect {
  color?: string;
  label?: string;
}

export interface MockSpec {
  url: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  status?: number;
  body?: unknown;
  fixture?: string;
}

export interface CaptureSpec {
  selector?: string;
  pad?: number;
  fullPage?: boolean;
  crop?: Rect;
  callouts?: Callout[];
  mocks?: MockSpec[];
  settle_ms?: number;
}

export interface Diataxis {
  page: string;
  type: "tutorial" | "how-to" | "reference" | "explanation";
  heading?: string;
}

export interface ManifestEntry {
  id: string;
  image: string;
  route: string;
  auth_as?: "platform_admin" | "org1_user" | "org2_user" | "unauthenticated";
  seed?: string;
  viewport?: { width: number; height: number };
  capture?: CaptureSpec;
  diataxis: Diataxis;
  source_globs?: string[];
  captured_at?: { bifrost_sha: string | null; timestamp: string | null } | null;
}

export interface Manifest {
  version: 1;
  defaults: {
    auth_as: string;
    viewport: { width: number; height: number };
    pad: number;
    settle_ms?: number;
    mocks?: MockSpec[];
  };
  entries: ManifestEntry[];
}

/**
 * Merge entry-specific mocks on top of manifest defaults. An entry mock with
 * the same `${method} ${url}` key overrides the default — useful when a
 * multi-step page needs a different fixture for the same endpoint.
 */
export function effectiveMocks(
  entry: ManifestEntry,
  manifest: Manifest,
): MockSpec[] {
  const defaultMocks = manifest.defaults.mocks ?? [];
  const entryMocks = entry.capture?.mocks ?? [];
  const byKey = new Map<string, MockSpec>();
  for (const m of defaultMocks) {
    byKey.set(`${m.method ?? "GET"} ${m.url}`, m);
  }
  for (const m of entryMocks) {
    byKey.set(`${m.method ?? "GET"} ${m.url}`, m);
  }
  return Array.from(byKey.values());
}

export function effectiveSettleMs(
  entry: ManifestEntry,
  manifest: Manifest,
): number {
  return entry.capture?.settle_ms ?? manifest.defaults.settle_ms ?? 500;
}

export function loadManifest(docsRepoPath: string): Manifest {
  const manifestPath = path.join(docsRepoPath, "screenshots.yaml");
  const raw = fs.readFileSync(manifestPath, "utf8");
  const parsed = yaml.load(raw) as Manifest | undefined;
  if (!parsed || typeof parsed !== "object" || parsed.version !== 1) {
    throw new Error(
      `Invalid manifest at ${manifestPath} — expected version: 1 at top level`,
    );
  }
  if (!Array.isArray(parsed.entries)) {
    throw new Error(`Invalid manifest at ${manifestPath} — missing entries[]`);
  }
  return parsed;
}

export function selectEntries(
  manifest: Manifest,
  ids: string[] | null,
): ManifestEntry[] {
  if (!ids || ids.length === 0) return manifest.entries;
  const wanted = new Set(ids);
  return manifest.entries.filter((e) => wanted.has(e.id));
}

export function effectiveViewport(
  entry: ManifestEntry,
  manifest: Manifest,
): { width: number; height: number } {
  return entry.viewport ?? manifest.defaults.viewport;
}

export function effectiveAuth(
  entry: ManifestEntry,
  manifest: Manifest,
): string {
  return entry.auth_as ?? manifest.defaults.auth_as;
}
