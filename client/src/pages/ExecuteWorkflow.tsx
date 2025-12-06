import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowsMetadata, useExecuteWorkflow } from "@/hooks/useWorkflows";
import { WorkflowParametersForm } from "@/components/workflows/WorkflowParametersForm";

export function ExecuteWorkflow() {
	const { workflowName } = useParams();
	const navigate = useNavigate();
	const { data, isLoading } = useWorkflowsMetadata();
	const executeWorkflow = useExecuteWorkflow();

	// Track navigation state to keep button disabled through redirect
	const [isNavigating, setIsNavigating] = useState(false);

	const workflow = data?.workflows?.find((w) => w.name === workflowName);

	const handleExecute = async (parameters: Record<string, unknown>) => {
		if (!workflow) return;

		setIsNavigating(true);
		try {
			// Execute workflow with workflowName and inputData
			const result = await executeWorkflow.mutateAsync({
				workflowName: workflow.name ?? "",
				inputData: parameters,
			});

			// Redirect directly to execution details page
			navigate(`/history/${result.execution_id}`);
			// Don't reset isNavigating - component will unmount on navigation
		} catch {
			setIsNavigating(false); // Only re-enable button on error
		}
	};

	if (isLoading) {
		return (
			<div className="space-y-6">
				<Skeleton className="h-12 w-64" />
				<Skeleton className="h-96 w-full" />
			</div>
		);
	}

	if (!workflow) {
		return (
			<div className="space-y-6">
				<Alert variant="destructive">
					<XCircle className="h-4 w-4" />
					<AlertTitle>Error</AlertTitle>
					<AlertDescription>Workflow not found</AlertDescription>
				</Alert>
				<Button onClick={() => navigate("/workflows")}>
					<ArrowLeft className="mr-2 h-4 w-4" />
					Back to Workflows
				</Button>
			</div>
		);
	}

	return (
		<div className="space-y-6">
			<div className="flex justify-center">
				<div className="w-full max-w-2xl">
					<div className="flex items-center gap-4">
						<Button
							variant="ghost"
							size="icon"
							onClick={() => navigate("/workflows")}
						>
							<ArrowLeft className="h-4 w-4" />
						</Button>
						<div>
							<h1 className="text-4xl font-extrabold tracking-tight">
								Execute Workflow
							</h1>
							<p className="mt-2 text-muted-foreground">
								Workflow:{" "}
								<span className="font-mono">
									{workflow.name}
								</span>
							</p>
						</div>
					</div>
				</div>
			</div>

			<div className="flex justify-center">
				<div className="w-full max-w-2xl">
					<Card>
						<CardHeader>
							<CardTitle>{workflow.name}</CardTitle>
							{workflow.description && (
								<CardDescription>
									{workflow.description}
								</CardDescription>
							)}
						</CardHeader>
						<CardContent>
							<WorkflowParametersForm
								parameters={workflow.parameters || []}
								onExecute={handleExecute}
								isExecuting={
									executeWorkflow.isPending || isNavigating
								}
							/>
						</CardContent>
					</Card>
				</div>
			</div>
		</div>
	);
}
