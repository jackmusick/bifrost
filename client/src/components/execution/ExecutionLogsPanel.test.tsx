/**
 * Component tests for ExecutionLogsPanel.
 *
 * The panel renders three distinct "modes" (running / complete / unknown)
 * and an embedded variant, each with its own empty-state copy and copy-
 * button affordance. We cover:
 *   - empty-state copy per status bucket
 *   - logs render in order (including order preservation when logs are
 *     appended via re-render, simulating streaming updates)
 *   - the copy button writes a formatted blob to the clipboard
 *   - the embedded variant shows a Live badge while streaming is running
 */

import { describe, it, expect, vi, beforeEach, MockInstance } from "vitest";
import { renderWithProviders, screen, within } from "@/test-utils";
import { ExecutionLogsPanel } from "./ExecutionLogsPanel";
import type { LogEntry } from "./ExecutionLogsPanel";

function log(level: string, message: string, ts = "2026-04-20T12:00:00Z"): LogEntry {
	return { level, message, timestamp: ts } as LogEntry;
}

let writeTextSpy: MockInstance;

beforeEach(() => {
	// happy-dom exposes `navigator.clipboard` as a getter on the prototype
	// that returns the same Clipboard instance, so spying on writeText via
	// that instance is the cleanest way to capture the call.
	writeTextSpy = vi
		.spyOn(navigator.clipboard, "writeText")
		.mockResolvedValue(undefined);
});

describe("ExecutionLogsPanel — empty states", () => {
	it("shows 'Waiting for logs...' while running with no logs yet", () => {
		renderWithProviders(
			<ExecutionLogsPanel logs={[]} status="Running" isConnected={true} />,
		);
		expect(screen.getByText(/waiting for logs/i)).toBeInTheDocument();
	});

	it("shows 'No logs captured' when a completed execution has none", () => {
		renderWithProviders(<ExecutionLogsPanel logs={[]} status="Success" />);
		expect(screen.getByText(/no logs captured/i)).toBeInTheDocument();
	});

	it("shows 'No execution in progress' when status is undefined", () => {
		renderWithProviders(<ExecutionLogsPanel logs={[]} />);
		expect(screen.getByText(/no execution in progress/i)).toBeInTheDocument();
	});
});

describe("ExecutionLogsPanel — rendering logs", () => {
	it("renders each log's level and message", () => {
		renderWithProviders(
			<ExecutionLogsPanel
				status="Success"
				logs={[
					log("INFO", "started"),
					log("WARNING", "slow query"),
					log("ERROR", "boom"),
				]}
			/>,
		);
		expect(screen.getByText("started")).toBeInTheDocument();
		expect(screen.getByText("slow query")).toBeInTheDocument();
		expect(screen.getByText("boom")).toBeInTheDocument();
		// Levels render upper-cased in a dedicated column.
		expect(screen.getByText("INFO")).toBeInTheDocument();
		expect(screen.getByText("WARNING")).toBeInTheDocument();
		expect(screen.getByText("ERROR")).toBeInTheDocument();
	});

	it("preserves log order when new logs are appended (streaming)", () => {
		const initial = [log("INFO", "first"), log("INFO", "second")];
		const { rerender } = renderWithProviders(
			<ExecutionLogsPanel status="Running" logs={initial} />,
		);
		expect(screen.getByText("first")).toBeInTheDocument();
		expect(screen.getByText("second")).toBeInTheDocument();

		// Simulate a new log streaming in.
		rerender(
			<ExecutionLogsPanel
				status="Running"
				logs={[...initial, log("INFO", "third")]}
			/>,
		);

		// All three are present in the DOM in order.
		const messages = ["first", "second", "third"].map((m) =>
			screen.getByText(m),
		);
		// Confirm DOM order by walking the rendered NodeList.
		const positions = messages.map(
			(el) =>
				Array.from(document.body.querySelectorAll("*")).indexOf(el) >>> 0,
		);
		expect(positions).toEqual([...positions].sort((a, b) => a - b));
	});

	it("hides DEBUG-only subtitle when the viewer is a platform admin", () => {
		renderWithProviders(
			<ExecutionLogsPanel
				status="Success"
				logs={[log("INFO", "hi")]}
				isPlatformAdmin={true}
			/>,
		);
		expect(
			screen.queryByText(/info, warning, error only/i),
		).not.toBeInTheDocument();
	});

	it("tells non-admin viewers which levels are filtered", () => {
		renderWithProviders(
			<ExecutionLogsPanel
				status="Success"
				logs={[log("INFO", "hi")]}
				isPlatformAdmin={false}
			/>,
		);
		expect(
			screen.getByText(/info, warning, error only/i),
		).toBeInTheDocument();
	});
});

describe("ExecutionLogsPanel — copy button", () => {
	it("writes formatted text to the clipboard when clicked", async () => {
		const { user } = renderWithProviders(
			<ExecutionLogsPanel
				status="Running"
				logs={[log("INFO", "hello"), log("ERROR", "oh no")]}
			/>,
		);

		// The running variant's copy button is an icon-only ghost button with
		// no accessible name, so we target it by the card header region.
		const buttons = screen.getAllByRole("button");
		expect(buttons.length).toBeGreaterThan(0);
		await user.click(buttons[0]);

		expect(writeTextSpy).toHaveBeenCalledTimes(1);
		const payload = writeTextSpy.mock.calls[0][0] as string;
		expect(payload).toContain("INFO");
		expect(payload).toContain("hello");
		expect(payload).toContain("ERROR");
		expect(payload).toContain("oh no");
	});
});

describe("ExecutionLogsPanel — embedded variant", () => {
	it("renders a Live badge while streaming is connected", () => {
		renderWithProviders(
			<ExecutionLogsPanel
				status="Running"
				isConnected={true}
				embedded={true}
				logs={[log("INFO", "streaming")]}
			/>,
		);
		expect(screen.getByText(/live/i)).toBeInTheDocument();
		// The embedded header labels the region with "Logs".
		const header = screen.getByText("Logs");
		expect(header).toBeInTheDocument();
		// And the streamed message body is present.
		expect(
			within(document.body).getByText("streaming"),
		).toBeInTheDocument();
	});

	it("omits the Live badge when not connected", () => {
		renderWithProviders(
			<ExecutionLogsPanel
				status="Running"
				isConnected={false}
				embedded={true}
				logs={[]}
			/>,
		);
		expect(screen.queryByText(/live/i)).not.toBeInTheDocument();
	});
});
