/**
 * Component tests for AutoMatchControls.
 *
 * Covers the three user-visible flows:
 *   - switching match mode between Exact and Fuzzy
 *   - kicking off auto-match with the currently selected mode
 *   - Accept-all / Clear affordances when suggestions exist
 *
 * No hook mocks required — this component is purely callback-driven.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { AutoMatchControls } from "./AutoMatchControls";

function renderControls(overrides: Partial<Parameters<typeof AutoMatchControls>[0]> = {}) {
	const onRunAutoMatch = vi.fn();
	const onAcceptAll = vi.fn();
	const onClear = vi.fn();
	const utils = renderWithProviders(
		<AutoMatchControls
			onRunAutoMatch={onRunAutoMatch}
			onAcceptAll={onAcceptAll}
			onClear={onClear}
			matchStats={null}
			hasSuggestions={false}
			isMatching={false}
			{...overrides}
		/>,
	);
	return { ...utils, onRunAutoMatch, onAcceptAll, onClear };
}

describe("AutoMatchControls — default state", () => {
	it("fires onRunAutoMatch with the default 'exact' mode", async () => {
		const { user, onRunAutoMatch } = renderControls();

		await user.click(
			screen.getByRole("button", { name: /auto-match unmapped/i }),
		);

		expect(onRunAutoMatch).toHaveBeenCalledWith("exact");
	});

	it("passes the newly selected mode through when the user switches to Fuzzy", async () => {
		const { user, onRunAutoMatch } = renderControls();

		await user.click(screen.getByRole("radio", { name: /fuzzy/i }));
		await user.click(
			screen.getByRole("button", { name: /auto-match unmapped/i }),
		);

		expect(onRunAutoMatch).toHaveBeenCalledWith("fuzzy");
	});

	it("disables the AI toggle until it's supported", () => {
		renderControls();
		expect(screen.getByRole("radio", { name: /ai/i })).toBeDisabled();
	});

	it("shows 'Matching...' and disables the button while isMatching is true", () => {
		renderControls({ isMatching: true });
		const btn = screen.getByRole("button", { name: /matching/i });
		expect(btn).toBeDisabled();
	});
});

describe("AutoMatchControls — has suggestions", () => {
	it("swaps in Accept All + Clear when suggestions are present", async () => {
		const { user, onAcceptAll, onClear } = renderControls({
			hasSuggestions: true,
			matchStats: {
				total: 5,
				matched: 3,
				highConfidence: 2,
				lowConfidence: 1,
			},
		});

		const acceptBtn = screen.getByRole("button", { name: /accept all \(3\)/i });
		await user.click(acceptBtn);
		expect(onAcceptAll).toHaveBeenCalledTimes(1);

		// Clear button is icon-only — it's the other button in the group.
		const allButtons = screen.getAllByRole("button");
		const clearBtn = allButtons.find((b) => b !== acceptBtn);
		expect(clearBtn).toBeDefined();
		await user.click(clearBtn!);
		expect(onClear).toHaveBeenCalledTimes(1);
	});

	it("falls back to 0 in the Accept All label when matchStats is null", () => {
		renderControls({ hasSuggestions: true, matchStats: null });
		expect(
			screen.getByRole("button", { name: /accept all \(0\)/i }),
		).toBeInTheDocument();
	});
});
