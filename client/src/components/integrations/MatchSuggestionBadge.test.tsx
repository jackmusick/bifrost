/**
 * Component tests for MatchSuggestionBadge.
 *
 * Covers the label/score rendering and accept/reject click wiring.
 */

import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { MatchSuggestionBadge } from "./MatchSuggestionBadge";

function renderBadge(
	suggestionOverrides: Partial<
		Parameters<typeof MatchSuggestionBadge>[0]["suggestion"]
	> = {},
	disabled = false,
) {
	const onAccept = vi.fn();
	const onReject = vi.fn();
	const utils = renderWithProviders(
		<MatchSuggestionBadge
			suggestion={{
				organizationId: "org-1",
				organizationName: "Acme",
				entityId: "ent-1",
				entityName: "Acme Corp",
				score: 92,
				matchType: "exact",
				...suggestionOverrides,
			}}
			onAccept={onAccept}
			onReject={onReject}
			disabled={disabled}
		/>,
	);
	return { ...utils, onAccept, onReject };
}

describe("MatchSuggestionBadge", () => {
	it("renders the entity name and confidence score", () => {
		renderBadge();
		expect(screen.getByText("Acme Corp")).toBeInTheDocument();
		expect(screen.getByText(/\(92%\)/)).toBeInTheDocument();
	});

	it("calls onAccept when the accept button is clicked", async () => {
		const { user, onAccept } = renderBadge();
		await user.click(
			screen.getByRole("button", { name: /accept suggestion/i }),
		);
		expect(onAccept).toHaveBeenCalledTimes(1);
	});

	it("calls onReject when the reject button is clicked", async () => {
		const { user, onReject } = renderBadge();
		await user.click(
			screen.getByRole("button", { name: /reject suggestion/i }),
		);
		expect(onReject).toHaveBeenCalledTimes(1);
	});

	it("disables both action buttons when disabled=true", () => {
		renderBadge({}, true);
		expect(
			screen.getByRole("button", { name: /accept suggestion/i }),
		).toBeDisabled();
		expect(
			screen.getByRole("button", { name: /reject suggestion/i }),
		).toBeDisabled();
	});
});
