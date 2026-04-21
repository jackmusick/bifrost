/**
 * Component tests for FieldsPanel.
 *
 * Lightweight wrapper around useFieldManager. Mock FieldConfigDialog (which
 * pulls Monaco and a lot of dependencies). Focus on behavior:
 * - empty state when no fields
 * - renders each field's label, name, and type badge
 * - Add Field opens the dialog
 * - moveUp/moveDown reorder via setFields
 * - delete flow: trash → confirm → setFields called without that field
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";
import type { FormField } from "@/lib/client-types";

// Stub FieldConfigDialog so we don't boot Monaco / services here. The dialog
// simply renders a marker whose props we can assert on if needed.
vi.mock("./FieldConfigDialog", () => ({
	FieldConfigDialog: ({ open }: { open: boolean }) =>
		open ? <div role="dialog" aria-label="field-config" /> : null,
}));

// Import AFTER mocks so the mock takes effect.
import { FieldsPanel } from "./FieldsPanel";

function makeField(overrides: Partial<FormField> = {}): FormField {
	return {
		name: "first_name",
		label: "First Name",
		type: "text",
		required: false,
		...overrides,
	};
}

describe("FieldsPanel — empty state", () => {
	it("shows an empty message and the Add Field button when fields=[]", () => {
		renderWithProviders(<FieldsPanel fields={[]} setFields={vi.fn()} />);

		expect(
			screen.getByText(/no fields added yet/i),
		).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /add field/i }),
		).toBeInTheDocument();
	});

	it("opens the config dialog when Add Field is clicked", async () => {
		const { user } = renderWithProviders(
			<FieldsPanel fields={[]} setFields={vi.fn()} />,
		);

		await user.click(screen.getByRole("button", { name: /add field/i }));

		expect(
			screen.getByRole("dialog", { name: /field-config/i }),
		).toBeInTheDocument();
	});
});

describe("FieldsPanel — with fields", () => {
	const fields: FormField[] = [
		makeField({ name: "first_name", label: "First Name", type: "text" }),
		makeField({
			name: "email",
			label: "Email",
			type: "email",
			required: true,
		}),
	];

	it("renders each field with its label, name, and type", () => {
		renderWithProviders(<FieldsPanel fields={fields} setFields={vi.fn()} />);

		expect(screen.getByText("First Name")).toBeInTheDocument();
		expect(screen.getByText("Email")).toBeInTheDocument();
		expect(screen.getByText("first_name")).toBeInTheDocument();
		expect(screen.getAllByText("text").length).toBeGreaterThan(0);
		expect(screen.getAllByText("email").length).toBeGreaterThan(0);
	});

	it("marks required fields with a Required badge", () => {
		renderWithProviders(<FieldsPanel fields={fields} setFields={vi.fn()} />);

		expect(screen.getByText(/^required$/i)).toBeInTheDocument();
	});

	it("delete flow: trash → confirm → setFields called without that field", async () => {
		const setFields = vi.fn();
		const { user } = renderWithProviders(
			<FieldsPanel fields={fields} setFields={setFields} />,
		);

		// Locate the Email row by walking up from its label to the bordered row div.
		const emailRow = screen
			.getByText("Email")
			.closest("div.flex.items-center.gap-3")!;
		const buttonsInRow = within(emailRow as HTMLElement).getAllByRole("button");
		// Order within the row: [moveUp, moveDown, edit, trash].
		await user.click(buttonsInRow[buttonsInRow.length - 1]!);

		// Confirm in the AlertDialog. There are two "Remove Field" elements
		// (the heading and the confirm button); pick the button.
		const confirm = await screen.findByRole("button", {
			name: /^remove field$/i,
		});
		await user.click(confirm);

		expect(setFields).toHaveBeenCalledTimes(1);
		const newFields = setFields.mock.calls[0]![0];
		expect(newFields).toHaveLength(1);
		expect(newFields[0].name).toBe("first_name");
	});

	it("moveUp swaps a field with the one above it via setFields", async () => {
		const setFields = vi.fn();
		const { user } = renderWithProviders(
			<FieldsPanel fields={fields} setFields={setFields} />,
		);

		// Locate the Email row (index 1) and click its move-up button.
		const emailRow = screen
			.getByText("Email")
			.closest("div.flex.items-center.gap-3")!;
		const rowButtons = within(emailRow as HTMLElement).getAllByRole("button");
		// Order: [moveUp, moveDown, edit, trash]. The moveUp on the second row
		// should be enabled.
		await user.click(rowButtons[0]!);

		expect(setFields).toHaveBeenCalledTimes(1);
		const reordered = setFields.mock.calls[0]![0];
		expect(reordered[0].name).toBe("email");
		expect(reordered[1].name).toBe("first_name");
	});
});
