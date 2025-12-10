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
import { Shield, AlertCircle, Loader2 } from "lucide-react";
import { useCreateUser } from "@/hooks/useUsers";
import { useOrganizations } from "@/hooks/useOrganizations";
import { toast } from "sonner";
import type { components } from "@/lib/v1";

type Organization = components["schemas"]["OrganizationPublic"];

interface CreateUserDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

// Extract dialog content to separate component for key-based remounting
function CreateUserDialogContent({
	onOpenChange,
}: {
	onOpenChange: (open: boolean) => void;
}) {
	const [email, setEmail] = useState("");
	const [displayName, setDisplayName] = useState("");
	const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);
	const [orgId, setOrgId] = useState<string>("");
	const [validationError, setValidationError] = useState<string | null>(null);

	const createMutation = useCreateUser();
	const { data: organizations, isLoading: orgsLoading } = useOrganizations();

	const validateForm = (): boolean => {
		if (!email || !email.includes("@")) {
			setValidationError("Please enter a valid email address");
			return false;
		}
		if (!displayName || displayName.trim().length === 0) {
			setValidationError("Please enter a display name");
			return false;
		}
		if (!isPlatformAdmin && !orgId) {
			setValidationError(
				"Please select an organization for non-admin users",
			);
			return false;
		}
		if (isPlatformAdmin && orgId) {
			setValidationError(
				"Platform administrators cannot be assigned to an organization",
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

		try {
			await createMutation.mutateAsync({
				body: {
					email: email.trim(),
					name: displayName.trim(),
					is_active: true,
					is_superuser: isPlatformAdmin,
					user_type: isPlatformAdmin ? "PLATFORM" : "ORG",
					organization_id: isPlatformAdmin ? null : orgId || null,
				},
			});

			toast.success("User created successfully", {
				description: `${displayName} (${email}) has been added to the platform`,
			});

			onOpenChange(false);
		} catch (error) {
			const errorMessage =
				error instanceof Error
					? error.message
					: "Unknown error occurred";
			toast.error("Failed to create user", {
				description: errorMessage,
			});
		}
	};

	return (
		<DialogContent className="sm:max-w-[500px]">
			<DialogHeader>
				<DialogTitle>Create New User</DialogTitle>
				<DialogDescription>
					Add a new user to the platform before they log in for the
					first time
				</DialogDescription>
			</DialogHeader>

			<form onSubmit={handleSubmit} className="space-y-4 mt-4">
				{validationError && (
					<Alert variant="destructive">
						<AlertCircle className="h-4 w-4" />
						<AlertDescription>{validationError}</AlertDescription>
					</Alert>
				)}

				<div className="space-y-2">
					<Label htmlFor="email">Email Address</Label>
					<Input
						id="email"
						type="email"
						placeholder="user@example.com"
						value={email}
						onChange={(e) => setEmail(e.target.value)}
						required
					/>
					<p className="text-xs text-muted-foreground">
						The user's email address for authentication
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
					<p className="text-xs text-muted-foreground">
						The name that will be shown in the platform
					</p>
				</div>

				<div className="space-y-2">
					<Label htmlFor="userType">User Type</Label>
					<Combobox
						id="userType"
						value={isPlatformAdmin ? "platform" : "org"}
						onValueChange={(value) =>
							setIsPlatformAdmin(value === "platform")
						}
						options={[
							{
								value: "platform",
								label: "Platform Administrator",
								description:
									"Full access to all organizations and settings",
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

				{!isPlatformAdmin && (
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
							The organization this user belongs to
						</p>
					</div>
				)}

				{isPlatformAdmin && (
					<Alert>
						<Shield className="h-4 w-4" />
						<AlertDescription>
							Platform administrators have unrestricted access to
							all features, organizations, and settings. Use this
							role carefully.
						</AlertDescription>
					</Alert>
				)}

				<DialogFooter>
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={createMutation.isPending}
					>
						Cancel
					</Button>
					<Button type="submit" disabled={createMutation.isPending}>
						{createMutation.isPending && (
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
						)}
						Create User
					</Button>
				</DialogFooter>
			</form>
		</DialogContent>
	);
}

export function CreateUserDialog({
	open,
	onOpenChange,
}: CreateUserDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			{open && <CreateUserDialogContent onOpenChange={onOpenChange} />}
		</Dialog>
	);
}
