import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { KVList } from "./KVList";

describe("KVList", () => {
	it("renders each label / value pair", () => {
		renderWithProviders(
			<KVList
				items={[
					{ label: "Model", value: "claude-opus", mono: true },
					{ label: "Channels", value: "chat, voice" },
					{ label: "Owner", value: "system" },
				]}
			/>,
		);
		expect(screen.getByText("Model")).toBeInTheDocument();
		expect(screen.getByText("claude-opus")).toBeInTheDocument();
		expect(screen.getByText("Channels")).toBeInTheDocument();
		expect(screen.getByText("chat, voice")).toBeInTheDocument();
		expect(screen.getByText("Owner")).toBeInTheDocument();
	});

	it("renders an empty list without crashing", () => {
		const { container } = renderWithProviders(<KVList items={[]} />);
		expect(container.querySelector("dl")).toBeInTheDocument();
	});
});
