/**
 * Text Component for App Builder
 *
 * Renders paragraph text with optional label and expression support.
 */

import { cn } from "@/lib/utils";
import type { TextComponentProps } from "@/lib/app-builder-types";
import { evaluateExpression } from "@/lib/expression-parser";
import type { RegisteredComponentProps } from "../ComponentRegistry";

/**
 * Text Component
 *
 * Renders a paragraph of text with optional label.
 * Supports expressions in both label and text content.
 *
 * @example
 * // Definition
 * {
 *   id: "user-email",
 *   type: "text",
 *   props: {
 *     label: "Email Address",
 *     text: "{{ user.email }}"
 *   }
 * }
 */
export function TextComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as TextComponentProps;
	const text = String(evaluateExpression(props?.text ?? "", context) ?? "");
	const label = props?.label
		? String(evaluateExpression(props.label, context) ?? "")
		: undefined;

	return (
		<div className={cn("space-y-1", props?.className)}>
			{label && (
				<p className="text-sm font-medium text-muted-foreground">
					{label}
				</p>
			)}
			<p className="leading-7">{text}</p>
		</div>
	);
}

export default TextComponent;
