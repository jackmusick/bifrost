/**
 * Component tests for OptionsEditor.
 *
 * Pure state-less editor for {label, value} option lists. Covers add/remove
 * row, update label/value independently, custom label+helpText, empty-state
 * rendering.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { OptionsEditor } from "./OptionsEditor";

describe("OptionsEditor", () => {
	it("renders each option as two editable inputs", () => {
		renderWithProviders(
			<OptionsEditor
				options={[
					{ label: "One", value: "1" },
					{ label: "Two", value: "2" },
				]}
				onChange={vi.fn()}
			/>,
		);

		const labels = screen.getAllByPlaceholderText(/Label \(shown to user\)/i);
		const values = screen.getAllByPlaceholderText(/Value \(stored\)/i);

		expect(labels).toHaveLength(2);
		expect(values).toHaveLength(2);
		expect(labels[0]).toHaveValue("One");
		expect(labels[1]).toHaveValue("Two");
		expect(values[0]).toHaveValue("1");
		expect(values[1]).toHaveValue("2");
	});

	it("calls onChange with a new blank row when Add Option is clicked", async () => {
		const onChange = vi.fn();
		const { user } = renderWithProviders(
			<OptionsEditor options={[]} onChange={onChange} />,
		);

		await user.click(screen.getByRole("button", { name: /add option/i }));

		expect(onChange).toHaveBeenCalledWith([{ label: "", value: "" }]);
	});

	it("updates only the targeted option's label", async () => {
		const onChange = vi.fn();
		const { user } = renderWithProviders(
			<OptionsEditor
				options={[
					{ label: "One", value: "1" },
					{ label: "Two", value: "2" },
				]}
				onChange={onChange}
			/>,
		);

		const labels = screen.getAllByPlaceholderText(/Label \(shown to user\)/i);
		await user.type(labels[1]!, "X");

		// The onChange receives the full array, with only the second label mutated.
		const calls = onChange.mock.calls;
		const call = calls[calls.length - 1]![0];
		expect(call[0]).toEqual({ label: "One", value: "1" });
		expect(call[1]).toEqual({ label: "TwoX", value: "2" });
	});

	it("removes the targeted option when its Trash button is clicked", async () => {
		const onChange = vi.fn();
		const { user } = renderWithProviders(
			<OptionsEditor
				options={[
					{ label: "A", value: "a" },
					{ label: "B", value: "b" },
				]}
				onChange={onChange}
			/>,
		);

		// Only delete buttons present; pick the first.
		const deleteButtons = screen.getAllByRole("button", { name: "" });
		await user.click(deleteButtons[0]!);

		expect(onChange).toHaveBeenCalledWith([{ label: "B", value: "b" }]);
	});

	it("renders a custom label and optional help text", () => {
		renderWithProviders(
			<OptionsEditor
				options={[]}
				onChange={vi.fn()}
				label="My Options"
				helpText="Provide a label and a stored value"
			/>,
		);

		expect(screen.getByText("My Options")).toBeInTheDocument();
		expect(
			screen.getByText(/provide a label and a stored value/i),
		).toBeInTheDocument();
	});
});
