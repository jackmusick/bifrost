/**
 * Realistic seed for the agent-management UX capture loop (Phase 7b T70).
 *
 * Entry points — called from the Playwright image with /tmp/ux-compare and the
 * worktree's test-stack docker network mounted in:
 *   1. SQL-hard-delete all agents (clears accumulated e2e residue).
 *   2. API-create 5 seed agents (same set as grab-ours-v3.mjs so routes match).
 *   3. SQL-insert 10–14 AgentRun rows per agent, spread across the last 7 days,
 *      mix of completed / failed / queued, ~20% flagged (verdict=down), with
 *      asked/did/confidence/run_metadata populated.
 *   4. SQL-insert 1 AgentRunFlagConversation on a flagged run with a realistic
 *      user → assistant → proposal → dryrun turn sequence (for tune page UX).
 *   5. SQL-insert 1 AgentPromptHistory row so prompt-versioning surface has data.
 *
 * Idempotent — clears by hard-delete + stable name prefix up front so re-running
 * is safe. Prints the primary agent id at the end so grab-ours-v3.mjs can
 * re-use it for screenshot capture.
 */

import jwt from "jsonwebtoken";
import pg from "pg";

const API = process.env.API_URL || "http://api:8000";
const PG_HOST = process.env.PG_HOST || "postgres";
const PG_DB = process.env.PG_DB || "bifrost_test";
const PG_USER = process.env.PG_USER || "bifrost";
const PG_PASS = process.env.PG_PASS || "bifrost_test";
const SECRET = "test-secret-key-for-e2e-testing-must-be-32-chars";

const client = new pg.Client({
	host: PG_HOST,
	user: PG_USER,
	password: PG_PASS,
	database: PG_DB,
	port: 5432,
});
await client.connect();

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

async function api(method, path, body) {
	const res = await fetch(API + path, {
		method,
		headers: {
			Authorization: `Bearer ${token}`,
			"Content-Type": "application/json",
		},
		body: body ? JSON.stringify(body) : undefined,
	});
	if (!res.ok) {
		throw new Error(`${method} ${path} ${res.status}: ${await res.text()}`);
	}
	const text = await res.text();
	return text ? JSON.parse(text) : null;
}

async function sql(stmt, params) {
	const res = await client.query(stmt, params);
	return res;
}

// ───────────────────────────────────────────────────────────────────────
// 1. Hard-delete all residue
// ───────────────────────────────────────────────────────────────────────

console.log("[1/5] Clearing existing agents + runs…");
await sql("DELETE FROM agent_run_flag_conversations");
await sql("DELETE FROM agent_run_steps");
await sql("DELETE FROM agent_runs");
await sql("DELETE FROM agent_prompt_history");
await sql("DELETE FROM agent_tools");
await sql("DELETE FROM agent_roles");
await sql("DELETE FROM agent_delegations");
await sql("DELETE FROM agents");

// ───────────────────────────────────────────────────────────────────────
// 2. API-create the 5 seed agents
// ───────────────────────────────────────────────────────────────────────

const SEEDS = [
	{
		name: "Ticket Triage",
		description:
			"Routes incoming tickets to the right team based on content and severity.",
		channels: ["chat", "teams"],
		paused: false,
	},
	{
		name: "Billing Assistant",
		description: "Answers billing questions and drafts invoice adjustments.",
		channels: ["chat", "slack"],
		paused: false,
	},
	{
		name: "Onboarding Guide",
		description:
			"Walks new users through first-time setup and answers getting-started questions.",
		channels: ["chat"],
		paused: false,
	},
	{
		name: "NOC Shift Summary",
		description: "Drafts end-of-shift summaries for network operations.",
		channels: ["teams"],
		paused: false,
	},
	{
		name: "Voice Intake",
		description: "First-line voice agent for after-hours callers.",
		channels: ["voice"],
		paused: true,
	},
];

console.log("[2/5] Creating 5 agents…");
const agents = [];
for (const seed of SEEDS) {
	const created = await api("POST", "/api/agents", {
		name: seed.name,
		description: seed.description,
		channels: seed.channels,
		system_prompt:
			"You are a helpful assistant. Triage the user's request and use the available tools to respond.",
		access_level: "authenticated",
	});
	if (seed.paused) {
		await api("PUT", `/api/agents/${created.id}`, { is_active: false });
	}
	agents.push({ ...created, paused: seed.paused });
	console.log(`    ${created.name}${seed.paused ? " (paused)" : ""}`);
}

// ───────────────────────────────────────────────────────────────────────
// 3. Per-agent run rows
// ───────────────────────────────────────────────────────────────────────

console.log("[3/5] Seeding runs…");

