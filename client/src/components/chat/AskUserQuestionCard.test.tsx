/**
 * Component tests for AskUserQuestionCard.
 *
 * Covers:
 *   - Submit is disabled until an option is picked (validation)
 *   - Single-select: choosing an option enables submit and onSubmit receives
 *     the label
 *   - "Other" radio reveals a text input; typing into it enables submit and
 *     the typed text becomes the answer
 *   - onCancel fires from the Cancel button
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, fireEvent } from "@/test-utils";
import { AskUserQuestionCard } from "./AskUserQuestionCard";
import type { AskUserQuestion } from "@/services/websocket";

function makeQuestion(overrides: Partial<AskUserQuestion> = {}): AskUserQuestion {
	return {
		question: "Pick one",
		header: "PICK",
		options: [
			{ label: "Option A", description: "" },
			{ label: "Option B", description: "with description" },
		],
		multi_select: false,
		...overrides,
	};
}

describe("AskUserQuestionCard — validation", () => {
	it("disables Submit until an option is selected", () => {
		renderWithProviders(
			<AskUserQuestionCard
				questions={[makeQuestion()]}
				onSubmit={vi.fn()}
				onCancel={vi.fn()}
			/>,
		);
		expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
	});
});

describe("AskUserQuestionCard — single-select", () => {
	it("enables Submit once an option is chosen and sends the label", async () => {
		const onSubmit = vi.fn();
		const { user } = renderWithProviders(
			<AskUserQuestionCard
				questions={[makeQuestion()]}
				onSubmit={onSubmit}
				onCancel={vi.fn()}
			/>,
		);

		await user.click(screen.getByLabelText("Option B"));

		const submit = screen.getByRole("button", { name: /submit/i });
		expect(submit).toBeEnabled();
		await user.click(submit);

		expect(onSubmit).toHaveBeenCalledWith({ "Pick one": "Option B" });
	});

	it("'Other' radio reveals a text input and submits the typed text", async () => {
		const onSubmit = vi.fn();
		const { user } = renderWithProviders(
			<AskUserQuestionCard
				questions={[makeQuestion()]}
				onSubmit={onSubmit}
				onCancel={vi.fn()}
			/>,
		);

		await user.click(screen.getByLabelText("Other"));

		const otherInput = screen.getByPlaceholderText(/enter your response/i);
		fireEvent.change(otherInput, {
			target: { value: "some custom answer" },
		});

		const submit = screen.getByRole("button", { name: /submit/i });
		expect(submit).toBeEnabled();
		await user.click(submit);

		expect(onSubmit).toHaveBeenCalledWith({
			"Pick one": "some custom answer",
		});
	});
});

describe("AskUserQuestionCard — cancel", () => {
	it("fires onCancel when Cancel is clicked", async () => {
		const onCancel = vi.fn();
		const { user } = renderWithProviders(
			<AskUserQuestionCard
				questions={[makeQuestion()]}
				onSubmit={vi.fn()}
				onCancel={onCancel}
			/>,
		);

		await user.click(screen.getByRole("button", { name: /cancel/i }));
		expect(onCancel).toHaveBeenCalledTimes(1);
	});
});

describe("AskUserQuestionCard — multi-select", () => {
	it("combines checkbox selections with 'Other' text on submit", async () => {
		const onSubmit = vi.fn();
		const { user } = renderWithProviders(
			<AskUserQuestionCard
				questions={[makeQuestion({ multi_select: true })]}
				onSubmit={onSubmit}
				onCancel={vi.fn()}
			/>,
		);

		await user.click(screen.getByLabelText("Option A"));
		await user.click(screen.getByLabelText("Other"));

		const otherInput = screen.getByPlaceholderText(/enter your response/i);
		fireEvent.change(otherInput, { target: { value: "C" } });

		await user.click(screen.getByRole("button", { name: /submit/i }));

		expect(onSubmit).toHaveBeenCalledWith({ "Pick one": "Option A, C" });
	});
});
