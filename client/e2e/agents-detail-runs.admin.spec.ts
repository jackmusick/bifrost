/**
 * Agent Detail — Runs Tab (Admin)
 *
 * Smoke tests for the per-agent detail page (`/agents/:id`):
 *   - Edit mode renders Overview/Runs/Settings tabs and the Runs tab opens.
 *   - Create mode (`/agents/new`) disables Overview/Runs and only Settings
 *     is interactive.
 *
 * Uses the api fixture to create + clean up an agent so the detail page
 * has deterministic state to render against.
 */

import { test, expect } from "./fixtures/api-fixture";

test.describe("Agent Detail — Runs Tab (admin)", () => {
	test("shows agent detail with tabs and Runs view", async ({
		page,
		api,
	}) => {
		const create = await api.post("/api/agents", {
			data: {
				name: `E2E Detail Test ${Date.now()}`,
				description: "e2e",
				system_prompt: "test",
				channels: ["chat"],
				access_level: "authenticated",
			},
		});
		expect(create.ok()).toBeTruthy();
		const agent = await create.json();

		try {
			await page.goto(`/agents/${agent.id}`);

			// Page header visible
			await expect(
				page.getByRole("heading", { name: agent.name }).first(),
			).toBeVisible({ timeout: 10000 });

			// Tabs visible — Overview, Runs, Settings
			await expect(
				page.getByRole("tab", { name: /overview/i }),
			).toBeVisible();
			await expect(
				page.getByRole("tab", { name: /runs/i }),
			).toBeVisible();
			await expect(
				page.getByRole("tab", { name: /settings/i }),
			).toBeVisible();

			// Click Runs tab
			await page.getByRole("tab", { name: /runs/i }).click();

			// Either run cards or empty state — accept either; this agent
			// has zero runs so we expect the empty state.
			await expect(
				page
					.getByText(/no runs|nothing yet|no flagged runs/i)
					.or(page.getByRole("table"))
					.first(),
			).toBeVisible({ timeout: 5000 });

			await page.screenshot({
				path: "test-results/screenshots/agent-detail-runs.png",
				fullPage: true,
			});
		} finally {
			await api.delete(`/api/agents/${agent.id}`);
		}
	});

	test("Settings tab is the only active tab in create mode", async ({
		page,
	}) => {
		await page.goto("/agents/new");
		await expect(
			page.getByRole("tab", { name: /settings/i }),
		).toBeVisible({ timeout: 10000 });
		// Overview/Runs disabled in create mode.
		const overviewTab = page.getByRole("tab", { name: /overview/i });
		await expect(overviewTab).toBeDisabled();
	});
});
