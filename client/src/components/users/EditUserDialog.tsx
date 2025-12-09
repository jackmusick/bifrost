import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Switch } from "@/components/ui/switch";
import { Shield, AlertCircle, Loader2, AlertTriangle } from "lucide-react";
import { useUpdateUser } from "@/hooks/useUsers";
import { useOrganizations } from "@/hooks/useOrganizations";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

type User = components["schemas"]["UserPublic"];
type Organization = components["schemas"]["OrganizationPublic"];

interface EditUserDialogProps {
	user: User | undefined;
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

// Extract dialog content to separate component for key-based remounting
function EditUserDialogContent({
	user,
	onOpenChange,
}: {
	user: User;
	onOpenChange: (open: boolean) => void;
}) {
	const [displayName, setDisplayName] = useState(user.name || "");
	const [isActive, setIsActive] = useState(user.is_active);
	const [isPlatformUser, setIsPlatformUser] = useState(
		user.user_type === "PLATFORM",
	);
	const [isSuperuser, setIsSuperuser] = useState(user.is_superuser);
	const [orgId, setOrgId] = useState<string>("");
	const [validationError, setValidationError] = useState<string | null>(null);

	const updateMutation = useUpdateUser();
	const { data: organizations, isLoading: orgsLoading } = useOrganizations();
	const { user: currentUser } = useAuth();

	// Check if editing own account
	const isEditingSelf = !!(currentUser && user.id === currentUser.id);

	const isRoleChanging = (user.user_type === "PLATFORM") !== isPlatformUser;
	const isDemoting = user.user_type === "PLATFORM" && !isPlatformUser;
	const isPromoting = user.user_type !== "PLATFORM" && isPlatformUser;

	const validateForm = (): boolean => {
		if (!displayName || displayName.trim().length === 0) {
			setValidationError("Please enter a display name");
			return false;
		}
		if (isDemoting && !orgId) {
			setValidationError(
				"Please select an organization when demoting to org user",
			);
			return false;
		}
		if (isPlatformUser && orgId) {
			setValidationError(
				"Platform users cannot be assigned to an organization",
			);
			return false;
		}
		setValidationError(null);
		return true;
	};

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		if (!validateForm()) {
			return;
		}

		// Build request body with all fields (nulls for unchanged)
		// When editing self, only allow displayName changes
		const body = {
			name:
				displayName.trim() !== (user.name || "")
					? displayName.trim()
					: null,
			is_active:
				!isEditingSelf && isActive !== user.is_active ? isActive : null,
			user_type:
				!isEditingSelf && isRoleChanging
					? isPlatformUser
						? "PLATFORM"
						: "ORG"
					: null,
			is_superuser:
				!isEditingSelf &&
				isPlatformUser &&
				isSuperuser !== user.is_superuser
					? isSuperuser
					: null,
			organization_id:
				!isEditingSelf && isDemoting ? orgId || null : null,
		};

		// If no actual changes, just close
		if (
			body.name === null &&
			body.is_active === null &&
			body.user_type === null &&
			body.is_superuser === null &&
			body.organization_id === null
		) {
			toast.info("No changes to save");
			onOpenChange(false);
			return;
		}

		try {
			await updateMutation.mutateAsync({
				userId: user.id,
				body,
			});

			toast.success("User updated successfully", {
				description: `Changes to ${user.name || user.email} have been saved`,
			});

			onOpenChange(false);
		} catch (error) {
			const errorMessage =
				error instanceof Error
					? error.message
					: "Unknown error occurred";
			toast.error("Failed to update user", {
				description: errorMessage,
			});
		}
	};

