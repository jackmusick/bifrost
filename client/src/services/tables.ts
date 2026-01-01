/**
 * Tables Service using openapi-react-query pattern
 *
 * All mutations automatically invalidate relevant queries so components
 * reading from useTables() will re-render with fresh data.
 */

import { useQueryClient } from "@tanstack/react-query";
import { $api, apiClient } from "@/lib/api-client";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

// Re-export types from OpenAPI spec
export type TablePublic = components["schemas"]["TablePublic"];
export type TableCreate = components["schemas"]["TableCreate"];
export type TableUpdate = components["schemas"]["TableUpdate"];
export type TableListResponse = components["schemas"]["TableListResponse"];
export type DocumentPublic = components["schemas"]["DocumentPublic"];
export type DocumentCreate = components["schemas"]["DocumentCreate"];
export type DocumentUpdate = components["schemas"]["DocumentUpdate"];
export type DocumentQuery = components["schemas"]["DocumentQuery"];
export type DocumentListResponse = components["schemas"]["DocumentListResponse"];
export type DocumentCountResponse = components["schemas"]["DocumentCountResponse"];

// Query filter operators (JSON-native, user-friendly)
export type QueryOperator =
	| "eq"
	| "ne"
	| "contains"
	| "starts_with"
	| "ends_with"
	| "gt"
	| "gte"
	| "lt"
	| "lte"
	| "in"
	| "is_null"
	| "has_key";

export interface QueryFilter {
	eq?: unknown;
	ne?: unknown;
	contains?: string;
	starts_with?: string;
	ends_with?: string;
	gt?: unknown;
	gte?: unknown;
	lt?: unknown;
	lte?: unknown;
	in?: unknown[];
	is_null?: boolean;
	has_key?: boolean;
}

// Default query values matching API defaults
const DEFAULT_QUERY: DocumentQuery = {
	order_dir: "asc",
	limit: 100,
	offset: 0,
};

// =============================================================================
// Table Hooks
// =============================================================================

/**
 * Hook to fetch all tables
 */
export function useTables(scope?: string) {
	return $api.useQuery(
		"get",
		"/api/tables",
		scope ? { params: { query: { scope } } } : undefined,
	);
}

/**
 * Hook to fetch a single table by name
 */
export function useTable(tableName: string, scope?: string) {
	return $api.useQuery(
		"get",
		"/api/tables/{name}",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
		},
		{ enabled: !!tableName },
	);
}

/**
 * Hook to create a new table
 */
export function useCreateTable() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/tables", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({ queryKey: ["get", "/api/tables"] });
			toast.success("Table created", {
				description: `Table "${data.name}" has been created`,
			});
		},
	});
}

/**
 * Hook to update a table
 */
export function useUpdateTable() {
	const queryClient = useQueryClient();

	return $api.useMutation("patch", "/api/tables/{name}", {
		onSuccess: (data) => {
			queryClient.invalidateQueries({ queryKey: ["get", "/api/tables"] });
			toast.success("Table updated", {
				description: `Table "${data.name}" has been updated`,
			});
		},
	});
}

/**
 * Hook to delete a table
 */
export function useDeleteTable() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/tables/{name}", {
		onSuccess: (_, variables) => {
			const tableName = variables.params.path.name;
			queryClient.invalidateQueries({ queryKey: ["get", "/api/tables"] });
			toast.success("Table deleted", {
				description: `Table "${tableName}" has been deleted`,
			});
		},
	});
}

// =============================================================================
// Document Hooks
// =============================================================================

/**
 * Hook to query documents with filtering and pagination
 */
export function useDocuments(
	tableName: string,
	query: Partial<DocumentQuery> = {},
	scope?: string,
) {
	const fullQuery: DocumentQuery = { ...DEFAULT_QUERY, ...query };

	return $api.useQuery(
		"post",
		"/api/tables/{name}/documents/query",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
			body: fullQuery,
		},
		{ enabled: !!tableName },
	);
}

/**
 * Hook to count documents in a table
 */
export function useDocumentCount(tableName: string, scope?: string) {
	return $api.useQuery(
		"get",
		"/api/tables/{name}/documents/count",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
		},
		{ enabled: !!tableName },
	);
}

/**
 * Hook to insert a new document
 */
export function useInsertDocument() {
	const queryClient = useQueryClient();

	return $api.useMutation("post", "/api/tables/{name}/documents", {
		onSuccess: () => {
			// Invalidate document queries
			queryClient.invalidateQueries({
				queryKey: ["post", "/api/tables/{name}/documents/query"],
			});
			toast.success("Document created", {
				description: "Document has been inserted",
			});
		},
	});
}

/**
 * Hook to update a document
 */
export function useUpdateDocument() {
	const queryClient = useQueryClient();

	return $api.useMutation("patch", "/api/tables/{name}/documents/{doc_id}", {
		onSuccess: () => {
			// Invalidate document queries
			queryClient.invalidateQueries({
				queryKey: ["post", "/api/tables/{name}/documents/query"],
			});
			toast.success("Document updated", {
				description: "Document has been updated",
			});
		},
	});
}

