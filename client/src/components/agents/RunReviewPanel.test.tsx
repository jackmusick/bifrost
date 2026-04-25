import { describe, it, expect, vi } from "vitest";
import { fireEvent } from "@testing-library/react";
import { renderWithProviders, screen } from "@/test-utils";
import type { components } from "@/lib/v1";

const mockRegenSummary = vi.fn();
const mockAuth = vi.fn(() => ({ isPlatformAdmin: true }));

vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => mockAuth(),
}));

vi.mock("@/services/agentRuns", () => ({
	useRegenerateSummary: () => ({
		mutate: mockRegenSummary,
		isPending: false,
	}),
}));

import { RunReviewPanel } from "./RunReviewPanel";

type AgentRunDetail = components["schemas"]["AgentRunDetailResponse"];

const baseRun: AgentRunDetail = {
	id: "00000000-0000-0000-0000-000000000001",
	agent_id: "00000000-0000-0000-0000-000000000002",
	agent_name: "Tier-1 Triage",
	trigger_type: "test",
	summary_status: "completed",
	status: "completed",
	iterations_used: 1,
	tokens_used: 100,
	asked: "How do I reset my password?",
	did: "Routed to Support",
	input: { message: "help" },
	output: { text: "ok" },
	verdict: null,
	verdict_note: null,
	created_at: "2026-04-21T10:00:00Z",
	metadata: {},
	steps: [],
};

