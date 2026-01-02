/**
 * Image Component for App Builder
 *
 * Displays an image with optional sizing constraints.
 */

import { cn } from "@/lib/utils";
import type { ImageComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";

export function ImageComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as ImageComponentProps;

	// Evaluate expressions
	const src = String(evaluateExpression(props?.src ?? "", context) ?? "");
	const alt = props?.alt
		? String(evaluateExpression(props.alt, context) ?? "")
		: "";

	const style: React.CSSProperties = {};

	if (props?.maxWidth) {
		style.maxWidth =
			typeof props.maxWidth === "number"
				? `${props.maxWidth}px`
				: props.maxWidth;
	}

	if (props?.maxHeight) {
		style.maxHeight =
			typeof props.maxHeight === "number"
				? `${props.maxHeight}px`
				: props.maxHeight;
	}

	const objectFitClass = props?.objectFit
		? `object-${props.objectFit}`
		: "object-contain";

	return (
		<img
			src={src}
			alt={alt}
			style={style}
			className={cn(objectFitClass, props?.className)}
		/>
	);
}
