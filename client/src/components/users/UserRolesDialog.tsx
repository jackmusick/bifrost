import { useState } from "react";
import { Shield } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useUserRoles } from "@/hooks/useUsers";
import {
	useRoles,
	useAssignUsersToRole,
	useRemoveUserFromRole,
} from "@/hooks/useRoles";
import type { components } from "@/lib/v1";
type User = components["schemas"]["UserPublic"];
type RoleResponse = components["schemas"]["RolePublic"];
type UserRolesResponse = components["schemas"]["UserRolesResponse"];
import { toast } from "sonner";

interface UserRolesDialogProps {
	user: User | undefined;
	open: boolean;
	onClose: () => void;
}

// Extract dialog content to separate component for key-based remounting
function UserRolesDialogContent({
	user,
	onClose,
}: {
	user: User;
	onClose: () => void;
}) {
	const { data: userRoles, isLoading: rolesLoading } = useUserRoles(user.id);
	const { data: allRoles, isLoading: allRolesLoading } = useRoles();
	const assignMutation = useAssignUsersToRole();
	const removeMutation = useRemoveUserFromRole();

	const [selectedRoles, setSelectedRoles] = useState<Set<string>>(
		userRoles && (userRoles as UserRolesResponse).roleIds
			? new Set((userRoles as UserRolesResponse).roleIds)
			: new Set(),
	);

	const handleToggleRole = async (roleId: string, checked: boolean) => {
		if (!user) return;

		try {
			if (checked) {
				// Assign role to user
				await assignMutation.mutateAsync({
					params: { path: { role_id: roleId } },
					body: { userIds: [user.id] },
				});
				setSelectedRoles((prev) => new Set([...prev, roleId]));
			} else {
				// Remove role
				await removeMutation.mutateAsync({
					params: { path: { role_id: roleId, user_id: user.id } },
				});
				setSelectedRoles((prev) => {
					const next = new Set(prev);
					next.delete(roleId);
					return next;
				});
			}
		} catch {
			toast.error(`Failed to ${checked ? "assign" : "remove"} role`);
		}
	};

	return (
		<DialogContent className="max-w-2xl">
			<DialogHeader>
				<DialogTitle className="flex items-center gap-2">
					<Shield className="h-5 w-5" />
					Manage Roles - {user.name || user.email}
				</DialogTitle>
				<DialogDescription>
					Assign or remove roles for this user. Roles determine which
					forms the user can access.
				</DialogDescription>
			</DialogHeader>

			<div className="space-y-4">
				{user.is_superuser ? (
					<div className="flex items-center justify-center p-8 rounded-lg border border-yellow-200 bg-yellow-50">
						<div className="text-center text-yellow-900">
							<Shield className="h-8 w-8 mx-auto mb-2 text-yellow-600" />
							<h3 className="font-semibold mb-2">
								Cannot Modify Superuser Roles
							</h3>
							<p className="text-sm text-yellow-700">
								Superusers have full system access and cannot be
								assigned additional roles.
							</p>
						</div>
					</div>
				) : (
					<>
						{rolesLoading || allRolesLoading ? (
							<div className="space-y-2">
								{[...Array(3)].map((_, i) => (
									<Skeleton key={i} className="h-16 w-full" />
								))}
							</div>
						) : allRoles && allRoles.length > 0 ? (
							<div className="space-y-3">
								{allRoles.map((role: RoleResponse) => {
									const isAssigned = selectedRoles.has(
										role.id,
									);
									return (
										<div
											key={role.id}
											className="flex items-start space-x-3 rounded-lg border p-4 hover:bg-accent/50 transition-colors"
										>
											<Checkbox
												id={role.id}
												checked={isAssigned}
												onCheckedChange={(checked) =>
													handleToggleRole(
														role.id,
														checked as boolean,
													)
												}
												disabled={
													assignMutation.isPending ||
													removeMutation.isPending
												}
											/>
											<div className="flex-1 space-y-1">
												<Label
													htmlFor={role.id}
													className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
												>
													{role.name}
												</Label>
												{role.description && (
													<p className="text-sm text-muted-foreground">
														{role.description}
													</p>
												)}
											</div>
										</div>
									);
								})}
							</div>
						) : (
							<div className="text-center py-8 text-muted-foreground">
								No roles available
							</div>
						)}
					</>
				)}
			</div>

			<div className="flex justify-end">
				<Button onClick={onClose}>Close</Button>
			</div>
		</DialogContent>
	);
}

export function UserRolesDialog({ user, open, onClose }: UserRolesDialogProps) {
	if (!user) return null;

	return (
		<Dialog open={open} onOpenChange={onClose}>
			{open && <UserRolesDialogContent user={user} onClose={onClose} />}
		</Dialog>
	);
}