	return (
		<DialogContent className="sm:max-w-[500px]">
			<DialogHeader>
				<DialogTitle>Edit User</DialogTitle>
				<DialogDescription>
					Update user details and permissions for {user.email}
				</DialogDescription>
			</DialogHeader>

			<form onSubmit={handleSubmit} className="space-y-4 mt-4">
				{isEditingSelf && (
					<Alert>
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>
							You are editing your own account. You can only
							change your display name. Role and status changes
							must be made by another administrator.
						</AlertDescription>
					</Alert>
				)}

				{validationError && (
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>{validationError}</AlertDescription>
					</Alert>
				)}

				<div className="space-y-2">
					<Label htmlFor="email-display">Email Address</Label>
					<Input
						id="email-display"
						type="email"
						value={user.email}
						disabled
						className="bg-muted"
					/>
					<p className="text-xs text-muted-foreground">
						Email address cannot be changed
					</p>
				</div>

				<div className="space-y-2">
					<Label htmlFor="displayName">Display Name</Label>
					<Input
						id="displayName"
						type="text"
						placeholder="John Doe"
						value={displayName}
						onChange={(e) => setDisplayName(e.target.value)}
						required
					/>
				</div>

				<div className="flex items-center justify-between rounded-lg border p-4">
					<div className="space-y-0.5">
						<Label htmlFor="active">Account Status</Label>
						<p className="text-xs text-muted-foreground">
							{isActive
								? "User can access the platform"
								: "User access is disabled"}
						</p>
					</div>
					<Switch
						id="active"
						checked={isActive}
						onCheckedChange={setIsActive}
						disabled={isEditingSelf}
					/>
				</div>

				<div className="space-y-2">
					<Label htmlFor="userType">User Type</Label>
					<Combobox
						id="userType"
						value={isPlatformUser ? "platform" : "org"}
						onValueChange={(value) =>
							setIsPlatformUser(value === "platform")
						}
						disabled={isEditingSelf}
						options={[
							{
								value: "platform",
								label: "Platform User",
								description:
									"Access to all organizations and settings",
							},
							{
								value: "org",
								label: "Organization User",
								description:
									"Access limited to specific organization",
							},
						]}
						placeholder="Select user type"
					/>
				</div>

				{isPlatformUser && (
					<div className="flex items-center justify-between rounded-lg border p-4">
						<div className="space-y-0.5">
							<Label htmlFor="superuser">Superuser</Label>
							<p className="text-xs text-muted-foreground">
								{isSuperuser
									? "Full administrative privileges"
									: "Standard platform user"}
							</p>
						</div>
						<Switch
							id="superuser"
							checked={isSuperuser}
							onCheckedChange={setIsSuperuser}
							disabled={isEditingSelf}
						/>
					</div>
				)}

				{isDemoting && (
					<>
						<div className="space-y-2">
							<Label htmlFor="organization">Organization</Label>
							<Combobox
								id="organization"
								value={orgId}
								onValueChange={setOrgId}
								options={
									organizations?.map((org: Organization) => {
										const option: {
											value: string;
											label: string;
											description?: string;
										} = {
											value: org.id,
											label: org.name,
										};
										if (org.domain) {
											option.description = `@${org.domain}`;
										}
										return option;
									}) ?? []
								}
								placeholder="Select an organization..."
								searchPlaceholder="Search organizations..."
								emptyText="No organizations found."
								isLoading={orgsLoading}
							/>
							<p className="text-xs text-muted-foreground">
								Required when demoting from Platform User
							</p>
						</div>

						<Alert variant="destructive">
							<AlertTriangle className="h-4 w-4" />
							<AlertDescription>
								You are demoting this user from Platform User to
								Organization User. They will lose access to all
								other organizations and platform settings.
							</AlertDescription>
						</Alert>
					</>
				)}

				{isPromoting && (
					<Alert>
						<Shield className="h-4 w-4" />
						<AlertDescription>
							You are promoting this user to Platform User. They
							will gain access to all features and organizations.
						</AlertDescription>
					</Alert>
				)}

				{isRoleChanging && (
					<div className="rounded-md bg-muted p-4 text-sm">
						<p className="font-medium mb-1">Role Change Summary:</p>
						<ul className="list-disc list-inside space-y-1 text-muted-foreground">
							{isPromoting && (
								<>
									<li>
										User will be promoted to Platform User
									</li>
									<li>
										Organization assignments will be removed
									</li>
									<li>
										Full platform access will be granted
									</li>
								</>
							)}
							{isDemoting && (
								<>
									<li>
										User will be demoted to Organization
										User
									</li>
									<li>
										Platform-wide access will be revoked
									</li>
									<li>
										Access limited to selected organization
									</li>
								</>
							)}
						</ul>
					</div>
				)}

				<DialogFooter>
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={updateMutation.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" disabled={updateMutation.isPending}>
						{updateMutation.isPending && (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						)}
						Save Changes
					</Button>
				</DialogFooter>
			</form>
		</DialogContent>
	);
}

export function EditUserDialog({
	user,
	open,
	onOpenChange,
}: EditUserDialogProps) {
	if (!user) return null;

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			{open && (
				<EditUserDialogContent
					user={user}
					onOpenChange={onOpenChange}
				/>
			)}
		</Dialog>
	);
}
