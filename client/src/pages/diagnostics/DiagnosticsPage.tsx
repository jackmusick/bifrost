import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";
import { WorkersTab } from "./components/WorkersTab";

export function DiagnosticsPage() {
	const { isPlatformAdmin } = useAuth();
	const navigate = useNavigate();

	if (!isPlatformAdmin) {
		return (
			<div className="container mx-auto py-8">
				<Alert variant="destructive">
					<AlertCircle className="h-4 w-4" />
					<AlertDescription>
						You do not have permission to view diagnostics. Platform
						administrator access is required.
					</AlertDescription>
				</Alert>
				<Button onClick={() => navigate("/")} className="mt-4">
					Return to Dashboard
				</Button>
			</div>
		);
	}

	return (
		<div className="h-full flex flex-col space-y-6">
			{/* Header - aligned with WorkersTab's inner container */}
			<div className="max-w-[900px] mx-auto w-full">
				<h1 className="text-4xl font-extrabold tracking-tight">
					Diagnostics
				</h1>
				<p className="mt-2 text-muted-foreground">
					Monitor system health, process pools, and troubleshoot issues
				</p>
			</div>

			<div className="flex-1 overflow-auto">
				<WorkersTab />
			</div>
		</div>
	);
}

export default DiagnosticsPage;
