import { authFetch } from "@/lib/api-client";

export type EntityType = "knowledge" | "tables" | "configs" | "integrations";

export interface ImportOptions {
	sourceSecretKey?: string;
	sourceFernetSalt?: string;
	replaceExisting: boolean;
	targetOrganizationId?: string | null; // undefined=from file, null=Global, string=org UUID
}

export interface ImportResultItem {
	name: string;
	status: "created" | "updated" | "skipped" | "error";
	error?: string;
}

export interface ImportResult {
	entity_type: string;
	created: number;
	updated: number;
	skipped: number;
	errors: number;
	warnings: string[];
	details: ImportResultItem[];
}

export async function exportEntities(
	type: EntityType,
	ids: string[],
): Promise<void> {
	const response = await authFetch(`/api/export-import/export/${type}`, {
		method: "POST",
		body: JSON.stringify({ ids }),
	});

	if (!response.ok) {
		throw new Error(`Export failed: ${response.statusText}`);
	}

	const blob = await response.blob();
	const disposition = response.headers.get("Content-Disposition");
	const filename =
		disposition?.match(/filename="(.+)"/)?.[1] || `${type}_export.json`;

	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}

export async function exportAll(ids: {
	knowledge_ids?: string[];
	table_ids?: string[];
	config_ids?: string[];
	integration_ids?: string[];
}): Promise<void> {
	const response = await authFetch("/api/export-import/export/all", {
		method: "POST",
		body: JSON.stringify(ids),
	});

	if (!response.ok) {
		throw new Error(`Export failed: ${response.statusText}`);
	}

	const blob = await response.blob();
	const disposition = response.headers.get("Content-Disposition");
	const filename =
		disposition?.match(/filename="(.+)"/)?.[1] || "bifrost_export.zip";

	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}

export async function importEntities(
	type: EntityType,
	file: File,
	options: ImportOptions,
): Promise<ImportResult> {
	const formData = new FormData();
	formData.append("file", file);
	formData.append("replace_existing", String(options.replaceExisting));
	if (options.sourceSecretKey) {
		formData.append("source_secret_key", options.sourceSecretKey);
	}
	if (options.sourceFernetSalt) {
		formData.append("source_fernet_salt", options.sourceFernetSalt);
	}
	if (options.targetOrganizationId !== undefined) {
		formData.append(
			"target_organization_id",
			options.targetOrganizationId ?? "",
		);
	}

	const response = await authFetch(`/api/export-import/import/${type}`, {
		method: "POST",
		body: formData,
	});

	if (!response.ok) {
		const error = await response
			.json()
			.catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || "Import failed");
	}

	return response.json();
}

export async function importAll(
	file: File,
	options: ImportOptions,
): Promise<ImportResult[]> {
	const formData = new FormData();
	formData.append("file", file);
	formData.append("replace_existing", String(options.replaceExisting));
	if (options.sourceSecretKey) {
		formData.append("source_secret_key", options.sourceSecretKey);
	}
	if (options.sourceFernetSalt) {
		formData.append("source_fernet_salt", options.sourceFernetSalt);
	}
	if (options.targetOrganizationId !== undefined) {
		formData.append(
			"target_organization_id",
			options.targetOrganizationId ?? "",
		);
	}

	const response = await authFetch("/api/export-import/import/all", {
		method: "POST",
		body: formData,
	});

	if (!response.ok) {
		const error = await response
			.json()
			.catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || "Import failed");
	}

	const data = await response.json();
	return data.results;
}
