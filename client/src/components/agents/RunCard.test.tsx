import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import type { components } from "@/lib/v1";

import { RunCard } from "./RunCard";

type AgentRun = components["schemas"]["AgentRunResponse"];

const baseRun: AgentRun = {
	id: "00000000-0000-0000-0000-000000000001",
	agent_id: "00000000-0000-0000-0000-000000000002",
	agent_name: "Tier-1 Triage",
	trigger_type: "test",
	status: "completed",
	iterations_used: 1,
	tokens_used: 1234,
	asked: "How do I reset my password?",
	did: "Routed to Support",
	input: { message: "help" },
	output: { text: "ok" },
	verdict: null,
	verdict_note: null,
	duration_ms: 2500,
	created_at: "2026-04-21T10:00:00Z",
	started_at: "2026-04-21T10:00:00Z",
	metadata: {},
};

describe("RunCard", () => {
	it("renders the asked text", () => {
		renderWithProviders(<RunCard run={baseRun} />);
		expect(
			screen.getByText(/how do i reset my password/i),
		).toBeInTheDocument();
	});

	it("renders the did text", () => {
		renderWithProviders(<RunCard run={baseRun} />);
		expect(screen.getByText(/routed to support/i)).toBeInTheDocument();
	});

	it("renders the status badge", () => {
		renderWithProviders(<RunCard run={baseRun} />);
		expect(screen.getByText(/^completed$/i)).toBeInTheDocument();
	});

	it("renders 'Good' verdict badge when verdict='up'", () => {
		renderWithProviders(<RunCard run={baseRun} verdict="up" />);
		// Both the badge label and the toggle button say "Good"; check for the badge text
		expect(screen.getAllByText(/good/i).length).toBeGreaterThan(0);
	});

	it("renders 'Wrong' verdict badge when verdict='down'", () => {
		renderWithProviders(
			<RunCard run={baseRun} verdict="down" conversationCount={3} />,
		);
		expect(screen.getByText(/wrong · 3 msg/i)).toBeInTheDocument();
	});

	it("calls onOpen when the card is clicked", async () => {
		const onOpen = vi.fn();
		const { user } = renderWithProviders(
			<RunCard run={baseRun} onOpen={onOpen} />,
		);
		await user.click(screen.getByRole("button", { name: /how do i reset/i }));
		expect(onOpen).toHaveBeenCalled();
	});

	it("calls onVerdict when verdict toggle clicked, without firing onOpen", async () => {
		const onOpen = vi.fn();
		const onVerdict = vi.fn();
		const { user } = renderWithProviders(
			<RunCard run={baseRun} onOpen={onOpen} onVerdict={onVerdict} />,
		);
		await user.click(
			screen.getByRole("button", { name: /mark as good/i }),
		);
		expect(onVerdict).toHaveBeenCalledWith("up");
		expect(onOpen).not.toHaveBeenCalled();
	});

	it("renders metadata chips and overflow count", () => {
		const run = {
			...baseRun,
			metadata: { a: "1", b: "2", c: "3", d: "4", e: "5" },
		};
		renderWithProviders(<RunCard run={run} />);
		// 3 visible chips + overflow "+2"
		expect(screen.getByText("a")).toBeInTheDocument();
		expect(screen.getByText("+2")).toBeInTheDocument();
	});

	it("renders error text when status is failed and did is empty", () => {
		const run = {
			...baseRun,
			status: "failed",
			did: null,
			error: "boom",
		};
		renderWithProviders(<RunCard run={run} />);
		expect(screen.getByText(/error: boom/i)).toBeInTheDocument();
	});

	it("does not render verdict toggles for non-completed runs", () => {
		const run = { ...baseRun, status: "running" };
		renderWithProviders(<RunCard run={run} onVerdict={() => {}} />);
		expect(
			screen.queryByRole("button", { name: /mark as good/i }),
		).not.toBeInTheDocument();
		expect(screen.getByText(/n\/a/i)).toBeInTheDocument();
	});
});
