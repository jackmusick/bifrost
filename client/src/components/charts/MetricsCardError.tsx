import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { getErrorMessage } from "@/lib/api-error";

interface MetricsCardErrorProps {
	label: string;
	error?: unknown;
}

export function MetricsCardError({ label, error }: MetricsCardErrorProps) {
	return (
		<Alert variant="destructive">
			<AlertCircle className="h-4 w-4" />
			<AlertDescription>
				Failed to load {label}:{" "}
				{getErrorMessage(error, "Please try again later.")}
			</AlertDescription>
		</Alert>
	);
}
