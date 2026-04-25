import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "@/test-utils";

import { ChatBubble, ChatBubbleSlot } from "./ChatBubble";

describe("ChatBubble", () => {
	it("renders a user bubble with content", () => {
		renderWithProviders(<ChatBubble kind="user">hello</ChatBubble>);
		expect(screen.getByText("hello")).toBeInTheDocument();
	});

	it("renders assistant bubble content", () => {
		renderWithProviders(
			<ChatBubble kind="assistant">thinking…</ChatBubble>,
		);
		expect(screen.getByText("thinking…")).toBeInTheDocument();
	});

	it("renders assistant slots inside the same bubble", () => {
		renderWithProviders(
			<ChatBubble
				kind="assistant"
				slots={
					<ChatBubbleSlot title="Proposed change">diff here</ChatBubbleSlot>
				}
			>
				Here's my plan.
			</ChatBubble>,
		);
		expect(screen.getByText("Here's my plan.")).toBeInTheDocument();
		expect(screen.getByText("Proposed change")).toBeInTheDocument();
		expect(screen.getByText("diff here")).toBeInTheDocument();
	});

	it("renders a system message centered with distinct styling", () => {
		renderWithProviders(
			<ChatBubble kind="system">applied 2m ago</ChatBubble>,
		);
		expect(screen.getByText("applied 2m ago")).toBeInTheDocument();
	});

	it("renders a timestamp when provided", () => {
		renderWithProviders(
			<ChatBubble kind="user" time="9:41">
				hi
			</ChatBubble>,
		);
		expect(screen.getByText("9:41")).toBeInTheDocument();
	});
});

describe("ChatBubbleSlot", () => {
	it("renders actions when provided", () => {
		renderWithProviders(
			<ChatBubbleSlot
				title="Dry-run passed"
				titleTone="emerald"
				actions={<button>Apply</button>}
			>
				result body
			</ChatBubbleSlot>,
		);
		expect(screen.getByText("Dry-run passed")).toBeInTheDocument();
		expect(screen.getByText("result body")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /apply/i })).toBeInTheDocument();
	});
});
