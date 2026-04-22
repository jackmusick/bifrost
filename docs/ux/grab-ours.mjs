/**
 * Capture agent-surface screenshots against a pre-seeded test stack.
 *
 * Expects seed-realistic.mjs to have run first (clears + inserts 5 agents +
 * ~46 runs + 1 flag conversation + 1 prompt history). Just navigates and
 * shoots.
 *
 * Primary agent id defaults to looking up "Ticket Triage" by name so this
 * script can be re-run independently without knowing which UUID the seed
 * produced.
 */

import { chromium } from "playwright";
import jwt from "jsonwebtoken";

const CLIENT = process.env.CLIENT_URL || "http://client";
const API = process.env.API_URL || "http://api:8000";
const SECRET = "test-secret-key-for-e2e-testing-must-be-32-chars";

const token = jwt.sign(
	{
		sub: "00000000-0000-4000-8000-000000000099",
		email: "admin@platform.com",
		name: "Platform Admin",
		is_superuser: true,
		org_id: null,
		roles: ["authenticated", "PlatformAdmin"],
		exp: Math.floor(Date.now() / 1000) + 60 * 60,
		iat: Math.floor(Date.now() / 1000),
		iss: "bifrost-api",
		aud: "bifrost-client",
		type: "access",
	},
	SECRET,
	{ algorithm: "HS256" },
);

async function api(path) {
	const r = await fetch(API + path, {
		headers: { Authorization: `Bearer ${token}` },
	});
	if (!r.ok) {
		throw new Error(`${path} → ${r.status}: ${await r.text()}`);
	}
	return r.json();
}

const agents = await api("/api/agents?active_only=false");

const primary = agents.find((a) => a.name === "Ticket Triage") ?? agents[0];
if (!primary) {
	console.error("No agents — run seed-realistic.mjs first.");
	process.exit(1);
}

// Look up one flagged run for review + run-detail captures.
let runsRaw = [];
try {
	const runs = await api(
		`/api/agent-runs?agent_id=${primary.id}&limit=50`,
	);
	runsRaw = runs.items ?? runs;
} catch (e) {
	console.log("runs fetch failed: " + e.message);
}
const flaggedRun = runsRaw.find((r) => r.verdict === "down") ?? null;
const sampleRunId = flaggedRun?.id ?? runsRaw[0]?.id ?? null;
console.log(`primary=${primary.id} sampleRun=${sampleRunId ?? "(none)"}`);

const ROUTES = [
	["fleet", CLIENT + "/agents"],
	["new-agent", CLIENT + "/agents/new"],
	["agent-detail-overview", CLIENT + "/agents/" + primary.id],
	["agent-detail-runs", CLIENT + "/agents/" + primary.id],
	["agent-detail-settings", CLIENT + "/agents/" + primary.id],
	["review-flipbook", CLIENT + "/agents/" + primary.id + "/review"],
	["tune-chat", CLIENT + "/agents/" + primary.id + "/tune"],
];
if (sampleRunId) {
	ROUTES.push([
		"run-detail",
		CLIENT + "/agents/" + primary.id + "/runs/" + sampleRunId,
	]);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
	viewport: { width: 1440, height: 900 },
	storageState: {
		cookies: [],
		origins: [
			{
				origin: CLIENT,
				localStorage: [{ name: "bifrost_access_token", value: token }],
			},
		],
	},
});
const page = await ctx.newPage();

// Mock the tuning endpoints since the test stack has no LLM wired up. Lets
// us capture the inline proposal bubble without touching prod.
await page.route("**/api/agents/*/tuning-session", (route) => {
	route.fulfill({
		status: 200,
		contentType: "application/json",
		body: JSON.stringify({
			summary:
				"Tighten the routing rules: promote infra keywords, demote hardware-adjacent ones when infra signals are present.",
			proposed_prompt: [
				"You are a helpful ticket-triage assistant.",
				"",
				"Routing rules:",
				"- If the message mentions 'production', 'latency', 'outage',",
				"  'database', or 'kubernetes' → route to SRE (bump severity +1).",
				"- If it mentions 'invoice', 'billing', 'PO' → route to Billing.",
				"- Only route to Workplace IT when no infra signals are present.",
				"",
				"Always include a one-line reason.",
			].join("\n"),
			affected_run_ids: [
				"e438a391-f198-4744-ae5a-146eb66bc088",
				"11111111-2222-3333-4444-555555555555",
			],
		}),
	});
});

for (const [name, url] of ROUTES) {
	try {
		await page.goto(url, { waitUntil: "networkidle", timeout: 15000 });
	} catch {
		await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
	}
	await page.waitForTimeout(1500);
	if (name === "agent-detail-runs") {
		try {
			await page
				.getByRole("tab", { name: /^runs/i })
				.click({ timeout: 3000 });
			await page.waitForTimeout(800);
		} catch (e) {
			console.log("runs tab click fail: " + e.message);
		}
	}
	if (name === "agent-detail-settings") {
		try {
			await page
				.getByRole("tab", { name: /^settings/i })
				.click({ timeout: 3000 });
			await page.waitForTimeout(800);
		} catch (e) {
			console.log("settings tab click fail: " + e.message);
		}
	}
	if (name === "tune-chat") {
		// Click "Propose change" so the capture shows the inline proposal bubble.
		try {
			await page
				.getByTestId("propose-button")
				.click({ timeout: 3000 });
			// Wait for the proposal to render — inline slot inside assistant bubble.
			await page.getByTestId("proposal-card").waitFor({ timeout: 8000 });
			await page.waitForTimeout(500);
		} catch (e) {
			console.log("tune propose click fail: " + e.message);
		}
	}
	await page.screenshot({
		path: "/tmp/ux-out/ours-" + name + ".png",
		fullPage: true,
	});
	console.log("captured " + name);
}

await browser.close();
