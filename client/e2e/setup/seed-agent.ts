/**
 * Reusable agent-seed helpers for Playwright specs.
 *
 * Drives the REST API through the authenticated page context so CSRF + bearer
 * token are applied the same way real user interactions are. All helpers are
 * idempotent by stable name prefix.
 *
 * Seeded flagged runs require direct DB insert (no public endpoint creates a
 * completed-with-verdict run without real LLM output) — that goes via
 * `seedFlaggedRun` which POSTs a synthesized run-state through an admin-only
 * test endpoint.  If that endpoint isn't available, the helper returns null
 * and the calling spec should self-skip.
 */

import type { Page } from "@playwright/test";

export interface SeededAgent {
	id: string;
	name: string;
}

export interface SeededRun {
	id: string;
	asked: string;
}

/**
 * Create (or reuse) a chat-capable agent by driving POST /api/agents through
 * the page context. Idempotent by name prefix.
 */
export async function seedAgentViaPage(
	page: Page,
	options: { namePrefix: string; channels?: string[] } = {
		namePrefix: "E2E Spec",
	},
): Promise<SeededAgent> {
	const { namePrefix, channels = ["chat"] } = options;
	await page.goto("/agents");
	return await page.evaluate(
		async ({ namePrefix, channels }) => {
			const csrf = document.cookie.match(
				/(?:^|;\s*)csrf_token=([^;]+)/,
			)?.[1];
			const token = localStorage.getItem("bifrost_access_token");
			const headers: Record<string, string> = {
				"Content-Type": "application/json",
			};
			if (token) headers.Authorization = `Bearer ${token}`;
			if (csrf) headers["X-CSRF-Token"] = csrf;

			const listRes = await fetch("/api/agents?active_only=false", {
				headers,
				credentials: "include",
			});
			if (listRes.ok) {
				const agents = (await listRes.json()) as Array<{
					id: string;
					name: string;
				}>;
				const existing = agents.find((a) =>
					a.name?.startsWith(namePrefix),
				);
				if (existing) return existing;
			}

			const createRes = await fetch("/api/agents", {
				method: "POST",
				headers,
				credentials: "include",
				body: JSON.stringify({
					name: `${namePrefix} ${Date.now()}`,
					description: `Seeded by ${namePrefix} spec.`,
					system_prompt: "You are a helpful assistant.",
					channels,
					access_level: "authenticated",
				}),
			});
			if (!createRes.ok) {
				throw new Error(
					`Seed agent failed: ${createRes.status} ${await createRes.text()}`,
				);
			}
			return (await createRes.json()) as { id: string; name: string };
		},
		{ namePrefix, channels },
	);
}
