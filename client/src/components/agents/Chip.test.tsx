import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { Chip } from "./Chip";

describe("Chip", () => {
	it("renders children", () => {
		renderWithProviders(<Chip>Globex</Chip>);
		expect(screen.getByText("Globex")).toBeInTheDocument();
	});

	it("renders the label prefix when provided", () => {
		renderWithProviders(<Chip label="ticket_id">4822</Chip>);
		expect(screen.getByText("ticket_id")).toBeInTheDocument();
		expect(screen.getByText("4822")).toBeInTheDocument();
	});

	it("applies a tone class for rose", () => {
		renderWithProviders(<Chip tone="rose">flagged</Chip>);
		const el = screen.getByText("flagged").parentElement;
		expect(el?.className).toMatch(/text-rose-500/);
	});
});