describe("RunReviewPanel", () => {
	it("renders the asked text", () => {
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.getByText(/how do i reset my password/i),
		).toBeInTheDocument();
	});

	it("renders the agent answer when completed (answered field, falls back to did)", () => {
		// `did` is also rendered in the "What it did" prose section, so the
		// text appears in both places; either is fine — we just need at
		// least one match.
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(screen.getAllByText(/routed to support/i).length).toBeGreaterThan(0);
	});

	it("uses `answered` over `did` in the answer section when both present", () => {
		renderWithProviders(
			<RunReviewPanel
				run={{
					...baseRun,
					did: "Looked up the user, then routed.",
					answered: "Sent password-reset link",
				}}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.getByText("Sent password-reset link"),
		).toBeInTheDocument();
	});

	it("calls onVerdict('up') when good toggle clicked", async () => {
		const onVerdict = vi.fn();
		const { user } = renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={onVerdict}
				onNote={() => {}}
			/>,
		);
		await user.click(screen.getByRole("button", { name: /mark as good/i }));
		expect(onVerdict).toHaveBeenCalledWith("up");
	});

	it("calls onVerdict(null) when active good toggle clicked again", async () => {
		const onVerdict = vi.fn();
		const { user } = renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict="up"
				note=""
				onVerdict={onVerdict}
				onNote={() => {}}
			/>,
		);
		await user.click(screen.getByRole("button", { name: /mark as good/i }));
		expect(onVerdict).toHaveBeenCalledWith(null);
	});

	it("calls onNote when note input changes", async () => {
		const onNote = vi.fn();
		const { user } = renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={onNote}
			/>,
		);
		const input = screen.getByPlaceholderText(/add a note/i);
		await user.type(input, "x");
		expect(onNote).toHaveBeenCalledWith("x");
	});

	it("hides verdict bar when hideVerdictBar=true", () => {
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				hideVerdictBar
			/>,
		);
		expect(
			screen.queryByRole("button", { name: /mark as good/i }),
		).not.toBeInTheDocument();
	});

	it("hides verdict bar when run is not completed", () => {
		renderWithProviders(
			<RunReviewPanel
				run={{ ...baseRun, status: "failed", error: "boom" }}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.queryByRole("button", { name: /mark as good/i }),
		).not.toBeInTheDocument();
		expect(screen.getByText(/run failed/i)).toBeInTheDocument();
		expect(screen.getByText(/boom/i)).toBeInTheDocument();
	});

	it("renders did prose even when there are zero [tool] markers", () => {
		// Regression guard: the v3 LLM occasionally omits markers. Narrative
		// must still render; markers are a bonus.
		const run: AgentRunDetail = {
			...baseRun,
			did: "Looked up the ticket and routed to Tier 2 because the issue was network-related.",
			steps: [],
		};
		renderWithProviders(
			<RunReviewPanel
				run={run}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		// `did` renders in both "What it did" prose AND falls back into
		// "What the agent answered" when `answered` is null — both fine.
		expect(
			screen.getAllByText(/looked up the ticket and routed to tier 2/i)
				.length,
		).toBeGreaterThan(0);
		// Tool-call list should NOT render — we have prose to show instead.
		expect(
			screen.queryByText(/what it did · 0 tool call/i),
		).not.toBeInTheDocument();
	});

	it("renders tool call section when steps include tool calls", () => {
		// Fallback path: when there's no `did` summary, fall back to the raw
		// tool-call list. Step content is { tool_name, arguments } per
		// autonomous_agent_executor.py _record_step(..., "tool_call", ...).
		const run: AgentRunDetail = {
			...baseRun,
			did: null,
			steps: [
				{
					id: "s1",
					run_id: baseRun.id,
					step_number: 1,
					type: "tool_call",
					content: {
						tool_name: "ai_ticketing_get_ticket_details",
						arguments: { ticket_id: 423068 },
					},
					duration_ms: 120,
					created_at: baseRun.created_at,
				},
			],
		};
		renderWithProviders(
			<RunReviewPanel
				run={run}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(screen.getByText(/what it did · 1 tool call/i)).toBeInTheDocument();
		// Real tool name must render, not the generic "tool" placeholder.
		expect(
			screen.getByText("ai_ticketing_get_ticket_details"),
		).toBeInTheDocument();
		// Args are collapsed by default behind a chevron disclosure; expand
		// them and confirm the args render via the JsonTree (key + value).
		fireEvent.click(
			screen.getByRole("button", { name: /show arguments/i }),
		);
		expect(screen.getByText(/"ticket_id"/)).toBeInTheDocument();
		expect(screen.getByText("423068")).toBeInTheDocument();
	});

	it("renders tool call rows even when arguments object is empty", () => {
		// Regression guard for the `tool {}` screenshot — zero-arg tool calls
		// must still show the tool name as the row label, but the args column
		// renders nothing (no `{}` clutter) and there's no expand affordance.
		const run: AgentRunDetail = {
			...baseRun,
			did: null,  // force the fallback tool-call list
			steps: [
				{
					id: "s1",
					run_id: baseRun.id,
					step_number: 1,
					type: "tool_call",
					content: { tool_name: "list_workflows", arguments: {} },
					duration_ms: null,
					created_at: baseRun.created_at,
				},
			],
		};
		renderWithProviders(
			<RunReviewPanel
				run={run}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(screen.getByText("list_workflows")).toBeInTheDocument();
		// No "{}" placeholder should appear; no expand button either.
		expect(screen.queryByText("{}")).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /show arguments/i }),
		).not.toBeInTheDocument();
	});

	it("collapses non-empty tool args behind a disclosure that expands inline", () => {
		const run: AgentRunDetail = {
			...baseRun,
			did: null,  // force the fallback tool-call list
			steps: [
				{
					id: "s1",
					run_id: baseRun.id,
					step_number: 1,
					type: "tool_call",
					content: {
						tool_name: "send_email",
						arguments: { to: "user@x.com", subject: "Hi" },
					},
					duration_ms: 120,
					created_at: baseRun.created_at,
				},
			],
		};
		renderWithProviders(
			<RunReviewPanel
				run={run}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		// Collapsed: button with the show-args label; one-line preview visible.
		const expandBtn = screen.getByRole("button", { name: /show arguments/i });
		expect(expandBtn).toHaveAttribute("aria-expanded", "false");
		fireEvent.click(expandBtn);
		expect(
			screen.getByRole("button", { name: /hide arguments/i }),
		).toHaveAttribute("aria-expanded", "true");
	});

	it("renders metadata chips when metadata present", () => {
		renderWithProviders(
			<RunReviewPanel
				run={{ ...baseRun, metadata: { ticket_id: "4821", org: "acme" } }}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(screen.getByText("ticket_id")).toBeInTheDocument();
		expect(screen.getByText("4821")).toBeInTheDocument();
	});

	it("uses 'What should it have done?' placeholder when verdict is down", () => {
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict="down"
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.getByPlaceholderText(/what should it have done/i),
		).toBeInTheDocument();
	});

	it("hides the in-panel regenerate bar when summary is completed", () => {
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.queryByTestId("regen-summary-panel-button"),
		).not.toBeInTheDocument();
	});

	it("shows the in-panel regenerate bar when summary is pending", () => {
		renderWithProviders(
			<RunReviewPanel
				run={{ ...baseRun, summary_status: "pending", asked: "", did: "" }}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(
			screen.getByTestId("regen-summary-panel-button"),
		).toBeInTheDocument();
	});

	it("disables regen for non-admins but still shows it (tooltip)", () => {
		mockAuth.mockReturnValueOnce({ isPlatformAdmin: false });
		renderWithProviders(
			<RunReviewPanel
				run={{ ...baseRun, summary_status: "failed", asked: "", did: "" }}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		const btn = screen.getByTestId("regen-summary-panel-button");
		expect(btn).toBeDisabled();
	});
});
