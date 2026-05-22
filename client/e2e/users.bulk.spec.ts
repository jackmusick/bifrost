/**
 * Bulk user actions — admin (Block 2).
 *
 * Drives the new selection checkbox column + BulkActionBar to verify the
 * happy path: select N users → "Move to org" → toast → invalidation refreshes
 * the rows.
 *
 * Avoids touching the platform_admin row (you can't bulk-act on yourself —
 * the row's checkbox is disabled with a tooltip).
 */

import { test, expect } from "./fixtures/api-fixture";

const SUFFIX = Math.random().toString(36).slice(2, 8);
const SOURCE_ORG_NAME = `Bulk Source ${SUFFIX}`;
const DEST_ORG_NAME = `Bulk Dest ${SUFFIX}`;
const USER_PREFIX = `bulk-spec-${SUFFIX}`;

test.describe("Bulk user actions", () => {
	test.beforeAll(async ({ api }) => {
		// Source + destination orgs so the move target is unambiguous.
		const sourceResp = await api.post("/api/organizations", {
			data: { name: SOURCE_ORG_NAME, domain: `${USER_PREFIX}-src.gobifrost.dev` },
		});
		expect(sourceResp.ok(), await sourceResp.text()).toBe(true);
		const source = await sourceResp.json();

		const destResp = await api.post("/api/organizations", {
			data: { name: DEST_ORG_NAME, domain: `${USER_PREFIX}-dst.gobifrost.dev` },
		});
		expect(destResp.ok(), await destResp.text()).toBe(true);
		const dest = await destResp.json();

		for (let i = 0; i < 3; i++) {
			const r = await api.post("/api/users", {
				data: {
					email: `${USER_PREFIX}-${i}@bulkspec.gobifrost.dev`,
					name: `${USER_PREFIX}-${i}`,
					organization_id: source.id,
					is_superuser: false,
					invite: false,
				},
			});
			expect(r.ok(), `Create user ${i} failed: ${await r.text()}`).toBe(true);
		}

		test.info().annotations.push(
			{ type: "bulk-source-org-id", description: source.id },
			{ type: "bulk-dest-org-id", description: dest.id },
		);
	});

	test.afterAll(async ({ api }) => {
		const list = await api.get("/api/users", {
			params: { include_inactive: true },
		});
		if (list.ok()) {
			const users = (await list.json()) as { id: string; email: string }[];
			for (const u of users) {
				if (u.email.startsWith(USER_PREFIX)) {
					await api.delete(`/api/users/${u.id}`);
				}
			}
		}
		for (const type of ["bulk-source-org-id", "bulk-dest-org-id"]) {
			const ann = test.info().annotations.find((a) => a.type === type);
			if (ann?.description) {
				await api.delete(`/api/organizations/${ann.description}`);
			}
		}
	});

	test("select 3, move to org, toast confirms", async ({ page }) => {
		await page.goto("/users");
		await expect(
			page.getByRole("heading", { name: /users/i }).first(),
		).toBeVisible({ timeout: 10000 });

		// Wait for the table to render with our seeded users.
		await expect(
			page.getByText(`${USER_PREFIX}-0`).first(),
		).toBeVisible({ timeout: 10000 });

		// Tick the row checkboxes for the 3 seeded users.
		for (let i = 0; i < 3; i++) {
			const checkbox = page.getByRole("checkbox", {
				name: new RegExp(`Select ${USER_PREFIX}-${i}`),
			});
			await checkbox.click();
		}

		// The sticky bulk action bar appears with the count.
		const actionBar = page.getByRole("region", { name: /bulk user actions/i });
		await expect(actionBar).toBeVisible();
		await expect(actionBar.getByText("3 selected")).toBeVisible();

		// Open the move-to-org dialog.
		await actionBar.getByRole("button", { name: /move to org/i }).click();
		const dialog = page.getByRole("dialog");
		await expect(dialog.getByText(/move 3 user/i)).toBeVisible();

		// Pick the destination org from the OrganizationSelect.
		await dialog.getByRole("combobox").click();
		await page.getByRole("option", { name: DEST_ORG_NAME }).click();

		// Submit and watch for the success toast.
		await dialog.getByRole("button", { name: /move users/i }).click();
		await expect(page.getByText(/move to org \(3\)/i)).toBeVisible({
			timeout: 10000,
		});
	});
});
