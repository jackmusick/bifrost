/**
 * Component tests for AppLoadingSkeleton.
 *
 * This is mostly a layout/presentational component, but it exposes one
 * small piece of behavior — the optional `message` prop that appears
 * alongside the spinner. Cover both the default and an explicit override
 * so regressions in the prop wiring surface as a failing test.
 */

import { describe, it, expect } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { AppLoadingSkeleton } from "./AppLoadingSkeleton";

describe("AppLoadingSkeleton", () => {
	it("shows the default 'Loading application...' message", () => {
		renderWithProviders(<AppLoadingSkeleton />);
		expect(screen.getByText(/loading application/i)).toBeInTheDocument();
	});

	it("uses a caller-provided message when one is passed", () => {
		renderWithProviders(
			<AppLoadingSkeleton message="Booting widgets..." />,
		);
		expect(screen.getByText("Booting widgets...")).toBeInTheDocument();
		expect(
			screen.queryByText(/loading application/i),
		).not.toBeInTheDocument();
	});
});
