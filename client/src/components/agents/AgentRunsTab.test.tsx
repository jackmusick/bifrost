/**
 * Tests for AgentRunsTab.
 *
 * Mocks the agent-runs hooks at module scope. RunReviewSheet is stubbed
 * to a thin probe so we can assert that clicking a card opens it without
 * pulling in the entire shadcn Sheet machinery.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// -----------------------------------------------------------------------------
// Mocks
// -----------------------------------------------------------------------------

const mockUseAgentRuns = vi.fn();
const mockUseAgentRun = vi.fn();
const mockUseFlagConversation = vi.fn();
const mockSendFlagMessage = vi.fn();
const mockSetVerdict = vi.fn();
const mockClearVerdict = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useAgentRuns: (params: unknown) => mockUseAgentRuns(params),
	useAgentRun: (id: string | undefined) => mockUseAgentRun(id),
	useFlagConversation: (id: string | undefined) =>
		mockUseFlagConversation(id),
	useSendFlagMessage: () => ({
		mutate: mockSendFlagMessage,
		isPending: false,
	}),
	useSetVerdict: () => ({ mutate: mockSetVerdict, isPending: false }),
	useClearVerdict: () => ({ mutate: mockClearVerdict, isPending: false }),
}));

// Stub the RunReviewSheet so we don't need a real Sheet portal in jsdom.
vi.mock("./RunReviewSheet", () => ({
	RunReviewSheet: ({
		open,
		run,
	}: {
		open: boolean;
		run: { id?: string } | null;
	}) =>
		open ? (
			<div data-testid="run-sheet" data-run-id={run?.id ?? ""}>
				sheet open
			</div>
		) : null,
}));

// -----------------------------------------------------------------------------
// Fixtures
// -----------------------------------------------------------------------------

function makeRun(overrides: Record<string, unknown> = {}) {
	return {
		id: "run-1",
		agent_id: "agent-1",
		agent_name: "Triage",
		trigger_type: "test",
		status: "completed",
		iterations_used: 1,
		tokens_used: 1000,
		asked: "How do I reset my password?",
		did: "Routed to Support",
		input: {},
		output: {},
		verdict: null,
		verdict_note: null,
		duration_ms: 1500,
		created_at: "2026-04-20T00:00:00Z",
		started_at: "2026-04-20T00:00:00Z",
		metadata: {},
		...overrides,
	};
}

beforeEach(() => {
	mockUseAgentRuns.mockReturnValue({
		data: { items: [makeRun()], total: 1, next_cursor: null },
		isLoading: false,
	});
	mockUseAgentRun.mockReturnValue({ data: undefined });
	mockUseFlagConversation.mockReturnValue({ data: undefined });
	mockSendFlagMessage.mockReset();
	mockSetVerdict.mockReset();
	mockClearVerdict.mockReset();
});

async function renderTab(agentId = "agent-1") {
	const { AgentRunsTab } = await import("./AgentRunsTab");
	return renderWithProviders(<AgentRunsTab agentId={agentId} />);
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe("AgentRunsTab — list", () => {
	it("renders run cards from the runs hook", async () => {
		await renderTab();
		expect(
			screen.getByText(/how do i reset my password/i),
		).toBeInTheDocument();
	});

	it("shows an empty message when the list is empty", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: { items: [], total: 0, next_cursor: null },
			isLoading: false,
		});
		await renderTab();
		expect(
			screen.getByText(/no runs match this filter/i),
		).toBeInTheDocument();
	});

	it("renders skeletons while loading", async () => {
		mockUseAgentRuns.mockReturnValue({ data: undefined, isLoading: true });
		const { container } = await renderTab();
		expect(
			container.querySelectorAll(".animate-pulse").length,
		).toBeGreaterThan(0);
	});
});

describe("AgentRunsTab — search", () => {
	it("passes the search query to useAgentRuns", async () => {
		const { user } = await renderTab();
		await user.type(screen.getByLabelText(/search runs/i), "acme");
		await waitFor(() => {
			expect(mockUseAgentRuns).toHaveBeenCalledWith(
				expect.objectContaining({ q: "acme" }),
			);
		});
	});
});

describe("AgentRunsTab — verdict actions", () => {
	it("calls useSetVerdict mutate when a 👍 toggle is clicked", async () => {
		const { user } = await renderTab();
		await user.click(
			screen.getByRole("button", { name: /mark as good/i }),
		);
		await waitFor(() => {
			expect(mockSetVerdict).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { run_id: "run-1" } },
					body: { verdict: "up" },
				}),
				expect.any(Object),
			);
		});
	});

	it("calls useClearVerdict mutate when toggling off the current verdict", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: {
				items: [makeRun({ verdict: "up" })],
				total: 1,
				next_cursor: null,
			},
			isLoading: false,
		});
		const { user } = await renderTab();
		await user.click(
			screen.getByRole("button", { name: /mark as good/i }),
		);
		await waitFor(() => {
			expect(mockClearVerdict).toHaveBeenCalled();
		});
	});

	it("renders the queue banner when there are flagged runs", async () => {
		mockUseAgentRuns.mockReturnValue({
			data: {
				items: [makeRun({ verdict: "down" })],
				total: 1,
				next_cursor: null,
			},
			isLoading: false,
		});
		await renderTab();
		expect(
			screen.getByText(/1 flagged run in tuning queue/i),
		).toBeInTheDocument();
	});
});

describe("AgentRunsTab — sheet open", () => {
	it("opens the RunReviewSheet stub when a card is clicked", async () => {
		// useAgentRun resolves the detail for the opened run id; return one
		// so the sheet stub gets a non-null `run` prop with the expected id.
		mockUseAgentRun.mockReturnValue({
			data: makeRun({ id: "run-1" }),
		});
		const { user } = await renderTab();
		// The card itself is a button with the asked text as its name
		await user.click(
			screen.getByRole("button", { name: /how do i reset/i }),
		);
		const sheet = await screen.findByTestId("run-sheet");
		expect(sheet).toHaveAttribute("data-run-id", "run-1");
	});
});
