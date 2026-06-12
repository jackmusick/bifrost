import { Loader2, CheckCircle2, XCircle, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type IntegrationTestResponse } from "@/services/integrations";
import { OrganizationSelect } from "@/components/forms/OrganizationSelect";

export interface IntegrationTestPanelProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	testOrgId: string | null;
	onTestOrgIdChange: (value: string | null) => void;
	testEndpoint: string;
	onTestEndpointChange: (value: string) => void;
	testResult: IntegrationTestResponse | null;
	onClearResult: () => void;
	onTest: () => void;
	isTestPending: boolean;
}

export function IntegrationTestPanel({
	open,
	onOpenChange,
	testOrgId,
	onTestOrgIdChange,
	testEndpoint,
	onTestEndpointChange,
	testResult,
	onClearResult,
	onTest,
	isTestPending,
}: IntegrationTestPanelProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-md">
				<DialogHeader>
					<DialogTitle>Test Integration Connection</DialogTitle>
					<DialogDescription>
						Test connectivity by making a GET request to the
						specified endpoint.
					</DialogDescription>
				</DialogHeader>
				<div className="space-y-4 py-4">
					<div className="space-y-2">
						<Label htmlFor="test-org">Organization</Label>
						<OrganizationSelect
							value={testOrgId}
							onChange={(value) => {
								// OrganizationSelect uses undefined for "All", but we only care about null (Global) or string (org)
								onTestOrgIdChange(
									value === undefined ? null : value,
								);
								onClearResult();
							}}
							showGlobal={true}
							showAll={false}
							placeholder="Select organization..."
						/>
						<p className="text-sm text-muted-foreground">
							Select "Global" to test with integration
							defaults only, or choose an organization to test
							with merged config and OAuth.
						</p>
					</div>

					<div className="space-y-2">
						<Label htmlFor="test-endpoint">Endpoint</Label>
						<Input
							id="test-endpoint"
							value={testEndpoint}
							onChange={(e) => {
								onTestEndpointChange(e.target.value);
								onClearResult();
							}}
							placeholder="/api/users"
						/>
						<p className="text-sm text-muted-foreground">
							API endpoint path to test. Will be appended to
							the integration's base_url.
						</p>
					</div>

					{/* Test Result Display */}
					{testResult && (
						<div
							className={`p-4 rounded-lg ring-1 ${
								testResult.success
									? "bg-green-50 dark:bg-green-950 ring-green-200 dark:ring-green-800"
									: "bg-red-50 dark:bg-red-950 ring-red-200 dark:ring-red-800"
							}`}
						>
							<div className="flex items-start gap-2">
								{testResult.success ? (
									<CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400 mt-0.5" />
								) : (
									<XCircle className="h-5 w-5 text-red-600 dark:text-red-400 mt-0.5" />
								)}
								<div className="flex-1 min-w-0">
									<p
										className={`font-medium ${
											testResult.success
												? "text-green-800 dark:text-green-200"
												: "text-red-800 dark:text-red-200"
										}`}
									>
										{testResult.message}
									</p>
									{testResult.method_called && (
										<p className="text-sm text-muted-foreground mt-1">
											Method:{" "}
											<code className="bg-muted px-1 rounded">
												{testResult.method_called}()
											</code>
										</p>
									)}
									{testResult.duration_ms && (
										<p className="text-sm text-muted-foreground">
											Duration:{" "}
											{testResult.duration_ms}
											ms
										</p>
									)}
									{testResult.error_details && (
										<p className="text-sm text-red-600 dark:text-red-400 mt-2 break-words">
											{testResult.error_details}
										</p>
									)}
								</div>
							</div>
						</div>
					)}
				</div>
				<DialogFooter>
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
					>
						Close
					</Button>
					<Button
						onClick={onTest}
						disabled={isTestPending}
					>
						{isTestPending ? (
							<>
								<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								Testing...
							</>
						) : (
							<>
								<Zap className="h-4 w-4 mr-2" />
								Test
							</>
						)}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
