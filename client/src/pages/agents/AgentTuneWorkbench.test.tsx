import { describe, it, expect, vi, beforeEach } from "vitest";
import { Routes, Route } from "react-router-dom";

import { renderWithProviders, screen } from "@/test-utils";

const mockUseAgent = vi.fn();
const mockUseAgentRuns = vi.fn();
const mockUseAgentStats = vi.fn();
const mockTuningSession = vi.fn();
const mockTuningDryRun = vi.fn();
const mockApplyTuning = vi.fn();

vi.mock("@/hooks/useAgents", () => ({
	useAgent: (id: string | undefined) => mockUseAgent(id),
}));

vi.mock("@/services/agentRuns", () => ({
	useAgentRuns: (params: unknown) => mockUseAgentRuns(params),
	useAgentRun: () => ({ data: null, isLoading: false }),
}));

vi.mock("@/services/agents", () => ({
	useAgentStats: (id: string | undefined) => mockUseAgentStats(id),
}));

vi.mock("@/services/agentTuning", () => ({
	useTuningSession: () => ({
		mutate: mockTuningSession,
		isPending: false,
	}),
	useTuningDryRun: () => ({
		mutate: mockTuningDryRun,
		isPending: false,
	}),
	useApplyTuning: () => ({ mutate: mockApplyTuning, isPending: false }),
}));

vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

const baseAgent = {
	id: "agent-1",
	name: "Test Parent Agent",
	system_prompt: "You are a helpful triage agent.",
};

const baseStats = {
	agent_id: "agent-1",
	runs_7d: 47,
	success_rate: 0.92,
	avg_duration_ms: 1200,
	total_cost_7d: "0.42",
	last_run_at: "2026-04-22T00:00:00Z",
	runs_by_day: [],
	needs_review: 2,
	unreviewed: 2,
};

function makeRun(id: string) {
	return {
		id,
		agent_id: "agent-1",
		agent_name: "Triage",
		trigger_type: "manual",
		status: "completed",
		iterations_used: 1,
		tokens_used: 100,
		duration_ms: 500,
		asked: `asked-${id}`,
		did: `did-${id}`,
		input: {},
		output: {},
		verdict: "down",
		verdict_note: `note-${id}`,
		created_at: "2026-04-20T00:00:00Z",
		started_at: "2026-04-20T00:00:00Z",
		metadata: {},
	};
}

beforeEach(() => {
	mockUseAgent.mockReturnValue({ data: baseAgent });
	mockUseAgentRuns.mockReturnValue({
		data: { items: [makeRun("a"), makeRun("b")], total: 2, next_cursor: null },
		isLoading: false,
	});
	mockUseAgentStats.mockReturnValue({ data: baseStats, isLoading: false });
	mockTuningSession.mockReset();
	mockTuningDryRun.mockReset();
	mockApplyTuning.mockReset();
});

async function renderPage() {
	const { AgentTuneWorkbench } = await import("./AgentTuneWorkbench");
	return renderWithProviders(
		<Routes>
			<Route path="/agents/:id/tune" element={<AgentTuneWorkbench />} />
			<Route path="/agents/:id" element={<div>agent page</div>} />
		</Routes>,
		{ initialEntries: ["/agents/agent-1/tune"] },
	);
}

describe("AgentTuneWorkbench — shell", () => {
	it("renders the header, stat strip, and three panes", async () => {
		await renderPage();

		expect(
			screen.getByRole("heading", { name: /tune agent/i }),
		).toBeInTheDocument();
		expect(screen.getByText("Flagged runs")).toBeInTheDocument();
		expect(screen.getByText("Runs (7d)")).toBeInTheDocument();
		expect(screen.getByText("47")).toBeInTheDocument();

		expect(screen.getByTestId("tune-pane-flagged")).toBeInTheDocument();
		expect(screen.getByTestId("tune-pane-editor")).toBeInTheDocument();
		expect(screen.getByTestId("tune-pane-impact")).toBeInTheDocument();
	});

	it("lists flagged runs in the left pane", async () => {
		await renderPage();
		const pane = screen.getByTestId("tune-pane-flagged");
		expect(pane).toHaveTextContent("asked-a");
		expect(pane).toHaveTextContent("asked-b");
	});

	it("disables Generate proposal when there are no flagged runs", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByTestId("generate-proposal-button")).toBeDisabled();
	});

	it("enables Generate proposal when there are flagged runs", async () => {
		await renderPage();
		expect(screen.getByTestId("generate-proposal-button")).toBeEnabled();
	});

	it("renders the empty-state CTA in the editor pane when no proposal exists", async () => {
		await renderPage();
		expect(
			screen.getByTestId("editor-empty-generate-button"),
		).toBeInTheDocument();
	});

	it("renders a before-dry-run card in the impact pane with the button disabled", async () => {
		await renderPage();
		const pane = screen.getByTestId("tune-pane-impact");
		expect(pane).toHaveTextContent(/simulate the proposed prompt/i);
		expect(screen.getByTestId("dryrun-button")).toBeDisabled();
	});
});
