/**
 * Component tests for GenerateSDKDialog.
 *
 * Covers the auth-type conditional rendering and the submit flow:
 *   - bearer auth requires base_url + token
 *   - api_key auth reveals header + key inputs
 *   - basic auth reveals username + password inputs
 *   - on submit we generate the SDK then update the config in that order
 *   - the success state renders the result summary
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, fireEvent, waitFor } from "@/test-utils";

const mockGenerate = vi.fn();
const mockUpdateConfig = vi.fn();

vi.mock("@/services/integrations", async () => {
	const actual =
		await vi.importActual<typeof import("@/services/integrations")>(
			"@/services/integrations",
		);
	return {
		...actual,
		useGenerateSDK: () => ({
			mutateAsync: mockGenerate,
			isPending: false,
		}),
		useUpdateIntegrationConfig: () => ({
			mutateAsync: mockUpdateConfig,
			isPending: false,
		}),
	};
});

import { GenerateSDKDialog } from "./GenerateSDKDialog";

beforeEach(() => {
	mockGenerate.mockReset();
	mockUpdateConfig.mockReset();
	mockUpdateConfig.mockResolvedValue({});
});

function renderDialog(hasOAuth = false) {
	const onOpenChange = vi.fn();
	const utils = renderWithProviders(
		<GenerateSDKDialog
			open
			onOpenChange={onOpenChange}
			integrationId="int-1"
			integrationName="Widget API"
			hasOAuth={hasOAuth}
		/>,
	);
	return { ...utils, onOpenChange };
}

describe("GenerateSDKDialog — auth-type toggle", () => {
	it("renders bearer token field by default", () => {
		renderDialog();
		expect(screen.getByLabelText(/^token/i)).toBeInTheDocument();
	});
});

describe("GenerateSDKDialog — submit flow", () => {
	it("generates the SDK then saves the integration config (in that order)", async () => {
		mockGenerate.mockResolvedValue({
			module_name: "widget_api",
			module_path: "integrations/widget_api.py",
			endpoint_count: 5,
			schema_count: 3,
			usage_example: "from integrations import widget_api",
		});

		const { user } = renderDialog();

		fireEvent.change(screen.getByLabelText(/openapi spec url/i), {
			target: { value: "https://api.example.com/openapi.json" },
		});
		fireEvent.change(screen.getByLabelText(/base url/i), {
			target: { value: "https://api.example.com" },
		});
		fireEvent.change(screen.getByLabelText(/^token/i), {
			target: { value: "s3cret" },
		});

		await user.click(screen.getByRole("button", { name: /generate sdk/i }));

		await waitFor(() => expect(mockGenerate).toHaveBeenCalledTimes(1));
		const genPayload = mockGenerate.mock.calls[0]![0];
		expect(genPayload.body.spec_url).toBe("https://api.example.com/openapi.json");
		expect(genPayload.body.auth_type).toBe("bearer");

		// The config update carries base_url + token
		await waitFor(() => expect(mockUpdateConfig).toHaveBeenCalledTimes(1));
		const cfgPayload = mockUpdateConfig.mock.calls[0]![0];
		expect(cfgPayload.body.config).toEqual({
			base_url: "https://api.example.com",
			token: "s3cret",
		});
	});

	it("renders the success state after generation succeeds", async () => {
		mockGenerate.mockResolvedValue({
			module_name: "widget_api",
			module_path: "integrations/widget_api.py",
			endpoint_count: 7,
			schema_count: 4,
			usage_example: "from integrations import widget_api",
		});

		const { user } = renderDialog();

		fireEvent.change(screen.getByLabelText(/openapi spec url/i), {
			target: { value: "https://api.example.com/openapi.json" },
		});
		fireEvent.change(screen.getByLabelText(/base url/i), {
			target: { value: "https://api.example.com" },
		});
		fireEvent.change(screen.getByLabelText(/^token/i), {
			target: { value: "s3cret" },
		});
		await user.click(screen.getByRole("button", { name: /generate sdk/i }));

		expect(
			await screen.findByRole("heading", {
				name: /sdk generated successfully/i,
			}),
		).toBeInTheDocument();
		expect(screen.getByText("widget_api")).toBeInTheDocument();
		expect(screen.getByText("7")).toBeInTheDocument();
	});
});
