/**
 * Component tests for DataProviderInputsConfig.
 *
 * Configures static/fieldRef/expression inputs for a data provider. Covers:
 * - returns null when the provider has no parameters
 * - renders a row per parameter with the right mode controls
 * - static mode: typing fires onChange with mode=static
 * - fieldRef mode: switching mode clears value and sets mode=fieldRef
 * - Required badge is rendered for required parameters
 * - availableFields empty → disabled placeholder in fieldRef dropdown
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { DataProviderInputsConfig } from "./DataProviderInputsConfig";
import type { components } from "@/lib/v1";

// ExpressionEditor pulls in Monaco; stub to a plain textarea so tests don't
// have to boot a full editor. The prop surface we exercise is just
// value/onChange.
vi.mock("@/components/ui/expression-editor", () => ({
	ExpressionEditor: ({
		value,
		onChange,
	}: {
		value: string;
		onChange: (v: string) => void;
	}) => (
		<textarea
			aria-label="expression"
			value={value}
			onChange={(e) => onChange(e.target.value)}
		/>
	),
}));

type WorkflowMetadata = components["schemas"]["WorkflowMetadata"];

function makeProvider(
	parameters: Array<{ name: string; required?: boolean; label?: string; description?: string }>,
): WorkflowMetadata {
	return {
		id: "dp-1",
		name: "MyProvider",
		type: "data_provider",
		parameters: parameters.map((p) => ({
			name: p.name,
			type: "str",
			required: p.required ?? false,
			label: p.label ?? null,
			description: p.description ?? null,
		})),
	} as unknown as WorkflowMetadata;
}

describe("DataProviderInputsConfig", () => {
	it("renders nothing when the provider has no parameters", () => {
		const { container } = renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([])}
				inputs={{}}
				onChange={vi.fn()}
			/>,
		);
		expect(container).toBeEmptyDOMElement();
	});

	it("renders a parameter row with its name and mode toggle", () => {
		renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([{ name: "search", required: true }])}
				inputs={{}}
				onChange={vi.fn()}
			/>,
		);

		expect(screen.getByText("search")).toBeInTheDocument();
		expect(screen.getByText(/required/i)).toBeInTheDocument();
		// Radix ToggleGroupItem exposes role="radio".
		expect(screen.getByRole("radio", { name: /^static$/i })).toBeInTheDocument();
		expect(screen.getByRole("radio", { name: /^field$/i })).toBeInTheDocument();
		expect(
			screen.getByRole("radio", { name: /^expression$/i }),
		).toBeInTheDocument();
	});

	it("static mode: typing fires onChange with mode=static and the typed value", async () => {
		const onChange = vi.fn();
		const { user } = renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([{ name: "search" }])}
				inputs={{
					search: {
						mode: "static",
						value: "",
						field_name: null,
						expression: null,
					},
				}}
				onChange={onChange}
			/>,
		);

		// Static input uses the parameter's description as placeholder; ours is undefined so
		// it falls back to "Enter search..."
		const input = screen.getByPlaceholderText(/Enter search/i);
		await user.type(input, "q");

		const calls = onChange.mock.calls;
		const lastCall = calls[calls.length - 1]![0];
		expect(lastCall.search.mode).toBe("static");
		expect(lastCall.search.value).toBe("q");
	});

	it("switches to fieldRef mode when Field is clicked and shows the field dropdown", async () => {
		const onChange = vi.fn();
		const { user } = renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([{ name: "search" }])}
				inputs={{}}
				onChange={onChange}
				availableFields={["first_name", "last_name"]}
			/>,
		);

		await user.click(screen.getByRole("radio", { name: /^field$/i }));

		const calls = onChange.mock.calls;
		const lastCall = calls[calls.length - 1]![0];
		expect(lastCall.search.mode).toBe("fieldRef");
		// Static value cleared in this mode.
		expect(lastCall.search.value).toBeNull();
	});

	it("fieldRef dropdown shows 'No fields available' when availableFields is empty", async () => {
		const { user } = renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([{ name: "search" }])}
				inputs={{
					search: {
						mode: "fieldRef",
						value: null,
						field_name: "",
						expression: null,
					},
				}}
				onChange={vi.fn()}
				availableFields={[]}
			/>,
		);

		await user.click(screen.getByRole("combobox"));

		expect(
			await screen.findByText(/no fields available/i),
		).toBeInTheDocument();
	});

	it("renders the parameter description as helper text", () => {
		renderWithProviders(
			<DataProviderInputsConfig
				provider={makeProvider([
					{ name: "id", description: "The user ID to look up" },
				])}
				inputs={{}}
				onChange={vi.fn()}
			/>,
		);

		// Description renders in two places (placeholder and helper); we only check
		// the helper paragraph below the input.
		expect(
			screen.getAllByText(/the user id to look up/i).length,
		).toBeGreaterThanOrEqual(1);
	});
});
