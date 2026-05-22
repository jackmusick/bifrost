import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { CustomClaimEditor } from "@/components/tables/CustomClaimEditor";
import { CustomClaimsList } from "@/components/tables/CustomClaimsList";
import {
	createClaim,
	deleteClaim,
	listClaims,
	updateClaim,
	type CustomClaim,
} from "@/services/claims";

interface EditingState {
	claim: CustomClaim;
	originalName: string | null;
}

const EMPTY_CLAIM: CustomClaim = {
	id: "00000000-0000-4000-8000-000000000000",
	organization_id: "00000000-0000-4000-8000-000000000000",
	name: "",
	description: "",
	type: "list",
	query: { table: "", select: "" },
};

export function TablesClaimsTab() {
	const [claims, setClaims] = useState<CustomClaim[]>([]);
	const [editing, setEditing] = useState<EditingState | null>(null);
	const [loading, setLoading] = useState(true);

	const loadClaims = useCallback(async (signal?: AbortSignal) => {
		const list = await listClaims({ signal });
		setClaims(list.claims ?? []);
	}, []);

	const refresh = useCallback(async () => {
		setLoading(true);
		try {
			await loadClaims();
		} finally {
			setLoading(false);
		}
	}, [loadClaims]);

	useEffect(() => {
		const controller = new AbortController();
		void (async () => {
			try {
				const list = await listClaims({ signal: controller.signal });
				if (controller.signal.aborted) return;
				setClaims(list.claims ?? []);
			} catch (error) {
				if (controller.signal.aborted) return;
				toast.error(
					error instanceof Error
						? error.message
						: "Failed to load custom claims",
				);
			} finally {
				if (!controller.signal.aborted) {
					setLoading(false);
				}
			}
		})();
		return () => controller.abort();
	}, []);

	async function handleSave(claim: CustomClaim) {
		try {
			if (editing?.originalName) {
				await updateClaim(editing.originalName, {
					description: claim.description,
					type: claim.type,
					query: claim.query,
				});
				toast.success("Claim updated");
			} else {
				await createClaim({
					name: claim.name,
					description: claim.description,
					type: claim.type,
					query: claim.query,
				});
				toast.success("Claim created");
			}
			setEditing(null);
			await refresh();
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : "Failed to save claim",
			);
		}
	}

	async function handleDelete(name: string) {
		try {
			await deleteClaim(name);
			toast.success("Claim deleted");
			await refresh();
		} catch (error) {
			toast.error(
				error instanceof Error
					? error.message
					: "Failed to delete claim",
			);
		}
	}

	if (editing) {
		return (
			<div className="py-4">
				<CustomClaimEditor
					value={editing.claim}
					onChange={(claim) => setEditing({ ...editing, claim })}
					onSave={handleSave}
					onCancel={() => setEditing(null)}
					nameDisabled={editing.originalName !== null}
				/>
			</div>
		);
	}

	return (
		<div className="py-4">
			{loading ? (
				<p className="text-sm text-muted-foreground">
					Loading custom claims...
				</p>
			) : (
				<CustomClaimsList
					claims={claims}
					onAdd={() =>
						setEditing({
							claim: EMPTY_CLAIM,
							originalName: null,
						})
					}
					onEdit={(name) => {
						const claim = claims.find((item) => item.name === name);
						if (!claim) return;
						setEditing({
							claim,
							originalName: claim.name,
						});
					}}
					onDelete={handleDelete}
				/>
			)}
		</div>
	);
}
