import { describe, it, expect, vi } from "vitest";
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

	it("renders the agent answer when completed", () => {
		renderWithProviders(
			<RunReviewPanel
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
			/>,
		);
		expect(screen.getByText(/routed to support/i)).toBeInTheDocument();
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

	it("renders tool call section when steps include tool calls", () => {
		const run: AgentRunDetail = {
			...baseRun,
			steps: [
				{
					id: "s1",
					run_id: baseRun.id,
					step_number: 1,
					type: "tool_call",
					content: { tool: "send_email", args: { to: "user@x.com" } },
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
		expect(screen.getByText("send_email")).toBeInTheDocument();
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
