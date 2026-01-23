# App Info Dialog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a unified AppInfoDialog component for app creation and editing with full access control support (organization, access level, roles).

**Architecture:** Single dialog component handles both create and edit modes based on `appId` prop. Follows the established AgentDialog pattern. Uses existing hooks and OrganizationSelect component.

**Tech Stack:** React, TypeScript, React Hook Form, Zod, shadcn/ui, TanStack Query

---

## Task 1: Create AppInfoDialog Component

**Files:**
- Create: `client/src/components/app-builder/AppInfoDialog.tsx`

**Step 1: Create the component file with imports and types**

```tsx
/**
 * App Info Dialog Component
 *
 * Unified dialog for creating and editing applications.
 * Handles form state, validation, and API mutations.
 */

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Loader2, Check, ChevronsUpDown, X } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Form,
	FormControl,
	FormDescription,
	FormField,
	FormItem,
	FormLabel,
	FormMessage,
} from "@/components/ui/form";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { cn } from "@/lib/utils";
import { useRoles } from "@/hooks/useRoles";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";
import {
	useApplication,
	useCreateApplication,
	useUpdateApplication,
} from "@/hooks/useApplications";
import type { components } from "@/lib/v1";

type RolePublic = components["schemas"]["RolePublic"];

const ACCESS_LEVELS = [
	{
		value: "role_based",
		label: "Role-Based",
		description: "Only users with assigned roles can access",
	},
	{
		value: "authenticated",
		label: "Authenticated Users",
		description: "Any authenticated user can access",
	},
];

const formSchema = z.object({
	name: z
		.string()
		.min(1, "Name is required")
		.max(255, "Name must be 255 characters or less"),
	slug: z
		.string()
		.min(1, "Slug is required")
		.max(255, "Slug must be 255 characters or less")
		.regex(
			/^[a-z][a-z0-9-]*$/,
			"Slug must start with a letter and contain only lowercase letters, numbers, and hyphens",
		),
	description: z.string().optional(),
	organization_id: z.string().nullable(),
	access_level: z.enum(["authenticated", "role_based"]),
	role_ids: z.array(z.string()),
});

type FormValues = z.infer<typeof formSchema>;

interface AppInfoDialogProps {
	appId?: string | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
	/** Called after successful create with the new app slug (for navigation) */
	onCreated?: (slug: string) => void;
}

export function AppInfoDialog({
	appId,
	open,
	onOpenChange,
	onCreated,
}: AppInfoDialogProps) {
	const isEditing = !!appId;
	const { isPlatformAdmin, user } = useAuth();

	// Fetch existing app when editing (by slug - appId is actually the slug here)
	const { data: existingApp, isLoading: isLoadingApp } = useApplication(
		isEditing ? appId : undefined,
	);

	const { data: roles, isLoading: rolesLoading } = useRoles();
	const createApplication = useCreateApplication();
	const updateApplication = useUpdateApplication();

	const [rolesPopoverOpen, setRolesPopoverOpen] = useState(false);
	const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);

	// Default organization_id for org users is their org, for platform admins it's null (global)
	const defaultOrgId = isPlatformAdmin
		? null
		: (user?.organizationId ?? null);

	const form = useForm<FormValues>({
		resolver: zodResolver(formSchema),
		defaultValues: {
			name: "",
			slug: "",
			description: "",
			organization_id: defaultOrgId,
			access_level: "role_based",
			role_ids: [],
		},
	});

	const accessLevel = form.watch("access_level");

	// Load existing app data when editing
	useEffect(() => {
		if (existingApp && isEditing) {
			form.reset({
				name: existingApp.name,
				slug: existingApp.slug,
				description: existingApp.description ?? "",
				organization_id: existingApp.organization_id ?? null,
				access_level: (existingApp.access_level as "authenticated" | "role_based") || "authenticated",
				role_ids: existingApp.role_ids ?? [],
			});
			setSlugManuallyEdited(true); // Don't auto-generate slug when editing
		} else if (!isEditing && open) {
			form.reset({
				name: "",
				slug: "",
				description: "",
				organization_id: defaultOrgId,
				access_level: "role_based",
				role_ids: [],
			});
			setSlugManuallyEdited(false);
		}
	}, [existingApp, isEditing, form, open, defaultOrgId]);

	// Auto-generate slug from name (only when creating and not manually edited)
	const handleNameChange = (newName: string) => {
		form.setValue("name", newName);
		if (!slugManuallyEdited && !isEditing) {
			const generated = newName
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-")
				.replace(/^-|-$/g, "");
			form.setValue("slug", generated);
		}
	};

	const handleSlugChange = (newSlug: string) => {
		form.setValue("slug", newSlug);
		setSlugManuallyEdited(true);
	};

	const handleClose = () => {
		form.reset();
		setSlugManuallyEdited(false);
		onOpenChange(false);
	};

	const onSubmit = async (values: FormValues) => {
		try {
			if (isEditing && appId) {
				await updateApplication.mutateAsync({
					params: {
						path: { slug: appId },
						query: values.organization_id
							? { scope: values.organization_id }
							: undefined,
					},
					body: {
						name: values.name,
						description: values.description || null,
						access_level: values.access_level,
						role_ids: values.role_ids,
						// Note: scope can only be changed by platform admins, handled by backend
					},
				});
				handleClose();
			} else {
				const result = await createApplication.mutateAsync({
					body: {
						name: values.name,
						slug: values.slug,
						description: values.description || null,
						access_level: values.access_level,
						role_ids: values.role_ids,
					},
					params: {
						query: values.organization_id
							? { scope: values.organization_id }
							: undefined,
					},
				});
				handleClose();
				onCreated?.(result.slug);
			}
		} catch {
			// Error handling is done by the mutation hooks via toast
		}
	};

	const toggleRole = (roleId: string) => {
		const current = form.getValues("role_ids");
		if (current.includes(roleId)) {
			form.setValue(
				"role_ids",
				current.filter((id) => id !== roleId),
			);
		} else {
			form.setValue("role_ids", [...current, roleId]);
		}
	};

	const removeRole = (roleId: string) => {
		const current = form.getValues("role_ids");
		form.setValue(
			"role_ids",
			current.filter((id) => id !== roleId),
		);
	};

	const isPending = createApplication.isPending || updateApplication.isPending;
	const selectedRoleIds = form.watch("role_ids");

	return (
		<Dialog open={open} onOpenChange={handleClose}>
			<DialogContent className="sm:max-w-[500px]">
				<DialogHeader>
					<DialogTitle>
						{isEditing ? "Edit Application" : "Create Application"}
					</DialogTitle>
					<DialogDescription>
						{isEditing
							? "Update the application settings"
							: "Configure your new application"}
					</DialogDescription>
				</DialogHeader>

				{isEditing && isLoadingApp ? (
					<div className="flex items-center justify-center py-8">
						<Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
					</div>
				) : (
					<Form {...form}>
						<form
							onSubmit={form.handleSubmit(onSubmit)}
							className="space-y-4"
						>
							{/* Organization Scope - Only show for platform admins */}
							{isPlatformAdmin && (
								<FormField
									control={form.control}
									name="organization_id"
									render={({ field }) => (
										<FormItem>
											<FormLabel>Organization</FormLabel>
											<FormControl>
												<OrganizationSelect
													value={field.value}
													onChange={field.onChange}
													showGlobal={true}
													disabled={isEditing}
												/>
											</FormControl>
											<FormDescription>
												{isEditing
													? "Organization cannot be changed after creation"
													: "Global apps are available to all organizations"}
											</FormDescription>
											<FormMessage />
										</FormItem>
									)}
								/>
							)}

							{/* Name */}
							<FormField
								control={form.control}
								name="name"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Name</FormLabel>
										<FormControl>
											<Input
												placeholder="My Application"
												{...field}
												onChange={(e) =>
													handleNameChange(e.target.value)
												}
											/>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Slug */}
							<FormField
								control={form.control}
								name="slug"
								render={({ field }) => (
									<FormItem>
										<FormLabel>URL Slug</FormLabel>
										<FormControl>
											<Input
												placeholder="my-application"
												{...field}
												onChange={(e) =>
													handleSlugChange(e.target.value)
												}
												disabled={isEditing}
											/>
										</FormControl>
										<FormDescription>
											{isEditing
												? "Slug cannot be changed after creation"
												: `Your app will be accessible at /apps/${field.value || "..."}`}
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Description */}
							<FormField
								control={form.control}
								name="description"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Description</FormLabel>
										<FormControl>
											<Textarea
												placeholder="A brief description of your application..."
												rows={3}
												{...field}
											/>
										</FormControl>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Access Level */}
							<FormField
								control={form.control}
								name="access_level"
								render={({ field }) => (
									<FormItem>
										<FormLabel>Access Level</FormLabel>
										<FormControl>
											<Combobox
												value={field.value}
												onValueChange={field.onChange}
												options={ACCESS_LEVELS}
												placeholder="Select access level"
											/>
										</FormControl>
										<FormDescription>
											Controls who can view and use this application
										</FormDescription>
										<FormMessage />
									</FormItem>
								)}
							/>

							{/* Role Selection - Only show when role_based */}
							{accessLevel === "role_based" && (
								<FormField
									control={form.control}
									name="role_ids"
									render={({ field }) => (
										<FormItem>
											<FormLabel>
												Assigned Roles{" "}
												{field.value.length > 0 &&
													`(${field.value.length})`}
											</FormLabel>
											<Popover
												open={rolesPopoverOpen}
												onOpenChange={setRolesPopoverOpen}
											>
												<PopoverTrigger asChild>
													<FormControl>
														<Button
															variant="outline"
															role="combobox"
															aria-expanded={rolesPopoverOpen}
															className="w-full justify-between font-normal"
															disabled={rolesLoading}
														>
															<span className="text-muted-foreground">
																{rolesLoading
																	? "Loading roles..."
																	: "Select roles..."}
															</span>
															<ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
														</Button>
													</FormControl>
												</PopoverTrigger>
												<PopoverContent
													className="w-[var(--radix-popover-trigger-width)] p-0"
													align="start"
												>
													<Command>
														<CommandInput placeholder="Search roles..." />
														<CommandList>
															<CommandEmpty>
																No roles found.
															</CommandEmpty>
															<CommandGroup>
																{roles?.map((role: RolePublic) => (
																	<CommandItem
																		key={role.id}
																		value={role.name || ""}
																		onSelect={() =>
																			toggleRole(role.id)
																		}
																	>
																		<div className="flex items-center gap-2 flex-1">
																			<Checkbox
																				checked={field.value.includes(
																					role.id,
																				)}
																				onCheckedChange={() =>
																					toggleRole(role.id)
																				}
																			/>
																			<div className="flex flex-col">
																				<span className="font-medium">
																					{role.name}
																				</span>
																				{role.description && (
																					<span className="text-xs text-muted-foreground">
																						{role.description}
																					</span>
																				)}
																			</div>
																		</div>
																		<Check
																			className={cn(
																				"ml-auto h-4 w-4",
																				field.value.includes(role.id)
																					? "opacity-100"
																					: "opacity-0",
																			)}
																		/>
																	</CommandItem>
																))}
															</CommandGroup>
														</CommandList>
													</Command>
												</PopoverContent>
											</Popover>
											{selectedRoleIds.length > 0 && (
												<div className="flex flex-wrap gap-2 p-2 border rounded-md bg-muted/50">
													{selectedRoleIds.map((roleId) => {
														const role = roles?.find(
															(r: RolePublic) => r.id === roleId,
														);
														return (
															<Badge
																key={roleId}
																variant="secondary"
																className="gap-1"
															>
																{role?.name || roleId}
																<X
																	className="h-3 w-3 cursor-pointer"
																	onClick={() => removeRole(roleId)}
																/>
															</Badge>
														);
													})}
												</div>
											)}
											<FormDescription>
												Users must have at least one of these roles to
												access the application
											</FormDescription>
											<FormMessage />
										</FormItem>
									)}
								/>
							)}

							<DialogFooter className="pt-4">
								<Button
									type="button"
									variant="outline"
									onClick={handleClose}
								>
									Cancel
								</Button>
								<Button type="submit" disabled={isPending}>
									{isPending && (
										<Loader2 className="mr-2 h-4 w-4 animate-spin" />
									)}
									{isPending
										? "Saving..."
										: isEditing
											? "Save Changes"
											: "Create Application"}
								</Button>
							</DialogFooter>
						</form>
					</Form>
				)}
			</DialogContent>
		</Dialog>
	);
}
```

