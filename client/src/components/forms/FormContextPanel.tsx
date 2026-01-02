import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { VariablesTreeView } from "@/components/ui/variables-tree-view";
import { useFormContext } from "@/contexts/FormContext";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

interface FormContextPanelProps {
	className?: string;
}

/**
 * Developer panel showing form context variables
 * Displays workflow results, query params, and field values in a tree view
 * Only visible to platform admins when Developer Mode is enabled
 */
export function FormContextPanel({ className }: FormContextPanelProps) {
	const { context, isLoadingLaunchWorkflow } = useFormContext();

	const hasWorkflow = Object.keys(context.workflow).length > 0;
	const hasQuery = Object.keys(context.query).length > 0;
	const hasField = Object.keys(context.field).length > 0;

	return (
		<Card className={cn("h-fit", className)}>
			<CardHeader className="pb-3">
				<CardTitle className="text-sm font-medium flex items-center gap-2">
					Form Context
					{isLoadingLaunchWorkflow && (
						<Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
					)}
				</CardTitle>
			</CardHeader>
			<CardContent className="space-y-4">
				{/* Workflow Results */}
				<ContextSection
					title="context.workflow"
					description="Launch workflow results"
					hasData={hasWorkflow}
					isLoading={isLoadingLaunchWorkflow}
					emptyMessage="No launch workflow configured"
				>
					<VariablesTreeView data={context.workflow} />
				</ContextSection>

				{/* Query Parameters */}
				<ContextSection
					title="context.query"
					description="URL query parameters"
					hasData={hasQuery}
					emptyMessage="No query parameters"
				>
					<VariablesTreeView data={context.query} />
				</ContextSection>

				{/* Field Values */}
				<ContextSection
					title="context.field"
					description="Current field values"
					hasData={hasField}
					emptyMessage="No field values yet"
				>
					<VariablesTreeView data={context.field} />
				</ContextSection>
			</CardContent>
		</Card>
	);
}

interface ContextSectionProps {
	title: string;
	description: string;
	hasData: boolean;
	isLoading?: boolean;
	emptyMessage: string;
	children: React.ReactNode;
}

function ContextSection({
	title,
	description,
	hasData,
	isLoading,
	emptyMessage,
	children,
}: ContextSectionProps) {
	return (
		<div className="space-y-1.5">
			<div>
				<code className="text-xs font-semibold text-primary">
					{title}
				</code>
				<p className="text-xs text-muted-foreground">{description}</p>
			</div>
			<div className="pl-2 border-l-2 border-muted">
				{isLoading ? (
					<div className="flex items-center gap-2 text-xs text-muted-foreground py-1">
						<Loader2 className="h-3 w-3 animate-spin" />
						Loading...
					</div>
				) : hasData ? (
					children
				) : (
					<p className="text-xs text-muted-foreground italic py-1">
						{emptyMessage}
					</p>
				)}
			</div>
		</div>
	);
}
