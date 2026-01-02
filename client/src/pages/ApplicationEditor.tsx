/**
 * Application Editor Page
 *
 * Editor for creating and modifying App Builder applications.
 * Includes visual drag-and-drop builder, JSON editor, and preview.
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
	ArrowLeft,
	Save,
	Eye,
	Upload,
	RotateCcw,
	AlertTriangle,
	Code2,
	Layout,
	Settings,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
	useApplication,
	useApplicationDraft,
	useApplicationDefinition,
	useCreateApplication,
	useSaveApplicationDraft,
	usePublishApplication,
	useRollbackApplication,
} from "@/hooks/useApplications";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { AppRenderer, EditorShell } from "@/components/app-builder";
import type { ApplicationDefinition as AppDefinitionType } from "@/lib/app-builder-types";

// Default empty application template
const DEFAULT_APP_DEFINITION: AppDefinitionType = {
	id: "",
	name: "New Application",
	description: "",
	version: "1.0.0",
	pages: [
		{
			id: "home",
			title: "Home",
			path: "/",
			layout: {
				type: "column",
				gap: 16,
				padding: 24,
				children: [
					{
						id: "heading-1",
						type: "heading",
						props: {
							text: "Welcome to your new application",
							level: 1,
						},
					},
					{
						id: "text-1",
						type: "text",
						props: {
							text: "Start building by editing the application definition.",
						},
					},
				],
			},
		},
	],
};

export function ApplicationEditor() {
	const navigate = useNavigate();
	const { applicationId: slugParam } = useParams();
	const isEditing = !!slugParam;
	const { user, isPlatformAdmin } = useAuth();

	// Default organization_id
	const defaultOrgId = isPlatformAdmin
		? null
		: (user?.organizationId ?? null);

	// Fetch existing application and draft (pass undefined if not editing)
	const { data: existingApp, isLoading: isLoadingApp } = useApplication(
		isEditing ? slugParam : undefined,
	);
	const { data: existingDraft, isLoading: isLoadingDraft } =
		useApplicationDraft(isEditing ? slugParam : undefined);
	const { data: liveDefinition } = useApplicationDefinition(
		isEditing && existingApp?.is_published ? slugParam : undefined,
	);

	// Mutations
	const createApplication = useCreateApplication();
	const saveDraft = useSaveApplicationDraft();
	const publishApplication = usePublishApplication();
	const rollbackApplication = useRollbackApplication();

	// Form state
	const [name, setName] = useState("");
	const [description, setDescription] = useState("");
	const [slug, setSlug] = useState("");
	const [organizationId, setOrganizationId] = useState<string | null>(
		defaultOrgId,
	);
	const [definitionJson, setDefinitionJson] = useState("");

	// Dialog state
	const [isPublishDialogOpen, setIsPublishDialogOpen] = useState(false);
	const [isRollbackDialogOpen, setIsRollbackDialogOpen] = useState(false);
	const [publishMessage, setPublishMessage] = useState("");

	// Visual editor state
	const [selectedComponentId, setSelectedComponentId] = useState<
		string | null
	>(null);

	// Parse result (combined definition + error)
	type ParseResult =
		| { definition: AppDefinitionType; error: null }
		| { definition: null; error: string };

	// Active tab
	const [activeTab, setActiveTab] = useState("visual");

	// Initialize state from existing data (sync from React Query to local form state)
	// This is an intentional pattern for form editing - we need local state for user edits
	/* eslint-disable react-hooks/set-state-in-effect */
	useEffect(() => {
		if (existingApp) {
			setName(existingApp.name || "");
			setDescription(existingApp.description || "");
			setSlug(existingApp.slug || "");
			setOrganizationId(existingApp.organization_id ?? defaultOrgId);
		}
	}, [existingApp, defaultOrgId]);
	/* eslint-enable react-hooks/set-state-in-effect */

	// Initialize definition from draft or live version (sync from React Query to local form state)
	// This is an intentional pattern for form editing - we need local state for user edits
	/* eslint-disable react-hooks/set-state-in-effect */
	useEffect(() => {
		if (existingDraft?.definition) {
			try {
				const formatted = JSON.stringify(
					existingDraft.definition,
					null,
					2,
				);
				setDefinitionJson(formatted);
			} catch {
				setDefinitionJson("");
			}
		} else if (liveDefinition?.definition) {
			try {
				const formatted = JSON.stringify(
					liveDefinition.definition,
					null,
					2,
				);
				setDefinitionJson(formatted);
			} catch {
				setDefinitionJson("");
			}
		} else if (!isEditing) {
			// New application - use default template
			const template = {
				...DEFAULT_APP_DEFINITION,
				name: name || "New Application",
			};
			setDefinitionJson(JSON.stringify(template, null, 2));
		}
	}, [existingDraft, liveDefinition, isEditing, name]);
	/* eslint-enable react-hooks/set-state-in-effect */

	// Parse and validate JSON - derive both result and error together
	const parseResult = useMemo((): ParseResult => {
		if (!definitionJson)
			return { definition: null, error: "No definition" };
		try {
			const parsed = JSON.parse(definitionJson);
			return { definition: parsed as AppDefinitionType, error: null };
		} catch (e) {
			return {
				definition: null,
				error: e instanceof Error ? e.message : "Invalid JSON",
			};
		}
	}, [definitionJson]);

	const parsedDefinition = parseResult.definition;
	const jsonError = parseResult.error;

	// Auto-generate slug from name (derived state that also needs to be editable)
	// This is an intentional pattern - user can override the generated slug
	/* eslint-disable react-hooks/set-state-in-effect */
	useEffect(() => {
		if (!isEditing && name && !slug) {
			const generated = name
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-")
				.replace(/^-|-$/g, "");
			setSlug(generated);
		}
	}, [name, slug, isEditing]);
	/* eslint-enable react-hooks/set-state-in-effect */

	// Handlers
	const handleSave = async () => {
		if (!parsedDefinition) {
			toast.error("Please fix JSON errors before saving");
			return;
		}

		try {
			if (isEditing && slugParam) {
				// Save draft - serialize and re-parse to ensure clean JSON
				const cleanDefinition = JSON.parse(
					JSON.stringify(parsedDefinition),
				);
				await saveDraft.mutateAsync({
					params: { path: { slug: slugParam } },
					body: {
						definition: cleanDefinition,
					},
				});
				toast.success("Draft saved successfully");
			} else {
				// Create new application
				const result = await createApplication.mutateAsync({
					body: {
						name,
						description: description || null,
						slug,
					},
				});

				// Save initial draft - serialize and re-parse to ensure clean JSON
				const cleanDefinition = JSON.parse(
					JSON.stringify(parsedDefinition),
				);
				await saveDraft.mutateAsync({
					params: { path: { slug: result.slug } },
					body: {
						definition: cleanDefinition,
					},
				});

				toast.success("Application created successfully");
				navigate(`/apps/${result.slug}/edit`);
			}
		} catch (error) {
			console.error("[ApplicationEditor] Save error:", error);
			const errorDetail =
				error instanceof Error ? error.message : JSON.stringify(error);
			toast.error(`Failed to save application: ${errorDetail}`);
		}
	};

	const handlePublish = async () => {
		if (!slugParam || !parsedDefinition) return;

		try {
			// Auto-save draft before publishing to ensure latest changes are included
			const cleanDefinition = JSON.parse(
				JSON.stringify(parsedDefinition),
			);
			await saveDraft.mutateAsync({
				params: { path: { slug: slugParam } },
				body: {
					definition: cleanDefinition,
				},
			});

			// Now publish the saved draft
			await publishApplication.mutateAsync({
				params: { path: { slug: slugParam } },
				body: {
					message: publishMessage || null,
				},
			});
			toast.success("Application published successfully");
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

	const handleRollback = async () => {
		if (!slugParam || !existingApp?.live_version) return;

		try {
			await rollbackApplication.mutateAsync({
				params: { path: { slug: slugParam } },
				body: {
					version: existingApp.live_version,
				},
			});
			toast.success("Draft discarded, reverted to live version");
			setIsRollbackDialogOpen(false);
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : "Failed to rollback",
			);
		}
	};

	const handleFormatJson = useCallback(() => {
		try {
			const parsed = JSON.parse(definitionJson);
			setDefinitionJson(JSON.stringify(parsed, null, 2));
		} catch {
			// Error state is derived from parseResult, no need to handle here
			// The toast or other user feedback could be added if needed
		}
	}, [definitionJson]);

	// Handle definition changes from visual editor
	const handleDefinitionChange = useCallback(
		(newDefinition: AppDefinitionType) => {
			setDefinitionJson(JSON.stringify(newDefinition, null, 2));
		},
		[],
	);

	// Loading state
	if (isEditing && (isLoadingApp || isLoadingDraft)) {
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

	const isSaving = createApplication.isPending || saveDraft.isPending;
	const isPublishing = publishApplication.isPending;
	const hasDraft = existingApp?.has_unpublished_changes || !isEditing;
	const hasLiveVersion = existingApp?.is_published;

	return (
		<div className="h-[calc(100vh-8rem)] flex flex-col">
			{/* Header */}
			<div className="flex items-center justify-between pb-6">
				<div className="flex items-center gap-4">
					<Button
						variant="ghost"
						size="icon"
						onClick={() => navigate("/apps")}
					>
						<ArrowLeft className="h-5 w-5" />
					</Button>
					<div>
						<div className="flex items-center gap-2">
							<h1 className="text-2xl font-bold">
								{isEditing
									? existingApp?.name || "Edit Application"
									: "New Application"}
							</h1>
							{existingApp?.has_unpublished_changes && (
								<Badge variant="outline">Draft</Badge>
							)}
							{existingApp?.is_published && (
								<Badge variant="default">
									v{existingApp.live_version}
								</Badge>
							)}
						</div>
						{existingApp?.slug && (
							<p className="text-sm text-muted-foreground">
								/apps/{existingApp.slug}
							</p>
						)}
					</div>
				</div>

				<div className="flex items-center gap-2">
					{hasDraft && hasLiveVersion && (
						<Button
							variant="outline"
							onClick={() => setIsRollbackDialogOpen(true)}
							disabled={rollbackApplication.isPending}
						>
							<RotateCcw className="mr-2 h-4 w-4" />
							Discard Draft
						</Button>
					)}
					<Button
						variant="outline"
						onClick={handleSave}
						disabled={isSaving || !!jsonError}
					>
						<Save className="mr-2 h-4 w-4" />
						{isSaving ? "Saving..." : "Save Draft"}
					</Button>
					{isEditing && hasDraft && (
						<Button
							onClick={() => setIsPublishDialogOpen(true)}
							disabled={isPublishing || !!jsonError}
						>
							<Upload className="mr-2 h-4 w-4" />
							{isPublishing ? "Publishing..." : "Publish"}
						</Button>
					)}
				</div>
			</div>

			{/* Main Content */}
			<Tabs
				value={activeTab}
				onValueChange={setActiveTab}
				className="flex-1 flex flex-col min-h-0"
			>
				<TabsList>
					<TabsTrigger value="visual">
						<Layout className="mr-2 h-4 w-4" />
						Visual Editor
					</TabsTrigger>
					<TabsTrigger value="settings">
						<Settings className="mr-2 h-4 w-4" />
						Settings
					</TabsTrigger>
					<TabsTrigger value="definition">
						<Code2 className="mr-2 h-4 w-4" />
						JSON
					</TabsTrigger>
					<TabsTrigger value="preview">
						<Eye className="mr-2 h-4 w-4" />
						Preview
					</TabsTrigger>
				</TabsList>

				{/* Visual Editor Tab */}
				<TabsContent
					value="visual"
					className="flex-1 mt-4 -mx-6 -mb-6 overflow-hidden"
				>
					{parsedDefinition ? (
						<EditorShell
							definition={parsedDefinition}
							onDefinitionChange={handleDefinitionChange}
							selectedComponentId={selectedComponentId}
							onSelectComponent={setSelectedComponentId}
							onSave={handleSave}
							onPublish={() => setIsPublishDialogOpen(true)}
							onPreview={() => setActiveTab("preview")}
						/>
					) : (
						<div className="flex h-full items-center justify-center">
							<Card className="max-w-md">
								<CardContent className="flex flex-col items-center justify-center py-12">
									<AlertTriangle className="h-12 w-12 text-destructive" />
									<p className="mt-4 text-center text-muted-foreground">
										Fix JSON errors in the JSON tab to use
										the visual editor
									</p>
									<Button
										variant="outline"
										className="mt-4"
										onClick={() =>
											setActiveTab("definition")
										}
									>
										<Code2 className="mr-2 h-4 w-4" />
										Go to JSON Editor
									</Button>
								</CardContent>
							</Card>
						</div>
					)}
				</TabsContent>

				{/* Settings Tab */}
				<TabsContent
					value="settings"
					className="flex-1 overflow-auto mt-4"
				>
					<Card className="max-w-2xl">
						<CardHeader>
							<CardTitle>Application Settings</CardTitle>
							<CardDescription>
								Configure the basic settings for your
								application.
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-4">
							<div className="space-y-2">
								<Label htmlFor="name">Name</Label>
								<Input
									id="name"
									value={name}
									onChange={(e) => setName(e.target.value)}
									placeholder="My Application"
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="description">Description</Label>
								<Textarea
									id="description"
									value={description}
									onChange={(e) =>
										setDescription(e.target.value)
									}
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
									placeholder="my-application"
									disabled={isEditing}
								/>
								{!isEditing && (
									<p className="text-xs text-muted-foreground">
										Your app will be accessible at /apps/
										{slug || "..."}
									</p>
								)}
							</div>

							{isPlatformAdmin && (
								<div className="space-y-2">
									<Label>Organization</Label>
									<OrganizationSelect
										value={organizationId}
										onChange={(val) =>
											setOrganizationId(val ?? null)
										}
										showGlobal={true}
										disabled={isEditing}
									/>
								</div>
							)}
						</CardContent>
					</Card>
				</TabsContent>

				{/* Definition Tab */}
				<TabsContent
					value="definition"
					className="flex-1 flex flex-col min-h-0 mt-4"
				>
					<div className="flex items-center justify-between mb-2">
						<div className="flex items-center gap-2">
							<Label>Application Definition (JSON)</Label>
							{jsonError && (
								<Badge variant="destructive" className="gap-1">
									<AlertTriangle className="h-3 w-3" />
									{jsonError}
								</Badge>
							)}
						</div>
						<Button
							variant="outline"
							size="sm"
							onClick={handleFormatJson}
						>
							Format JSON
						</Button>
					</div>
					<Textarea
						value={definitionJson}
						onChange={(e) => setDefinitionJson(e.target.value)}
						className="flex-1 font-mono text-sm resize-none"
						placeholder="Enter application definition JSON..."
					/>
				</TabsContent>

				{/* Preview Tab */}
				<TabsContent
					value="preview"
					className="flex-1 overflow-auto mt-4"
				>
					{parsedDefinition ? (
						<div className="border rounded-lg overflow-hidden h-full">
							<AppRenderer definition={parsedDefinition} />
						</div>
					) : (
						<Card>
							<CardContent className="flex flex-col items-center justify-center py-12">
								<AlertTriangle className="h-12 w-12 text-muted-foreground" />
								<p className="mt-4 text-muted-foreground">
									Fix JSON errors to preview the application
								</p>
							</CardContent>
						</Card>
					)}
				</TabsContent>
			</Tabs>

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
								onChange={(e) =>
									setPublishMessage(e.target.value)
								}
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

			{/* Rollback Dialog */}
			<AlertDialog
				open={isRollbackDialogOpen}
				onOpenChange={setIsRollbackDialogOpen}
			>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Discard Draft?</AlertDialogTitle>
						<AlertDialogDescription>
							This will discard all changes in the current draft
							and revert to the last published version. This
							action cannot be undone.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Cancel</AlertDialogCancel>
						<AlertDialogAction
							onClick={handleRollback}
							className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
						>
							Discard Draft
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
