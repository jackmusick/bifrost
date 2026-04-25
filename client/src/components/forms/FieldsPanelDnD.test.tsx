/**
 * Component tests for FieldsPanelDnD.
 *
 * The full pragmatic-drag-and-drop machinery is impractical to drive in jsdom,
 * so we mock the @atlaskit primitives to no-ops and focus on render behavior,
 * the add/edit/delete flows that are driven via click events, and the workflow
 * input palette population logic.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";
import type { FormField } from "@/lib/client-types";

// Stub out pragmatic-drag-and-drop — the cleanup-returning noops let useEffect
// teardown succeed without errors, and canDrop / getInitialData don't fire
// because we never dispatch real drag events.
vi.mock("@atlaskit/pragmatic-drag-and-drop/element/adapter", () => ({
	draggable: () => () => {},
	dropTargetForElements: () => () => {},
}));
vi.mock("@atlaskit/pragmatic-drag-and-drop/combine", () => ({
	combine: (..._cleanups: unknown[]) => () => {},
}));
vi.mock("@atlaskit/pragmatic-drag-and-drop/reorder", () => ({
	reorder: ({ list }: { list: unknown[] }) => list,
}));
vi.mock("@atlaskit/pragmatic-drag-and-drop-auto-scroll/element", () => ({
	autoScrollForElements: () => () => {},
}));

// Stub the inner FieldConfigDialog to avoid Monaco / heavy deps.
vi.mock("./FieldConfigDialog", () => ({
	FieldConfigDialog: ({ open }: { open: boolean }) =>
		open ? <div role="dialog" aria-label="field-config" /> : null,
}));

// Mock useWorkflowsMetadata since the palette reads linked-workflow params.
const mockMetadata = vi.fn();
vi.mock("@/hooks/useWorkflows", () => ({
	useWorkflowsMetadata: () => ({ data: mockMetadata() }),
}));

import { FieldsPanelDnD } from "./FieldsPanelDnD";

function makeField(overrides: Partial<FormField> = {}): FormField {
	return {
		name: "first_name",
		label: "First Name",
		type: "text",
		required: false,
		...overrides,
	};
}

describe("FieldsPanelDnD — layout", () => {
	it("renders the field palette with all 11 field templates", () => {
		mockMetadata.mockReturnValue({ workflows: [] });

		renderWithProviders(
			<FieldsPanelDnD fields={[]} setFields={vi.fn()} />,
		);

		expect(screen.getByText("Field Palette")).toBeInTheDocument();
		// Check for a few representative templates.
		expect(screen.getByText("Text Input")).toBeInTheDocument();
		expect(screen.getByText("Email")).toBeInTheDocument();
		expect(screen.getByText("File Upload")).toBeInTheDocument();
		expect(screen.getByText("Markdown")).toBeInTheDocument();
	});

	it("renders the empty drop-zone copy when there are no fields", () => {
		mockMetadata.mockReturnValue({ workflows: [] });

		renderWithProviders(
			<FieldsPanelDnD fields={[]} setFields={vi.fn()} />,
		);

		expect(screen.getByText(/drop fields here/i)).toBeInTheDocument();
	});

	it("renders each existing field with its label and name", () => {
		mockMetadata.mockReturnValue({ workflows: [] });

		renderWithProviders(
			<FieldsPanelDnD
				fields={[
					makeField({ name: "first_name", label: "First Name" }),
					makeField({ name: "user_email", label: "User Email", type: "email" }),
				]}
				setFields={vi.fn()}
			/>,
		);

		// Field labels ("First Name" and "User Email") are unique; the names
		// ("first_name", "user_email") appear in the field rows alongside the
		// type badge.
		expect(screen.getByText("First Name")).toBeInTheDocument();
		expect(screen.getByText("User Email")).toBeInTheDocument();
		expect(screen.getByText("first_name")).toBeInTheDocument();
		expect(screen.getByText("user_email")).toBeInTheDocument();
	});
});

describe("FieldsPanelDnD — Add Field button", () => {
	it("opens the FieldConfigDialog", async () => {
		mockMetadata.mockReturnValue({ workflows: [] });

		const { user } = renderWithProviders(
			<FieldsPanelDnD fields={[]} setFields={vi.fn()} />,
		);

		await user.click(screen.getByRole("button", { name: /add field/i }));

		expect(
			screen.getByRole("dialog", { name: /field-config/i }),
		).toBeInTheDocument();
	});
});

describe("FieldsPanelDnD — delete flow", () => {
	it("removes the field when the user confirms deletion", async () => {
		mockMetadata.mockReturnValue({ workflows: [] });
		const fields = [
			makeField({ name: "first_name", label: "First Name" }),
			makeField({ name: "user_email", label: "User Email", type: "email" }),
		];
		const setFields = vi.fn();

		const { user } = renderWithProviders(
			<FieldsPanelDnD fields={fields} setFields={setFields} />,
		);

		// Locate the User Email row (has classes "flex items-center gap-3 rounded-lg border p-3")
		// and its action buttons: [edit, trash].
		const emailRow = screen
			.getByText("User Email")
			.closest("div.rounded-lg.border")!;
		const rowButtons = within(emailRow as HTMLElement).getAllByRole(
			"button",
		);
		await user.click(rowButtons[rowButtons.length - 1]!);

		// Confirm in AlertDialog.
		await user.click(
			await screen.findByRole("button", { name: /^remove field$/i }),
		);

		expect(setFields).toHaveBeenCalledTimes(1);
		const remaining = setFields.mock.calls[0]![0];
		expect(remaining).toHaveLength(1);
		expect(remaining[0].name).toBe("first_name");
	});
});

describe("FieldsPanelDnD — workflow input palette", () => {
	it("renders workflow inputs for the linked workflow, excluding already-added fields", () => {
		mockMetadata.mockReturnValue({
			workflows: [
				{
					id: "wf-1",
					name: "Onboard",
					parameters: [
						{
							name: "user_email",
							type: "str",
							required: true,
							description: "User's email",
						},
						{
							name: "first_name",
							type: "str",
							required: false,
						},
					],
				},
			],
		});

		renderWithProviders(
			<FieldsPanelDnD
				fields={[makeField({ name: "first_name" })]}
				setFields={vi.fn()}
				linkedWorkflow="wf-1"
			/>,
		);

		// user_email should show in the palette; first_name is already a field
		// and is filtered out.
		expect(screen.getByText("user_email")).toBeInTheDocument();
		// "first_name" appears once — for the existing form field row — but NOT
		// in the workflow inputs panel.
		const palette = screen.getByText(/workflow inputs/i).closest("div")!
			.parentElement!;
		expect(
			within(palette).queryByText("first_name"),
		).not.toBeInTheDocument();
	});

	it("does not render the workflow inputs section if no linkedWorkflow is provided", () => {
		mockMetadata.mockReturnValue({
			workflows: [
				{
					id: "wf-1",
					name: "Onboard",
					parameters: [{ name: "foo", type: "str" }],
				},
			],
		});

		renderWithProviders(
			<FieldsPanelDnD fields={[]} setFields={vi.fn()} />,
		);

		expect(
			screen.queryByText(/workflow inputs/i),
		).not.toBeInTheDocument();
	});
});
