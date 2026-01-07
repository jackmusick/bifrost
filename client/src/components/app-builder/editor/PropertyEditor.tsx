/**
 * Property Editor Panel for App Builder Visual Editor
 *
 * Displays editable properties for the currently selected component,
 * organized into sections using accordions.
 */

import { useState, useCallback } from "react";
import { Trash2, Shield, AlertTriangle } from "lucide-react";
import { useRoles } from "@/hooks/useRoles";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
	Accordion,
	AccordionContent,
	AccordionItem,
	AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type {
	AppComponent,
	LayoutContainer,
	ComponentType,
	LayoutType,
	HeadingLevel,
	LayoutAlign,
	LayoutJustify,
	LayoutMaxWidth,
	ButtonActionType,
	PageDefinition,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
import {
	WorkflowSelector,
	KeyValueEditor,
	ColumnBuilder,
	OptionBuilder,
	TableActionBuilder,
	WorkflowParameterEditor,
} from "./property-editors";

export interface PropertyEditorProps {
	/** Currently selected component or layout container */
	component: AppComponent | LayoutContainer | null;
	/** Callback when properties change */
	onChange: (updates: Partial<AppComponent | LayoutContainer>) => void;
	/** Callback when component should be deleted */
	onDelete?: () => void;
	/** Page being edited (for page-level settings like launch workflow) */
	page?: PageDefinition;
	/** Callback when page properties change */
	onPageChange?: (updates: Partial<PageDefinition>) => void;
	/** App-level access control settings */
	appAccessLevel?: "authenticated" | "role_based";
	/** Role IDs allowed for the app (when role_based) */
	appRoleIds?: string[];
	/** Additional CSS classes */
	className?: string;
}

/** Field wrapper component for consistent form field styling */
function FormField({
	label,
	children,
	description,
}: {
	label: string;
	children: React.ReactNode;
	description?: string;
}) {
	return (
		<div className="space-y-2">
			<Label className="text-sm font-medium">{label}</Label>
			{children}
			{description && (
				<p className="text-xs text-muted-foreground">{description}</p>
			)}
		</div>
	);
}

/** JSON editor for complex object values */
function JsonEditor({
	value,
	onChange,
	rows = 6,
}: {
	value: unknown;
	onChange: (value: unknown) => void;
	rows?: number;
}) {
	const [jsonString, setJsonString] = useState(() =>
		JSON.stringify(value, null, 2),
	);
	const [error, setError] = useState<string | null>(null);

	const handleChange = useCallback(
		(newValue: string) => {
			setJsonString(newValue);
			try {
				const parsed = JSON.parse(newValue);
				setError(null);
				onChange(parsed);
			} catch {
				setError("Invalid JSON");
			}
		},
		[onChange],
	);

	return (
		<div className="space-y-1">
			<Textarea
				value={jsonString}
				onChange={(e) => handleChange(e.target.value)}
				rows={rows}
				className={cn(
					"font-mono text-xs",
					error &&
						"border-destructive focus-visible:border-destructive",
				)}
			/>
			{error && <p className="text-xs text-destructive">{error}</p>}
		</div>
	);
}

/** Common properties section for all components */
function CommonPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent | LayoutContainer;
	onChange: (updates: Partial<AppComponent | LayoutContainer>) => void;
}) {
	const isLayout = isLayoutContainer(component);
	const id = isLayout ? undefined : (component as AppComponent).id;

	return (
		<AccordionItem value="common">
			<AccordionTrigger>Common</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				{id && (
					<FormField
						label="ID"
						description="Unique component identifier"
					>
						<Input value={id} disabled className="bg-muted" />
					</FormField>
				)}
				<FormField
					label="Visibility Expression"
					description="Expression to control visibility (e.g., {{ user.role == 'admin' }})"
				>
					<Input
						value={component.visible ?? ""}
						onChange={(e) =>
							onChange({ visible: e.target.value || undefined })
						}
						placeholder="Always visible"
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Layout-specific properties */
/**
 * Page Properties Section
 * Shows page-level settings like title, path, data sources, and launch workflow
 */
function PagePropertiesSection({
	page,
	onChange,
	appAccessLevel,
	appRoleIds,
}: {
	page: PageDefinition;
	onChange: (updates: Partial<PageDefinition>) => void;
	appAccessLevel?: "authenticated" | "role_based";
	appRoleIds?: string[];
}) {
	// Fetch roles for page-level access control
	const { data: rolesData } = useRoles();

	// Get current page-level allowed roles
	const pageAllowedRoles = page.permission?.allowedRoles ?? [];

	// Filter roles to only show those that are allowed at app level
	const availableRoles = rolesData?.filter(
		(role) => !appRoleIds?.length || appRoleIds.includes(role.id)
	) ?? [];

	// Handle role toggle
	const handleRoleToggle = (roleId: string, checked: boolean) => {
		const currentRoles = pageAllowedRoles;
		const newRoles = checked
			? [...currentRoles, roleId]
			: currentRoles.filter((id) => id !== roleId);

		onChange({
			permission: {
				...page.permission,
				allowedRoles: newRoles.length > 0 ? newRoles : undefined,
			},
		});
	};

	return (
		<AccordionItem value="page">
			<AccordionTrigger>Page Settings</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Title"
					description="Page title shown in navigation"
				>
					<Input
						value={page.title}
						onChange={(e) => onChange({ title: e.target.value })}
						placeholder="Page Title"
					/>
				</FormField>

				<FormField label="Path" description="URL path for this page">
					<Input
						value={page.path}
						onChange={(e) => onChange({ path: e.target.value })}
						placeholder="/page-path"
					/>
				</FormField>

				{/* Launch Workflow Section */}
				<div className="pt-2 border-t">
					<FormField
						label="Launch Workflow"
						description="Workflow when page loads. Access via {{ workflow.<dataSourceId> }}"
					>
						<WorkflowSelector
							value={page.launchWorkflowId}
							onChange={(workflowId: string | undefined) =>
								onChange({
									launchWorkflowId: workflowId || undefined,
									launchWorkflowParams: workflowId
										? page.launchWorkflowParams
										: undefined,
									launchWorkflowDataSourceId: workflowId
										? page.launchWorkflowDataSourceId
										: undefined,
								})
							}
							placeholder="Select launch workflow (optional)"
							allowClear
						/>
					</FormField>

					{page.launchWorkflowId && (
						<>
							<FormField
								label="Data Source ID"
								description="Access workflow result via {{ workflow.<id> }}. Defaults to workflow function name."
							>
								<Input
									value={page.launchWorkflowDataSourceId ?? ""}
									onChange={(e) =>
										onChange({
											launchWorkflowDataSourceId:
												e.target.value || undefined,
										})
									}
									placeholder="Auto (workflow function name)"
								/>
							</FormField>

							<FormField
								label="Launch Workflow Parameters"
								description="Parameters to pass to the launch workflow"
							>
								<WorkflowParameterEditor
									workflowId={page.launchWorkflowId}
									value={page.launchWorkflowParams ?? {}}
									onChange={(params) =>
										onChange({ launchWorkflowParams: params })
									}
									isRowAction={false}
								/>
							</FormField>
						</>
					)}
				</div>

				{/* Page Access Control (only shown when app uses role-based access) */}
				{appAccessLevel === "role_based" && (
					<div className="pt-2 border-t">
						<div className="flex items-center gap-2 mb-2">
							<Shield className="h-4 w-4" />
							<Label className="text-sm font-medium">Page Access</Label>
						</div>
						<p className="text-xs text-muted-foreground mb-3">
							Restrict this page to specific roles. Leave empty to allow all app roles.
						</p>

						{availableRoles.length === 0 ? (
							<p className="text-sm text-muted-foreground">
								No roles available at app level.
							</p>
						) : (
							<div className="space-y-2 max-h-40 overflow-y-auto">
								{availableRoles.map((role) => {
									const isSelected = pageAllowedRoles.includes(role.id);
									return (
										<label
											key={role.id}
											htmlFor={`page-role-${role.id}`}
											className={`flex items-start space-x-3 rounded-md border p-2 hover:bg-accent/50 transition-colors cursor-pointer ${
												isSelected ? "border-primary bg-primary/5" : ""
											}`}
										>
											<Checkbox
												id={`page-role-${role.id}`}
												checked={isSelected}
												onCheckedChange={(checked) =>
													handleRoleToggle(role.id, checked as boolean)
												}
											/>
											<div className="flex-1 min-w-0">
												<span className="cursor-pointer text-sm font-medium">
													{role.name}
												</span>
											</div>
										</label>
									);
								})}
							</div>
						)}

						{pageAllowedRoles.length > 0 && (
							<Alert className="mt-2 py-2">
								<AlertTriangle className="h-3 w-3" />
								<AlertDescription className="text-xs">
									Only selected roles can access this page.
								</AlertDescription>
							</Alert>
						)}

						<FormField
							label="Redirect Path"
							description="Where to redirect users without access"
						>
							<Input
								value={page.permission?.redirectTo ?? ""}
								onChange={(e) =>
									onChange({
										permission: {
											...page.permission,
											redirectTo: e.target.value || undefined,
										},
									})
								}
								placeholder="/access-denied (optional)"
							/>
						</FormField>
					</div>
				)}
			</AccordionContent>
		</AccordionItem>
	);
}

function LayoutPropertiesSection({
	component,
	onChange,
}: {
	component: LayoutContainer;
	onChange: (updates: Partial<LayoutContainer>) => void;
}) {
	const isGrid = component.type === "grid";

	return (
		<AccordionItem value="layout">
			<AccordionTrigger>Layout</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Type">
					<Select
						value={component.type}
						onValueChange={(value) =>
							onChange({ type: value as LayoutType })
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="row">Row</SelectItem>
							<SelectItem value="column">Column</SelectItem>
							<SelectItem value="grid">Grid</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField
					label="Gap"
					description="Space between children (pixels)"
				>
					<Input
						type="number"
						value={component.gap ?? ""}
						onChange={(e) =>
							onChange({
								gap: e.target.value
									? Number(e.target.value)
									: undefined,
							})
						}
						placeholder="0"
						min={0}
					/>
				</FormField>

				<FormField label="Padding" description="Inner padding (pixels)">
					<Input
						type="number"
						value={component.padding ?? ""}
						onChange={(e) =>
							onChange({
								padding: e.target.value
									? Number(e.target.value)
									: undefined,
							})
						}
						placeholder="0"
						min={0}
					/>
				</FormField>

				<FormField label="Align" description="Cross-axis alignment">
					<Select
						value={component.align ?? "stretch"}
						onValueChange={(value) =>
							onChange({ align: value as LayoutAlign })
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="start">Start</SelectItem>
							<SelectItem value="center">Center</SelectItem>
							<SelectItem value="end">End</SelectItem>
							<SelectItem value="stretch">Stretch</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField label="Justify" description="Main-axis distribution">
					<Select
						value={component.justify ?? "start"}
						onValueChange={(value) =>
							onChange({ justify: value as LayoutJustify })
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="start">Start</SelectItem>
							<SelectItem value="center">Center</SelectItem>
							<SelectItem value="end">End</SelectItem>
							<SelectItem value="between">
								Space Between
							</SelectItem>
							<SelectItem value="around">Space Around</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField
					label="Max Width"
					description="Constrain layout width (use lg for forms)"
				>
					<Select
						value={component.maxWidth ?? "none"}
						onValueChange={(value) =>
							onChange({
								maxWidth:
									value === "none"
										? undefined
										: (value as LayoutMaxWidth),
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="none">
								None (full width)
							</SelectItem>
							<SelectItem value="sm">Small (384px)</SelectItem>
							<SelectItem value="md">Medium (448px)</SelectItem>
							<SelectItem value="lg">Large (512px)</SelectItem>
							<SelectItem value="xl">X-Large (576px)</SelectItem>
							<SelectItem value="2xl">
								2X-Large (672px)
							</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				{isGrid && (
					<FormField
						label="Columns"
						description="Number of grid columns"
					>
						<Input
							type="number"
							value={component.columns ?? ""}
							onChange={(e) =>
								onChange({
									columns: e.target.value
										? Number(e.target.value)
										: undefined,
								})
							}
							placeholder="1"
							min={1}
							max={12}
						/>
					</FormField>
				)}
			</AccordionContent>
		</AccordionItem>
	);
}

/** Heading component properties */
function HeadingPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "heading") return null;

	const props = component.props;

	return (
		<AccordionItem value="heading">
			<AccordionTrigger>Heading</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Text"
					description="Supports expressions like {{ data.title }}"
				>
					<Input
						value={props.text}
						onChange={(e) =>
							onChange({
								props: { ...props, text: e.target.value },
							})
						}
					/>
				</FormField>

				<FormField
					label="Level"
					description="Heading size (1 = largest)"
				>
					<Select
						value={String(props.level ?? 1)}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									level: Number(value) as HeadingLevel,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="1">H1 - Extra Large</SelectItem>
							<SelectItem value="2">H2 - Large</SelectItem>
							<SelectItem value="3">H3 - Medium</SelectItem>
							<SelectItem value="4">H4 - Small</SelectItem>
							<SelectItem value="5">H5 - Extra Small</SelectItem>
							<SelectItem value="6">H6 - Smallest</SelectItem>
						</SelectContent>
					</Select>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Text component properties */
function TextPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "text") return null;

	const props = component.props;

	return (
		<AccordionItem value="text">
			<AccordionTrigger>Text</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Text"
					description="Supports expressions like {{ user.name }}"
				>
					<Textarea
						value={props.text}
						onChange={(e) =>
							onChange({
								props: { ...props, text: e.target.value },
							})
						}
						rows={3}
					/>
				</FormField>

				<FormField
					label="Label"
					description="Optional label above the text"
				>
					<Input
						value={props.label ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									label: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** HTML/JSX component properties */
function HtmlPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "html") return null;

	const props = component.props;

	return (
		<AccordionItem value="html">
			<AccordionTrigger>HTML/JSX Content</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Content"
					description="Plain HTML or JSX with context access (use className= for JSX, class= for HTML)"
				>
					<Textarea
						value={props.content}
						onChange={(e) =>
							onChange({
								props: { ...props, content: e.target.value },
							})
						}
						rows={12}
						className="font-mono text-xs"
						placeholder={
							'<div className="p-4 bg-muted rounded">\n  <p>Hello {context.workflow.user.name}!</p>\n</div>'
						}
					/>
				</FormField>
				<p className="text-xs text-muted-foreground">
					JSX templates have access to{" "}
					<code className="bg-muted px-1 rounded">
						context.workflow.*
					</code>{" "}
					for variables and data.
				</p>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Button component properties */
function ButtonPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "button") return null;

	const props = component.props;
	// Support both 'label' and 'text' for button text (matches ButtonComponent behavior)
	const labelValue =
		props.label ?? (props as Record<string, unknown>).text ?? "";

	return (
		<AccordionItem value="button">
			<AccordionTrigger>Button</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Label">
					<Input
						value={String(labelValue)}
						onChange={(e) => {
							// Normalize to use 'label' and remove 'text' if present
							const newProps = {
								...props,
								label: e.target.value,
							};
							if ("text" in newProps) {
								delete (newProps as Record<string, unknown>)
									.text;
							}
							onChange({ props: newProps });
						}}
						placeholder="Button text..."
					/>
				</FormField>

				<FormField label="Variant">
					<Select
						value={props.variant ?? "default"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									variant: value as typeof props.variant,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="default">Default</SelectItem>
							<SelectItem value="destructive">
								Destructive
							</SelectItem>
							<SelectItem value="outline">Outline</SelectItem>
							<SelectItem value="secondary">Secondary</SelectItem>
							<SelectItem value="ghost">Ghost</SelectItem>
							<SelectItem value="link">Link</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField label="Size">
					<Select
						value={props.size ?? "default"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									size: value as typeof props.size,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="sm">Small</SelectItem>
							<SelectItem value="default">Default</SelectItem>
							<SelectItem value="lg">Large</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField
					label="Disabled"
					description="Boolean or expression (e.g., {{ status == 'completed' }})"
				>
					<Input
						value={
							typeof props.disabled === "boolean"
								? props.disabled
									? "true"
									: ""
								: (props.disabled ?? "")
						}
						onChange={(e) => {
							const value = e.target.value;
							// Empty = not disabled
							if (!value || value === "false") {
								onChange({
									props: { ...props, disabled: false },
								});
							} else if (value === "true") {
								onChange({
									props: { ...props, disabled: true },
								});
							} else {
								// Expression string
								onChange({
									props: { ...props, disabled: value },
								});
							}
						}}
						placeholder="false, true, or {{ expression }}"
					/>
				</FormField>

				<FormField label="Action Type">
					<Select
						value={props.actionType ?? ""}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									actionType: value as ButtonActionType,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue placeholder="Select action..." />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="navigate">Navigate</SelectItem>
							<SelectItem value="workflow">Workflow</SelectItem>
							<SelectItem value="submit">Submit Form</SelectItem>
							<SelectItem value="custom">Custom</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				{props.actionType === "navigate" && (
					<FormField
						label="Navigate To"
						description="Path to navigate (supports expressions)"
					>
						<Input
							value={props.navigateTo ?? ""}
							onChange={(e) =>
								onChange({
									props: {
										...props,
										navigateTo: e.target.value,
									},
								})
							}
							placeholder="/path/to/page"
						/>
					</FormField>
				)}

				{props.actionType === "workflow" && (
					<>
						<FormField label="Workflow">
							<WorkflowSelector
								value={props.workflowId}
								onChange={(workflowId: string | undefined) =>
									onChange({
										props: {
											...props,
											workflowId,
											actionParams: {},
										},
									})
								}
								placeholder="Select a workflow"
							/>
						</FormField>

						{props.workflowId && (
							<FormField
								label="Parameters"
								description="Values to pass to the workflow"
							>
								<WorkflowParameterEditor
									workflowId={props.workflowId}
									value={props.actionParams ?? {}}
									onChange={(actionParams) =>
										onChange({
											props: { ...props, actionParams },
										})
									}
									isRowAction={false}
								/>
							</FormField>
						)}
					</>
				)}

				{props.actionType === "submit" && (
					<>
						<FormField
							label="Workflow"
							description="All form field values will be passed automatically"
						>
							<WorkflowSelector
								value={props.workflowId}
								onChange={(workflowId: string | undefined) =>
									onChange({
										props: {
											...props,
											workflowId,
											actionParams: {},
										},
									})
								}
								placeholder="Select a workflow"
							/>
						</FormField>

						{props.workflowId && (
							<FormField
								label="Additional Parameters"
								description="Extra values to include (form fields auto-included)"
							>
								<WorkflowParameterEditor
									workflowId={props.workflowId}
									value={props.actionParams ?? {}}
									onChange={(actionParams) =>
										onChange({
											props: { ...props, actionParams },
										})
									}
									isRowAction={false}
								/>
							</FormField>
						)}
					</>
				)}

				{props.actionType === "custom" && (
					<>
						<FormField label="Custom Action ID">
							<Input
								value={props.customActionId ?? ""}
								onChange={(e) =>
									onChange({
										props: {
											...props,
											customActionId: e.target.value,
										},
									})
								}
								placeholder="action-id"
							/>
						</FormField>

						<FormField label="Parameters">
							<KeyValueEditor
								value={props.actionParams ?? {}}
								onChange={(actionParams) =>
									onChange({
										props: { ...props, actionParams },
									})
								}
							/>
						</FormField>
					</>
				)}
			</AccordionContent>
		</AccordionItem>
	);
}

/** Image component properties */
function ImagePropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "image") return null;

	const props = component.props;

	return (
		<AccordionItem value="image">
			<AccordionTrigger>Image</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Source URL"
					description="Image URL or expression"
				>
					<Input
						value={props.src}
						onChange={(e) =>
							onChange({
								props: { ...props, src: e.target.value },
							})
						}
						placeholder="https://example.com/image.png"
					/>
				</FormField>

				<FormField
					label="Alt Text"
					description="Accessibility description"
				>
					<Input
						value={props.alt ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									alt: e.target.value || undefined,
								},
							})
						}
						placeholder="Image description"
					/>
				</FormField>

				<FormField
					label="Max Width"
					description="Maximum width (e.g., 200 or 100%)"
				>
					<Input
						value={props.maxWidth ?? ""}
						onChange={(e) => {
							const val = e.target.value;
							const numVal = Number(val);
							onChange({
								props: {
									...props,
									maxWidth: val
										? isNaN(numVal)
											? val
											: numVal
										: undefined,
								},
							});
						}}
						placeholder="auto"
					/>
				</FormField>

				<FormField
					label="Max Height"
					description="Maximum height (e.g., 200 or 100%)"
				>
					<Input
						value={props.maxHeight ?? ""}
						onChange={(e) => {
							const val = e.target.value;
							const numVal = Number(val);
							onChange({
								props: {
									...props,
									maxHeight: val
										? isNaN(numVal)
											? val
											: numVal
										: undefined,
								},
							});
						}}
						placeholder="auto"
					/>
				</FormField>

				<FormField
					label="Object Fit"
					description="How the image scales within its container"
				>
					<Select
						value={props.objectFit ?? "contain"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									objectFit: value as typeof props.objectFit,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="contain">Contain</SelectItem>
							<SelectItem value="cover">Cover</SelectItem>
							<SelectItem value="fill">Fill</SelectItem>
							<SelectItem value="none">None</SelectItem>
						</SelectContent>
					</Select>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Card component properties */
function CardPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "card") return null;

	const props = component.props;

	return (
		<AccordionItem value="card">
			<AccordionTrigger>Card</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Title" description="Optional card title">
					<Input
						value={props.title ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									title: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField
					label="Description"
					description="Optional card description"
				>
					<Textarea
						value={props.description ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									description: e.target.value || undefined,
								},
							})
						}
						rows={2}
						placeholder="None"
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** StatCard component properties */
function StatCardPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "stat-card") return null;

	const props = component.props;

	return (
		<AccordionItem value="stat-card">
			<AccordionTrigger>Stat Card</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Title">
					<Input
						value={props.title}
						onChange={(e) =>
							onChange({
								props: { ...props, title: e.target.value },
							})
						}
					/>
				</FormField>

				<FormField
					label="Value"
					description="Supports expressions like {{ data.count }}"
				>
					<Input
						value={props.value}
						onChange={(e) =>
							onChange({
								props: { ...props, value: e.target.value },
							})
						}
					/>
				</FormField>

				<FormField label="Description" description="Additional context">
					<Input
						value={props.description ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									description: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField
					label="Icon"
					description="Icon name (e.g., users, chart)"
				>
					<Input
						value={props.icon ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									icon: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField label="Trend" description="Optional trend indicator">
					<JsonEditor
						value={
							props.trend ?? { value: "", direction: "neutral" }
						}
						onChange={(value) =>
							onChange({
								props: {
									...props,
									trend: value as typeof props.trend,
								},
							})
						}
						rows={4}
					/>
				</FormField>

				<FormField
					label="Click Action"
					description="Optional click behavior"
				>
					<JsonEditor
						value={
							props.onClick ?? {
								type: "navigate",
								navigateTo: "",
							}
						}
						onChange={(value) =>
							onChange({
								props: {
									...props,
									onClick: value as typeof props.onClick,
								},
							})
						}
						rows={4}
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** DataTable component properties */
function DataTablePropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "data-table") return null;

	const props = component.props;

	return (
		<AccordionItem value="data-table">
			<AccordionTrigger>Data Table</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Data Source"
					description="ID of a page data source (e.g., clientsList)"
				>
					<Input
						value={props.dataSource}
						onChange={(e) =>
							onChange({
								props: { ...props, dataSource: e.target.value },
							})
						}
						placeholder="dataSourceId"
					/>
				</FormField>

				<FormField
					label="Data Path"
					description="Path to array in result (e.g., 'clients' if workflow returns { clients: [...] })"
				>
					<Input
						value={props.dataPath ?? ""}
						onChange={(e) =>
							onChange({
								props: { ...props, dataPath: e.target.value || undefined },
							})
						}
						placeholder="Leave empty if result is already an array"
					/>
				</FormField>

				<FormField label="Searchable">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.searchable ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, searchable: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.searchable ? "Yes" : "No"}
						</span>
					</div>
				</FormField>

				<FormField label="Selectable">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.selectable ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, selectable: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.selectable ? "Yes" : "No"}
						</span>
					</div>
				</FormField>

				<FormField label="Paginated">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.paginated ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, paginated: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.paginated ? "Yes" : "No"}
						</span>
					</div>
				</FormField>

				{props.paginated && (
					<FormField label="Page Size" description="Rows per page">
						<Input
							type="number"
							value={props.pageSize ?? 10}
							onChange={(e) =>
								onChange({
									props: {
										...props,
										pageSize: Number(e.target.value) || 10,
									},
								})
							}
							min={1}
							max={100}
						/>
					</FormField>
				)}

				<FormField
					label="Empty Message"
					description="Message when no data"
				>
					<Input
						value={props.emptyMessage ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									emptyMessage: e.target.value || undefined,
								},
							})
						}
						placeholder="No data available"
					/>
				</FormField>

				<FormField label="Columns" description="Define table columns">
					<ColumnBuilder
						value={props.columns}
						onChange={(columns) =>
							onChange({
								props: { ...props, columns },
							})
						}
					/>
				</FormField>

				<FormField
					label="Row Actions"
					description="Actions available for each row"
				>
					<TableActionBuilder
						value={props.rowActions ?? []}
						onChange={(rowActions) =>
							onChange({
								props: { ...props, rowActions },
							})
						}
						isRowAction={true}
					/>
				</FormField>

				<FormField
					label="Header Actions"
					description="Actions in table header"
				>
					<TableActionBuilder
						value={props.headerActions ?? []}
						onChange={(headerActions) =>
							onChange({
								props: { ...props, headerActions },
							})
						}
						isRowAction={false}
					/>
				</FormField>

				<FormField
					label="Row Click Behavior"
					description="What happens when a row is clicked"
				>
					<Select
						value={props.onRowClick?.type ?? "none"}
						onValueChange={(type) => {
							if (type === "none") {
								onChange({
									props: { ...props, onRowClick: undefined },
								});
							} else {
								onChange({
									props: {
										...props,
										onRowClick: {
											type: type as
												| "navigate"
												| "select"
												| "set-variable",
											navigateTo:
												type === "navigate"
													? "/details/{{ row.id }}"
													: undefined,
											variableName:
												type === "set-variable"
													? "selectedRow"
													: undefined,
										},
									},
								});
							}
						}}
					>
						<SelectTrigger>
							<SelectValue placeholder="No action" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="none">No action</SelectItem>
							<SelectItem value="navigate">
								Navigate to page
							</SelectItem>
							<SelectItem value="select">Select row</SelectItem>
							<SelectItem value="set-variable">
								Set variable
							</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				{props.onRowClick?.type === "navigate" && (
					<FormField
						label="Navigate To"
						description="Path with {{ row.* }} expressions"
					>
						<Input
							value={props.onRowClick.navigateTo ?? ""}
							onChange={(e) =>
								onChange({
									props: {
										...props,
										onRowClick: {
											...props.onRowClick!,
											navigateTo: e.target.value,
										},
									},
								})
							}
							placeholder="/details/{{ row.id }}"
						/>
					</FormField>
				)}

				{props.onRowClick?.type === "set-variable" && (
					<FormField
						label="Variable Name"
						description="Store the row in this variable"
					>
						<Input
							value={props.onRowClick.variableName ?? ""}
							onChange={(e) =>
								onChange({
									props: {
										...props,
										onRowClick: {
											...props.onRowClick!,
											variableName: e.target.value,
										},
									},
								})
							}
							placeholder="selectedRow"
						/>
					</FormField>
				)}
			</AccordionContent>
		</AccordionItem>
	);
}

