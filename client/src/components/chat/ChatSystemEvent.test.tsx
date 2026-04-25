/**
 * Component tests for ChatSystemEvent.
 *
 * The component has three rendering branches (agent_switch, error, info),
 * and agent_switch has two sub-variants ("routed" vs "@mention"). Cover
 * each so a regression in the branch logic surfaces immediately.
 */

import { describe, it, expect } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { ChatSystemEvent, type SystemEvent } from "./ChatSystemEvent";

function makeEvent(overrides: Partial<SystemEvent>): SystemEvent {
	return {
		id: "evt-1",
		type: "info",
		timestamp: "2026-04-20T12:00:00Z",
		...overrides,
	};
}

describe("ChatSystemEvent — agent_switch", () => {
	it("renders 'Routed to <agent>' for routed switches", () => {
		renderWithProviders(
			<ChatSystemEvent
				event={makeEvent({
					type: "agent_switch",
					reason: "routed",
					agentName: "SupportBot",
				})}
			/>,
		);
		expect(screen.getByText(/routed to/i)).toBeInTheDocument();
		expect(screen.getByText("SupportBot")).toBeInTheDocument();
	});

	it("renders 'Switched to <agent>' for @mention switches", () => {
		renderWithProviders(
			<ChatSystemEvent
				event={makeEvent({
					type: "agent_switch",
					reason: "@mention",
					agentName: "DevBot",
				})}
			/>,
		);
		expect(screen.getByText(/switched to/i)).toBeInTheDocument();
		expect(screen.getByText("DevBot")).toBeInTheDocument();
	});
});

describe("ChatSystemEvent — error", () => {
	it("renders the error message text", () => {
		renderWithProviders(
			<ChatSystemEvent
				event={makeEvent({ type: "error", error: "Connection lost" })}
			/>,
		);
		expect(screen.getByText("Connection lost")).toBeInTheDocument();
	});

	it("falls back to a generic message when no error text is provided", () => {
		renderWithProviders(
			<ChatSystemEvent event={makeEvent({ type: "error" })} />,
		);
		expect(screen.getByText(/an error occurred/i)).toBeInTheDocument();
	});
});

describe("ChatSystemEvent — info", () => {
	it("renders the info message", () => {
		renderWithProviders(
			<ChatSystemEvent
				event={makeEvent({ type: "info", message: "Thinking..." })}
			/>,
		);
		expect(screen.getByText("Thinking...")).toBeInTheDocument();
	});
});
