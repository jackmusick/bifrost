import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AppLogoPicker } from "./AppLogoPicker";

vi.mock("sonner", () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

describe("AppLogoPicker", () => {
	let fetchSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), { status: 200 }),
		);
	});

	afterEach(() => {
		fetchSpy.mockRestore();
	});

	it("shows a file input labelled 'Upload logo'", () => {
		render(
			<AppLogoPicker
				applicationId="11111111-1111-1111-1111-111111111111"
				onUploaded={vi.fn()}
				onRemoved={vi.fn()}
			/>,
		);
		expect(screen.getByLabelText(/upload logo/i)).toBeInTheDocument();
	});

	it("POSTs the selected file to the app logo endpoint and calls onUploaded", async () => {
		const onUploaded = vi.fn();
		render(
			<AppLogoPicker
				applicationId="11111111-1111-1111-1111-111111111111"
				onUploaded={onUploaded}
				onRemoved={vi.fn()}
			/>,
		);
		const input = screen.getByLabelText(/upload logo/i) as HTMLInputElement;
		const file = new File(["x"], "logo.png", { type: "image/png" });
		fireEvent.change(input, { target: { files: [file] } });
		await waitFor(() => expect(onUploaded).toHaveBeenCalled());
		expect(fetchSpy).toHaveBeenCalledWith(
			expect.stringContaining(
				"/api/applications/11111111-1111-1111-1111-111111111111/logo",
			),
			expect.objectContaining({ method: "POST" }),
		);
	});

	it("DELETEs the logo and calls onRemoved when Remove is clicked", async () => {
		fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }));
		const onRemoved = vi.fn();
		render(
			<AppLogoPicker
				applicationId="11111111-1111-1111-1111-111111111111"
				onUploaded={vi.fn()}
				onRemoved={onRemoved}
			/>,
		);
		fireEvent.click(screen.getByRole("button", { name: /remove/i }));
		await waitFor(() => expect(onRemoved).toHaveBeenCalled());
		expect(fetchSpy).toHaveBeenCalledWith(
			expect.stringContaining(
				"/api/applications/11111111-1111-1111-1111-111111111111/logo",
			),
			expect.objectContaining({ method: "DELETE" }),
		);
	});
});
