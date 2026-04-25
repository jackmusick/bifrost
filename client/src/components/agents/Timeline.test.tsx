/**
 * Timeline tests — friendly labels per step type, expand-to-detail flow, and
 * empty state. Covers regression risk from the JSON-dump → structured view
 * rebuild.
 */

import { describe, it, expect } from "vitest";
import { fireEvent } from "@testing-library/react";

import { renderWithProviders, screen } from "@/test-utils";
import { Timeline } from "./Timeline";
import type { components } from "@/lib/v1";

type AgentRunStepResponse = components["schemas"]["AgentRunStepResponse"];

function step(
	type: string,
	content: Record<string, unknown>,
	overrides: Partial<AgentRunStepResponse> = {},
): AgentRunStepResponse {
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

describe("Timeline", () => {
	it("shows the empty placeholder when there are no steps", () => {
		renderWithProviders(<Timeline steps={[]} />);
		expect(screen.getByText(/no steps recorded/i)).toBeInTheDocument();
	});

	it("renders friendly labels by step type, not raw type strings", () => {
		const steps = [
			step("tool_call", {
				tool_name: "send_email",
				arguments: { to: "u@x.com" },
			}),
			step("tool_result", {
				tool_name: "send_email",
				result: "queued",
			}),
			step("llm_response", {
				content: "Decision text",
				tool_calls: [{ name: "send_email" }],
			}),
		];
		renderWithProviders(<Timeline steps={steps} />);
		expect(screen.getByText(/Called send_email/i)).toBeInTheDocument();
		expect(
			screen.getByText(/Result from send_email/i),
		).toBeInTheDocument();
		// Label names the called tool directly instead of saying "LLM
		// decided to call tools" — saves a click of comprehension.
		expect(
			screen.getByText(/Decided to call send_email/i),
		).toBeInTheDocument();
	});

	it("expands a tool_call row to show pretty-printed args", () => {
		const steps = [
			step("tool_call", {
				tool_name: "send_email",
				arguments: { to: "u@x.com", subject: "Hi" },
			}),
		];
		renderWithProviders(<Timeline steps={steps} />);
		const btn = screen.getByRole("button", {
			name: /toggle details for step 1/i,
		});
		expect(btn).toHaveAttribute("aria-expanded", "false");
		fireEvent.click(btn);
		expect(btn).toHaveAttribute("aria-expanded", "true");
		// Args should be visible as JSON in the expanded body via JsonTree —
		// JsonTree wraps strings in quotes.
		expect(screen.getByText(/"u@x.com"/i)).toBeInTheDocument();
	});

	it("does not render an expand affordance for steps with no detail", () => {
		// tool_call with empty args — nothing to expand to.
		const steps = [
			step("tool_call", { tool_name: "list_workflows", arguments: {} }),
		];
		renderWithProviders(<Timeline steps={steps} />);
		// Button is rendered but disabled (no detail = nothing to toggle).
		const btn = screen.getByRole("button", {
			name: /list_workflows/i,
		});
		expect(btn).toBeDisabled();
	});

	it("falls back to the raw type label for unknown step types", () => {
		const steps = [step("custom_kind", { foo: "bar" })];
		renderWithProviders(<Timeline steps={steps} />);
		expect(screen.getByText("custom_kind")).toBeInTheDocument();
	});
});
