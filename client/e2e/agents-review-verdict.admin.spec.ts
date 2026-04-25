/**
 * Agent Review Flipbook (Admin)
 *
 * Seeds an agent and navigates to its review page. Without real LLM output
 * we can't generate a flagged run, so the assertion accepts the
 * "nothing to review" empty state — but the critical part (the page loads,
 * the flipbook surface renders, the route is wired) is now exercised
 * against a real agent id rather than self-skipping.
 */

import { test, expect } from "@playwright/test";
import { seedAgentViaPage } from "./setup/seed-agent";

test.describe("Agent Run Review + Verdict (admin)", () => {
	test("review flipbook page renders for an agent", async ({ page }) => {
		const agent = await seedAgentViaPage(page, {
			namePrefix: "Review Spec",
		});

		await page.goto(`/agents/${agent.id}/review`);
		await expect(
			page
				.getByText(/nothing to review|no flagged runs/i)
				.or(page.getByRole("heading", { name: /review/i }))
				.first(),
		).toBeVisible({ timeout: 10000 });

		await page.screenshot({
			path: "test-results/screenshots/agent-review.png",
			fullPage: true,
		});
	});
});
