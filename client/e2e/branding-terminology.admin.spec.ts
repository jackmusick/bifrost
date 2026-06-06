/**
 * Branding Terminology (Admin)
 *
 * Covers: platform admins can rename fixed product nouns through branding,
 * and those names render before the main UI appears.
 */

import { test, expect } from "./fixtures/api-fixture";

const DEFAULT_TERMINOLOGY = {
	app: { singular: "App", plural: "Apps" },
	agent: { singular: "Agent", plural: "Agents" },
	form: { singular: "Form", plural: "Forms" },
};

test.describe("Branding terminology", () => {
	test.afterEach(async ({ api }) => {
		const reset = await api.put("/api/branding", {
			data: { terminology: DEFAULT_TERMINOLOGY },
		});
		expect(reset.ok(), await reset.text()).toBe(true);
	});

	test("renders renamed product nouns in primary navigation", async ({
		api,
		page,
	}) => {
		const update = await api.put("/api/branding", {
			data: {
				terminology: {
					app: { singular: "Game", plural: "Games" },
					agent: { singular: "Character", plural: "Characters" },
					form: { singular: "Quest", plural: "Quests" },
				},
			},
		});
		expect(update.ok(), await update.text()).toBe(true);

		await page.goto("/apps");
		await expect(
			page.getByRole("link", { name: "Games" }),
		).toBeVisible();
		await expect(
			page.getByRole("heading", { name: "Games", exact: true }),
		).toBeVisible();

		await page.goto("/agents");
		await expect(
			page.getByRole("link", { name: "Characters" }),
		).toBeVisible();
		await expect(
			page.getByRole("heading", { name: "Characters", exact: true }),
		).toBeVisible();

		await page.goto("/forms");
		await expect(
			page.getByRole("link", { name: "Quests" }),
		).toBeVisible();
		await expect(
			page.getByRole("heading", { name: "Quests", exact: true }),
		).toBeVisible();
	});
});
