/**
 * App Builder Tree Manipulation Utilities
 *
 * Functions for manipulating the component tree structure in App Builder definitions.
 * Used by the editor for adding, removing, moving, and updating components.
 */

import type { components } from "./v1";
import type { LayoutContainer } from "@/types/app-builder";
import {
	isLayoutContainer,
	canHaveChildren,
	getElementChildren,
} from "./app-builder-utils";

// Type aliases for generated API types
type AppComponent =
	| components["schemas"]["HeadingComponent"]
	| components["schemas"]["TextComponent"]
	| components["schemas"]["HtmlComponent"]
	| components["schemas"]["CardComponent"]
	| components["schemas"]["DividerComponent"]
	| components["schemas"]["SpacerComponent"]
	| components["schemas"]["ButtonComponent"]
	| components["schemas"]["StatCardComponent"]
	| components["schemas"]["ImageComponent"]
	| components["schemas"]["BadgeComponent"]
	| components["schemas"]["ProgressComponent"]
	| components["schemas"]["DataTableComponent"]
	| components["schemas"]["TabsComponent"]
	| components["schemas"]["FileViewerComponent"]
	| components["schemas"]["ModalComponent"]
	| components["schemas"]["TextInputComponent"]
	| components["schemas"]["NumberInputComponent"]
	| components["schemas"]["SelectComponent"]
	| components["schemas"]["CheckboxComponent"]
	| components["schemas"]["FormEmbedComponent"]
	| components["schemas"]["FormGroupComponent"];

type ComponentType =
	| "heading"
	| "text"
	| "html"
	| "card"
	| "divider"
	| "spacer"
	| "button"
	| "stat-card"
	| "image"
	| "badge"
	| "progress"
	| "data-table"
	| "tabs"
	| "file-viewer"
	| "modal"
	| "text-input"
	| "number-input"
	| "select"
	| "checkbox"
	| "form-embed"
	| "form-group";

type LayoutType = "row" | "column" | "grid";

// ============================================================================
// ID Generation
// ============================================================================

/**
 * Generate a unique component ID
 */
