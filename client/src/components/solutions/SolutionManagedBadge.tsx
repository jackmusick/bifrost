/**
 * SolutionManagedBadge
 *
 * A compact "Managed" lock chip shown on solution-managed entity cards/rows.
 * ADMIN-ONLY (platform admins) — a non-admin sees nothing. Links to the owning
 * Solution's detail view so an operator can jump from any managed entity to the
 * install that owns it. Read-only ENFORCEMENT is server-side regardless; this is
 * purely the operator affordance.
 */
import { Lock } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";

export interface SolutionManagedBadgeProps {
	/** The owning Solution install id (from the entity's solution_id). */
	solutionId: string | null | undefined;
}

export function SolutionManagedBadge({ solutionId }: SolutionManagedBadgeProps) {
	const { isPlatformAdmin } = useAuth();
	if (!isPlatformAdmin || !solutionId) return null;
	return (
		<Link
			to={`/solutions/${solutionId}`}
			className="flex shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
			title="Managed by a Solution — read-only on the platform. Click to view the Solution."
			data-testid="solution-managed-badge"
			onClick={(e) => e.stopPropagation()}
		>
			<Lock className="h-3 w-3" />
			Managed
		</Link>
	);
}

export default SolutionManagedBadge;
