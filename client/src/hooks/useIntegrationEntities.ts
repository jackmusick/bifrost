/**
 * Hook to fetch entities from a data provider for integration entity selection
 */

import { useQuery } from "@tanstack/react-query";
import {
	getDataProviderOptions,
	type DataProviderOption,
} from "@/services/dataProviders";

export function useIntegrationEntities(dataProviderId?: string | null) {
	return useQuery<DataProviderOption[]>({
		queryKey: ["integration-entities", dataProviderId],
		queryFn: async () => {
			if (!dataProviderId) {
				return [];
			}
			return getDataProviderOptions(dataProviderId);
		},
		enabled: !!dataProviderId,
		staleTime: 5 * 60 * 1000, // 5 minutes
	});
}