// Fixed seed for reproducible-looking data.
// All metadata values must be strings — contract is dict[str, str].
const PROMPTS = {
	"Ticket Triage": [
		{
			asked: "Printer on 3rd floor is offline — what queue?",
			did: "Routed to Workplace IT, P2",
			meta: { customer: "Globex", ticket_id: "4822", severity: "P2" },
		},
		{
			asked: "Can't log in to VPN after laptop swap",
			did: "Routed to Identity, P2",
			meta: { customer: "Hooli", ticket_id: "4823", severity: "P2" },
		},
		{
			asked: "CEO says Outlook is broken",
			did: "Routed to Workplace IT, P1",
			meta: { customer: "Hooli", ticket_id: "4824", severity: "P1" },
		},
		{
			asked: "Need a new starter laptop for tomorrow",
			did: "Routed to Procurement, P3",
			meta: { customer: "Globex", ticket_id: "4825", severity: "P3" },
		},
		{
			asked: "Production DB latency spike 10x",
			did: "Routed to SRE, P1 (paged)",
			meta: { customer: "Initech", ticket_id: "4826", severity: "P1" },
		},
		{
			asked: "S3 bucket is throwing 403s",
			did: "Routed to Platform, P2",
			meta: { customer: "Initech", ticket_id: "4827", severity: "P2" },
		},
	],
	"Billing Assistant": [
		{
			asked: "Why did my invoice go up this month?",
			did: "Explained the seat addition + forwarded usage breakdown",
			meta: { customer: "Globex", invoice: "INV-10-0421" },
		},
		{
			asked: "Need to change the PO number on the last invoice",
			did: "Opened amendment ticket + notified AR team",
			meta: { customer: "Hooli", invoice: "INV-10-0418" },
		},
		{
			asked: "Credit for outage on the 15th?",
			did: "Drafted $420 credit memo, pending approval",
			meta: { customer: "Initech", invoice: "INV-10-0420" },
		},
		{
			asked: "Prorate this month's upgrade?",
			did: "Calculated prorated amount $116.40, sent for review",
			meta: { customer: "Globex", invoice: "INV-10-0421" },
		},
	],
	"Onboarding Guide": [
		{
			asked: "Where do I set up SSO?",
			did: "Walked user through Okta config + sent setup doc",
			meta: { customer: "Hooli", step: "sso_config" },
		},
		{
			asked: "How do I invite my team?",
			did: "Opened invite flow, added 3 users",
			meta: { customer: "Globex", step: "invite_team" },
		},
		{
			asked: "What's the free tier limit?",
			did: "Summarized plan, quoted 5k runs/mo",
			meta: { customer: "Hooli", step: "plan_info" },
		},
	],
	"NOC Shift Summary": [
		{
			asked: "EOS for Tuesday night shift",
			did: "Drafted summary: 2 P1, 4 P2, 0 backlog",
			meta: { shift: "tue-night", incidents: "6" },
		},
		{
			asked: "EOS for Wed morning",
			did: "Drafted summary: 1 P1 (resolved), 2 P2, 1 backlog",
			meta: { shift: "wed-am", incidents: "3" },
		},
	],
	"Voice Intake": [
		{
			asked: "Can you speak with a human?",
			did: "Escalated to after-hours queue",
			meta: { channel: "voice", escalated: "true" },
		},
	],
};

const STATUSES = ["completed", "completed", "completed", "completed", "failed"];

function pickStatus(isFlagged, day) {
	if (day === 0 && Math.random() < 0.15) return "queued";
	if (isFlagged) return "completed";
	return STATUSES[Math.floor(Math.random() * STATUSES.length)];
}

function isoDaysAgo(days, hour) {
	const d = new Date();
	d.setDate(d.getDate() - days);
	d.setHours(hour, Math.floor(Math.random() * 60), 0, 0);
	return d.toISOString();
}

const runRows = [];
for (const agent of agents) {
	const prompts = PROMPTS[agent.name] ?? PROMPTS["Onboarding Guide"];
	if (agent.paused) continue; // paused agent has zero runs
	const count = 10 + Math.floor(Math.random() * 5); // 10–14
	const flaggedIndexes = new Set();
	// ~2–3 flagged per agent
	while (flaggedIndexes.size < Math.min(3, Math.max(2, Math.floor(count * 0.2)))) {
		flaggedIndexes.add(Math.floor(Math.random() * count));
	}
	for (let i = 0; i < count; i++) {
		const prompt = prompts[i % prompts.length];
		const isFlagged = flaggedIndexes.has(i);
		const day = Math.floor((i / count) * 7);
		const hour = 8 + Math.floor(Math.random() * 10);
		const started = isoDaysAgo(day, hour);
		const completed = new Date(
			new Date(started).getTime() + 500 + Math.floor(Math.random() * 7500),
		).toISOString();
		const status = pickStatus(isFlagged, day);
		const duration = Math.max(
			200,
			new Date(completed).getTime() - new Date(started).getTime(),
		);
		const tokens = 800 + Math.floor(Math.random() * 3200);
		const iterations = 1 + Math.floor(Math.random() * 4);
		const confidence = isFlagged
			? 0.4 + Math.random() * 0.25
			: 0.75 + Math.random() * 0.24;
		const verdict = isFlagged ? "down" : null;
		const verdictNote = isFlagged
			? "Wrong queue — should have gone to SRE"
			: null;
		runRows.push({
			agent_id: agent.id,
			status,
			asked: prompt.asked,
			did: status === "failed" ? null : prompt.did,
			run_metadata: prompt.meta,
			confidence,
			started,
			completed: status === "queued" ? null : completed,
			duration_ms: status === "queued" ? null : duration,
			tokens_used: status === "queued" ? 0 : tokens,
			iterations_used: status === "queued" ? 0 : iterations,
			verdict,
			verdict_note: verdictNote,
		});
	}
}

