/**
 * Tabs Component for App Builder
 *
 * Displays tabbed content with support for horizontal/vertical orientation.
 */

import { cn } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { components } from "@/lib/v1";

type TabsComponent = components["schemas"]["TabsComponent"];
import type { RegisteredComponentProps } from "../ComponentRegistry";
import { LayoutRenderer } from "../LayoutRenderer";

export function TabsComponent({
	component,
	context,
}: RegisteredComponentProps) {
	const { props } = component as TabsComponent;

	// Guard against undefined props or items
	const items = props?.items ?? [];
	if (items.length === 0) {
		return null;
	}

	const defaultTab = props?.default_tab || items[0]?.id;
	const isVertical = props?.orientation === "vertical";

	return (
		<Tabs
			defaultValue={defaultTab}
			className={cn(isVertical && "flex gap-4", props?.class_name)}
			orientation={props?.orientation ?? undefined}
		>
			<TabsList
				className={cn(
					isVertical && "flex-col h-auto items-stretch"
				)}
			>
				{items.map((item) => (
					<TabsTrigger
						key={item.id}
						value={item.id}
						className={cn(isVertical && "justify-start")}
					>
						{item.label}
					</TabsTrigger>
				))}
			</TabsList>
			<div className={cn(isVertical ? "flex-1" : "")}>
				{items.map((item) => (
					<TabsContent key={item.id} value={item.id} className="mt-0 pt-4">
						<LayoutRenderer
							layout={item.content}
							context={context}
						/>
					</TabsContent>
				))}
			</div>
		</Tabs>
	);
}
