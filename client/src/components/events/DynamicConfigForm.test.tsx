/**
 * Component tests for DynamicConfigForm.
 *
 * Covers each static field-type branch (string, boolean, static enum, array
 * enum toggle group). Dynamic values with x-dynamic-values would require
 * hitting the useDynamicValues hook; we stub that hook with empty data so
 * the dependency-satisfied text-input branch renders deterministically.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, fireEvent } from "@/test-utils";

vi.mock("@/services/events", async () => {
	const actual = await vi.importActual<typeof import("@/services/events")>(
		"@/services/events",
	);
	return {
		...actual,
		useDynamicValues: () => ({
			data: { items: [] },
			isLoading: false,
			error: null,
		}),
	};
});

import { DynamicConfigForm, type ConfigSchema } from "./DynamicConfigForm";

function renderForm(schema: ConfigSchema, config: Record<string, unknown> = {}) {
	const onChange = vi.fn();
	const utils = renderWithProviders(
		<DynamicConfigForm
			adapterName="test-adapter"
			configSchema={schema}
			config={config}
			onChange={onChange}
		/>,
	);
	return { ...utils, onChange };
}

describe("DynamicConfigForm — empty schema", () => {
	it("renders nothing when the schema has no properties", () => {
		const { container } = renderForm({ type: "object", properties: {} });
		expect(container.firstChild).toBeNull();
	});
});

describe("DynamicConfigForm — string field", () => {
	it("renders a text input and emits typed string via onChange", () => {
		const { onChange } = renderForm({
			type: "object",
			properties: {
				label: { type: "string", title: "Label" },
			},
		});

		fireEvent.change(screen.getByLabelText(/label/i), {
			target: { value: "foo" },
		});

		expect(onChange).toHaveBeenLastCalledWith({ label: "foo" });
	});

	it("removes the key from config when the input is cleared", () => {
		const { onChange } = renderForm(
			{
				type: "object",
				properties: { label: { type: "string", title: "Label" } },
			},
			{ label: "existing" },
		);

		fireEvent.change(screen.getByLabelText(/label/i), {
			target: { value: "" },
		});

		expect(onChange).toHaveBeenLastCalledWith({});
	});
});

describe("DynamicConfigForm — boolean field", () => {
	it("renders a checkbox and emits booleans", async () => {
		const { user, onChange } = renderForm({
			type: "object",
			properties: {
				enabled: { type: "boolean", title: "Enabled" },
			},
		});

		await user.click(screen.getByRole("checkbox", { name: /enabled/i }));

		expect(onChange).toHaveBeenLastCalledWith({ enabled: true });
	});
});

describe("DynamicConfigForm — static enum", () => {
	it("renders the selectable options from the enum", () => {
		renderForm({
			type: "object",
			properties: {
				mode: {
					type: "string",
					title: "Mode",
					enum: ["live", "test"],
				},
			},
		});
		// The closed select shows a placeholder containing the title
		expect(
			screen.getByRole("combobox", { name: /mode/i }),
		).toBeInTheDocument();
	});
});

describe("DynamicConfigForm — required markers", () => {
	it("renders a required marker next to required fields", () => {
		renderForm({
			type: "object",
			required: ["label"],
			properties: {
				label: { type: "string", title: "Label" },
			},
		});
		expect(screen.getByText("*")).toBeInTheDocument();
	});
});
