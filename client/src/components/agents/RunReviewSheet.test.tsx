import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import type { components } from "@/lib/v1";

vi.mock("@/contexts/AuthContext", () => ({
	useAuth: () => ({ isPlatformAdmin: true }),
}));

vi.mock("@/services/agentRuns", () => ({
	useRegenerateSummary: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { RunReviewSheet } from "./RunReviewSheet";

type AgentRunDetail = components["schemas"]["AgentRunDetailResponse"];
type FlagConversationResponse = components["schemas"]["FlagConversationResponse"];

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

const baseConversation: FlagConversationResponse = {
	id: "00000000-0000-0000-0000-0000000000c1",
	run_id: baseRun.id,
	messages: [],
	created_at: baseRun.created_at,
	last_updated_at: baseRun.created_at,
};

describe("RunReviewSheet", () => {
	it("renders nothing when run is null", () => {
		const { container } = renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={() => {}}
				run={null}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={null}
				onSendChat={() => {}}
			/>,
		);
		expect(container.firstChild).toBeNull();
	});

	it("renders sheet content with run title when open", () => {
		renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={() => {}}
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={baseConversation}
				onSendChat={() => {}}
			/>,
		);
		const titles = screen.getAllByText(/routed to support/i);
		expect(titles.length).toBeGreaterThan(0);
		expect(screen.getByRole("tab", { name: /^review$/i })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: /tune/i })).toBeInTheDocument();
	});

	it("renders the Review tab content by default", () => {
		renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={() => {}}
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={baseConversation}
				onSendChat={() => {}}
			/>,
		);
		// Review tab body shows the asked text
		expect(
			screen.getByText(/how do i reset my password/i),
		).toBeInTheDocument();
	});

	it("switches to Tune tab on click", async () => {
		const { user } = renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={() => {}}
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={baseConversation}
				onSendChat={() => {}}
			/>,
		);
		await user.click(screen.getByRole("tab", { name: /tune/i }));
		// FlagConversation empty state is visible after switching
		expect(
			screen.getByText(/flag this run and tell me what went wrong/i),
		).toBeInTheDocument();
	});

	it("starts on the tune tab when defaultTab='tune'", () => {
		renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={() => {}}
				run={baseRun}
				verdict="down"
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={baseConversation}
				onSendChat={() => {}}
				defaultTab="tune"
			/>,
		);
		expect(
			screen.getByText(/flag this run and tell me what went wrong/i),
		).toBeInTheDocument();
	});

	it("calls onOpenChange(false) when the close button is clicked", async () => {
		const onOpenChange = vi.fn();
		const { user } = renderWithProviders(
			<RunReviewSheet
				open={true}
				onOpenChange={onOpenChange}
				run={baseRun}
				verdict={null}
				note=""
				onVerdict={() => {}}
				onNote={() => {}}
				conversation={baseConversation}
				onSendChat={() => {}}
			/>,
		);
		await user.click(screen.getByRole("button", { name: /close/i }));
		expect(onOpenChange).toHaveBeenCalledWith(false);
	});
});