/** Tabs component properties */
function TabsPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "tabs") return null;

	const props = component.props;

	return (
		<AccordionItem value="tabs">
			<AccordionTrigger>Tabs</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Orientation">
					<Select
						value={props.orientation ?? "horizontal"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									orientation: value as
										| "horizontal"
										| "vertical",
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="horizontal">
								Horizontal
							</SelectItem>
							<SelectItem value="vertical">Vertical</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField
					label="Default Tab"
					description="ID of initially active tab"
				>
					<Input
						value={props.defaultTab ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									defaultTab: e.target.value || undefined,
								},
							})
						}
						placeholder="First tab"
					/>
				</FormField>

				<FormField
					label="Tab Items"
					description="Tab definitions (JSON array)"
				>
					<JsonEditor
						value={props.items}
						onChange={(value) =>
							onChange({
								props: {
									...props,
									items: value as typeof props.items,
								},
							})
						}
						rows={10}
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Badge component properties */
function BadgePropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "badge") return null;

	const props = component.props;

	return (
		<AccordionItem value="badge">
			<AccordionTrigger>Badge</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Text">
					<Input
						value={props.text}
						onChange={(e) =>
							onChange({
								props: { ...props, text: e.target.value },
							})
						}
					/>
				</FormField>

				<FormField label="Variant">
					<Select
						value={props.variant ?? "default"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									variant: value as typeof props.variant,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="default">Default</SelectItem>
							<SelectItem value="secondary">Secondary</SelectItem>
							<SelectItem value="destructive">
								Destructive
							</SelectItem>
							<SelectItem value="outline">Outline</SelectItem>
						</SelectContent>
					</Select>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Progress component properties */
function ProgressPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "progress") return null;

	const props = component.props;

	return (
		<AccordionItem value="progress">
			<AccordionTrigger>Progress</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Value" description="0-100 or expression">
					<Input
						value={String(props.value)}
						onChange={(e) => {
							const val = e.target.value;
							const numVal = Number(val);
							onChange({
								props: {
									...props,
									value: isNaN(numVal) ? val : numVal,
								},
							});
						}}
					/>
				</FormField>

				<FormField label="Show Label">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.showLabel ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, showLabel: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.showLabel ? "Yes" : "No"}
						</span>
					</div>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Divider component properties */
function DividerPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "divider") return null;

	const props = component.props;

	return (
		<AccordionItem value="divider">
			<AccordionTrigger>Divider</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField label="Orientation">
					<Select
						value={props.orientation ?? "horizontal"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									orientation: value as
										| "horizontal"
										| "vertical",
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="horizontal">
								Horizontal
							</SelectItem>
							<SelectItem value="vertical">Vertical</SelectItem>
						</SelectContent>
					</Select>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Spacer component properties */
function SpacerPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "spacer") return null;

	const props = component.props;

	return (
		<AccordionItem value="spacer">
			<AccordionTrigger>Spacer</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Size"
					description="Size in pixels or Tailwind units"
				>
					<Input
						value={String(props.size ?? "")}
						onChange={(e) => {
							const val = e.target.value;
							const numVal = Number(val);
							onChange({
								props: {
									...props,
									size: val
										? isNaN(numVal)
											? val
											: numVal
										: undefined,
								},
							});
						}}
						placeholder="16"
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Text Input component properties */
function TextInputPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "text-input") return null;

	const props = component.props;

	return (
		<AccordionItem value="text-input">
			<AccordionTrigger>Text Input</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Field ID"
					description="ID for accessing value via {{ field.fieldId }}"
				>
					<Input
						value={props.fieldId}
						onChange={(e) =>
							onChange({
								props: { ...props, fieldId: e.target.value },
							})
						}
						placeholder="fieldName"
					/>
				</FormField>

				<FormField label="Label">
					<Input
						value={props.label ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									label: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField label="Placeholder">
					<Input
						value={props.placeholder ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									placeholder: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField
					label="Default Value"
					description="Supports expressions"
				>
					<Input
						value={props.defaultValue ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									defaultValue: e.target.value || undefined,
								},
							})
						}
					/>
				</FormField>

				<FormField label="Input Type">
					<Select
						value={props.inputType ?? "text"}
						onValueChange={(value) =>
							onChange({
								props: {
									...props,
									inputType: value as typeof props.inputType,
								},
							})
						}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="text">Text</SelectItem>
							<SelectItem value="email">Email</SelectItem>
							<SelectItem value="password">Password</SelectItem>
							<SelectItem value="url">URL</SelectItem>
							<SelectItem value="tel">Phone</SelectItem>
						</SelectContent>
					</Select>
				</FormField>

				<FormField label="Required">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.required ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, required: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.required ? "Yes" : "No"}
						</span>
					</div>
				</FormField>

				<FormField
					label="Disabled"
					description="Boolean or expression (e.g., {{ status == 'locked' }})"
				>
					<Input
						value={
							typeof props.disabled === "boolean"
								? props.disabled
									? "true"
									: ""
								: (props.disabled ?? "")
						}
						onChange={(e) => {
							const value = e.target.value;
							if (!value || value === "false") {
								onChange({
									props: { ...props, disabled: false },
								});
							} else if (value === "true") {
								onChange({
									props: { ...props, disabled: true },
								});
							} else {
								onChange({
									props: { ...props, disabled: value },
								});
							}
						}}
						placeholder="false, true, or {{ expression }}"
					/>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Number Input component properties */
function NumberInputPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "number-input") return null;

	const props = component.props;

	return (
		<AccordionItem value="number-input">
			<AccordionTrigger>Number Input</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Field ID"
					description="ID for accessing value via {{ field.fieldId }}"
				>
					<Input
						value={props.fieldId}
						onChange={(e) =>
							onChange({
								props: { ...props, fieldId: e.target.value },
							})
						}
						placeholder="fieldName"
					/>
				</FormField>

				<FormField label="Label">
					<Input
						value={props.label ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									label: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField label="Placeholder">
					<Input
						value={props.placeholder ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									placeholder: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField
					label="Default Value"
					description="Number or expression"
				>
					<Input
						value={String(props.defaultValue ?? "")}
						onChange={(e) => {
							const val = e.target.value;
							const numVal = Number(val);
							onChange({
								props: {
									...props,
									defaultValue: val
										? isNaN(numVal)
											? val
											: numVal
										: undefined,
								},
							});
						}}
					/>
				</FormField>

				<FormField label="Min">
					<Input
						type="number"
						value={props.min ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									min: e.target.value
										? Number(e.target.value)
										: undefined,
								},
							})
						}
					/>
				</FormField>

				<FormField label="Max">
					<Input
						type="number"
						value={props.max ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									max: e.target.value
										? Number(e.target.value)
										: undefined,
								},
							})
						}
					/>
				</FormField>

				<FormField label="Step">
					<Input
						type="number"
						value={props.step ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									step: e.target.value
										? Number(e.target.value)
										: undefined,
								},
							})
						}
						placeholder="1"
					/>
				</FormField>

				<FormField label="Required">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.required ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, required: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.required ? "Yes" : "No"}
						</span>
					</div>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Select component properties */
function SelectPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "select") return null;

	const props = component.props;

	return (
		<AccordionItem value="select">
			<AccordionTrigger>Select</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Field ID"
					description="ID for accessing value via {{ field.fieldId }}"
				>
					<Input
						value={props.fieldId}
						onChange={(e) =>
							onChange({
								props: { ...props, fieldId: e.target.value },
							})
						}
						placeholder="fieldName"
					/>
				</FormField>

				<FormField label="Label">
					<Input
						value={props.label ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									label: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField label="Placeholder">
					<Input
						value={props.placeholder ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									placeholder: e.target.value || undefined,
								},
							})
						}
						placeholder="Select an option"
					/>
				</FormField>

				<FormField label="Default Value">
					<Input
						value={props.defaultValue ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									defaultValue: e.target.value || undefined,
								},
							})
						}
					/>
				</FormField>

				<FormField
					label="Options"
					description="Static options for the dropdown"
				>
					<OptionBuilder
						value={
							Array.isArray(props.options) ? props.options : []
						}
						onChange={(options) =>
							onChange({
								props: { ...props, options },
							})
						}
					/>
				</FormField>

				<FormField
					label="Options Data Source"
					description="Data source name for dynamic options"
				>
					<Input
						value={props.optionsSource ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									optionsSource: e.target.value || undefined,
								},
							})
						}
						placeholder="None (use static options)"
					/>
				</FormField>

				{props.optionsSource && (
					<>
						<FormField
							label="Value Field"
							description="Field in data source for option value"
						>
							<Input
								value={props.valueField ?? ""}
								onChange={(e) =>
									onChange({
										props: {
											...props,
											valueField:
												e.target.value || undefined,
										},
									})
								}
								placeholder="value"
							/>
						</FormField>

						<FormField
							label="Label Field"
							description="Field in data source for option label"
						>
							<Input
								value={props.labelField ?? ""}
								onChange={(e) =>
									onChange({
										props: {
											...props,
											labelField:
												e.target.value || undefined,
										},
									})
								}
								placeholder="label"
							/>
						</FormField>
					</>
				)}

				<FormField label="Required">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.required ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, required: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.required ? "Yes" : "No"}
						</span>
					</div>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Checkbox component properties */