**Step 2: Verify the file compiles**

Run: `cd client && npm run tsc`
Expected: No errors related to AppInfoDialog.tsx

**Step 3: Commit**

```bash
git add client/src/components/app-builder/AppInfoDialog.tsx
git commit -m "feat(client): add AppInfoDialog component for create/edit apps

Unified dialog component following AgentDialog pattern with:
- Organization scope (platform admins, disabled when editing)
- Name, slug, description fields
- Access level selector (authenticated/role_based)
- Role picker for role-based access

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Update CreateAppModal to Use AppInfoDialog

**Files:**
- Modify: `client/src/components/app-builder/CreateAppModal.tsx`

**Step 1: Replace CreateAppModal implementation**

Replace the entire file content with:

```tsx
/**
 * Create App Modal
 *
 * Wrapper around AppInfoDialog for creating new applications.
 */

import { useNavigate } from "react-router-dom";
import { AppInfoDialog } from "./AppInfoDialog";

interface CreateAppModalProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

export function CreateAppModal({ open, onOpenChange }: CreateAppModalProps) {
	const navigate = useNavigate();

	const handleCreated = (slug: string) => {
		navigate(`/apps/${slug}/edit`);
	};

	return (
		<AppInfoDialog
			open={open}
			onOpenChange={onOpenChange}
			onCreated={handleCreated}
		/>
	);
}
```

**Step 2: Verify compilation**

Run: `cd client && npm run tsc`
Expected: No errors

**Step 3: Commit**

```bash
git add client/src/components/app-builder/CreateAppModal.tsx
git commit -m "refactor(client): simplify CreateAppModal to use AppInfoDialog

