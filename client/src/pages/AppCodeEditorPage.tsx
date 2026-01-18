/**
 * App Code Editor Page
 *
 * Editor for creating and modifying code-based App Builder applications.
 * Uses the file-based routing pattern with code-first development.
 */

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Upload, Settings, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { AppCodeEditorLayout } from "@/components/app-code-editor/AppCodeEditorLayout";
import {
	useApplication,
	useCreateApplication,
	usePublishApplication,
} from "@/hooks/useApplications";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";

export function AppCodeEditorPage() {
	const navigate = useNavigate();
	const { applicationId: slugParam } = useParams();
	const isEditing = !!slugParam;
	const { user, isPlatformAdmin } = useAuth();

	// Default organization_id
	const defaultOrgId = isPlatformAdmin
		? null
		: (user?.organizationId ?? null);

	// Fetch existing application metadata
	const { data: existingApp, isLoading: isLoadingApp } = useApplication(
		isEditing ? slugParam : undefined,
	);

	// Mutations
	const createApplication = useCreateApplication();
	const publishApplication = usePublishApplication();

	// Form state for new apps (only used when !isEditing)
	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [slug, setSlug] = useState("");
	const [organizationId, setOrganizationId] = useState<string | null>(
		defaultOrgId,
	);

	// Dialog state
	const [isPublishDialogOpen, setIsPublishDialogOpen] = useState(false);
	const [publishMessage, setPublishMessage] = useState("");
	const [isSettingsOpen, setIsSettingsOpen] = useState(false);

	// For existing apps, we skip the creation form and go straight to the editor
	// For new apps, we show the creation form first
	const appCreated = isEditing ? !!existingApp : false;

	// Auto-generate slug from name (only for new apps)
	const handleNameChange = (newName: string) => {
		setName(newName);
		// Auto-generate slug if it hasn't been manually edited
		if (!isEditing && !slug) {
			const generated = newName
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-")
				.replace(/^-|-$/g, "");
			setSlug(generated);
		}
	};

	// Create a new code-based application
	const handleCreate = async () => {
		if (!name.trim()) {
			toast.error("Please enter an application name");
			return;
		}

		try {
			const result = await createApplication.mutateAsync({
				body: {
					name,
					description: description || null,
					slug,
					// Engine property will be typed after types are regenerated
					engine: "jsx",
				} as Parameters<typeof createApplication.mutateAsync>[0]["body"] & { engine?: string },
			});

			toast.success("Application created");
			// Navigate to edit the new app
			navigate(`/apps/${result.slug}/edit/code`, { replace: true });
		} catch (error) {
			console.error("[AppCodeEditorPage] Create error:", error);
			toast.error(
				error instanceof Error ? error.message : "Failed to create",
			);
		}
	};

	const handlePublish = async () => {
		if (!existingApp?.id) return;

		try {
			await publishApplication.mutateAsync({
				params: { path: { app_id: existingApp.id } },
				body: {
					message: publishMessage || null,
				},
			});
			toast.success("Application published");
			setIsPublishDialogOpen(false);
			setPublishMessage("");
		} catch (error) {
			toast.error(
				error instanceof Error
					? error.message
					: "Failed to publish application",
			);
		}
	};

	// Loading state
	if (isEditing && isLoadingApp) {
		return (
			<div className="space-y-6">
				<div className="flex items-center gap-4">
					<Skeleton className="h-10 w-10" />
					<Skeleton className="h-8 w-64" />
				</div>
				<Skeleton className="h-[600px] w-full" />
			</div>
		);
	}

	// Show creation form for new apps
	if (!appCreated) {
		return (
			<div className="h-[calc(100vh-8rem)] flex flex-col">
				{/* Header */}
				<div className="flex items-center justify-between pb-4">
					<div className="flex items-center gap-4">
						<Button
							variant="ghost"
							size="icon"
							onClick={() => navigate("/apps")}
						>
							<ArrowLeft className="h-5 w-5" />
						</Button>
						<h1 className="text-xl font-semibold">
							New Code Application
						</h1>
					</div>
				</div>

				{/* Creation Form */}
				<div className="max-w-xl mx-auto py-8 space-y-6">
					<div className="space-y-2">
						<Label htmlFor="name">Name</Label>
						<Input
							id="name"
							value={name}
							onChange={(e) => handleNameChange(e.target.value)}
							placeholder="My Code Application"
							autoFocus
						/>
					</div>

					<div className="space-y-2">
						<Label htmlFor="description">Description</Label>
						<Textarea
							id="description"
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							placeholder="A brief description of your application..."
							rows={3}
						/>
					</div>

					<div className="space-y-2">
						<Label htmlFor="slug">URL Slug</Label>
						<Input
							id="slug"
							value={slug}
							onChange={(e) => setSlug(e.target.value)}
							placeholder="my-code-application"
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

					<div className="flex gap-3 pt-4">
						<Button
							variant="outline"
							onClick={() => navigate("/apps")}
						>
							Cancel
						</Button>
						<Button
							onClick={handleCreate}
							disabled={createApplication.isPending || !name.trim()}
						>
							{createApplication.isPending ? (
								<>
									<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									Creating...
								</>
							) : (
								"Create Application"
							)}
						</Button>
					</div>
				</div>
			</div>
		);
	}

	// Show the code editor for existing apps
	const isPublishing = publishApplication.isPending;
	const hasDraft = existingApp?.has_unpublished_changes;

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col -mx-6 lg:-mx-8 -mb-6 lg:-mb-8">
			{/* Header */}
			<div className="flex items-center justify-between px-4 py-2 border-b bg-background">
				<div className="flex items-center gap-4">
					<Button
						variant="ghost"
						size="icon"
						onClick={() => navigate("/apps")}
					>
						<ArrowLeft className="h-5 w-5" />
					</Button>
					<div className="flex items-center gap-3">
						<h1 className="text-lg font-semibold">
							{existingApp?.name || "Edit Application"}
						</h1>
					</div>
				</div>

				<div className="flex items-center gap-2">
					{/* Settings */}
					<Dialog open={isSettingsOpen} onOpenChange={setIsSettingsOpen}>
						<DialogTrigger asChild>
							<Button variant="ghost" size="icon">
								<Settings className="h-4 w-4" />
							</Button>
						</DialogTrigger>
						<DialogContent>
							<DialogHeader>
								<DialogTitle>Application Settings</DialogTitle>
								<DialogDescription>
									Configure your code application settings.
								</DialogDescription>
							</DialogHeader>
							<div className="mt-2 space-y-4">
								<div className="space-y-2">
									<Label>Name</Label>
									<Input value={existingApp?.name || ""} disabled />
								</div>
								<div className="space-y-2">
									<Label>Slug</Label>
									<Input value={existingApp?.slug || ""} disabled />
								</div>
								<div className="space-y-2">
									<Label>Description</Label>
									<Textarea
										value={existingApp?.description || ""}
										disabled
										rows={3}
									/>
								</div>
							</div>
						</DialogContent>
					</Dialog>

					{/* Publish */}
					{hasDraft && (
						<Button
							size="sm"
							onClick={() => setIsPublishDialogOpen(true)}
							disabled={isPublishing}
						>
							<Upload className="mr-2 h-4 w-4" />
							{isPublishing ? "Publishing..." : "Publish"}
						</Button>
					)}
				</div>
			</div>

			{/* Code Editor */}
			<div className="flex-1 min-h-0">
				{existingApp?.id && existingApp?.draft_version_id && (
					<AppCodeEditorLayout
						appId={existingApp.id}
						versionId={existingApp.draft_version_id}
						appName={existingApp.name}
					/>
				)}
			</div>

			{/* Publish Dialog */}
			<Dialog
				open={isPublishDialogOpen}
				onOpenChange={setIsPublishDialogOpen}
			>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Publish Application</DialogTitle>
						<DialogDescription>
							This will make the current draft live. Users will
							see the new version immediately.
						</DialogDescription>
					</DialogHeader>
					<div className="space-y-4">
						<div className="space-y-2">
							<Label htmlFor="publish-message">
								Publish Message (optional)
							</Label>
							<Textarea
								id="publish-message"
								value={publishMessage}
								onChange={(e) => setPublishMessage(e.target.value)}
								placeholder="What changed in this version?"
								rows={3}
							/>
						</div>
					</div>
					<DialogFooter>
						<Button
							variant="outline"
							onClick={() => setIsPublishDialogOpen(false)}
						>
							Cancel
						</Button>
						<Button onClick={handlePublish} disabled={isPublishing}>
							{isPublishing ? "Publishing..." : "Publish"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</div>
	);
}
