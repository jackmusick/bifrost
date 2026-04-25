/**
 * Tests for AgentRunDetailPage.
 *
 * Mocks the run + agent + tuning hooks at module scope. RunReviewPanel and
 * FlagConversation are stubbed to thin probes — they have their own tests.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { Routes, Route } from "react-router-dom";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// -----------------------------------------------------------------------------
// Mocks
// -----------------------------------------------------------------------------

const mockUseAgentRun = vi.fn();
const mockUseFlagConversation = vi.fn();
const mockSendFlagMessage = vi.fn();
const mockSetVerdict = vi.fn();
const mockClearVerdict = vi.fn();
const mockRegenSummary = vi.fn();
const mockRerun = vi.fn();

vi.mock("@/services/agentRuns", () => ({
	useAgentRun: (id: string | undefined) => mockUseAgentRun(id),
	useFlagConversation: (id: string | undefined) =>
		mockUseFlagConversation(id),
	useSendFlagMessage: () => ({
		mutate: mockSendFlagMessage,
		isPending: false,
	}),
	useSetVerdict: () => ({ mutate: mockSetVerdict, isPending: false }),
	useClearVerdict: () => ({ mutate: mockClearVerdict, isPending: false }),
	useRegenerateSummary: () => ({
		mutate: mockRegenSummary,
		isPending: false,
	}),
	useRerunAgentRun: () => ({
		mutate: mockRerun,
		isPending: false,
	}),
}));

const mockUseAgent = vi.fn();
vi.mock("@/hooks/useAgents", () => ({
	useAgent: (id: string | undefined) => mockUseAgent(id),
}));

vi.mock("@/hooks/useAgentRunUpdates", () => ({
	useAgentRunUpdates: () => {},
}));

const mockAuth = vi.fn();
vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => mockAuth(),
}));

// Stub heavy children
vi.mock("@/components/agents/RunReviewPanel", () => ({
	RunReviewPanel: ({
		run,
		verdict,
		onVerdict,
	}: {
		run: { id: string };
		verdict: string | null;
		onVerdict: (v: string | null) => void;
	}) => (
		<div data-testid="run-review-panel" data-run-id={run.id}>
			<span data-testid="verdict-label">{verdict ?? "none"}</span>
			<button
				type="button"
				onClick={() => onVerdict("up")}
				data-testid="set-up"
			>
				up
			</button>
			<button
				type="button"
				onClick={() => onVerdict("down")}
				data-testid="set-down"
			>
				down
			</button>
			<button
				type="button"
				onClick={() => onVerdict(null)}
				data-testid="clear-verdict"
			>
				clear
			</button>
		</div>
	),
}));

vi.mock("@/components/agents/FlagConversation", () => ({
	FlagConversation: ({
		conversation,
	}: {
		conversation: { id: string } | null;
	}) => (
		<div data-testid="flag-conversation">
			conv-{conversation?.id ?? "none"}
		</div>
	),
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
		iterations_used: 3,
		tokens_used: 5000,
		duration_ms: 1500,
		llm_model: "claude-opus-4-7",
		asked: "Reset password please",
		did: "Routed to Support",
		started_at: "2026-04-20T12:34:56Z",
		created_at: "2026-04-20T12:34:56Z",
		input: {},
		output: {},
		verdict: null,
		verdict_note: null,
		caller_email: "alice@acme.com",
		caller_name: "Alice",
		steps: [],
		ai_usage: [],
		ai_totals: null,
		...overrides,
	};
}

const baseAgent = {
	id: "agent-1",
	name: "Tier-1 Triage",
	description: "Handles tier-1 tickets",
	is_active: true,
};

beforeEach(() => {
	mockUseAgentRun.mockReturnValue({ data: makeRun(), isLoading: false });
	mockUseAgent.mockReturnValue({ data: baseAgent, isLoading: false });
	mockUseFlagConversation.mockReturnValue({ data: undefined });
	mockSendFlagMessage.mockReset();
	mockSetVerdict.mockReset();
	mockClearVerdict.mockReset();
	mockRegenSummary.mockReset();
	mockAuth.mockReturnValue({ isPlatformAdmin: false });
});

async function renderPage(path = "/agents/agent-1/runs/run-1") {
	const { AgentRunDetailPage } = await import("./AgentRunDetailPage");
	return renderWithProviders(
		<Routes>
			<Route
				path="/agents/:agentId/runs/:runId"
				element={<AgentRunDetailPage />}
			/>
		</Routes>,
		{ initialEntries: [path] },
	);
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe("AgentRunDetailPage — header + summary", () => {
	it("renders the run summary in the header", async () => {
		// Header uses `asked` as the TL;DR title (not `did` — that's prose
		// under v3+ and too long for a heading).
		await renderPage();
		expect(
			screen.getByRole("heading", { name: /reset password please/i }),
		).toBeInTheDocument();
	});

	it("renders the agent name in the breadcrumb", async () => {
		await renderPage();
		const links = screen.getAllByRole("link", { name: /tier-1 triage/i });
		// Both breadcrumb and the sidebar Agent card link to the same URL.
		expect(links.length).toBeGreaterThan(0);
		for (const link of links) {
			expect(link).toHaveAttribute("href", "/agents/agent-1");
		}
	});

	it("renders the RunReviewPanel with the run id", async () => {
		await renderPage();
		expect(screen.getByTestId("run-review-panel")).toHaveAttribute(
			"data-run-id",
			"run-1",
		);
	});
});

describe("AgentRunDetailPage — loading + empty", () => {
	it("renders skeletons while loading", async () => {
		mockUseAgentRun.mockReturnValue({ data: undefined, isLoading: true });
		const { container } = await renderPage();
		expect(
			container.querySelectorAll(".animate-pulse").length,
		).toBeGreaterThan(0);
	});

	it("renders not-found when the run is missing", async () => {
		mockUseAgentRun.mockReturnValue({ data: null, isLoading: false });
		await renderPage();
		expect(screen.getByTestId("run-not-found")).toBeInTheDocument();
	});
});

describe("AgentRunDetailPage — verdict actions", () => {
	it("calls useSetVerdict when verdict is set to up", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("set-up"));
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

	it("calls useClearVerdict when verdict is cleared", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("clear-verdict"));
		await waitFor(() => {
			expect(mockClearVerdict).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { run_id: "run-1" } },
				}),
				expect.any(Object),
			);
		});
	});
});

describe("AgentRunDetailPage — sidebar metadata", () => {
	it("renders run id, model, caller and trigger in the sidebar", async () => {
		await renderPage();
		// Run ID rendered
		expect(screen.getByText(/run-1/)).toBeInTheDocument();
		// Model
		expect(screen.getByText(/claude-opus-4-7/)).toBeInTheDocument();
		// Trigger type
		expect(screen.getByText(/test/)).toBeInTheDocument();
		// Caller name preferred over email
		expect(screen.getByText(/alice/i)).toBeInTheDocument();
	});
});

describe("AgentRunDetailPage — regenerate summary", () => {
	it("hides the regenerate button for non-admins when summary is healthy", async () => {
		mockAuth.mockReturnValue({ isPlatformAdmin: false });
		await renderPage();
		expect(
			screen.queryByTestId("regen-summary-button"),
		).not.toBeInTheDocument();
	});

	it("shows the regenerate button for platform admins", async () => {
		mockAuth.mockReturnValue({ isPlatformAdmin: true });
		await renderPage();
		expect(screen.getByTestId("regen-summary-button")).toBeInTheDocument();
	});

	it("shows the regenerate button when summary_status is failed (any role)", async () => {
		mockAuth.mockReturnValue({ isPlatformAdmin: false });
		mockUseAgentRun.mockReturnValue({
			data: makeRun({ summary_status: "failed" }),
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByTestId("regen-summary-button")).toBeInTheDocument();
	});

	it("calls useRegenerateSummary when the button is clicked", async () => {
		mockAuth.mockReturnValue({ isPlatformAdmin: true });
		const { user } = await renderPage();
		await user.click(screen.getByTestId("regen-summary-button"));
		await waitFor(() => {
			expect(mockRegenSummary).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { run_id: "run-1" } },
				}),
				expect.any(Object),
			);
		});
	});
});

describe("AgentRunDetailPage — rerun", () => {
	it("renders the rerun button in the header", async () => {
		await renderPage();
		expect(screen.getByTestId("rerun-button")).toBeInTheDocument();
	});

	it("calls useRerunAgentRun with the current run id on click", async () => {
		const { user } = await renderPage();
		await user.click(screen.getByTestId("rerun-button"));
		await waitFor(() => {
			expect(mockRerun).toHaveBeenCalledWith(
				expect.objectContaining({
					params: { path: { run_id: "run-1" } },
				}),
				expect.any(Object),
			);
		});
	});
});

describe("AgentRunDetailPage — flag conversation", () => {
	it("does not render the flag conversation when verdict is not down", async () => {
		await renderPage();
		expect(
			screen.queryByTestId("flag-conversation-card"),
		).not.toBeInTheDocument();
	});

	it("renders the flag conversation when verdict is down", async () => {
		mockUseAgentRun.mockReturnValue({
			data: makeRun({ verdict: "down" }),
			isLoading: false,
		});
		mockUseFlagConversation.mockReturnValue({
			data: { id: "conv-1", run_id: "run-1", messages: [] },
		});
		await renderPage();
		expect(
			screen.getByTestId("flag-conversation-card"),
		).toBeInTheDocument();
		expect(screen.getByTestId("flag-conversation")).toHaveTextContent(
			"conv-conv-1",
		);
	});
});

describe("AgentRunDetailPage — AI usage card", () => {
	it("renders the AI usage card when usage data is present", async () => {
		mockUseAgentRun.mockReturnValue({
			data: makeRun({
				ai_usage: [
					{
						provider: "anthropic",
						model: "claude-opus-4-7",
						input_tokens: 1000,
						output_tokens: 500,
						cost: "0.025",
					},
				],
				ai_totals: {
					total_input_tokens: 1000,
					total_output_tokens: 500,
					total_cost: "0.025",
					total_duration_ms: 1500,
					call_count: 1,
				},
			}),
			isLoading: false,
		});
		await renderPage();
		expect(screen.getByTestId("ai-usage-card")).toBeInTheDocument();
	});

	it("hides the AI usage card when there is no usage data", async () => {
		await renderPage();
		expect(
			screen.queryByTestId("ai-usage-card"),
		).not.toBeInTheDocument();
	});
});
