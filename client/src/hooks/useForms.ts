/**
 * React Query hooks for forms management using openapi-react-query pattern
 * All hooks use the centralized api client which handles X-Organization-Id automatically
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import type { components } from "@/lib/v1";
import type { FormSubmission, FormExecutionResponse } from "@/lib/client-types";

import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

type FormCreate = components["schemas"]["FormCreate"];
type FormUpdate = components["schemas"]["FormUpdate"];
type FormPublic = components["schemas"]["FormPublic"];

/** Helper to extract error message from API error response */
function getErrorMessage(error: unknown, fallback: string): string {
	if (typeof error === "object" && error && "message" in error) {
		return String((error as Record<string, unknown>)["message"]);
	}
	return fallback;
}

/**
 * Get all forms
 */
export async function getForms(): Promise<FormPublic[]> {
	const { data, error } = await apiClient.GET("/api/forms");
	if (error) throw new Error(getErrorMessage(error, "Failed to fetch forms"));
	return data || [];
}

/**
 * Get a specific form by ID
 */
export async function getForm(formId: string): Promise<FormPublic> {
	const { data, error } = await apiClient.GET("/api/forms/{form_id}", {
		params: { path: { form_id: formId } },
	});
	if (error) throw new Error(getErrorMessage(error, "Failed to fetch form"));
	return data!;
}

/**
 * Create a new form
 */
export async function createForm(
	request: FormCreate,
): Promise<FormPublic> {
	const { data, error } = await apiClient.POST("/api/forms", {
		body: request,
	});
	if (error) throw new Error(getErrorMessage(error, "Failed to create form"));
	return data!;
}

/**
 * Update a form
 */
export async function updateForm(
	formId: string,
	request: FormUpdate,
): Promise<FormPublic> {
	const { data, error } = await apiClient.PATCH("/api/forms/{form_id}", {
		params: { path: { form_id: formId } },
		body: request,
	});
	if (error) throw new Error(getErrorMessage(error, "Failed to update form"));
	return data!;
}

/**
 * Delete a form (soft delete - sets isActive=false)
 */
export async function deleteForm(formId: string): Promise<void> {
	const { error } = await apiClient.DELETE("/api/forms/{form_id}", {
		params: { path: { form_id: formId } },
	});
	if (error)
		throw new Error(getErrorMessage(error, "Failed to delete form"));
}

/**
 * Execute a form to run workflow
 */
export async function submitForm(
	submission: FormSubmission,
): Promise<FormExecutionResponse> {
	const { data, error } = await apiClient.POST(
		"/api/forms/{form_id}/execute",
		{
			params: { path: { form_id: submission.form_id } },
			body: submission.form_data,
		},
	);
	if (error || !data) {
		throw new Error(getErrorMessage(error, "Failed to submit form"));
	}
	return data as FormExecutionResponse;
}

/**
 * Query hook to fetch all forms
 */
export function useForms() {
	const { user } = useAuth();

	return $api.useQuery(
		"get",
		"/api/forms",
		{},
		{
			queryKey: ["forms"],
			// Only fetch when authenticated
			enabled: !!user,
			// Don't use cached data from previous scope
			staleTime: 0,
			// Always refetch when component mounts (navigating to page)
			refetchOnMount: "always",
		},
	);
}

/**
 * Query hook to fetch a single form by ID
 */
export function useForm(formId: string | undefined) {
	if (!formId) {
		return $api.useQuery(
			"get",
			"/api/forms/{form_id}",
			{ params: { path: { form_id: "" } } },
			{
				queryKey: ["forms", formId],
				enabled: false,
			},
		);
	}

	return $api.useQuery(
		"get",
		"/api/forms/{form_id}",
		{ params: { path: { form_id: formId } } },
		{
			queryKey: ["forms", formId],
			enabled: !!formId,
		},
	);
}

/**
 * Mutation hook to create a form
 */
export function useCreateForm() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"post",
		"/api/forms",
		{
			onSuccess: (_responseData, variables) => {
				queryClient.invalidateQueries({ queryKey: ["forms"] });
				const name = (variables.body as FormCreate)?.name;
				toast.success("Form created", {
					description: `Form "${name}" has been created`,
				});
			},
			onError: (error) => {
				toast.error("Failed to create form", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Mutation hook to update a form
 */
export function useUpdateForm() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"patch",
		"/api/forms/{form_id}",
		{
			onSuccess: (_responseData, variables) => {
				const formId = (
					variables.params as { path: { form_id: string } }
				).path.form_id;
				queryClient.invalidateQueries({ queryKey: ["forms"] });
				queryClient.invalidateQueries({
					queryKey: ["forms", formId],
				});
				toast.success("Form updated", {
					description: "The form has been updated successfully",
				});
			},
			onError: (error) => {
				toast.error("Failed to update form", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Mutation hook to delete a form
 */
export function useDeleteForm() {
	const queryClient = useQueryClient();

	return $api.useMutation(
		"delete",
		"/api/forms/{form_id}",
		{
			onSuccess: () => {
				queryClient.invalidateQueries({ queryKey: ["forms"] });
				toast.success("Form deleted", {
					description: "The form has been deactivated",
				});
			},
			onError: (error) => {
				toast.error("Failed to delete form", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}

/**
 * Mutation hook to submit a form and execute workflow
 */
export function useSubmitForm() {
	return $api.useMutation(
		"post",
		"/api/forms/{form_id}/execute",
		{
			onSuccess: (responseData) => {
				toast.success("Workflow execution started", {
					description: `Execution ID: ${(responseData as FormExecutionResponse).execution_id}`,
				});
			},
			onError: (error) => {
				toast.error("Failed to submit form", {
					description: getErrorMessage(error, "Unknown error"),
				});
			},
		},
	);
}
