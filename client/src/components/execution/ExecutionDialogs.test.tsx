/**
 * Component tests for ExecutionCancelDialog and ExecutionRerunDialog.
 *
 * Both dialogs are tiny alert-dialog wrappers. We assert they render the
 * workflow name, that confirm triggers the callback, and for rerun that
 * the isRerunning flag disables both buttons and swaps label.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import {
	ExecutionCancelDialog,
	ExecutionRerunDialog,
} from "./ExecutionDialogs";

describe("ExecutionCancelDialog", () => {
	it("renders the workflow name in the description", () => {
		renderWithProviders(
			<ExecutionCancelDialog
				open={true}
				onOpenChange={vi.fn()}
				workflowName="send_emails"
				onConfirm={vi.fn()}
			/>,
		);
		expect(screen.getByText("send_emails")).toBeInTheDocument();
		expect(
			screen.getByRole("heading", { name: /cancel execution/i }),
		).toBeInTheDocument();
	});

	it("calls onConfirm when the confirm action is clicked", async () => {
		const onConfirm = vi.fn();
		const { user } = renderWithProviders(
			<ExecutionCancelDialog
				open={true}
				onOpenChange={vi.fn()}
				workflowName="x"
				onConfirm={onConfirm}
			/>,
		);
		await user.click(
			screen.getByRole("button", { name: /yes, cancel execution/i }),
		);
		expect(onConfirm).toHaveBeenCalledTimes(1);
	});

	it("renders nothing when open is false", () => {
		renderWithProviders(
			<ExecutionCancelDialog
				open={false}
				onOpenChange={vi.fn()}
				workflowName="x"
				onConfirm={vi.fn()}
			/>,
		);
		expect(
			screen.queryByRole("heading", { name: /cancel execution/i }),
		).not.toBeInTheDocument();
	});
});

describe("ExecutionRerunDialog", () => {
	it("calls onConfirm when the confirm action is clicked", async () => {
		const onConfirm = vi.fn();
		const { user } = renderWithProviders(
			<ExecutionRerunDialog
				open={true}
				onOpenChange={vi.fn()}
				workflowName="x"
				isRerunning={false}
				onConfirm={onConfirm}
			/>,
		);
		await user.click(
			screen.getByRole("button", { name: /yes, rerun workflow/i }),
		);
		expect(onConfirm).toHaveBeenCalledTimes(1);
	});

	it("disables both buttons and shows 'Rerunning...' while isRerunning", () => {
		renderWithProviders(
			<ExecutionRerunDialog
				open={true}
				onOpenChange={vi.fn()}
				workflowName="x"
				isRerunning={true}
				onConfirm={vi.fn()}
			/>,
		);
		expect(screen.getByText(/rerunning\.\.\./i)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
		expect(
			screen.getByRole("button", { name: /rerunning/i }),
		).toBeDisabled();
	});
});
