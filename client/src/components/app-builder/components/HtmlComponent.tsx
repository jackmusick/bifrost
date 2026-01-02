/**
 * HTML Component for App Builder
 *
 * Renders HTML or JSX template content with context access.
 * Reuses the JsxTemplateRenderer from forms for JSX support.
 */

import DOMPurify from "dompurify";
import { cn } from "@/lib/utils";
import type {
	HtmlComponentProps,
	ExpressionContext,
} from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { JsxTemplateRenderer } from "@/components/ui/jsx-template-renderer";

/**
 * Adapts App Builder context to JsxTemplateRenderer context format
 */
function adaptContext(context: ExpressionContext): {
	workflow: Record<string, unknown>;
	query: Record<string, string>;
	field: Record<string, unknown>;
} {
	return {
		// Map variables to workflow for compatibility with existing templates
		workflow: {
			...context.variables,
			...context.data,
			user: context.user,
		},
		// Empty query params (could be populated from URL if needed)
		query: {},
		// Field context for self-referential templates
		field: {},
	};
}

/**
 * HTML Component
 *
 * Renders HTML or JSX template content. Automatically detects JSX
 * and uses the appropriate renderer.
 *
 * For plain HTML, content is sanitized with DOMPurify.
 * For JSX templates, content is compiled with Babel and rendered as React.
 *
 * JSX templates have access to context variables:
 * - `context.workflow.*` - All variables and data
 * - `context.workflow.user` - Current user info
 *
 * @example
 * // Plain HTML
 * {
 *   id: "banner",
 *   type: "html",
 *   props: {
 *     content: '<div class="p-4 bg-blue-100 rounded">Welcome!</div>'
 *   }
 * }
 *
 * @example
 * // JSX template with context
 * {
 *   id: "greeting",
 *   type: "html",
 *   props: {
 *     content: '<div className="p-4">Hello {context.workflow.user.name}!</div>'
 *   }
 * }
 */
export function HtmlComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as HtmlComponentProps;
	const content = props.content || "";

	// Check if content looks like JSX (contains React-style attributes or JSX expressions)
	const isJsxTemplate =
		content.includes("className=") || content.includes("{context.");

	if (isJsxTemplate) {
		// Render as JSX template with full context access
		return (
			<JsxTemplateRenderer
				template={content}
				context={adaptContext(context)}
				className={cn(props.className)}
			/>
		);
	}

	// Fallback to sanitized HTML
	const sanitizedHtml = DOMPurify.sanitize(content);

	return (
		<div
			className={cn(props.className)}
			dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
		/>
	);
}

export default HtmlComponent;
