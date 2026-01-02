/**
 * Form Group Component for App Builder
 *
 * Groups multiple form input components together with an optional label.
 * Useful for creating logical groupings of related form fields.
 */

import { cn } from "@/lib/utils";
import type {
	FormGroupComponentProps,
	AppComponent,
	LayoutContainer,
} from "@/lib/app-builder-types";
import { isLayoutContainer } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { Label } from "@/components/ui/label";
import { renderRegisteredComponent } from "../ComponentRegistry";
import { LayoutRenderer } from "../LayoutRenderer";

/**
 * Form Group Component
 *
 * Renders a group of form fields with an optional label and description.
 * Child components are rendered in a row or column layout with configurable gap.
 *
 * @example
 * // Horizontal form group
 * {
 *   id: "name-group",
 *   type: "form-group",
 *   props: {
 *     label: "Full Name",
 *     direction: "row",
 *     gap: 16,
 *     children: [
 *       { id: "first", type: "text-input", props: { fieldId: "firstName", label: "First", placeholder: "First name" } },
 *       { id: "last", type: "text-input", props: { fieldId: "lastName", label: "Last", placeholder: "Last name" } }
 *     ]
 *   }
 * }
 *
 * @example
 * // Vertical form group with required indicator
 * {
 *   id: "contact-group",
 *   type: "form-group",
 *   props: {
 *     label: "Contact Information",
 *     description: "How should we reach you?",
 *     required: true,
 *     direction: "column",
 *     children: [
 *       { id: "email", type: "text-input", props: { fieldId: "email", inputType: "email", label: "Email" } },
 *       { id: "phone", type: "text-input", props: { fieldId: "phone", inputType: "tel", label: "Phone" } }
 *     ]
 *   }
 * }
 */
export function FormGroupComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as FormGroupComponentProps;
	const direction = props.direction || "column";
	const gap = props.gap ?? 16;

	// Build container styles
	const containerStyles: React.CSSProperties = {
		display: "flex",
		flexDirection: direction,
		gap: `${gap}px`,
	};

	// Render children
	const children = props.children || [];

	return (
		<div className={cn("space-y-2", props.className)}>
			{/* Group label */}
			{props.label && (
				<div className="space-y-1">
					<Label className="text-base font-medium">
						{props.label}
						{props.required && (
							<span className="text-destructive ml-1">*</span>
						)}
					</Label>
					{props.description && (
						<p className="text-sm text-muted-foreground">
							{props.description}
						</p>
					)}
				</div>
			)}

			{/* Child form fields */}
			<div style={containerStyles}>
				{children.map(
					(child: AppComponent | LayoutContainer, index: number) => {
						const key = isLayoutContainer(child)
							? `layout-${index}`
							: child.id;
						return (
							<div
								key={key}
								className={
									direction === "row" ? "flex-1" : undefined
								}
							>
								{isLayoutContainer(child) ? (
									<LayoutRenderer
										layout={child}
										context={context}
									/>
								) : (
									renderRegisteredComponent(child, context)
								)}
							</div>
						);
					},
				)}
			</div>
		</div>
	);
}

export default FormGroupComponent;
