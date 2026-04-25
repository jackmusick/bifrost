import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { MetaLine } from "./MetaLine";

describe("MetaLine", () => {
	it("renders items separated by middle dots", () => {
		renderWithProviders(
			<MetaLine items={["1h ago", "3.4s", "2 iter"]} />,
		);
		expect(screen.getByText("1h ago")).toBeInTheDocument();
		expect(screen.getByText("3.4s")).toBeInTheDocument();
		expect(screen.getByText("2 iter")).toBeInTheDocument();
		// Two separators between three items.
		expect(screen.getAllByText("·")).toHaveLength(2);
	});

	it("skips null, false, and empty-string items", () => {
		renderWithProviders(
			<MetaLine items={["3.4s", null, false, "", "2 iter"]} />,
		);
		expect(screen.getByText("3.4s")).toBeInTheDocument();
		expect(screen.getByText("2 iter")).toBeInTheDocument();
		expect(screen.getAllByText("·")).toHaveLength(1);
	});

	it("renders nothing when every item is filtered out", () => {
		const { container } = renderWithProviders(
			<MetaLine items={[null, false, ""]} />,
		);
		expect(container.firstChild).toBeNull();
	});

	it("honors a custom separator", () => {
		renderWithProviders(<MetaLine items={["a", "b"]} separator="|" />);
		expect(screen.getByText("|")).toBeInTheDocument();
	});
});
