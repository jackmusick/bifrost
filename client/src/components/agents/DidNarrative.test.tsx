/**
 * DidNarrative tests — markers split correctly, chips match steps, and the
 * popover surfaces args/result for matched tool calls.
 */

import { describe, it, expect } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithProviders, screen } from "@/test-utils";
import { DidNarrative } from "./DidNarrative";
import type { components } from "@/lib/v1";

type AgentRunStep = components["schemas"]["AgentRunStepResponse"];

function makeStep(
	type: string,
	content: Record<string, unknown>,
	overrides: Partial<AgentRunStep> = {},
): AgentRunStep {
	return {
		id: `s-${Math.random().toString(36).slice(2, 8)}`,
		run_id: "00000000-0000-0000-0000-000000000001",
		step_number: 1,
		type,
		content,
		duration_ms: null,
		created_at: "2026-04-24T00:00:00Z",
		...overrides,
	};
}

describe("DidNarrative", () => {
	it("renders plain prose with chips for [tool] markers", () => {
		const steps = [
			makeStep(
				"tool_call",
				{
					tool_name: "ai_ticketing_get_ticket_details",
					arguments: { ticket_id: 423068 },
				},
				{ duration_ms: 120 },
			),
			makeStep("tool_result", {
				tool_name: "ai_ticketing_get_ticket_details",
				result: "ticket #423068 details...",
			}),
		];
		renderWithProviders(
			<DidNarrative
				text="I called [ai_ticketing_get_ticket_details] to fetch the ticket."
				steps={steps}
			/>,
		);
		// Chip renders the tool name; surrounding prose renders too.
		expect(
			screen.getByText("ai_ticketing_get_ticket_details"),
		).toBeInTheDocument();
		expect(
			screen.getByText(/I called/i),
		).toBeInTheDocument();
		expect(
			screen.getByText(/to fetch the ticket/i),
		).toBeInTheDocument();
	});

	it("clicking a chip pops a panel with args + result for that call", () => {
		const steps = [
			makeStep(
				"tool_call",
				{
					tool_name: "send_email",
					arguments: { to: "user@x.com", subject: "Hi" },
				},
				{ duration_ms: 80 },
			),
			makeStep("tool_result", {
				tool_name: "send_email",
				result: "Email queued (id=42)",
			}),
		];
		renderWithProviders(
			<DidNarrative
				text="Then I called [send_email] to confirm."
				steps={steps}
			/>,
		);
		fireEvent.click(
			screen.getByRole("button", { name: /show details for send_email/i }),
		);
		// Args + result both surface inside the popover. Use getAllByText
		// because the matched tool name appears in trigger and popover header.
		expect(screen.getByText(/Arguments/i)).toBeInTheDocument();
		expect(screen.getByText(/Result/i)).toBeInTheDocument();
		expect(
			screen.getByText(/Email queued \(id=42\)/),
		).toBeInTheDocument();
	});

	it("renders an unmatched chip when the marker has no recorded call", () => {
		// Defensive: summarizer might hallucinate a tool name that wasn't
		// actually called. Chip should still render so the prose isn't
		// fragmented, but the styling indicates 'no record'.
		renderWithProviders(
			<DidNarrative
				text="Maybe I called [phantom_tool] once."
				steps={[]}
			/>,
		);
		const btn = screen.getByRole("button", {
			name: /phantom_tool.*no matching call recorded/i,
		});
		expect(btn).toBeInTheDocument();
	});

	it("returns the fallback when text is empty/null", () => {
		renderWithProviders(
			<DidNarrative
				text={null}
				steps={[]}
				fallback={<span data-testid="fb">placeholder</span>}
			/>,
		);
		expect(screen.getByTestId("fb")).toBeInTheDocument();
	});

	it("supports multiple chips on one line in order", () => {
		const steps = [
			makeStep("tool_call", { tool_name: "alpha", arguments: {} }),
			makeStep("tool_call", { tool_name: "beta", arguments: {} }),
		];
		const { container } = renderWithProviders(
			<DidNarrative
				text="First [alpha] then [beta]."
				steps={steps}
			/>,
		);
		const buttons = container.querySelectorAll("button");
		const labels = Array.from(buttons).map((b) =>
			b.getAttribute("aria-label") ?? "",
		);
		expect(labels[0]).toMatch(/alpha/);
		expect(labels[1]).toMatch(/beta/);
	});
});
