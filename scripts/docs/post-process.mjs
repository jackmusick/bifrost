#!/usr/bin/env node
/**
 * Host-side post-processor for the docs screenshot pipeline.
 *
 * After the capture spec finishes, each parallel Playwright worker has
 * dropped its own `<docs>/.tmp-captures/results-<id>.json` (per-entry
 * files avoid the read-modify-write race that a single shared
 * results.json had). This script:
 *
 *   1. Globs every `results-*.json` and merges them into a single list.
 *   2. Reads each captured PNG.
 *   3. Applies `capture.crop` (if defined) to extract a sub-region.
 *   4. Overlays `capture.callouts` rectangles + labels.
 *   5. Compares the result to the committed PNG at `<docs>/<entry.image>`.
 *      If pixel diff exceeds threshold, replaces the committed PNG and
 *      marks the entry's `captured_at` with the current bifrost SHA.
 *      Otherwise discards the temp file silently.
 *
 * Inputs:
 *   --docs-repo <path>     required
 *   --bifrost-repo <path>  required (for git rev-parse HEAD)
 *   --threshold <pct>      default 0.1 (% of pixels that must differ)
 *
 * Outputs (to stdout):
 *   JSON summary { committed, unchanged, errors, missing }
 */
import { readFileSync, writeFileSync, existsSync, copyFileSync, unlinkSync, mkdirSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { execSync } from "node:child_process";
import yaml from "js-yaml";
import sharp from "sharp";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

function parseArgs(argv) {
  const out = { threshold: 0.001, captureExitCode: 0 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--docs-repo") out.docsRepo = argv[++i];
    else if (a === "--bifrost-repo") out.bifrostRepo = argv[++i];
    else if (a === "--threshold") out.threshold = parseFloat(argv[++i]);
    else if (a === "--capture-exit-code") out.captureExitCode = parseInt(argv[++i], 10) || 0;
    else if (a === "-h" || a === "--help") {
      console.log("usage: post-process.mjs --docs-repo <path> --bifrost-repo <path> [--threshold <0..1>] [--capture-exit-code <n>]");
      process.exit(0);
    } else {
      console.error(`unknown arg: ${a}`);
      process.exit(2);
    }
  }
  if (!out.docsRepo || !out.bifrostRepo) {
    console.error("--docs-repo and --bifrost-repo are required");
    process.exit(2);
  }
  return out;
}

function bifrostHead(bifrostRepo) {
  return execSync("git rev-parse HEAD", { cwd: bifrostRepo, encoding: "utf8" }).trim();
}

async function applyAnnotations(imageBuf, capture, defaults) {
  let img = sharp(imageBuf);
  const meta = await img.metadata();
  let width = meta.width ?? 0;
  let height = meta.height ?? 0;
  let buf = imageBuf;

  // Per-entry crop wins; fall back to manifest-wide defaults.crop so a single
  // value can strip sidebar/header chrome from every screenshot.
  const effectiveCrop = capture?.crop ?? defaults?.crop;
  if (effectiveCrop) {
    const c = effectiveCrop;
    const left = Math.max(0, Math.min(c.x, width - 1));
    const top = Math.max(0, Math.min(c.y, height - 1));
    const w = Math.max(1, Math.min(c.width, width - left));
    const h = Math.max(1, Math.min(c.height, height - top));
    buf = await sharp(buf).extract({ left, top, width: w, height: h }).png().toBuffer();
    const cropMeta = await sharp(buf).metadata();
    width = cropMeta.width ?? w;
    height = cropMeta.height ?? h;
  }

  const callouts = capture?.callouts ?? [];
  if (callouts.length) {
    // For each callout, render an SVG overlay (rectangle + optional label badge).
    const svgParts = callouts.map((co, idx) => {
      const color = co.color ?? "#f59e0b";
      const stroke = 4;
      const x = co.x;
      const y = co.y;
      const w = co.width;
      const h = co.height;
      const labelText = co.label ?? String(idx + 1);
      const labelSize = 28;
      const labelX = Math.max(0, x - labelSize / 2);
      const labelY = Math.max(0, y - labelSize / 2);
      return `
        <rect x="${x}" y="${y}" width="${w}" height="${h}"
              fill="none" stroke="${color}" stroke-width="${stroke}" rx="4" />
        <circle cx="${labelX + labelSize / 2}" cy="${labelY + labelSize / 2}"
                r="${labelSize / 2}" fill="${color}" />
        <text x="${labelX + labelSize / 2}" y="${labelY + labelSize / 2 + 5}"
              font-family="Inter, system-ui, sans-serif" font-size="16"
              font-weight="700" fill="white" text-anchor="middle">${escapeXml(labelText)}</text>
      `;
    });
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
           viewBox="0 0 ${width} ${height}">
        ${svgParts.join("\n")}
      </svg>
    `;
    buf = await sharp(buf)
      .composite([{ input: Buffer.from(svg), top: 0, left: 0 }])
      .png()
      .toBuffer();
  }

  return buf;
}

function escapeXml(s) {
  return String(s).replace(/[<>&"']/g, (c) => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
  })[c]);
}

function pngFromBuffer(buf) {
  return PNG.sync.read(buf);
}

function diffPercent(aBuf, bBuf) {
  const a = pngFromBuffer(aBuf);
  const b = pngFromBuffer(bBuf);
  if (a.width !== b.width || a.height !== b.height) return 1;
  const diff = new PNG({ width: a.width, height: a.height });
  const numDiff = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
    threshold: 0.1,
  });
  return numDiff / (a.width * a.height);
}

function loadResults(tmpDir) {
  // Per-entry result files: each parallel worker drops one
  // results-<id>.json. Merge them all into a single list. We do NOT fall
  // back to a legacy aggregated results.json — the capture spec writes
  // per-entry only, and any legacy file would be stale.
  if (!existsSync(tmpDir)) return [];
  const merged = [];
  const seen = new Set();
  for (const f of readdirSync(tmpDir)) {
    if (!f.startsWith("results-") || !f.endsWith(".json")) continue;
    const p = resolve(tmpDir, f);
    let parsed;
    try {
      parsed = JSON.parse(readFileSync(p, "utf8"));
    } catch (e) {
      console.error(`[post-process] skipping unreadable ${f}: ${e instanceof Error ? e.message : e}`);
      continue;
    }
    // Defensive: if a worker somehow wrote an array, flatten it.
    const entries = Array.isArray(parsed) ? parsed : [parsed];
    for (const r of entries) {
      if (!r || typeof r.id !== "string") continue;
      if (seen.has(r.id)) continue;
      seen.add(r.id);
      merged.push(r);
    }
  }
  return merged;
}

async function main() {
  const args = parseArgs(process.argv);
  const docsRepo = resolve(args.docsRepo);
  const bifrostRepo = resolve(args.bifrostRepo);
  const tmpDir = resolve(docsRepo, ".tmp-captures");
  const manifestPath = resolve(docsRepo, "screenshots.yaml");

  const results = loadResults(tmpDir);
  if (results.length === 0) {
    console.error(`No capture results found in ${tmpDir} (expected results-*.json files)`);
    process.exit(1);
  }

  const manifest = yaml.load(readFileSync(manifestPath, "utf8"));
  const byId = new Map(manifest.entries.map((e) => [e.id, e]));
  const sha = bifrostHead(bifrostRepo);

  const summary = { committed: [], unchanged: [], errors: [], missing: [], capture_exit_code: args.captureExitCode };

  for (const r of results) {
    if (r.status !== "captured") {
      summary.errors.push({ id: r.id, message: r.message });
      continue;
    }
    const entry = byId.get(r.id);
    if (!entry) {
      summary.missing.push(r.id);
      continue;
    }
    // results.json records the container-side path (/docs/.tmp-captures/...).
    // Translate it to the host-side path so the post-processor can read it.
    const tempBasename = r.tempPath.split("/").pop();
    const hostTempPath = resolve(tmpDir, tempBasename);
    if (!existsSync(hostTempPath)) {
      summary.missing.push(r.id);
      continue;
    }

    try {
      const tempBuf = readFileSync(hostTempPath);
      const finalBuf = await applyAnnotations(tempBuf, entry.capture, manifest.defaults);
      const targetPath = resolve(docsRepo, entry.image);
      mkdirSync(dirname(targetPath), { recursive: true });

      let shouldCommit = true;
      if (existsSync(targetPath)) {
        const existing = readFileSync(targetPath);
        let pct;
        try {
          pct = diffPercent(existing, finalBuf);
        } catch (diffErr) {
          // Existing PNG is unreadable (e.g. placeholder stub written by an
          // earlier failed capture). Treat as first-capture so we overwrite it.
          pct = 1;
        }
        if (pct < args.threshold) {
          shouldCommit = false;
          summary.unchanged.push({ id: r.id, diffPct: pct });
        } else {
          summary.committed.push({ id: r.id, diffPct: pct });
        }
      } else {
        summary.committed.push({ id: r.id, diffPct: 1, reason: "first-capture" });
      }

      if (shouldCommit) {
        writeFileSync(targetPath, finalBuf);
        entry.captured_at = { bifrost_sha: sha, timestamp: new Date().toISOString() };
      }

      try {
        unlinkSync(hostTempPath);
      } catch {
        // Containers run as root; the host user may not be able to unlink.
        // Harmless — the next pipeline run wipes .tmp-captures/ anyway.
      }
    } catch (e) {
      summary.errors.push({ id: r.id, message: e instanceof Error ? e.message : String(e) });
    }
  }

  // Write back the manifest with updated captured_at fields.
  writeFileSync(manifestPath, yaml.dump(manifest, { lineWidth: 120, noRefs: true }));

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
