/**
 * Component tests for ToolExecutionGroup.
 *
 * Presentational wrapper that adds indent + a vertical connecting line.
 * We cover: children render inside it, and a custom className composes
 * with the base layout classes.
 */

import { describe, it, expect } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { ToolExecutionGroup } from "./ToolExecutionGroup";

describe("ToolExecutionGroup", () => {
	it("renders children within the group container", () => {
		renderWithProviders(
			<ToolExecutionGroup>
				<span>child A</span>
				<span>child B</span>
			</ToolExecutionGroup>,
		);
		expect(screen.getByText("child A")).toBeInTheDocument();
		expect(screen.getByText("child B")).toBeInTheDocument();
	});

	it("composes a custom className with base layout classes", () => {
		renderWithProviders(
			<ToolExecutionGroup className="extra-class">
				<span>inside</span>
			</ToolExecutionGroup>,
		);
		const child = screen.getByText("inside");
		// Outer-most wrapper is two levels up (.flex.gap-2 > .relative.pl-6)
		const outer = child.parentElement?.parentElement;
		expect(outer?.className).toMatch(/relative/);
		expect(outer?.className).toMatch(/pl-6/);
		expect(outer?.className).toMatch(/extra-class/);
	});
});