function CheckboxPropertiesSection({
	component,
	onChange,
}: {
	component: AppComponent;
	onChange: (updates: Partial<AppComponent>) => void;
}) {
	if (component.type !== "checkbox") return null;

	const props = component.props;

	return (
		<AccordionItem value="checkbox">
			<AccordionTrigger>Checkbox</AccordionTrigger>
			<AccordionContent className="space-y-4 px-1">
				<FormField
					label="Field ID"
					description="ID for accessing value via {{ field.fieldId }}"
				>
					<Input
						value={props.fieldId}
						onChange={(e) =>
							onChange({
								props: { ...props, fieldId: e.target.value },
							})
						}
						placeholder="fieldName"
					/>
				</FormField>

				<FormField label="Label">
					<Input
						value={props.label}
						onChange={(e) =>
							onChange({
								props: { ...props, label: e.target.value },
							})
						}
					/>
				</FormField>

				<FormField
					label="Description"
					description="Help text below the checkbox"
				>
					<Input
						value={props.description ?? ""}
						onChange={(e) =>
							onChange({
								props: {
									...props,
									description: e.target.value || undefined,
								},
							})
						}
						placeholder="None"
					/>
				</FormField>

				<FormField label="Default Checked">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.defaultChecked ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: {
										...props,
										defaultChecked: checked,
									},
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.defaultChecked ? "Yes" : "No"}
						</span>
					</div>
				</FormField>

				<FormField label="Required">
					<div className="flex items-center gap-2">
						<Switch
							checked={props.required ?? false}
							onCheckedChange={(checked) =>
								onChange({
									props: { ...props, required: checked },
								})
							}
						/>
						<span className="text-sm text-muted-foreground">
							{props.required ? "Yes" : "No"}
						</span>
					</div>
				</FormField>
			</AccordionContent>
		</AccordionItem>
	);
}

