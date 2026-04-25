/**
 * Component tests for ExecutionStatusBadge.
 *
 * The badge is a pure switch over status + a few optional queue/memory props.
 * We test that each status renders the user-visible label (what an operator
 * would read to know the state) and that the Pending variant chooses the
 * right copy based on waitReason.
 */

import { describe, it, expect } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import {
	ExecutionStatusBadge,
	isExecutionComplete,
	isExecutionRunning,
} from "./ExecutionStatusBadge";

describe("ExecutionStatusBadge — status labels", () => {
	it.each([
		["Success", /completed/i],
		["Failed", /^failed$/i],
		["Running", /running/i],
		["Cancelling", /cancelling/i],
		["Cancelled", /cancelled/i],
		["CompletedWithErrors", /completed with errors/i],
		["Timeout", /timeout/i],
	])("renders %s as '%s'", (status, expectedLabel) => {
		renderWithProviders(<ExecutionStatusBadge status={status} />);
		expect(screen.getByText(expectedLabel)).toBeInTheDocument();
	});

	it("renders a bare Pending badge when no waitReason is supplied", () => {
		renderWithProviders(<ExecutionStatusBadge status="Pending" />);
		expect(screen.getByText(/^pending$/i)).toBeInTheDocument();
	});

	it("renders queue position for Pending + queued", () => {
		renderWithProviders(
			<ExecutionStatusBadge
				status="Pending"
				waitReason="queued"
				queuePosition={3}
			/>,
		);
		expect(screen.getByText(/queued - position 3/i)).toBeInTheDocument();
	});

	it("renders memory details for Pending + memory_pressure", () => {
		renderWithProviders(
			<ExecutionStatusBadge
				status="Pending"
				waitReason="memory_pressure"
				availableMemoryMb={512}
				requiredMemoryMb={1024}
			/>,
		);
		expect(
			screen.getByText(/heavy load \(512MB \/ 1024MB\)/i),
		).toBeInTheDocument();
	});

	it("falls back to '?' when memory numbers are missing", () => {
		renderWithProviders(
			<ExecutionStatusBadge
				status="Pending"
				waitReason="memory_pressure"
			/>,
		);
		expect(
			screen.getByText(/heavy load \(\?MB \/ \?MB\)/i),
		).toBeInTheDocument();
	});

	it("renders the raw status text for unknown statuses", () => {
		renderWithProviders(<ExecutionStatusBadge status="WeirdNewStatus" />);
		expect(screen.getByText("WeirdNewStatus")).toBeInTheDocument();
	});
});

describe("ExecutionStatusBadge — Scheduled", () => {
	it("renders the label without inline datetime", () => {
		renderWithProviders(
			<ExecutionStatusBadge
				status="Scheduled"
				scheduledAt="2026-04-25T13:00:00Z"
			/>,
		);
		const badge = screen.getByText(/^scheduled$/i);
		expect(badge).toBeInTheDocument();
		// The badge's rendered text content is exactly "Scheduled", no date.
		expect(badge.textContent?.trim()).toBe("Scheduled");
	});

	it("carries absolute datetime in title attribute on hover", () => {
		const { container } = renderWithProviders(
			<ExecutionStatusBadge
				status="Scheduled"
				scheduledAt="2026-04-25T13:00:00Z"
			/>,
		);
		const withTitle = container.querySelector("[title]");
		expect(withTitle).not.toBeNull();
		expect(withTitle?.getAttribute("title")).toMatch(/2026/);
	});

	it("still renders without title when scheduledAt is undefined", () => {
		const { container } = renderWithProviders(
			<ExecutionStatusBadge status="Scheduled" scheduledAt={undefined} />,
		);
		expect(screen.getByText(/^scheduled$/i)).toBeInTheDocument();
		const withTitle = container.querySelector("[title]");
		expect(withTitle).toBeNull();
	});

	it("ignores scheduledAt for non-Scheduled statuses", () => {
		const { container } = renderWithProviders(
			<ExecutionStatusBadge
				status="Pending"
				scheduledAt="2026-04-25T13:00:00Z"
			/>,
		);
		const withTitle = container.querySelector("[title]");
		expect(withTitle).toBeNull();
	});
});

describe("isExecutionComplete / isExecutionRunning helpers", () => {
	it.each(["Success", "Failed", "CompletedWithErrors", "Timeout", "Cancelled"])(
		"treats %s as complete",
		(status) => {
			expect(isExecutionComplete(status)).toBe(true);
			expect(isExecutionRunning(status)).toBe(false);
		},
	);

	it.each(["Running", "Pending", "Cancelling"])(
		"treats %s as running",
		(status) => {
			expect(isExecutionRunning(status)).toBe(true);
			expect(isExecutionComplete(status)).toBe(false);
		},
	);
});
