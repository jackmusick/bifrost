/**
 * Component tests for ToolOutputDisplay.
 *
 * Pure, stateless renderer that applies per-line class names based on text
 * pattern (diff, grep, errors, status). Each test asserts both that the line
 * renders and that the expected pattern-class is applied.
 */

import { describe, it, expect } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";
import { ToolOutputDisplay } from "./ToolOutputDisplay";

describe("ToolOutputDisplay — line classification", () => {
	it("renders each line in the input text", () => {
		renderWithProviders(
			<ToolOutputDisplay text={"line one\nline two\nline three"} />,
		);
		expect(screen.getByText("line one")).toBeInTheDocument();
		expect(screen.getByText("line two")).toBeInTheDocument();
		expect(screen.getByText("line three")).toBeInTheDocument();
	});

	it("colors diff added lines green", () => {
		renderWithProviders(<ToolOutputDisplay text={"+added line"} />);
		const line = screen.getByText(/\+added line/);
		expect(line.className).toMatch(/text-green/);
	});

	it("colors diff removed lines red", () => {
		renderWithProviders(<ToolOutputDisplay text={"-removed line"} />);
		const line = screen.getByText(/-removed line/);
		expect(line.className).toMatch(/text-red/);
	});

	it("colors grep-format file:line matches cyan", () => {
		renderWithProviders(
			<ToolOutputDisplay text={"src/foo.ts:42: match here"} />,
		);
		const line = screen.getByText(/src\/foo\.ts:42: match here/);
		expect(line.className).toMatch(/text-cyan/);
	});

	it("colors status messages like 'Updated ...' blue", () => {
		renderWithProviders(<ToolOutputDisplay text={"Updated config.yaml"} />);
		const line = screen.getByText(/Updated config\.yaml/);
		expect(line.className).toMatch(/text-blue/);
	});

	it("colors Error: prefixed lines red", () => {
		renderWithProviders(
			<ToolOutputDisplay text={"Error: something went wrong"} />,
		);
		const line = screen.getByText(/Error: something went wrong/);
		expect(line.className).toMatch(/text-red/);
	});

	it("colors check-mark (✓) success lines green", () => {
		renderWithProviders(<ToolOutputDisplay text={"✓ passed"} />);
		const line = screen.getByText(/✓ passed/);
		expect(line.className).toMatch(/text-green/);
	});

	it("leaves plain text lines without a color class", () => {
		renderWithProviders(<ToolOutputDisplay text={"just a normal line"} />);
		const line = screen.getByText(/just a normal line/);
		// No green/red/cyan/blue color applied.
		expect(line.className).not.toMatch(/text-(green|red|cyan|blue)/);
	});
});