Replace custom implementation with thin wrapper around AppInfoDialog.
Maintains same API for backwards compatibility.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update AppCodeEditorPage Settings Dialog

**Files:**
- Modify: `client/src/pages/AppCodeEditorPage.tsx`

**Step 1: Add AppInfoDialog import**

Add to the imports section (around line 1-30):

```tsx
import { AppInfoDialog } from "@/components/app-builder/AppInfoDialog";
```

**Step 2: Replace the Settings Dialog**

Find the Settings Dialog section (approximately lines 268-300):

```tsx
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
```

Replace with:

```tsx
{/* Settings */}
<Button
	variant="ghost"
	size="icon"
	onClick={() => setIsSettingsOpen(true)}
>
	<Settings className="h-4 w-4" />
</Button>
<AppInfoDialog
	appId={existingApp?.slug}
	open={isSettingsOpen}
	onOpenChange={setIsSettingsOpen}
/>
```

**Step 3: Remove unused Dialog imports if no longer needed**

Check if `DialogTrigger` is still used elsewhere in the file. If not, remove it from the imports:

```tsx
// Before:
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";

// After (if DialogTrigger not used elsewhere):
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
```

Also check if `Label`, `Input`, `Textarea` are still used. The Publish Dialog still uses them, so they should stay.

**Step 4: Verify compilation**