let inserted = 0;
for (const r of runRows) {
	await sql(
		`INSERT INTO agent_runs
			(id, agent_id, trigger_type, status, asked, did, metadata, confidence,
			 started_at, completed_at, duration_ms, tokens_used, iterations_used,
			 verdict, verdict_note, verdict_set_at, summary_status, created_at)
		 VALUES
			(gen_random_uuid(), $1, 'api', $2, $3, $4, $5::jsonb, $6, $7, $8, $9,
			 $10, $11, $12, $13, $14, 'completed', $15)`,
		[
			r.agent_id,
			r.status,
			r.asked,
			r.did,
			JSON.stringify(r.run_metadata),
			r.confidence,
			r.started,
			r.completed,
			r.duration_ms,
			r.tokens_used,
			r.iterations_used,
			r.verdict,
			r.verdict_note,
			r.verdict ? r.started : null,
			r.started,
		],
	);
	inserted += 1;
}
console.log(`    inserted ${inserted} runs`);

// ───────────────────────────────────────────────────────────────────────
// 4. One flag conversation with a realistic turn sequence
// ───────────────────────────────────────────────────────────────────────

console.log("[4/5] Seeding a flag conversation…");
const primary = agents[0];
const flaggedRes = await sql(
	`SELECT id FROM agent_runs WHERE agent_id = $1 AND verdict = 'down' ORDER BY created_at DESC LIMIT 1`,
	[primary.id],
);
const flaggedRunId = flaggedRes.rows[0]?.id ?? null;
if (flaggedRunId) {
	const now = new Date().toISOString();
	const messages = [
		{
			kind: "user",
			content:
				"This one should have gone to SRE — the customer said 'production DB latency'. Why did it land in Workplace IT?",
			at: now,
		},
		{
			kind: "assistant",
			content:
				"Good catch. I matched on 'production' + 'latency' but the classifier is weighting 'laptop' and 'VPN' keywords too heavily, which pulls some infra-sounding tickets into Workplace IT. Two patterns I'd tighten.",
			at: now,
		},
		{
			kind: "proposal",
			summary:
				"Tighten the routing rules: promote infra keywords, demote hardware-adjacent ones when infra signals are present.",
			diff: [
				{ op: "keep", text: "Route tickets based on content + severity." },
				{
					op: "remove",
					text: "Keyword-match on 'laptop', 'login', 'printer' → Workplace IT.",
				},
				{
					op: "add",
					text: "If the message mentions 'production', 'latency', 'outage', 'database', or 'kubernetes', route to SRE with +1 severity bump.",
				},
				{
					op: "add",
					text: "Only route to Workplace IT when infra keywords are absent.",
				},
			],
			at: now,
		},
		{
			kind: "dryrun",
			before: "Workplace IT · P2",
			after: "SRE · P1",
			predicted: "up",
			at: now,
		},
	];
	await sql(
		`INSERT INTO agent_run_flag_conversations (id, run_id, messages, created_at, last_updated_at)
		 VALUES (gen_random_uuid(), $1, $2::jsonb, $3, $3)`,
		[flaggedRunId, JSON.stringify(messages), now],
	);
	console.log(`    conversation on run ${flaggedRunId}`);
} else {
	console.log("    (no flagged run found — skipping conversation)");
}

// ───────────────────────────────────────────────────────────────────────
// 5. One prompt history row
// ───────────────────────────────────────────────────────────────────────

console.log("[5/5] Seeding prompt history…");
const nowIso = new Date(Date.now() - 86400000).toISOString();
await sql(
	`INSERT INTO agent_prompt_history
		(id, agent_id, previous_prompt, new_prompt, changed_at, reason)
	 VALUES (gen_random_uuid(), $1, $2, $3, $4, $5)`,
	[
		primary.id,
		"You are a helpful assistant. Route tickets by keyword.",
		"You are a helpful assistant. Route tickets by keyword AND severity. Prefer SRE for infra signals.",
		nowIso,
		"Applied tuning proposal: infra-signal priority routing",
	],
);

await client.end();

console.log("\nSeed complete.");
console.log("primary agent id: " + primary.id);
console.log(
	"agents: " +
		agents.map((a) => `${a.name}=${a.id}${a.paused ? "(paused)" : ""}`).join(", "),
);
