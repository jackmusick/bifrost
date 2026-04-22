/**
 * Tests for AgentTunePage.
 *
 * Mocks the tuning + agent + runs hooks at module scope. Verifies the
 * sidebar lists flagged runs, the propose / apply / dry-run flow calls
 * the right mutations, and that apply navigates back to the agent page.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { Routes, Route, useLocation } from "react-router-dom";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// -----------------------------------------------------------------------------
// Mocks
// -----------------------------------------------------------------------------

const mockUseAgentRuns = vi.fn();
const mockUseAgent = vi.fn();
const mockTuningSession = vi.fn();
const mockTuningDryRun = vi.fn();
const mockApplyTuning = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useAgentRuns: (params: unknown) => mockUseAgentRuns(params),
}));

vi.mock("@/hooks/useAgents", () => ({
	useAgent: (id: string | undefined) => mockUseAgent(id),
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
	useApplyTuning: () => ({
		mutate: mockApplyTuning,
		isPending: false,
	}),
}));

vi.mock("sonner", () => ({
	toast: {
		success: vi.fn(),
		error: vi.fn(),
	},
}));

// -----------------------------------------------------------------------------
// Fixtures
// -----------------------------------------------------------------------------

function makeRun(id: string, overrides: Record<string, unknown> = {}) {
	return {
		id,
		agent_id: "agent-1",
		agent_name: "Triage",
		trigger_type: "test",
		status: "completed",
		iterations_used: 1,
		tokens_used: 1000,
		duration_ms: 1000,
		asked: `asked-${id}`,
		did: `did-${id}`,
		input: {},
		output: {},
		verdict: "down",
		verdict_note: `note-${id}`,
		created_at: "2026-04-20T00:00:00Z",
		started_at: "2026-04-20T00:00:00Z",
		metadata: {},
		...overrides,
	};
}

const baseAgent = {
	id: "agent-1",
	name: "Tier-1 Triage",
	system_prompt: "You are a helpful triage agent.",
};

const sampleProposal = {
	summary: "Tighten routing rules for password resets.",
	proposed_prompt: "You are a helpful triage agent. Always X.",
	affected_run_ids: ["a", "b"],
};

const sampleDryRun = {
	results: [
		{
			run_id: "a",
			would_still_decide_same: false,
			reasoning: "Now routes to Support",
			confidence: 0.9,
		},
		{
			run_id: "b",
			would_still_decide_same: true,
			reasoning: "Still answers itself",
			confidence: 0.7,
		},
	],
};

beforeEach(() => {
	mockUseAgentRuns.mockReturnValue({
		data: { items: [makeRun("a"), makeRun("b")], total: 2, next_cursor: null },
		isLoading: false,
	});
	mockUseAgent.mockReturnValue({ data: baseAgent });
	mockTuningSession.mockReset();
	mockTuningDryRun.mockReset();
	mockApplyTuning.mockReset();
	// Default: invoke onSuccess with sample data so proposal renders.
	mockTuningSession.mockImplementation((_args, opts) => {
		opts?.onSuccess?.(sampleProposal);
	});
	mockTuningDryRun.mockImplementation((_args, opts) => {
		opts?.onSuccess?.(sampleDryRun);
	});
	mockApplyTuning.mockImplementation((_args, opts) => {
		opts?.onSuccess?.({ agent_id: "agent-1", history_id: "h-1", affected_run_ids: ["a", "b"] });
	});
});

async function renderPage(path = "/agents/agent-1/tune") {
	const { AgentTunePage } = await import("./AgentTunePage");
	function LocationProbe() {
		const loc = useLocation();
		return <div data-testid="location">{loc.pathname}</div>;
	}
	return renderWithProviders(
		<Routes>
			<Route
				path="/agents/:id/tune"
				element={
					<>
						<AgentTunePage />
						<LocationProbe />
					</>
				}
			/>
			<Route path="/agents/:id" element={<LocationProbe />} />
		</Routes>,
		{ initialEntries: [path] },
	);
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe("AgentTunePage — sidebar", () => {
	it("renders flagged runs in the sidebar", async () => {
		await renderPage();
		const list = screen.getByTestId("flagged-list");
		expect(list).toHaveTextContent("asked-a");
		expect(list).toHaveTextContent("asked-b");
	});

	it("renders the empty state when no runs are flagged", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByText(/no flagged runs/i)).toBeInTheDocument();
	});

	it("renders the agent's current prompt", async () => {
		await renderPage();
		expect(
			screen.getByText(/you are a helpful triage agent/i),
		).toBeInTheDocument();
	});
});

describe("AgentTunePage — propose flow", () => {
	it("calls useTuningSession when Propose is clicked", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("propose-button"));
		await waitFor(() => {
			expect(mockTuningSession).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
				}),
				expect.any(Object),
			);
		});
	});

	it("renders the proposal card after a successful propose", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("propose-button"));
		await waitFor(() => {
			expect(screen.getByTestId("proposal-card")).toBeInTheDocument();
		});
		expect(screen.getByTestId("proposal-after")).toHaveTextContent(
			/always x/i,
		);
	});

	it("disables the propose button when there are no flagged runs", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByTestId("propose-button")).toBeDisabled();
	});
});

describe("AgentTunePage — dry-run + apply", () => {
	async function openProposal() {
		const result = await renderPage();
		await result.user.click(screen.getByTestId("propose-button"));
		await screen.findByTestId("proposal-card");
		return result;
	}

	it("calls useTuningDryRun when dry-run is clicked", async () => {
		const { user } = await openProposal();
		await user.click(screen.getByTestId("dryrun-button"));
		await waitFor(() => {
			expect(mockTuningDryRun).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
					body: {
						proposed_prompt: sampleProposal.proposed_prompt,
					},
				}),
				expect.any(Object),
			);
		});
		await waitFor(() => {
			expect(screen.getByTestId("dryrun-card")).toBeInTheDocument();
		});
	});

	it("calls useApplyTuning and navigates back to the agent page on apply", async () => {
		const { user } = await openProposal();
		await user.click(screen.getByTestId("apply-button"));
		await waitFor(() => {
			expect(mockApplyTuning).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { agent_id: "agent-1" } },
					body: {
						new_prompt: sampleProposal.proposed_prompt,
					},
				}),
				expect.any(Object),
			);
		});
		await waitFor(() => {
			expect(screen.getByTestId("location")).toHaveTextContent(
				"/agents/agent-1",
			);
		});
	});
});
