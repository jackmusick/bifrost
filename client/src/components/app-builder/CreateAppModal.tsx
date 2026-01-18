/**
 * Create App Modal
 *
 * Modal for creating new applications (code-based only).
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useCreateApplication } from "@/hooks/useApplications";

interface CreateAppModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

/**
 * Internal modal content - rendered fresh each time the dialog opens
 */
function CreateAppModalContent({
	onOpenChange,
}: {
	onOpenChange: (open: boolean) => void;
}) {
	const navigate = useNavigate();
	const { user, isPlatformAdmin } = useAuth();
	const createApplication = useCreateApplication();

	// Form fields - initialize with defaults
	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [slug, setSlug] = useState("");
	const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
	const [organizationId, setOrganizationId] = useState<string | null>(
		isPlatformAdmin ? null : (user?.organizationId ?? null),
	);

	// Auto-generate slug from name
	const handleNameChange = useCallback(
		(newName: string) => {
			setName(newName);
			if (!slugManuallyEdited) {
				const generated = newName
					.toLowerCase()
					.replace(/[^a-z0-9]+/g, "-")
					.replace(/^-|-$/g, "");
				setSlug(generated);
			}
		},
		[slugManuallyEdited],
	);

	const handleSlugChange = useCallback((newSlug: string) => {
		setSlug(newSlug);
		setSlugManuallyEdited(true);
	}, []);

	const handleCreate = useCallback(async () => {
		if (!name.trim()) {
			toast.error("Please enter an application name");
			return;
		}

		try {
			// Ensure slug is valid (generate from name if empty)
			const finalSlug =
				slug ||
				name
					.toLowerCase()
					.replace(/[^a-z0-9]+/g, "-")
					.replace(/^-|-$/g, "") ||
				`app-${Date.now()}`;

			const result = await createApplication.mutateAsync({
				body: {
					name,
					description: description || null,
					slug: finalSlug,
					access_level: "authenticated",
				},
				params: {
					query: organizationId ? { scope: organizationId } : undefined,
				},
			});

			toast.success("Application created");
			onOpenChange(false);

			// Navigate to code editor
			navigate(`/apps/${result.slug}/code`);
		} catch (error) {
			console.error("[CreateAppModal] Create error:", error);
			toast.error(
				error instanceof Error ? error.message : "Failed to create application",
			);
		}
	}, [
		name,
		slug,
		description,
		organizationId,
		createApplication,
		onOpenChange,
		navigate,
	]);

	const isCreating = createApplication.isPending;

	return (
		<>
			<DialogHeader>
				<DialogTitle>Create New Application</DialogTitle>
				<DialogDescription>
					Configure your new application
				</DialogDescription>
			</DialogHeader>

			{/* Details Form */}
			<div className="space-y-4 py-4">
				<div className="space-y-2">
					<Label htmlFor="app-name">Name</Label>
					<Input
						id="app-name"
						value={name}
						onChange={(e) => handleNameChange(e.target.value)}
						placeholder="My Application"
						autoFocus
					/>
				</div>

				<div className="space-y-2">
					<Label htmlFor="app-description">Description</Label>
					<Textarea
						id="app-description"
						value={description}
						onChange={(e) => setDescription(e.target.value)}
						placeholder="A brief description of your application..."
						rows={3}
					/>
				</div>

				<div className="space-y-2">
					<Label htmlFor="app-slug">URL Slug</Label>
					<Input
						id="app-slug"
						value={slug}
						onChange={(e) => handleSlugChange(e.target.value)}
						placeholder="my-application"
					/>
					<p className="text-xs text-muted-foreground">
						Your app will be accessible at /apps/{slug || "..."}
					</p>
				</div>

				{isPlatformAdmin && (
					<div className="space-y-2">
						<Label>Organization Scope</Label>
						<OrganizationSelect
							value={organizationId}
							onChange={(val) => setOrganizationId(val ?? null)}
							showGlobal={true}
						/>
					</div>
				)}
			</div>

			<div className="flex justify-end gap-2 pt-4 border-t">
				<Button
					variant="outline"
					onClick={() => onOpenChange(false)}
					disabled={isCreating}
				>
					Cancel
				</Button>
				<Button
					onClick={handleCreate}
					disabled={isCreating || !name.trim()}
				>
					{isCreating ? (
						<>
							<Loader2 className="mr-2 h-4 w-4 animate-spin" />
							Creating...
						</>
					) : (
						"Create Application"
					)}
				</Button>
			</div>
		</>
	);
}

/**
 * Create App Modal wrapper
 *
 * Uses a key based on open state to force fresh render each time the modal opens.
 * This ensures all state is reset without using useEffect.
 */
export function CreateAppModal({ open, onOpenChange }: CreateAppModalProps) {
	// Use a counter to force remount when opening
	const [instanceKey, setInstanceKey] = useState(0);

	const handleOpenChange = useCallback(
		(newOpen: boolean) => {
			if (newOpen) {
				// Increment key to force fresh component instance
				setInstanceKey((k) => k + 1);
			}
			onOpenChange(newOpen);
		},
		[onOpenChange],
	);

	return (
		<Dialog open={open} onOpenChange={handleOpenChange}>
			<DialogContent className="max-w-md">
				{open && (
					<CreateAppModalContent key={instanceKey} onOpenChange={onOpenChange} />
				)}
			</DialogContent>
		</Dialog>
	);
}
