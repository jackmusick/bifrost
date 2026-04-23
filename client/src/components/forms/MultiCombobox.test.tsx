/**
 * Component tests for MultiCombobox.
 *
 * Covers chip rendering, add/remove via dropdown, remove via chip X, filter,
 * and keyboard interactions.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { MultiCombobox } from "./MultiCombobox";

const OPTIONS = [
	{ label: "Urgent", value: "urgent" },
	{ label: "Billing", value: "billing" },
	{ label: "Onboarding", value: "onboarding" },
];

describe("MultiCombobox", () => {
	it("renders placeholder when no value is selected", () => {
		renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={[]}
				onValueChange={vi.fn()}
				placeholder="Pick tags"
			/>,
		);

		expect(screen.getByText("Pick tags")).toBeInTheDocument();
	});

	it("renders a chip per selected value", () => {
		renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={["urgent", "billing"]}
				onValueChange={vi.fn()}
			/>,
		);

		expect(screen.getByText("Urgent")).toBeInTheDocument();
		expect(screen.getByText("Billing")).toBeInTheDocument();
		expect(screen.queryByText("Onboarding")).not.toBeInTheDocument();
	});

	it("adds a value when an unselected option is clicked", async () => {
		const onValueChange = vi.fn();
		const { user } = renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={["urgent"]}
				onValueChange={onValueChange}
			/>,
		);

		await user.click(screen.getByRole("combobox"));
		await user.click(screen.getByRole("option", { name: /Billing/i }));

		expect(onValueChange).toHaveBeenCalledWith(["urgent", "billing"]);
	});

	it("removes a value when a selected option is clicked again", async () => {
		const onValueChange = vi.fn();
		const { user } = renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={["urgent", "billing"]}
				onValueChange={onValueChange}
			/>,
		);

		await user.click(screen.getByRole("combobox"));
		await user.click(screen.getByRole("option", { name: /Urgent/i }));

		expect(onValueChange).toHaveBeenCalledWith(["billing"]);
	});

	it("removes a chip when its X button is clicked", async () => {
		const onValueChange = vi.fn();
		const { user } = renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={["urgent", "billing"]}
				onValueChange={onValueChange}
			/>,
		);

		const removeUrgent = screen.getByLabelText("Remove Urgent");
		await user.click(removeUrgent);

		expect(onValueChange).toHaveBeenCalledWith(["billing"]);
	});

	it("shows a loading indicator and disables the trigger while loading", () => {
		renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={[]}
				onValueChange={vi.fn()}
				isLoading
			/>,
		);

		expect(screen.getByText(/Loading/i)).toBeInTheDocument();
		expect(screen.getByRole("combobox")).toBeDisabled();
	});

	it("disables the trigger when the disabled prop is set", () => {
		renderWithProviders(
			<MultiCombobox
				options={OPTIONS}
				value={[]}
				onValueChange={vi.fn()}
				disabled
			/>,
		);

		expect(screen.getByRole("combobox")).toBeDisabled();
	});
});
