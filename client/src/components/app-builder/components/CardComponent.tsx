/**
 * Card Component for App Builder
 *
 * Card wrapper with optional header, supporting nested content.
 */

import { cn } from "@/lib/utils";
import type { CardComponentProps } from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
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
export function CardComponent({ component, context }: RegisteredComponentProps) {
	const { props } = component as CardComponentProps;
	const title = props.title
		? String(evaluateExpression(props.title, context) ?? "")
		: undefined;
	const description = props.description
		? String(evaluateExpression(props.description, context) ?? "")
		: undefined;

	const hasHeader = title || description;

	return (
		<Card className={cn(props.className)}>
			{hasHeader && (
				<CardHeader>
					{title && <CardTitle>{title}</CardTitle>}
					{description && <CardDescription>{description}</CardDescription>}
				</CardHeader>
			)}
			{props.children && props.children.length > 0 && (
				<CardContent>
					<div className="flex flex-col gap-4">
						{props.children.map((child, index) => (
							<LayoutRenderer
								key={"id" in child ? child.id : `child-${index}`}
								layout={child}
								context={context}
							/>
						))}
					</div>
				</CardContent>
			)}
		</Card>
	);
}

export default CardComponent;
