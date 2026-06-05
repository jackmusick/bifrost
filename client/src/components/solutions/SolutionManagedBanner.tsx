/**
 * SolutionManagedBanner
 *
 * Shown at the top of an entity editor when the entity is managed by a deployed
 * Solution (`is_solution_managed`). Solution-managed entities are read-only on
 * the platform — the single writer is deployment (success-criteria §3.2,
 * criterion 6). Editors render this banner and disable their save/delete
 * controls; the API rejects the mutation regardless, so this is purely the
 * read-only *affordance*.
 */

import { Lock } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export interface SolutionManagedBannerProps {
	/** Entity noun for the message, e.g. "workflow", "form", "agent". */
	entityLabel?: string;
}

export function SolutionManagedBanner({
	entityLabel = "entity",
}: SolutionManagedBannerProps) {
	return (
		<Alert data-testid="solution-managed-banner">
			<Lock className="h-4 w-4" />
			<AlertTitle>Managed by a Solution</AlertTitle>
			<AlertDescription>
				This {entityLabel} was installed by a Solution and is read-only here.
				Changes are made by re-deploying the Solution, not edited on the
				platform.
			</AlertDescription>
		</Alert>
	);
}

export default SolutionManagedBanner;
