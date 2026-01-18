/**
 * App Engine Selector
 *
 * Dialog for selecting the app engine type when creating a new application.
 * - Components: Visual drag-and-drop editor (default, existing)
 * - JSX: Code-based React components with file-based routing
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LayoutGrid, Code2, ArrowRight } from "lucide-react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface AppEngineSelectorProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
}

type EngineType = "components" | "code";

interface EngineOption {
	id: EngineType;
	title: string;
	description: string;
	icon: React.ReactNode;
	features: string[];
	recommended?: boolean;
}

const ENGINE_OPTIONS: EngineOption[] = [
	{
		id: "components",
		title: "Visual Builder",
		description: "Drag-and-drop interface for building apps without code",
		icon: <LayoutGrid className="h-8 w-8" />,
		features: [
			"No coding required",
			"Real-time visual preview",
			"Component palette with pre-built blocks",
			"Best for simple data displays and forms",
		],
		recommended: true,
	},
	{
		id: "code",
		title: "Code Editor",
		description: "Write React components with full control over behavior",
		icon: <Code2 className="h-8 w-8" />,
		features: [
			"Full React component support",
			"File-based routing (like Next.js)",
			"TypeScript with IntelliSense",
			"Best for complex logic and custom UIs",
		],
	},
];

export function AppEngineSelector({
	open,
	onOpenChange,
}: AppEngineSelectorProps) {
	const navigate = useNavigate();
	const [selectedEngine, setSelectedEngine] = useState<EngineType>("components");

	const handleContinue = () => {
		onOpenChange(false);
		if (selectedEngine === "code") {
			navigate("/apps/new/code");
		} else {
			navigate("/apps/new");
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-2xl">
				<DialogHeader>
					<DialogTitle>Create New Application</DialogTitle>
					<DialogDescription>
						Choose how you want to build your application
					</DialogDescription>
				</DialogHeader>

				<div className="grid grid-cols-2 gap-4 py-4">
					{ENGINE_OPTIONS.map((option) => (
						<button
							key={option.id}
							type="button"
							onClick={() => setSelectedEngine(option.id)}
							className={cn(
								"relative flex flex-col items-start gap-3 rounded-lg border-2 p-4 text-left transition-all hover:border-primary/50",
								selectedEngine === option.id
									? "border-primary bg-primary/5"
									: "border-border",
							)}
						>
							{option.recommended && (
								<span className="absolute -top-2.5 right-3 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
									Recommended
								</span>
							)}

							<div
								className={cn(
									"rounded-lg p-2",
									selectedEngine === option.id
										? "bg-primary text-primary-foreground"
										: "bg-muted text-muted-foreground",
								)}
							>
								{option.icon}
							</div>

							<div>
								<h3 className="font-semibold">{option.title}</h3>
								<p className="text-sm text-muted-foreground">
									{option.description}
								</p>
							</div>

							<ul className="mt-2 space-y-1 text-sm text-muted-foreground">
								{option.features.map((feature, i) => (
									<li key={i} className="flex items-center gap-2">
										<span className="h-1 w-1 rounded-full bg-muted-foreground" />
										{feature}
									</li>
								))}
							</ul>
						</button>
					))}
				</div>

				<div className="flex justify-end gap-2 pt-4 border-t">
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button onClick={handleContinue}>
						Continue
						<ArrowRight className="ml-2 h-4 w-4" />
					</Button>
				</div>
			</DialogContent>
		</Dialog>
	);
}
