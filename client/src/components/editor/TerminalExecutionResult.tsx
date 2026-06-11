import { useState } from "react";
import { useExecutionResult } from "@/hooks/useExecutions";
import { Loader2, FileText, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TerminalResultModal } from "./TerminalResultModal";
import { useNavigate } from "react-router-dom";

interface TerminalExecutionResultProps {
	executionId: string;
	status: string;
}

// Type for the execution result from the API
interface ExecutionResultData {
	result: unknown;
	resultType?: "html" | "json" | "text";
}

/**
 * Component to display execution results in the terminal
 * Shows a preview or link to view results based on result type
 */
export function TerminalExecutionResult({
	executionId,
	status,
}: TerminalExecutionResultProps) {
	const [showHtmlModal, setShowHtmlModal] = useState(false);
	const navigate = useNavigate();

	// Only fetch result if execution is complete (not running or pending)
	const isComplete =
		status === "Success" ||
		status === "Failed" ||
		status === "CompletedWithErrors" ||
		status === "Timeout" ||
		status === "Cancelled";

	const { data: resultData, isLoading } = useExecutionResult(
		executionId,
		isComplete,
	);

	// Cast to expected type
	const typedResultData = resultData as ExecutionResultData | undefined;

	// Don't render anything if not complete or no result
	if (!isComplete || (!isLoading && !typedResultData?.result)) {
		return null;
	}

	if (isLoading) {
		return (
			<div className="flex items-center gap-2 text-muted-foreground text-xs mt-1 ml-4">
				<Loader2 className="h-3 w-3 animate-spin" />
				<span>Loading result...</span>
			</div>
		);
	}

	const handleViewDetails = () => {
		navigate(`/history/${executionId}`);
	};

	// HTML result - show button to view in modal
	if (
		typedResultData?.resultType === "html" &&
		typeof typedResultData?.result === "string"
	) {
		return (
			<>
				<div className="ml-4 mt-1">
					<Button
						variant="link"
						size="sm"
						onClick={() => setShowHtmlModal(true)}
						className="h-auto p-0 text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300"
					>
						<FileText className="h-3 w-3 mr-1" />
						Click to view HTML result
					</Button>
				</div>
				<TerminalResultModal
					open={showHtmlModal}
					onOpenChange={setShowHtmlModal}
					html={typedResultData.result}
					executionId={executionId}
				/>
			</>
		);
	}

	// JSON/Object result - show formatted preview with max height
	if (
		(typedResultData?.resultType === "json" &&
			typeof typedResultData?.result === "object") ||
		(!typedResultData?.resultType &&
			typeof typedResultData?.result === "object" &&
			typedResultData?.result !== null)
	) {
		const jsonString = JSON.stringify(typedResultData.result, null, 2);
		const lines = jsonString.split("\n");
		const preview = lines.slice(0, 10).join("\n");
		const hasMore = lines.length > 10;

		return (
			<div className="ml-4 mt-1 text-xs">
				<div className="bg-muted/50 p-2 rounded-md ring-1 ring-foreground/5 max-h-[200px] overflow-auto">
					<pre className="text-foreground/80 whitespace-pre-wrap font-mono">
						{preview}
						{hasMore && "\n..."}
					</pre>
				</div>
				{hasMore && (
					<Button
						variant="link"
						size="sm"
						onClick={handleViewDetails}
						className="h-auto p-0 mt-1 text-xs"
					>
						<ExternalLink className="h-3 w-3 mr-1" />
						View full result in Execution Details
					</Button>
				)}
			</div>
		);
	}

	// Text result - show inline with max height
	if (
		typedResultData?.resultType === "text" &&
		typeof typedResultData?.result === "string"
	) {
		const lines = typedResultData.result.split("\n");
		const preview = lines.slice(0, 10).join("\n");
		const hasMore = lines.length > 10;

		return (
			<div className="ml-4 mt-1 text-xs">
				<div className="bg-muted/50 p-2 rounded-md ring-1 ring-foreground/5 max-h-[200px] overflow-auto">
					<pre className="text-foreground/80 whitespace-pre-wrap font-mono">
						{preview}
						{hasMore && "\n..."}
					</pre>
				</div>
				{hasMore && (
					<Button
						variant="link"
						size="sm"
						onClick={handleViewDetails}
						className="h-auto p-0 mt-1 text-xs"
					>
						<ExternalLink className="h-3 w-3 mr-1" />
						View full result in Execution Details
					</Button>
				)}
			</div>
		);
	}

	// No result to display
	return null;
}