/**
 * Hook to delete a document
 */
export function useDeleteDocument() {
	const queryClient = useQueryClient();

	return $api.useMutation("delete", "/api/tables/{name}/documents/{doc_id}", {
		onSuccess: () => {
			// Invalidate document queries
			queryClient.invalidateQueries({
				queryKey: ["post", "/api/tables/{name}/documents/query"],
			});
			toast.success("Document deleted", {
				description: "Document has been deleted",
			});
		},
	});
}

// =============================================================================
// Imperative API Functions (for use outside React components)
// =============================================================================

/**
 * List tables (imperative)
 */
export async function listTables(scope?: string): Promise<TableListResponse> {
	const { data, error } = await apiClient.GET("/api/tables", {
		params: {
			query: scope ? { scope } : undefined,
		},
	});
	if (error) throw new Error("Failed to list tables");
	return data;
}

/**
 * Get a table by name (imperative)
 */
export async function getTable(
	name: string,
	scope?: string,
): Promise<TablePublic> {
	const { data, error } = await apiClient.GET("/api/tables/{name}", {
		params: {
			path: { name },
			query: scope ? { scope } : undefined,
		},
	});
	if (error) throw new Error("Failed to get table");
	return data;
}

/**
 * Create a table (imperative)
 */
export async function createTable(
	tableData: TableCreate,
	scope?: string,
): Promise<TablePublic> {
	const { data, error } = await apiClient.POST("/api/tables", {
		params: {
			query: scope ? { scope } : undefined,
		},
		body: tableData,
	});
	if (error) throw new Error("Failed to create table");
	return data;
}

/**
 * Update a table (imperative)
 */
export async function updateTable(
	name: string,
	tableData: TableUpdate,
	scope?: string,
): Promise<TablePublic> {
	const { data, error } = await apiClient.PATCH("/api/tables/{name}", {
		params: {
			path: { name },
			query: scope ? { scope } : undefined,
		},
		body: tableData,
	});
	if (error) throw new Error("Failed to update table");
	return data;
}

/**
 * Delete a table (imperative)
 */
export async function deleteTable(name: string, scope?: string): Promise<void> {
	const { error } = await apiClient.DELETE("/api/tables/{name}", {
		params: {
			path: { name },
			query: scope ? { scope } : undefined,
		},
	});
	if (error) throw new Error("Failed to delete table");
}

/**
 * Query documents (imperative)
 */
export async function queryDocuments(
	tableName: string,
	query: Partial<DocumentQuery> = {},
	scope?: string,
): Promise<DocumentListResponse> {
	const fullQuery: DocumentQuery = { ...DEFAULT_QUERY, ...query };
	const { data, error } = await apiClient.POST(
		"/api/tables/{name}/documents/query",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
			body: fullQuery,
		},
	);
	if (error) throw new Error("Failed to query documents");
	return data;
}

/**
 * Insert a document (imperative)
 */
export async function insertDocument(
	tableName: string,
	documentData: DocumentCreate,
	scope?: string,
): Promise<DocumentPublic> {
	const { data, error } = await apiClient.POST(
		"/api/tables/{name}/documents",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
			body: documentData,
		},
	);
	if (error) throw new Error("Failed to insert document");
	return data;
}

/**
 * Get a document by ID (imperative)
 */
export async function getDocument(
	tableName: string,
	documentId: string,
	scope?: string,
): Promise<DocumentPublic> {
	const { data, error } = await apiClient.GET(
		"/api/tables/{name}/documents/{doc_id}",
		{
			params: {
				path: { name: tableName, doc_id: documentId },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error) throw new Error("Failed to get document");
	return data;
}

/**
 * Update a document (imperative)
 */
export async function updateDocument(
	tableName: string,
	documentId: string,
	documentData: DocumentUpdate,
	scope?: string,
): Promise<DocumentPublic> {
	const { data, error } = await apiClient.PATCH(
		"/api/tables/{name}/documents/{doc_id}",
		{
			params: {
				path: { name: tableName, doc_id: documentId },
				query: scope ? { scope } : undefined,
			},
			body: documentData,
		},
	);
	if (error) throw new Error("Failed to update document");
	return data;
}

/**
 * Delete a document (imperative)
 */
export async function deleteDocument(
	tableName: string,
	documentId: string,
	scope?: string,
): Promise<void> {
	const { error } = await apiClient.DELETE(
		"/api/tables/{name}/documents/{doc_id}",
		{
			params: {
				path: { name: tableName, doc_id: documentId },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error) throw new Error("Failed to delete document");
}

/**
 * Count documents (imperative)
 */
export async function countDocuments(
	tableName: string,
	scope?: string,
): Promise<number> {
	const { data, error } = await apiClient.GET(
		"/api/tables/{name}/documents/count",
		{
			params: {
				path: { name: tableName },
				query: scope ? { scope } : undefined,
			},
		},
	);
	if (error) throw new Error("Failed to count documents");
	return data.count;
}
