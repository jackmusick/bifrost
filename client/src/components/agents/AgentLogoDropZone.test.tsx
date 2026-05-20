import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AgentLogoDropZone } from "./AgentLogoDropZone";

vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

describe("AgentLogoDropZone", () => {
	let fetchSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
			new Response(null, { status: 200 })
		);
	});

	afterEach(() => {
		fetchSpy.mockRestore();
	});

	it("posts a dropped file to the agent logo endpoint and calls onUploaded", async () => {
		const onUploaded = vi.fn();
		render(
			<AgentLogoDropZone
				agentId="22222222-2222-2222-2222-222222222222"
				agentName="Bot"
				onUploaded={onUploaded}
			/>
		);
		const zone = screen.getByTestId("agent-logo-zone");
		const file = new File(["x"], "logo.png", { type: "image/png" });
		fireEvent.drop(zone, { dataTransfer: { files: [file] } });
		await waitFor(() => expect(onUploaded).toHaveBeenCalled());
		expect(fetchSpy).toHaveBeenCalledWith(
			expect.stringContaining(
				"/api/agents/22222222-2222-2222-2222-222222222222/logo"
			),
			expect.objectContaining({ method: "POST" })
		);
	});

	it("opens the file picker when the zone is clicked", () => {
		const clickSpy = vi.fn();
		const orig = HTMLInputElement.prototype.click;
		HTMLInputElement.prototype.click = clickSpy;
		try {
			render(
				<AgentLogoDropZone
					agentId="22222222-2222-2222-2222-222222222222"
					agentName="Bot"
					onUploaded={vi.fn()}
				/>
			);
			fireEvent.click(screen.getByTestId("agent-logo-zone"));
			expect(clickSpy).toHaveBeenCalled();
		} finally {
			HTMLInputElement.prototype.click = orig;
		}
	});

	it("renders initials as the fallback when there's no logo", () => {
		render(
			<AgentLogoDropZone
				agentId="22222222-2222-2222-2222-222222222222"
				agentName="Alpha Beta"
				onUploaded={vi.fn()}
			/>
		);
		fireEvent.error(screen.getByTestId("entity-logo"));
		expect(screen.getByText("AB")).toBeInTheDocument();
	});
});
