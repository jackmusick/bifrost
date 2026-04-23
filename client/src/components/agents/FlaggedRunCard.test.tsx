import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { FlaggedRunCard } from "./FlaggedRunCard";

const mockUseAgentRun = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useAgentRun: (id: string | undefined) => mockUseAgentRun(id),
}));

const runReviewPanelProps = vi.fn();

vi.mock("./RunReviewPanel", () => ({
	RunReviewPanel: (props: unknown) => {
		runReviewPanelProps(props);
		return <div data-testid="run-review-panel">panel</div>;
	},
}));

const baseRun = {
	id: "run-1",
	agent_id: "agent-1",
	agent_name: "Triage",
	status: "completed",
	asked: "Send a test event",
	did: "Sent webhook",
	verdict: "down",
	verdict_note: "Responded with a little more happiness",
	trigger_type: "manual",
	iterations_used: 1,
	tokens_used: 100,
	duration_ms: 500,
	started_at: "2026-04-20T00:00:00Z",
};

beforeEach(() => {
	mockUseAgentRun.mockReturnValue({ data: baseRun, isLoading: false });
	runReviewPanelProps.mockClear();
});

describe("FlaggedRunCard", () => {
	it("renders collapsed by default with title and verdict note", () => {
		renderWithProviders(<FlaggedRunCard run={baseRun as never} />);
		expect(screen.getByText(/send a test event/i)).toBeInTheDocument();
		expect(
			screen.getByText(/responded with a little more happiness/i),
		).toBeInTheDocument();
		expect(screen.queryByTestId("run-review-panel")).toBeNull();
	});

	it("expands to show the transcript when the header is clicked", async () => {
		const { user } = renderWithProviders(
			<FlaggedRunCard run={baseRun as never} />,
		);
		await user.click(screen.getByTestId("flagged-run-toggle"));
		expect(screen.getByTestId("run-review-panel")).toBeInTheDocument();
		expect(runReviewPanelProps).toHaveBeenCalledWith(
			expect.objectContaining({
				variant: "drawer",
				hideVerdictBar: true,
			}),
		);
	});

	it("collapses again on a second click", async () => {
		const { user } = renderWithProviders(
			<FlaggedRunCard run={baseRun as never} />,
		);
		const toggle = screen.getByTestId("flagged-run-toggle");
		await user.click(toggle);
		expect(screen.getByTestId("run-review-panel")).toBeInTheDocument();
		await user.click(toggle);
		expect(screen.queryByTestId("run-review-panel")).toBeNull();
	});
});
