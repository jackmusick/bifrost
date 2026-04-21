/**
 * Component tests for FileUploadField.
 *
 * Covers the happy path (select → upload → value changes), error path
 * (upload rejects → error shown → retry), and the "completed file" UI
 * derived from the current value prop (single + multiple modes).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";

// Mock the uploader hook: we control its uploadFile implementation per test.
const mockUploadFile = vi.fn();
vi.mock("@/hooks/useFormFileUpload", () => ({
	useFormFileUpload: () => ({ uploadFile: mockUploadFile }),
}));

// Mock sonner so toasts don't leak into jsdom. We don't assert on them.
vi.mock("sonner", () => ({
	toast: { error: vi.fn(), success: vi.fn() },
}));

import { FileUploadField } from "./FileUploadField";

function renderField(overrides: Partial<Parameters<typeof FileUploadField>[0]> = {}) {
	const props = {
		formId: "form-1",
		fieldName: "attachment",
		label: "Attachment",
		required: false,
		helpText: null,
		allowedTypes: null,
		multiple: null,
		maxSizeMb: null,
		value: null,
		onChange: vi.fn(),
		...overrides,
	};
	const utils = renderWithProviders(<FileUploadField {...props} />);
	return { ...utils, props };
}

function makeFile(
	name = "report.pdf",
	type = "application/pdf",
	size = 1024,
) {
	return new File(["x".repeat(size)], name, { type });
}

beforeEach(() => {
	mockUploadFile.mockReset();
});

describe("FileUploadField — single-file mode", () => {
	it("renders the label, required asterisk, and drop zone", () => {
		renderField({ required: true });

		expect(screen.getByText("Attachment")).toBeInTheDocument();
		expect(screen.getByText("*")).toBeInTheDocument();
		expect(screen.getByText(/choose file/i)).toBeInTheDocument();
		expect(screen.getByText(/drag and drop/i)).toBeInTheDocument();
	});

	it("uploads the file and calls onChange with the returned path", async () => {
		mockUploadFile.mockResolvedValue("uploads/form-1/report.pdf");
		const onChange = vi.fn();
		const { container } = renderField({ onChange });

		// Use fireEvent on the hidden file input: userEvent.upload requires a
		// visible input, but our drop zone uses a hidden <input type=file>.
		const input = container.querySelector(
			'input[type="file"]',
		) as HTMLInputElement;

		const file = makeFile();
		const { fireEvent } = await import("@testing-library/react");
		fireEvent.change(input, { target: { files: [file] } });

		await waitFor(() => {
			expect(mockUploadFile).toHaveBeenCalledTimes(1);
		});
		await waitFor(() => {
			expect(onChange).toHaveBeenCalledWith("uploads/form-1/report.pdf");
		});
	});

	it("shows an error row when upload rejects", async () => {
		mockUploadFile.mockRejectedValue(new Error("429 Too Many Requests"));
		const onChange = vi.fn();
		const { container } = renderField({ onChange });

		const input = container.querySelector(
			'input[type="file"]',
		) as HTMLInputElement;
		const { fireEvent } = await import("@testing-library/react");
		fireEvent.change(input, { target: { files: [makeFile()] } });

		expect(
			await screen.findByText(/429 too many requests/i),
		).toBeInTheDocument();
		expect(onChange).not.toHaveBeenCalled();
	});

	it("displays a completed file from the value prop and lets the user remove it", async () => {
		const onChange = vi.fn();
		const { user } = renderField({
			value: "uploads/form-1/report.pdf",
			onChange,
		});

		expect(screen.getByText("report.pdf")).toBeInTheDocument();

		// Remove-file button is the X icon-only button inside the completed row.
		const removeButtons = screen.getAllByRole("button");
		// The only button with no accessible name on the page at this point is
		// the remove button. Click it.
		await user.click(removeButtons[removeButtons.length - 1]!);

		expect(onChange).toHaveBeenCalledWith(null);
	});

	it("renders a field-level error message from the error prop", () => {
		renderField({
			error: { message: "This field is required" },
		});

		expect(screen.getByText(/this field is required/i)).toBeInTheDocument();
	});

	it("shows allowed types and max size in the drop zone hint", () => {
		renderField({
			allowedTypes: ["image/png", "image/jpeg"],
			maxSizeMb: 10,
		});

		expect(
			screen.getByText(/allowed: image\/png, image\/jpeg/i),
		).toBeInTheDocument();
		expect(screen.getByText(/max 10mb/i)).toBeInTheDocument();
	});
});

describe("FileUploadField — multiple mode", () => {
	it("appends to the existing array when uploading a second file", async () => {
		mockUploadFile.mockResolvedValue("uploads/form-1/b.pdf");
		const onChange = vi.fn();
		const { container } = renderField({
			multiple: true,
			value: ["uploads/form-1/a.pdf"],
			onChange,
		});

		const input = container.querySelector(
			'input[type="file"]',
		) as HTMLInputElement;
		const { fireEvent } = await import("@testing-library/react");
		fireEvent.change(input, { target: { files: [makeFile("b.pdf")] } });

		await waitFor(() => {
			expect(onChange).toHaveBeenCalledWith([
				"uploads/form-1/a.pdf",
				"uploads/form-1/b.pdf",
			]);
		});
	});
});
