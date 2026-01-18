/**
 * Create App Modal
 *
 * Two-step modal for creating new applications:
 * 1. Select engine type (Visual Builder or Code Editor)
 * 2. Enter app details (name, description, slug, organization)
 *
 * Replaces the previous flow that navigated to separate pages.
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
	LayoutGrid,
	Code2,
	ArrowRight,
	ArrowLeft,
	Loader2,
} from "lucide-react";
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
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import { useCreateApplication, ApplicationCreate } from "@/hooks/useApplications";

interface CreateAppModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

type Step = "engine" | "details";

interface EngineOption {
	id: ApplicationCreate["engine"];
	title: string;
	description: string;
	icon: React.ReactNode;
	features: string[];
	recommended?: boolean;
}

const ENGINE_OPTIONS: EngineOption[] = [
	{
		id: "components",
		title: "Visual Builder",
		description: "Drag-and-drop interface for building apps without code",
		icon: <LayoutGrid className="h-8 w-8" />,
		features: [
			"No coding required",
			"Real-time visual preview",
			"Component palette with pre-built blocks",
			"Best for simple data displays and forms",
		],
		recommended: true,
	},
	{
		id: "code",
		title: "Code Editor",
		description: "Write React components with full control over behavior",
		icon: <Code2 className="h-8 w-8" />,
		features: [
			"Full React component support",
			"File-based routing (like Next.js)",
			"TypeScript with IntelliSense",
			"Best for complex logic and custom UIs",
		],
	},
];

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

	// Step state
	const [step, setStep] = useState<Step>("engine");

	// Engine selection
	const [selectedEngine, setSelectedEngine] =
		useState<ApplicationCreate["engine"]>("components");

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

	const handleContinueToDetails = useCallback(() => {
		setStep("details");
	}, []);

	const handleBackToEngine = useCallback(() => {
		setStep("engine");
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
					engine: selectedEngine,
				},
				params: {
					query: organizationId ? { scope: organizationId } : undefined,
				},
			});

			toast.success("Application created");
			onOpenChange(false);

			// Navigate to the appropriate editor
			if (selectedEngine === "code") {
				navigate(`/apps/${result.slug}/code`);
			} else {
				navigate(`/apps/${result.slug}/edit`);
			}
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
		selectedEngine,
		organizationId,
		createApplication,
		onOpenChange,
		navigate,
	]);

	const isCreating = createApplication.isPending;

	return (
		<>
			<DialogHeader>
				<DialogTitle>
					{step === "engine"
						? "Create New Application"
						: "Application Details"}
				</DialogTitle>
				<DialogDescription>
					{step === "engine"
						? "Choose how you want to build your application"
						: `Configure your new ${selectedEngine === "code" ? "code-based" : "visual"} application`}
				</DialogDescription>
			</DialogHeader>

			{step === "engine" ? (
				<>
					{/* Engine Selection */}
					<div className="grid grid-cols-2 gap-4 py-4">
						{ENGINE_OPTIONS.map((option) => (
							<button
								key={option.id}
								type="button"
								onClick={() => setSelectedEngine(option.id)}
								className={cn(
									"relative flex flex-col items-start gap-3 rounded-lg border-2 p-4 text-left transition-all hover:border-primary/50",
									selectedEngine === option.id
										? "border-primary bg-primary/5"
										: "border-border",
								)}
							>
								{option.recommended && (
									<span className="absolute -top-2.5 right-3 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
										Recommended
									</span>
								)}

								<div
									className={cn(
										"rounded-lg p-2",
										selectedEngine === option.id
											? "bg-primary text-primary-foreground"
											: "bg-muted text-muted-foreground",
									)}
								>
									{option.icon}
								</div>

								<div>
									<h3 className="font-semibold">{option.title}</h3>
									<p className="text-sm text-muted-foreground">
										{option.description}
									</p>
								</div>

								<ul className="mt-2 space-y-1 text-sm text-muted-foreground">
									{option.features.map((feature, i) => (
										<li key={i} className="flex items-center gap-2">
											<span className="h-1 w-1 rounded-full bg-muted-foreground" />
											{feature}
										</li>
									))}
								</ul>
							</button>
						))}
					</div>

					<div className="flex justify-end gap-2 pt-4 border-t">
						<Button variant="outline" onClick={() => onOpenChange(false)}>
							Cancel
						</Button>
						<Button onClick={handleContinueToDetails}>
							Continue
							<ArrowRight className="ml-2 h-4 w-4" />
						</Button>
					</div>
				</>
			) : (
				<>
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

					<div className="flex justify-between pt-4 border-t">
						<Button
							variant="ghost"
							onClick={handleBackToEngine}
							disabled={isCreating}
						>
							<ArrowLeft className="mr-2 h-4 w-4" />
							Back
						</Button>
						<div className="flex gap-2">
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
					</div>
				</>
			)}
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
			<DialogContent className="max-w-2xl">
				{open && (
					<CreateAppModalContent key={instanceKey} onOpenChange={onOpenChange} />
				)}
			</DialogContent>
		</Dialog>
	);
}
