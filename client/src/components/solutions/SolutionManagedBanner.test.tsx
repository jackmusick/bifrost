import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SolutionManagedBanner } from "./SolutionManagedBanner";

describe("SolutionManagedBanner", () => {
	it("renders the read-only affordance", () => {
		render(<SolutionManagedBanner />);
		expect(screen.getByTestId("solution-managed-banner")).toBeInTheDocument();
		expect(screen.getByText("Managed by a Solution")).toBeInTheDocument();
		expect(screen.getByText(/read-only here/i)).toBeInTheDocument();
	});

	it("uses the provided entity label in the message", () => {
		render(<SolutionManagedBanner entityLabel="workflow" />);
		expect(screen.getByText(/This workflow was installed by a Solution/i)).toBeInTheDocument();
	});
});
