/**
 * Image Component for App Builder
 *
 * Displays an image with optional sizing constraints.
 * Expression evaluation is handled centrally by ComponentRegistry.
 */

import { cn } from "@/lib/utils";
import type { ImageComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";

export function ImageComponent({ component }: RegisteredComponentProps) {
	const { props } = component as ImageComponentProps;

	// Props are pre-evaluated by ComponentRegistry
	const src = String(props?.src ?? "");
	const alt = props?.alt ? String(props.alt) : "";

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
