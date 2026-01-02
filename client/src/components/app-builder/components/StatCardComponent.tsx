/**
 * StatCard Component for App Builder
 *
 * Displays a statistic with optional trend indicator and click action.
 */

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { StatCardComponentProps } from "@/lib/app-builder-types";
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { evaluateExpression } from "@/lib/expression-parser";
import { getIcon } from "@/lib/icons";

function getTrendIcon(direction: "up" | "down" | "neutral") {
	switch (direction) {
		case "up":
			return <TrendingUp className="h-4 w-4 text-green-500" />;
		case "down":
			return <TrendingDown className="h-4 w-4 text-red-500" />;
		case "neutral":
			return <Minus className="h-4 w-4 text-muted-foreground" />;
	}
}

function getTrendColor(direction: "up" | "down" | "neutral") {
	switch (direction) {
		case "up":
			return "text-green-500";
		case "down":
			return "text-red-500";
		case "neutral":
			return "text-muted-foreground";
	}
}

export function StatCardComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as StatCardComponentProps;

	// Evaluate expressions - get raw values to check if undefined
	const rawValue = evaluateExpression(props?.value ?? "", context);
	const title = String(evaluateExpression(props?.title ?? "", context) ?? "");
	const value = String(rawValue ?? "");
	const description = props?.description
		? String(evaluateExpression(props.description, context) ?? "")
		: undefined;

	// Show skeleton if value is undefined AND data is still loading
	const isLoading = rawValue === undefined && context.isDataLoading;

	const handleClick = () => {
		if (!props?.onClick) return;

		if (
			props.onClick.type === "navigate" &&
			props.onClick.navigateTo &&
			context.navigate
		) {
			const path = String(
				evaluateExpression(props.onClick.navigateTo, context) ?? "",
			);
			context.navigate(path);
		} else if (
			props.onClick.type === "workflow" &&
			props.onClick.workflowId &&
			context.triggerWorkflow
		) {
			context.triggerWorkflow(props.onClick.workflowId);
		}
	};

	const isClickable = !!props?.onClick;

	return (
		<Card
			className={cn(
				"flex-1 transition-colors",
				isClickable && "cursor-pointer hover:bg-accent",
				props?.className,
			)}
			onClick={isClickable ? handleClick : undefined}
		>
			{/* Fixed height container ensures consistent card sizes */}
			<CardContent className="p-6 h-full flex flex-col">
				<div className="flex items-center justify-between">
					{isLoading ? (
						<Skeleton className="h-4 w-24" />
					) : (
						<p className="text-sm font-medium text-muted-foreground">
							{title}
						</p>
					)}
					{props?.icon &&
						(() => {
							const IconComponent = getIcon(props.icon);
							return (
								<IconComponent className="h-5 w-5 text-muted-foreground" />
							);
						})()}
				</div>
				<div className="mt-2 flex items-baseline gap-2">
					{isLoading ? (
						<Skeleton className="h-8 w-16" />
					) : (
						<p className="text-2xl font-bold">{value}</p>
					)}
					{props?.trend && !isLoading && (
						<div
							className={cn(
								"flex items-center gap-1 text-sm",
								getTrendColor(props.trend.direction),
							)}
						>
							{getTrendIcon(props.trend.direction)}
							<span>{props.trend.value}</span>
						</div>
					)}
				</div>
				{/* Description area - always reserve space for consistent height */}
				{isLoading ? (
					<Skeleton className="mt-auto h-4 w-32" />
				) : (
					<p
						className={cn(
							"mt-auto pt-1 text-sm text-muted-foreground min-h-[1.25rem]",
							!description && "invisible",
						)}
					>
						{description || "\u00A0"}
					</p>
				)}
			</CardContent>
		</Card>
	);
}