/** Get component type sections based on component type */
function getComponentTypeSections(
	component: AppComponent,
	onChange: (updates: Partial<AppComponent>) => void,
): React.ReactNode {
	const componentType = component.type as ComponentType;

	switch (componentType) {
		case "heading":
			return (
				<HeadingPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "text":
			return (
				<TextPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "html":
			return (
				<HtmlPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "button":
			return (
				<ButtonPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "image":
			return (
				<ImagePropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "card":
			return (
				<CardPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "stat-card":
			return (
				<StatCardPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "data-table":
			return (
				<DataTablePropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "tabs":
			return (
				<TabsPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "badge":
			return (
				<BadgePropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "progress":
			return (
				<ProgressPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "divider":
			return (
				<DividerPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "spacer":
			return (
				<SpacerPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "text-input":
			return (
				<TextInputPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "number-input":
			return (
				<NumberInputPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "select":
			return (
				<SelectPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		case "checkbox":
			return (
				<CheckboxPropertiesSection
					component={component}
					onChange={onChange}
				/>
			);
		default:
			return null;
	}
}

/** Get display name for component type */
function getComponentDisplayName(
	component: AppComponent | LayoutContainer,
): string {
	if (isLayoutContainer(component)) {
		switch (component.type) {
			case "row":
				return "Row Layout";
			case "column":
				return "Column Layout";
			case "grid":
				return "Grid Layout";
			default:
				return "Layout";
		}
	}

	const typeNames: Record<ComponentType, string> = {
		heading: "Heading",
		text: "Text",
		html: "HTML/JSX",
		card: "Card",
		divider: "Divider",
		spacer: "Spacer",
		button: "Button",
		"stat-card": "Stat Card",
		image: "Image",
		badge: "Badge",
		progress: "Progress",
		"data-table": "Data Table",
		tabs: "Tabs",
		"file-viewer": "File Viewer",
		modal: "Modal",
		"text-input": "Text Input",
		"number-input": "Number Input",
		select: "Select",
		checkbox: "Checkbox",
		"form-embed": "Form Embed",
		"form-group": "Form Group",
	};

	return typeNames[component.type as ComponentType] ?? "Component";
}

/**
 * Property Editor Panel
 *
 * Displays and allows editing of properties for the selected component
 * in the app builder visual editor.
 */
export function PropertyEditor({
	component,
	onChange,
	onDelete,
	page,
	onPageChange,
	appAccessLevel,
	appRoleIds,
	className,
}: PropertyEditorProps) {
	if (!component) {
		return (
			<div
				className={cn(
					"flex items-center justify-center h-full text-muted-foreground text-sm p-4",
					className,
				)}
			>
				Select a component to edit its properties
			</div>
		);
	}

	const isLayout = isLayoutContainer(component);
	const displayName = getComponentDisplayName(component);

	// Check if this is the root layout (show page settings)
	const isRootLayout = isLayout && page && onPageChange;

	// Determine which accordion sections to open by default
	const defaultOpenSections = isRootLayout
		? ["page", "common", "layout"]
		: isLayout
			? ["common", "layout"]
			: ["common", component.type];

	return (
		<div className={cn("flex flex-col h-full", className)}>
			{/* Header */}
			<div className="px-4 py-3 border-b bg-muted/30">
				<h3 className="font-semibold text-sm">
					{isRootLayout ? page.title : displayName}
				</h3>
				<p className="text-xs text-muted-foreground mt-0.5">
					{isRootLayout
						? "Page settings and root layout"
						: isLayout
							? "Layout container"
							: `Component type: ${component.type}`}
				</p>
			</div>

			{/* Properties */}
			<div className="flex-1 overflow-y-auto px-4 py-2">
				<Accordion
					type="multiple"
					defaultValue={defaultOpenSections}
					className="w-full"
				>
					{/* Page settings for root layout */}
					{isRootLayout && (
						<PagePropertiesSection
							page={page}
							onChange={onPageChange}
							appAccessLevel={appAccessLevel}
							appRoleIds={appRoleIds}
						/>
					)}

					<CommonPropertiesSection
						component={component}
						onChange={onChange}
					/>

					{isLayout ? (
						<LayoutPropertiesSection
							component={component}
							onChange={
								onChange as (
									updates: Partial<LayoutContainer>,
								) => void
							}
						/>
					) : (
						getComponentTypeSections(
							component,
							onChange as (
								updates: Partial<AppComponent>,
							) => void,
						)
					)}
				</Accordion>
			</div>

			{/* Delete button */}
			{onDelete && (
				<div className="px-4 py-3 border-t mt-auto">
					<Button
						variant="destructive"
						size="sm"
						className="w-full"
						onClick={onDelete}
					>
						<Trash2 className="h-4 w-4 mr-2" />
						Delete Component
					</Button>
				</div>
			)}
		</div>
	);
}

export default PropertyEditor;
