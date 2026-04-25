/**
 * Component tests for IntegrationDefaultsDialog.
 *
 * Covers text field edits, bool field (rendered as a native <select>), the
 * required-marker, and the save submit. The dialog is controlled so we render
 * it with open=true.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, fireEvent } from "@/test-utils";
import { IntegrationDefaultsDialog } from "./IntegrationDefaultsDialog";

function renderDialog(
	overrides: Partial<Parameters<typeof IntegrationDefaultsDialog>[0]> = {},
) {
	const onFormValuesChange = vi.fn();
	const onSave = vi.fn();
	const onOpenChange = vi.fn();
	const utils = renderWithProviders(
		<IntegrationDefaultsDialog
			open
			onOpenChange={onOpenChange}
			configSchema={[
				{ key: "tenant_id", type: "string", required: true },
				{ key: "enabled", type: "bool" },
			]}
			formValues={{}}
			onFormValuesChange={onFormValuesChange}
			onSave={onSave}
			isSaving={false}
			{...overrides}
		/>,
	);
	return { ...utils, onFormValuesChange, onSave, onOpenChange };
}

describe("IntegrationDefaultsDialog — fields", () => {
	it("renders a field per schema entry with required markers", () => {
		renderDialog();
		expect(screen.getByLabelText(/tenant_id/i)).toBeInTheDocument();
		expect(screen.getByLabelText(/enabled/i)).toBeInTheDocument();
		// required marker on tenant_id
		expect(screen.getByText("*")).toBeInTheDocument();
	});

	it("bubbles up text edits through onFormValuesChange", () => {
		const { onFormValuesChange } = renderDialog();
		fireEvent.change(screen.getByLabelText(/tenant_id/i), {
			target: { value: "acme" },
		});
		expect(onFormValuesChange).toHaveBeenLastCalledWith({ tenant_id: "acme" });
	});

	it("bool fields emit proper true/false payloads", () => {
		const { onFormValuesChange } = renderDialog();
		fireEvent.change(screen.getByLabelText(/enabled/i), {
			target: { value: "true" },
		});
		expect(onFormValuesChange).toHaveBeenLastCalledWith({ enabled: true });
	});
});

describe("IntegrationDefaultsDialog — save", () => {
	it("calls onSave when the submit button is clicked", async () => {
		const { user, onSave } = renderDialog();
		await user.click(screen.getByRole("button", { name: /save defaults/i }));
		expect(onSave).toHaveBeenCalledTimes(1);
	});

	it("disables buttons and shows 'Saving...' while isSaving=true", () => {
		renderDialog({ isSaving: true });
		expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
		expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
	});
});
