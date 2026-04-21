/**
 * Component tests for FormInfoPanel.
 *
 * Dumb controlled panel: four setters and four pieces of state. Covers
 * propagation of typed input, scope toggle (Global vs Organization-Specific),
 * and that the workflow input is wired to setLinkedWorkflow.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { FormInfoPanel } from "./FormInfoPanel";

function renderPanel(overrides: Partial<Parameters<typeof FormInfoPanel>[0]> = {}) {
	const props = {
		formName: "",
		setFormName: vi.fn(),
		formDescription: "",
		setFormDescription: vi.fn(),
		linkedWorkflow: "",
		setLinkedWorkflow: vi.fn(),
		isGlobal: true,
		setIsGlobal: vi.fn(),
		...overrides,
	};
	const utils = renderWithProviders(<FormInfoPanel {...props} />);
	return { ...utils, props };
}

describe("FormInfoPanel", () => {
	it("renders inputs populated with current values", () => {
		renderPanel({
			formName: "Onboarding",
			formDescription: "Welcome form",
			linkedWorkflow: "user_onboarding",
		});

		expect(screen.getByLabelText(/form name/i)).toHaveValue("Onboarding");
		expect(screen.getByLabelText(/linked workflow/i)).toHaveValue(
			"user_onboarding",
		);
		expect(screen.getByLabelText(/description/i)).toHaveValue("Welcome form");
	});

	it("calls setFormName as the user types into Form Name", async () => {
		const { user, props } = renderPanel();

		await user.type(screen.getByLabelText(/form name/i), "X");

		expect(props.setFormName).toHaveBeenLastCalledWith("X");
	});

	it("calls setLinkedWorkflow as the user types into Linked Workflow", async () => {
		const { user, props } = renderPanel();

		await user.type(screen.getByLabelText(/linked workflow/i), "Y");

		expect(props.setLinkedWorkflow).toHaveBeenLastCalledWith("Y");
	});

	it("calls setFormDescription as the user types into Description", async () => {
		const { user, props } = renderPanel();

		await user.type(screen.getByLabelText(/description/i), "Z");

		expect(props.setFormDescription).toHaveBeenLastCalledWith("Z");
	});

	it("flips scope to organization-specific when that button is clicked", async () => {
		const { user, props } = renderPanel({ isGlobal: true });

		await user.click(
			screen.getByRole("button", {
				name: /organization-specific.*specific to one organization/i,
			}),
		);

		expect(props.setIsGlobal).toHaveBeenCalledWith(false);
	});

	it("flips scope back to Global when Global is clicked", async () => {
		const { user, props } = renderPanel({ isGlobal: false });

		await user.click(
			screen.getByRole("button", {
				name: /global.*available to all organizations/i,
			}),
		);

		expect(props.setIsGlobal).toHaveBeenCalledWith(true);
	});
});
