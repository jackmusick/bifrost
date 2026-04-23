import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import type { components } from "@/lib/v1";

import { NeedsReviewCard } from "./NeedsReviewCard";

type AgentRun = components["schemas"]["AgentRunResponse"];

const baseRun: AgentRun = {
	id: "00000000-0000-0000-0000-000000000001",
	agent_id: "00000000-0000-0000-0000-000000000002",
	agent_name: "Tier-1 Triage",
	trigger_type: "test",
	summary_status: "completed",
	status: "completed",
	iterations_used: 1,
	tokens_used: 100,
	asked: "Why was the ticket closed?",
	did: "Closed as duplicate",
	input: { message: "help" },
	output: { text: "ok" },
	verdict: "down",
	verdict_note: "Should not have closed — agent missed escalation flag.",
	duration_ms: 2500,
	created_at: "2026-04-21T10:00:00Z",
	started_at: "2026-04-21T10:00:00Z",
	metadata: {},
};

describe("NeedsReviewCard", () => {
	it("renders the asked text", () => {
		renderWithProviders(<NeedsReviewCard run={baseRun} />);
		expect(
			screen.getByText(/why was the ticket closed/i),
		).toBeInTheDocument();
	});

	it("renders the Flagged badge", () => {
		renderWithProviders(<NeedsReviewCard run={baseRun} />);
		expect(screen.getByText(/flagged/i)).toBeInTheDocument();
	});

	it("prefers verdict_note over did when present", () => {
		renderWithProviders(<NeedsReviewCard run={baseRun} />);
		expect(
			screen.getByText(/should not have closed/i),
		).toBeInTheDocument();
		expect(
			screen.queryByText(/closed as duplicate/i),
		).not.toBeInTheDocument();
	});

	it("falls back to did when verdict_note is missing", () => {
		renderWithProviders(
			<NeedsReviewCard
				run={{ ...baseRun, verdict_note: null }}
			/>,
		);
		expect(screen.getByText(/closed as duplicate/i)).toBeInTheDocument();
	});

	it("calls onOpen when clicked", async () => {
		const onOpen = vi.fn();
		const { user } = renderWithProviders(
			<NeedsReviewCard run={baseRun} onOpen={onOpen} />,
		);
		await user.click(
			screen.getByRole("button", { name: /why was the ticket closed/i }),
		);
		expect(onOpen).toHaveBeenCalled();
	});

	it("is keyboard activatable when onOpen is provided", async () => {
		const onOpen = vi.fn();
		const { user } = renderWithProviders(
			<NeedsReviewCard run={baseRun} onOpen={onOpen} />,
		);
		const card = screen.getByRole("button", {
			name: /why was the ticket closed/i,
		});
		card.focus();
		await user.keyboard("{Enter}");
		expect(onOpen).toHaveBeenCalled();
	});
});