export function generateComponentId(): string {
	return `comp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Generate a unique page ID
 */
export function generatePageId(): string {
	return `page_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

// ============================================================================
// Component Creation
// ============================================================================

/**
 * Create a default component with the given type
 */
export function createDefaultComponent(
	type: ComponentType | LayoutType,
): AppComponent | LayoutContainer {
	const id = generateComponentId();

	// Check if it's a layout type
	if (type === "row" || type === "column" || type === "grid") {
		return {
			id,
			type,
			children: [],
			gap: 16,
			padding: 16,
		} as LayoutContainer;
	}

	// Component types
	switch (type) {
		case "heading":
			return {
				id,
				type: "heading",
				props: {
					text: "New Heading",
					level: 2,
				},
			};
		case "text":
			return {
				id,
				type: "text",
				props: {
					text: "Enter your text here...",
				},
			};
		case "html":
			return {
				id,
				type: "html",
				props: {
					content:
						'<div className="p-4 bg-muted rounded-lg">\n  <p>Custom HTML or JSX content</p>\n</div>',
				},
			};
		case "button":
			return {
				id,
				type: "button",
				props: {
					label: "Click Me",
					action_type: "navigate",
					variant: "default",
				},
			};
		case "card":
			return {
				id,
				type: "card",
				props: {
					title: "Card Title",
					description: "Card description",
				},
			};
		case "stat-card":
			return {
				id,
				type: "stat-card",
				props: {
					title: "Metric",
					value: "0",
				},
			};
		case "image":
			return {
				id,
				type: "image",
				props: {
					src: "https://via.placeholder.com/400x200",
					alt: "Placeholder image",
				},
			};
		case "divider":
			return {
				id,
				type: "divider",
				props: {
					orientation: "horizontal",
				},
			};
		case "spacer":
			return {
				id,
				type: "spacer",
				props: {
					size: 24,
				},
			};
		case "badge":
			return {
				id,
				type: "badge",
				props: {
					text: "Badge",
					variant: "default",
				},
			};
		case "progress":
			return {
				id,
				type: "progress",
				props: {
					value: 50,
					show_label: true,
				},
			};
		case "data-table":
			return {
				id,
				type: "data-table",
				props: {
					data_source: "tableName",
					columns: [
						{ key: "id", header: "ID" },
						{ key: "name", header: "Name" },
					],
					paginated: true,
					page_size: 10,
				},
			};
		case "tabs":
			return {
				id,
				type: "tabs",
				props: {
					items: [
						{
							id: "tab1",
							label: "Tab 1",
							content: { id: `${id}_tab1_content`, type: "column", children: [], gap: 8 },
						},
						{
							id: "tab2",
							label: "Tab 2",
							content: { id: `${id}_tab2_content`, type: "column", children: [], gap: 8 },
						},
					],
					orientation: "horizontal",
				},
			};
		case "text-input":
			return {
				id,
				type: "text-input",
				props: {
					field_id: `field_${id.slice(-6)}`,
					label: "Label",
					placeholder: "Enter text...",
				},
			};
		case "number-input":
			return {
				id,
				type: "number-input",
				props: {
					field_id: `field_${id.slice(-6)}`,
					label: "Number",
					placeholder: "0",
				},
			};
		case "select":
			return {
				id,
				type: "select",
				props: {
					field_id: `field_${id.slice(-6)}`,
					label: "Select",
					placeholder: "Select an option",
					options: [
						{ value: "option1", label: "Option 1" },
						{ value: "option2", label: "Option 2" },
					],
				},
			};
		case "checkbox":
			return {
				id,
				type: "checkbox",
				props: {
					field_id: `field_${id.slice(-6)}`,
					label: "Checkbox label",
				},
			};
		case "file-viewer":
			return {
				id,
				type: "file-viewer",
				props: {
					src: "https://example.com/file.pdf",
					display_mode: "inline",
				},
			};
		case "modal":
			return {
				id,
				type: "modal",
				props: {
					title: "Modal Title",
					description: "Modal description",
					trigger_label: "Open Modal",
					content: {
						id: `${id}_modal_content`,
						type: "column",
						children: [],
						gap: 16,
						padding: 16,
					},
					show_close_button: true,
				},
			};
		case "form-embed":
			return {
				id,
				type: "form-embed",
				props: {
					form_id: "",
					show_title: true,
					show_description: true,
				},
			};
		case "form-group":
			return {
				id,
				type: "form-group",
				props: {
					label: "Form Group",
					direction: "column",
					gap: 8,
					children: [],
				},
			};
		default:
			// Handle unknown component types
			return {
				id,
				type: "text",
				props: {
					text: `Unknown component type: ${type}`,
				},
			};
	}
}

// ============================================================================
// Tree Search
// ============================================================================

/**
 * Find an element in the layout tree by ID and return its reference along with
 * info about its location.
 */
export function findElementInTree(
	layout: LayoutContainer,
	targetId: string,
): {
	element: LayoutContainer | AppComponent;
	parentPath: string;
	index: number;
} | null {
	// Check if the layout itself is the target
	if (layout.id === targetId) {
		return { element: layout, parentPath: "", index: 0 };
	}

	// Helper to search any element with children
	function searchElement(
		element: LayoutContainer | AppComponent,
	): { element: LayoutContainer | AppComponent; parentPath: string; index: number } | null {
		const children = getElementChildren(element);
		for (let i = 0; i < children.length; i++) {
			const child = children[i];

			if (child.id === targetId) {
				return { element: child, parentPath: element.id, index: i };
			}

			// Recurse into children if this element can have them
			if (canHaveChildren(child)) {
				const result = searchElement(child);
				if (result) return result;
			}
		}
		return null;
	}

	return searchElement(layout);
}

/**
 * Find an element's ID by its object reference in the tree.
 * All elements now have persistent IDs, so this just returns the element's id.
 */
export function findElementId(
	layout: LayoutContainer,
	targetElement: LayoutContainer | AppComponent,
): string | null {
	// Check if the layout itself is the target
	if (layout === targetElement || layout.id === targetElement.id) {
		return layout.id;
	}

	// Helper to search any element with children
	function searchElement(
		element: LayoutContainer | AppComponent,
	): string | null {
		const children = getElementChildren(element);
		for (const child of children) {
			// Compare by reference or by ID
			if (child === targetElement || child.id === targetElement.id) {
				return child.id;
			}

			if (canHaveChildren(child)) {
				const result = searchElement(child);
				if (result) return result;
			}
		}
		return null;
	}

	return searchElement(layout);
}

/**
 * Get the element ID for a child element.
 * All elements (layouts and components) now have an `id` field.
 */
export function getChildId(child: LayoutContainer | AppComponent): string {
	return child.id;
}

// ============================================================================
// Tree Mutations
// ============================================================================

/**
 * Insert an element into the layout tree
 */
export function insertIntoTree(
	layout: LayoutContainer,
	newElement: LayoutContainer | AppComponent,
	targetId: string,
	position: "before" | "after" | "inside",
): LayoutContainer {
	// If target is this container itself, add to its children
	if (targetId === layout.id) {
		if (position === "before") {
			return {
				...layout,
				children: [newElement, ...layout.children],
			};
		}
		// "after" or "inside" - add to end
		return {
			...layout,
			children: [...layout.children, newElement],
		};
	}

	// Helper to recursively insert into any element with children
	function insertIntoElement(
		element: LayoutContainer | AppComponent,
	): LayoutContainer | AppComponent {
		const children = getElementChildren(element);
		const newChildren: (LayoutContainer | AppComponent)[] = [];

		for (const child of children) {
			if (child.id === targetId) {
				if (position === "before") {
					newChildren.push(newElement);
					newChildren.push(child);
				} else if (position === "after") {
					newChildren.push(child);
					newChildren.push(newElement);
				} else if (position === "inside" && canHaveChildren(child)) {
					// Add inside this child's children
					const childChildren = getElementChildren(child);
					if (isLayoutContainer(child)) {
						newChildren.push({
							...child,
							children: [...childChildren, newElement],
						});
					} else {
						// Component like Card - add to props.children
						newChildren.push({
							...child,
							props: { ...child.props, children: [...childChildren, newElement] },
						} as AppComponent);
					}
				} else {
					// Can't add inside non-container, add after instead
					newChildren.push(child);
					newChildren.push(newElement);
				}
			} else if (canHaveChildren(child)) {
				// Recursively process children
				newChildren.push(insertIntoElement(child));
			} else {
				newChildren.push(child);
			}
		}

		// Return updated element with new children in the right place
		if (isLayoutContainer(element)) {
			return { ...element, children: newChildren };
		}
		// For components like Card, children are in props.children
		return {
			...element,
			props: { ...element.props, children: newChildren },
		} as AppComponent;
	}

	return insertIntoElement(layout) as LayoutContainer;
}

/**
 * Remove an element from the layout tree
 */
export function removeFromTree(
	layout: LayoutContainer,
	targetId: string,
): { layout: LayoutContainer; removed: LayoutContainer | AppComponent | null } {
	let removed: LayoutContainer | AppComponent | null = null;

	// Helper to recursively remove from any element with children
	function removeFromElement(
		element: LayoutContainer | AppComponent,
	): { element: LayoutContainer | AppComponent; removed: LayoutContainer | AppComponent | null } {
		const children = getElementChildren(element);
		const newChildren: (LayoutContainer | AppComponent)[] = [];
		let localRemoved: LayoutContainer | AppComponent | null = null;

		for (const child of children) {
			if (child.id === targetId) {
				localRemoved = child;
				// Don't add to newChildren - this removes it
			} else if (canHaveChildren(child)) {
				const result = removeFromElement(child);
				newChildren.push(result.element);
				if (result.removed) localRemoved = result.removed;
			} else {
				newChildren.push(child);
			}
		}

		// Return updated element with new children in the right place
		let updatedElement: LayoutContainer | AppComponent;
		if (isLayoutContainer(element)) {
			updatedElement = { ...element, children: newChildren };
		} else {
			// For components like Card, children are in props.children
			updatedElement = {
				...element,
				props: { ...element.props, children: newChildren },
			} as AppComponent;
		}

		return { element: updatedElement, removed: localRemoved };
	}

	const result = removeFromElement(layout);
	removed = result.removed;

	return {
		layout: result.element as LayoutContainer,
		removed,
	};
}

/**
 * Move an element within the layout tree using element references instead of IDs.
 * This avoids the issue where removing an element shifts indices
 * and invalidates index-based layout container IDs.
 */
export function moveInTree(
	layout: LayoutContainer,
	sourceId: string,
	targetId: string,
	position: "before" | "after" | "inside",
): { layout: LayoutContainer; moved: boolean } {
	// Don't move an element onto itself
	if (sourceId === targetId) {
		return { layout, moved: false };
	}

	// Find the actual source and target elements BEFORE any modifications
	const sourceInfo = findElementInTree(layout, sourceId);
	const targetInfo = findElementInTree(layout, targetId);

	if (!sourceInfo || !targetInfo) {
		return { layout, moved: false };
	}

	// Store reference to the actual target element (not by ID)
	const targetElement = targetInfo.element;

	// First remove the source
	const removeResult = removeFromTree(layout, sourceId);
	if (!removeResult.removed) {
		return { layout, moved: false };
	}

	const elementToMove = removeResult.removed;
	const layoutAfterRemoval = removeResult.layout;

	// Now find where the target element is in the modified tree
	const newTargetId = findElementId(layoutAfterRemoval, targetElement);

	if (!newTargetId) {
		// Target was a child of source (which we removed), so fail gracefully
		return { layout, moved: false };
	}

	// Insert at the target position using the updated ID
	const insertResult = insertIntoTree(
		layoutAfterRemoval,
		elementToMove,
		newTargetId,
		position,
	);

	return { layout: insertResult, moved: true };
}

/**
 * Update an element in the layout tree
 */
export function updateInTree(
	layout: LayoutContainer,
	targetId: string,
	updates: Partial<AppComponent | LayoutContainer>,
): LayoutContainer {
	// Check if we're updating the layout itself
	if (layout.id === targetId) {
		return { ...layout, ...updates } as LayoutContainer;
	}

	// Helper to recursively update any element with children
	function updateElement(
		element: LayoutContainer | AppComponent,
	): LayoutContainer | AppComponent {
		const children = getElementChildren(element);
		let childrenUpdated = false;
		const newChildren: (LayoutContainer | AppComponent)[] = [];

		for (const child of children) {
			if (child.id === targetId) {
				// Apply updates to this element
				newChildren.push({ ...child, ...updates } as LayoutContainer | AppComponent);
				childrenUpdated = true;
			} else if (canHaveChildren(child)) {
				// Recursively update
				const updated = updateElement(child);
				newChildren.push(updated);
				if (updated !== child) childrenUpdated = true;
			} else {
				newChildren.push(child);
			}
		}

		if (!childrenUpdated) {
			return element;
		}

		// Return updated element with new children in the right place
		if (isLayoutContainer(element)) {
			return { ...element, children: newChildren };
		}
		// For components like Card, children are in props.children
		return {
			...element,
			props: { ...element.props, children: newChildren },
		} as AppComponent;
	}

	return updateElement(layout) as LayoutContainer;
}

/**
 * Duplicate an element in the layout tree
 * Returns the new layout and the duplicated element
 */
export function duplicateInTree(
	layout: LayoutContainer,
	targetId: string,
): { layout: LayoutContainer; duplicatedId: string | null } {
	const elementInfo = findElementInTree(layout, targetId);
	if (!elementInfo) {
		return { layout, duplicatedId: null };
	}

	// Deep clone the element with new IDs
	const duplicated = deepCloneWithNewIds(elementInfo.element);

	// Insert after the original
	const newLayout = insertIntoTree(layout, duplicated, targetId, "after");

	// Get the ID of the new element
	const duplicatedId = isLayoutContainer(duplicated)
		? null // Layout IDs are position-based, hard to determine
		: duplicated.id;

	return { layout: newLayout, duplicatedId };
}

/**
 * Deep clone an element with new IDs for all components
 */
function deepCloneWithNewIds(
	element: LayoutContainer | AppComponent,
): LayoutContainer | AppComponent {
	if (isLayoutContainer(element)) {
		return {
			...element,
			children: (element.children ?? []).map((child) => {
				// Validate child has required structure before recursing
				if (!child || typeof child !== "object" || !("type" in child)) {
					console.error("Invalid child in tree during clone:", child);
					return child;
				}
				// Use type guard to determine element type
				if (isLayoutContainer(child as LayoutContainer | AppComponent)) {
					return deepCloneWithNewIds(child as LayoutContainer);
				}
				return deepCloneWithNewIds(child as AppComponent);
			}),
		};
	}

	// It's a component - give it a new ID
	return {
		...element,
		id: generateComponentId(),
	};
}

/**
 * Wrap an element in a container
 */
export function wrapInContainer(
	layout: LayoutContainer,
	targetId: string,
	containerType: LayoutType,
): LayoutContainer {
	const elementInfo = findElementInTree(layout, targetId);
	if (!elementInfo) {
		return layout;
	}

	// Create the wrapper container
	const wrapper: LayoutContainer = {
		id: generateComponentId(),
		type: containerType,
		children: [elementInfo.element],
		gap: 16,
		padding: 0,
	};

	// Remove the original and insert the wrapper
	const { layout: layoutWithoutOriginal } = removeFromTree(layout, targetId);

	// Find where to insert - we need to find a sibling or use root
	// For simplicity, insert at root if we can't determine position
	// This could be improved to insert at the exact same position
	return insertIntoTree(
		layoutWithoutOriginal,
		wrapper,
		elementInfo.parentPath,
		"inside",
	);
}

// ============================================================================
// Display Helpers
// ============================================================================

/**
 * Get display label for a component type
 */
export function getComponentLabel(type: ComponentType | LayoutType): string {
	const labels: Record<ComponentType | LayoutType, string> = {
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
		row: "Row",
		column: "Column",
		grid: "Grid",
		"text-input": "Text Input",
		"number-input": "Number Input",
		select: "Select",
		checkbox: "Checkbox",
		"form-embed": "Form Embed",
		"form-group": "Form Group",
	};
	return labels[type] || type;
}

/**
 * Safely extract a string property from component props
 */
function getStringProp(props: unknown, key: string): string {
	if (props && typeof props === "object" && key in props) {
		const value = (props as Record<string, unknown>)[key];
		if (typeof value === "string") {
			return value;
		}
	}
	return "";
}

/**
 * Get additional info text for a component (title, text, etc.)
 */
export function getComponentInfo(
	element: LayoutContainer | AppComponent,
): string {
	if (isLayoutContainer(element)) {
		const childCount = (element.children ?? []).length;
		return `${childCount} ${childCount === 1 ? "child" : "children"}`;
	}

	// TypeScript knows element is AppComponent here due to the type guard above
	const props = element.props;
	switch (element.type) {
		case "heading":
		case "text":
			return getStringProp(props, "text").slice(0, 30);
		case "button":
			return getStringProp(props, "label");
		case "card":
		case "stat-card":
			return getStringProp(props, "title");
		case "data-table":
			return getStringProp(props, "data_source");
		default:
			return "";
	}
}

// ============================================================================
// Component Categories (for insertion popover)
// ============================================================================

export interface ComponentCategory {
	name: string;
	items: Array<{
		type: ComponentType | LayoutType;
		label: string;
		description: string;
	}>;
}

export const componentCategories: ComponentCategory[] = [
	{
		name: "Layout",
		items: [
			{ type: "row", label: "Row", description: "Horizontal container" },
			{
				type: "column",
				label: "Column",
				description: "Vertical container",
			},
			{ type: "grid", label: "Grid", description: "Grid layout" },
			{ type: "card", label: "Card", description: "Card with header" },
			{
				type: "tabs",
				label: "Tabs",
				description: "Tabbed content sections",
			},
		],
	},
	{
		name: "Display",
		items: [
			{ type: "heading", label: "Heading", description: "Page heading" },
			{ type: "text", label: "Text", description: "Paragraph text" },
			{ type: "html", label: "HTML/JSX", description: "Custom HTML" },
			{ type: "image", label: "Image", description: "Image display" },
			{ type: "badge", label: "Badge", description: "Status badge" },
			{
				type: "progress",
				label: "Progress",
				description: "Progress bar",
			},
			{
				type: "stat-card",
				label: "Stat Card",
				description: "Metric card",
			},
			{
				type: "divider",
				label: "Divider",
				description: "Horizontal line",
			},
			{ type: "spacer", label: "Spacer", description: "Empty space" },
		],
	},
	{
		name: "Form Inputs",
		items: [
			{
				type: "text-input",
				label: "Text Input",
				description: "Text field",
			},
			{
				type: "number-input",
				label: "Number Input",
				description: "Number field",
			},
			{ type: "select", label: "Select", description: "Dropdown select" },
			{
				type: "checkbox",
				label: "Checkbox",
				description: "Boolean checkbox",
			},
			{
				type: "form-group",
				label: "Form Group",
				description: "Group of inputs",
			},
			{
				type: "form-embed",
				label: "Form Embed",
				description: "Embed existing form",
			},
		],
	},
	{
		name: "Data",
		items: [
			{
				type: "data-table",
				label: "Data Table",
				description: "Table with actions",
			},
			{
				type: "file-viewer",
				label: "File Viewer",
				description: "PDF/file viewer",
			},
		],
	},
	{
		name: "Interactive",
		items: [
			{ type: "button", label: "Button", description: "Action button" },
			{ type: "modal", label: "Modal", description: "Dialog modal" },
		],
	},
];
