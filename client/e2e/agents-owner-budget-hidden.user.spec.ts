/**
 * Agent Settings — Budget Field Visibility (Non-Admin User)
 *
 * Server-gates the budget fields (max_iterations, max_token_budget,
 * llm_max_tokens) to platform admins (T19). The settings tab also visually
 * hides both the Budgets section AND the Organization selector for non-admins.
 * This spec runs under the org-user storage state and verifies neither
 * appears.
 *
 * `beforeAll` seeds an authenticated-access agent from a throwaway admin
 * browser context so the org-user has something to navigate to.
 */

import { test, expect, chromium } from "@playwright/test";
import * as path from "path";
import { seedAgentViaPage } from "./setup/seed-agent";

const ADMIN_STATE = path.resolve(
	process.cwd(),
	"e2e",
	".auth",
	"platform_admin.json",
);

let seededAgentId: string | null = null;

test.describe("Agent Settings — Budget Visibility (non-admin user)", () => {
	test.beforeAll(async () => {
		const browser = await chromium.launch();
		const ctx = await browser.newContext({ storageState: ADMIN_STATE });
		const adminPage = await ctx.newPage();
		try {
			const agent = await seedAgentViaPage(adminPage, {
				namePrefix: "Budget Vis Spec",
			});
			seededAgentId = agent.id;
		} finally {
			await ctx.close();
			await browser.close();
		}
	});

	test("budget fields are not visible to non-admin users", async ({
		page,
	}) => {
		expect(seededAgentId).not.toBeNull();

		await page.goto(`/agents/${seededAgentId}`);
		await page.getByRole("tab", { name: /settings/i }).click();
		await expect(
			page.getByRole("textbox", { name: /name/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Budget fields must not appear for non-admins.
		await expect(page.getByLabel(/max iterations/i)).toHaveCount(0);
		await expect(page.getByLabel(/max token budget/i)).toHaveCount(0);
		await expect(
			page.getByLabel(/max tokens \/ response/i),
		).toHaveCount(0);

		// Organization selector is also admin-only (see AgentSettingsTab).
		await expect(page.getByLabel(/^organization/i)).toHaveCount(0);

		await page.screenshot({
			path: "test-results/screenshots/agent-settings-no-budget.png",
			fullPage: true,
		});
	});
});
