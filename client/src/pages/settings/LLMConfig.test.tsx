import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test-utils";
import { LLMConfig } from "./LLMConfig";

const mockUseQuery = vi.fn();
const mockUseMutation = vi.fn();
const mockTestConnection = vi.fn();
const mockTestSavedConnection = vi.fn();
const mockSaveConfig = vi.fn();
const mockRefetchConfig = vi.fn();
const mockRefetchEmbedding = vi.fn();
const embeddingConfig = {
	model: "",
	dimensions: 1536,
	endpoint: null,
	is_configured: false,
	api_key_set: false,
	uses_llm_key: false,
};

vi.mock("@/lib/api-client", () => ({
	$api: {
		useQuery: (...args: unknown[]) => mockUseQuery(...args),
		useMutation: (...args: unknown[]) => mockUseMutation(...args),
	},
	authFetch: vi.fn(),
}));

vi.mock("@/stores/notificationStore", () => ({
	useNotificationStore: (
		selector: (state: { notifications: unknown[] }) => unknown,
	) => selector({ notifications: [] }),
}));

vi.mock("@/services/ai-pricing", () => ({
	listPricing: vi.fn(async () => ({
		pricing: [],
		models_without_pricing: [],
	})),
	createPricing: vi.fn(),
	updatePricing: vi.fn(),
	deletePricing: vi.fn(),
}));

vi.mock("sonner", () => ({
	toast: {
		success: vi.fn(),
		error: vi.fn(),
	},
}));

describe("LLMConfig", () => {
	beforeEach(() => {
		mockUseQuery.mockReset();
		mockUseMutation.mockReset();
		mockTestConnection.mockReset();
		mockTestSavedConnection.mockReset();
		mockSaveConfig.mockReset();
		mockRefetchConfig.mockReset();
		mockRefetchEmbedding.mockReset();

		mockTestConnection.mockResolvedValue({
			success: true,
			message: "Connected to Azure OpenAI. Listed 1 model(s).",
			models: [
				{
					id: "azure-gpt-4.1",
					display_name: "Azure GPT 4.1",
				},
			],
		});
		mockTestSavedConnection.mockResolvedValue({
			success: true,
			message: "Connected to Azure OpenAI. Listed 1 model(s).",
			models: [
				{
					id: "AI21-Jamba-1.5-Large",
					display_name: "AI21 Jamba 1.5 Large",
				},
			],
		});
		mockSaveConfig.mockResolvedValue({});

		const testMutation = { mutateAsync: mockTestConnection };
		const testSavedMutation = { mutateAsync: mockTestSavedConnection };
		const saveMutation = { mutateAsync: mockSaveConfig };
		const defaultMutation = { mutateAsync: vi.fn() };

		mockUseQuery.mockImplementation((_method: string, path: string) => {
			if (path === "/api/admin/llm/config") {
				return {
					data: undefined,
					isLoading: false,
					refetch: mockRefetchConfig,
				};
			}
			if (path === "/api/admin/llm/embedding-config") {
				return {
					data: embeddingConfig,
					isLoading: false,
					refetch: mockRefetchEmbedding,
				};
			}
			return {
				data: undefined,
				isLoading: false,
				refetch: vi.fn(),
			};
		});

		mockUseMutation.mockImplementation((_method: string, path: string) => {
			if (path === "/api/admin/llm/test") {
				return testMutation;
			}
			if (path === "/api/admin/llm/test-saved") {
				return testSavedMutation;
			}
			if (path === "/api/admin/llm/config") {
				return saveMutation;
			}
			return defaultMutation;
		});
	});

	it("tests an OpenAI-compatible endpoint without sending the gpt-4o fallback", async () => {
		const { user } = renderWithProviders(<LLMConfig />);

		const endpointInputs = screen.getAllByLabelText("API Endpoint");
		await user.clear(endpointInputs[0]);
		await user.type(
			endpointInputs[0],
			"https://example.openai.azure.com/openai/v1",
		);

		const apiKeyInputs = screen.getAllByLabelText("API Key");
		await user.type(apiKeyInputs[0], "sk-test-key");
		await user.click(screen.getAllByRole("button", { name: /test/i })[0]);

		await waitFor(() => expect(mockTestConnection).toHaveBeenCalled());
		expect(mockTestConnection).toHaveBeenCalledWith({
			body: {
				provider: "openai",
				api_key: "sk-test-key",
				endpoint: "https://example.openai.azure.com/openai/v1",
			},
		});

		await waitFor(() =>
			expect(screen.getByText("Azure GPT 4.1")).toBeInTheDocument(),
		);

		await user.click(
			screen.getByRole("button", { name: /save configuration/i }),
		);

		await waitFor(() => expect(mockSaveConfig).toHaveBeenCalled());
		expect(mockSaveConfig).toHaveBeenCalledWith({
			body: expect.objectContaining({
				provider: "openai",
				model: "azure-gpt-4.1",
				api_key: "sk-test-key",
				endpoint: "https://example.openai.azure.com/openai/v1",
			}),
		});
	});

	it("preserves saved deployment model when provider model list omits it", async () => {
		const savedConfig = {
			provider: "openai",
			model: "DeepSeek-V4-Flash",
			endpoint:
				"https://bifrost-integrations-resource.openai.azure.com/openai/v1",
			max_tokens: 4096,
			default_system_prompt: null,
			summarization_model: null,
			tuning_model: null,
			is_configured: true,
			api_key_set: true,
		};

		mockUseQuery.mockImplementation((_method: string, path: string) => {
			if (path === "/api/admin/llm/config") {
				return {
					data: savedConfig,
					isLoading: false,
					refetch: mockRefetchConfig,
				};
			}
			if (path === "/api/admin/llm/embedding-config") {
				return {
					data: embeddingConfig,
					isLoading: false,
					refetch: mockRefetchEmbedding,
				};
			}
			return {
				data: undefined,
				isLoading: false,
				refetch: vi.fn(),
			};
		});

		const { user } = renderWithProviders(<LLMConfig />);

		await waitFor(() => expect(mockTestSavedConnection).toHaveBeenCalled());
		await waitFor(() =>
			expect(
				screen.getByText("DeepSeek-V4-Flash (configured)"),
			).toBeInTheDocument(),
		);

		await user.click(
			screen.getByRole("button", { name: /save configuration/i }),
		);

		await waitFor(() => expect(mockSaveConfig).toHaveBeenCalled());
		expect(mockSaveConfig).toHaveBeenCalledWith({
			body: expect.objectContaining({
				provider: "openai",
				model: "DeepSeek-V4-Flash",
				api_key: undefined,
				endpoint:
					"https://bifrost-integrations-resource.openai.azure.com/openai/v1",
			}),
		});
	});
});