Run: `cd client && npm run tsc`
Expected: No errors

**Step 5: Run linting**

Run: `cd client && npm run lint`
Expected: No errors (or only pre-existing ones)

**Step 6: Commit**

```bash
git add client/src/pages/AppCodeEditorPage.tsx
git commit -m "feat(client): replace read-only settings with AppInfoDialog

Settings button now opens AppInfoDialog in edit mode with:
- Editable name and description
- Access level and role configuration
- Organization display (disabled for editing)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Manual Testing

**Step 1: Start the dev environment**

Run: `./debug.sh`
Wait for all services to start.

**Step 2: Test create flow**

1. Navigate to http://localhost:3000/apps
2. Click "Create Application" button
3. Verify the dialog shows:
   - Organization field (if platform admin)
   - Name field with auto-slug generation
   - Slug field
   - Description field
   - Access Level dropdown (defaults to "Role-Based")
   - Role picker (when role_based selected)
4. Create an app and verify navigation to editor

**Step 3: Test edit flow**

1. From the app editor, click the Settings (gear) icon
2. Verify the dialog shows:
   - Organization field (disabled with explanation)
   - Name field (editable)
   - Slug field (disabled with explanation)
   - Description field (editable)
   - Access Level dropdown (editable)
   - Role picker (when role_based selected)
3. Make changes and save
4. Verify changes persist after refresh

**Step 4: Commit any fixes if needed**

---

## Task 5: Final Verification

**Step 1: Run type checking**

Run: `cd client && npm run tsc`
Expected: 0 errors

**Step 2: Run linting**

Run: `cd client && npm run lint`
Expected: 0 errors (or only pre-existing)

**Step 3: Run tests (if applicable)**

Run: `./test.sh --client` (if frontend tests exist)

**Step 4: Final commit if any cleanup needed**

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create AppInfoDialog component | `client/src/components/app-builder/AppInfoDialog.tsx` |
| 2 | Update CreateAppModal | `client/src/components/app-builder/CreateAppModal.tsx` |
| 3 | Update AppCodeEditorPage | `client/src/pages/AppCodeEditorPage.tsx` |
| 4 | Manual testing | - |
| 5 | Final verification | - |
