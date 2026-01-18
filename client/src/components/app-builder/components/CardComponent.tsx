/**
 * Card Component for App Builder
 *
 * Card wrapper with optional header, supporting nested content.
 * Expression evaluation is handled centrally by ComponentRegistry.
 */

import { cn } from "@/lib/utils";
import type { components } from "@/lib/v1";
import type { AppComponent } from "@/lib/app-builder-helpers";

type CardComponentType = components["schemas"]["CardComponent"];
import type { RegisteredComponentProps } from "../ComponentRegistry";
import {
	Card,
	CardHeader,
	CardTitle,
	CardDescription,
	CardContent,
} from "@/components/ui/card";
import { LayoutRenderer } from "../LayoutRenderer";

/**
 * Card Component
 *
 * Renders a card container with optional title and description.
 * Can contain nested layouts and components.
 *
 * @example
 * // Definition
 * {
 *   id: "user-card",
 *   type: "card",
 *   props: {
 *     title: "User Profile",
 *     description: "View and edit your profile information",
 *     children: [
 *       { id: "name", type: "text", props: { label: "Name", text: "{{ user.name }}" } }
 *     ]
 *   }
 * }
 */
export function CardComponent({
	component,
	context,
}: RegisteredComponentProps) {
	// In the unified model, props are at the top level of the component
	const comp = component as CardComponentType;
	// Props are pre-evaluated by ComponentRegistry
	const title = comp.title ? String(comp.title) : undefined;
	const description = comp.description
		? String(comp.description)
		: undefined;

	const hasHeader = title || description;

	const hasChildren = comp.children && comp.children.length > 0;

	// Build card styles for flex support
	// Note: overflow is NOT applied to the card itself - it goes on the content container
	// to enable internal scrolling while the card maintains its flex layout
	const cardStyle: React.CSSProperties = {};
	if (comp.flex === "grow") {
		cardStyle.flex = "1 1 0%";
		cardStyle.minHeight = 0;
	}

	// Content container needs flex-1 and overflow when card has flex grow
	const contentContainerClass = cn(
		"flex flex-col gap-4",
		comp.flex === "grow" && "flex-1 min-h-0",
		comp.overflow === "auto" && "overflow-auto",
	);

	return (
		<Card
			className={cn(
				"h-full",
				comp.flex === "grow" && "flex flex-col",
				comp.class_name,
			)}
			style={cardStyle}
		>
			{hasHeader && (
				<CardHeader className={comp.flex === "grow" ? "flex-shrink-0" : undefined}>
					{title && <CardTitle>{title}</CardTitle>}
					{description && (
						<CardDescription>{description}</CardDescription>
					)}
				</CardHeader>
			)}
			{hasChildren ? (
				<CardContent className={comp.flex === "grow" ? "flex-1 min-h-0 flex flex-col" : undefined}>
					<div className={contentContainerClass}>
						{comp.children!.map((child, index: number) => (
							<LayoutRenderer
								key={child.id ?? `child-${index}`}
								layout={child as AppComponent}
								context={context}
							/>
						))}
					</div>
				</CardContent>
			) : !hasHeader ? (
				// If card has no header and no children, show placeholder
				<CardContent>
					<div className="h-24 flex items-center justify-center text-muted-foreground text-sm">
						Empty card
					</div>
				</CardContent>
			) : null}
		</Card>
	);
}

export default CardComponent;
