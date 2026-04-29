/**
 * ModelPicker — thin wrapper around <ModelSelect /> for the chat composer.
 *
 * Loads the configured-provider's /v1/models response and the platform
 * catalog (synced from LiteLLM), then defers all rendering to the canonical
 * ModelSelect component so the chat picker, the org allowlist, and the
 * default-model picker all share the same UX.
 */

import { useEffect, useMemo, useState } from "react";

import {
	listPlatformModels,
	resellerForEndpoint,
	type PlatformModel,
} from "@/services/platformModels";
import { $api } from "@/lib/api-client";
import { ModelSelect, type ModelSelectModel } from "./ModelSelect";

interface ModelPickerProps {
	value: string | null | undefined;
	allowedModelIds?: string[];
	onChange: (modelId: string) => void;
	disabled?: boolean;
}

export function ModelPicker({
	value,
	allowedModelIds,
	onChange,
	disabled = false,
}: ModelPickerProps) {
	const [catalog, setCatalog] = useState<PlatformModel[]>([]);

	useEffect(() => {
		let cancelled = false;
		listPlatformModels()
			.then((res) => {
				if (!cancelled) setCatalog(res.models);
			})
			.catch(() => {
				/* ignore — picker still works without enriched info */
			});
		return () => {
			cancelled = true;
		};
	}, []);

	const llmConfigQuery = $api.useQuery(
		"get",
		"/api/admin/llm/config",
		undefined,
		{ staleTime: 5 * 60 * 1000 },
	);
	const reseller = resellerForEndpoint(llmConfigQuery.data?.endpoint ?? null);

	const providerModelsQuery = $api.useQuery(
		"get",
		"/api/admin/llm/models",
		undefined,
		{ retry: false, staleTime: 5 * 60 * 1000 },
	);
	const providerModels: ModelSelectModel[] = providerModelsQuery.data?.models ?? [];

	const catalogById = useMemo(() => {
		const idx: Record<string, PlatformModel> = {};
		for (const m of catalog) idx[m.model_id] = m;
		return idx;
	}, [catalog]);

	return (
		<ModelSelect
			models={providerModels}
			catalog={catalogById}
			reseller={reseller}
			restrictToIds={allowedModelIds}
			value={value ?? null}
			onChange={(v) => v && onChange(v)}
			disabled={disabled}
			placeholder="Choose a model…"
			className="min-w-[14rem]"
		/>
	);
}
