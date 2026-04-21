/**
 * Component tests for OrgConfigDialog.
 *
 * Covers the override/reset flow and the save-payload shape — values that
 * are blanked after being previously set should round-trip as `null` so the
 * backend deletes them, while brand-new empty keys should be omitted.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, fireEvent, waitFor } from "@/test-utils";
import { OrgConfigDialog } from "./OrgConfigDialog";
import type { ConfigSchemaItem } from "@/services/integrations";

function configSchema(): ConfigSchemaItem[] {
	return [
		{ key: "tenant_id", type: "string", required: false },
		{ key: "enabled", type: "bool", required: false },
	] as ConfigSchemaItem[];
}

function renderDialog(
	overrides: Partial<Parameters<typeof OrgConfigDialog>[0]> = {},
) {
	const onSave = vi.fn().mockResolvedValue(undefined);
	const onOpenChange = vi.fn();
	const utils = renderWithProviders(
		<OrgConfigDialog
			open
			onOpenChange={onOpenChange}
			orgId="org-1"
			orgName="Acme Corp"
			configSchema={configSchema()}
			currentConfig={{}}
			onSave={onSave}
			{...overrides}
		/>,
	);
	return { ...utils, onSave, onOpenChange };
}

describe("OrgConfigDialog — save payloads", () => {
	it("saves only the keys the user set", async () => {
		const { user, onSave, onOpenChange } = renderDialog();

		// ConfigFieldInput's Label has no htmlFor. Target input by placeholder,
		// which falls back to the field key when description is absent.
		const tenantInput = screen.getByPlaceholderText("tenant_id");
		fireEvent.change(tenantInput, { target: { value: "acme" } });

		await user.click(screen.getByRole("button", { name: /^save$/i }));

		await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
		expect(onSave).toHaveBeenCalledWith({ tenant_id: "acme" });
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});

	it("sends null for keys that were previously set but are now blank (delete semantics)", async () => {
		const { user, onSave } = renderDialog({
			currentConfig: { tenant_id: "oldval" },
		});

		const tenantInput = screen.getByPlaceholderText("tenant_id");
		fireEvent.change(tenantInput, { target: { value: "" } });

		await user.click(screen.getByRole("button", { name: /^save$/i }));

		await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
		expect(onSave).toHaveBeenCalledWith({ tenant_id: null });
	});

	it("Reset button removes a key from the save payload", async () => {
		const { user, onSave } = renderDialog({
			currentConfig: { tenant_id: "oldval" },
		});

		// Reset exists because tenant_id has an override
		await user.click(screen.getByRole("button", { name: /reset/i }));
		await user.click(screen.getByRole("button", { name: /^save$/i }));

		await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
		// Reset clears the form value; since the key was in currentConfig it
		// gets sent as null so the backend deletes it.
		expect(onSave).toHaveBeenCalledWith({ tenant_id: null });
	});
});

describe("OrgConfigDialog — UI wiring", () => {
	it("renders a message when configSchema is empty", () => {
		renderDialog({ configSchema: [] });
		expect(
			screen.getByText(/no configuration fields defined/i),
		).toBeInTheDocument();
	});

	it("shows the org name in the title", () => {
		renderDialog({ orgName: "Acme Corp" });
		expect(
			screen.getByRole("heading", { name: /configure acme corp/i }),
		).toBeInTheDocument();
	});
});
