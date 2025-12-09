import { useState, useEffect, useCallback } from "react";
import { AlertCircle, CheckCircle2, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { formatDistanceToNow } from "date-fns";

interface ValidationResult {
	valid: boolean;
	human_readable: string;
	next_runs?: string[];
	interval_seconds?: number;
	warning?: string;
	error?: string;
}

const EXAMPLE_EXPRESSIONS = [
	{ label: "Every 5 min", expression: "*/5 * * * *" },
	{ label: "Hourly", expression: "0 * * * *" },
	{ label: "Daily 9 AM", expression: "0 9 * * *" },
	{ label: "Weekly Mon", expression: "0 0 * * 1" },
];

export function CronTester() {
	const [expression, setExpression] = useState("");
	const [result, setResult] = useState<ValidationResult | null>(null);
	const [copied, setCopied] = useState(false);

	const validateExpression = useCallback(async (expr: string) => {
		if (!expr.trim()) return;

		try {
			const response = await fetch("/api/schedules/validate", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ expression: expr }),
			});
			const data = await response.json();
			setResult(data);
		} catch {
			setResult({
				valid: false,
				human_readable: "Failed to validate",
				error: "Unable to connect to validation service",
			});
		}
	}, []);

	// Debounced validation - only validate non-empty expressions
	useEffect(() => {
		if (!expression) {
			// Don't call setResult in effect - result will be filtered in render
			return;
		}

		const timer = setTimeout(() => {
			validateExpression(expression);
		}, 500);

		return () => clearTimeout(timer);
	}, [expression, validateExpression]);

	// Computed result - null when expression is empty
	const displayResult = expression ? result : null;

	const handleCopy = () => {
		navigator.clipboard.writeText(expression);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	return (
		<div className="space-y-4">
			<div className="flex gap-2">
				<Input
					placeholder="0 9 * * *"
					value={expression}
					onChange={(e) => setExpression(e.target.value)}
					className="font-mono"
				/>
				{expression && (
					<Button
						variant="outline"
						size="icon"
						onClick={handleCopy}
						title="Copy expression"
					>
						{copied ? (
							<Check className="h-4 w-4" />
						) : (
							<Copy className="h-4 w-4" />
						)}
					</Button>
				)}
			</div>

			{displayResult && (
				<div className="space-y-3">
					{displayResult.valid ? (
						<Alert className="bg-green-50 border-green-200 dark:bg-green-950 dark:border-green-800">
							<CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
							<AlertDescription className="text-green-800 dark:text-green-200">
								{displayResult.human_readable}
							</AlertDescription>
						</Alert>
					) : (
						<Alert variant="destructive">
							<AlertCircle className="h-4 w-4" />
							<AlertDescription>
								{displayResult.error ||
									displayResult.human_readable}
							</AlertDescription>
						</Alert>
					)}

					{displayResult.warning && (
						<Alert className="bg-yellow-50 border-yellow-200 dark:bg-yellow-950 dark:border-yellow-800">
							<AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
							<AlertDescription className="text-yellow-800 dark:text-yellow-200">
								{displayResult.warning}
							</AlertDescription>
						</Alert>
					)}

					{displayResult.next_runs &&
						displayResult.next_runs.length > 0 && (
							<div>
								<h4 className="text-sm font-semibold mb-2">
									Next 5 runs:
								</h4>
								<div className="space-y-1">
									{displayResult.next_runs.map((run, i) => {
										const date = new Date(run);
										return (
											<div
												key={i}
												className="text-sm flex items-center gap-2"
											>
												<span className="text-gray-500 dark:text-gray-400">
													•
												</span>
												<span>
													{date.toLocaleString()}
												</span>
												<span className="text-xs text-gray-500">
													(
													{formatDistanceToNow(date, {
														addSuffix: true,
													})}
													)
												</span>
											</div>
										);
									})}
								</div>
							</div>
						)}
				</div>
			)}

			<div>
				<h4 className="text-sm font-semibold mb-2">Quick examples:</h4>
				<div className="flex flex-wrap gap-2">
					{EXAMPLE_EXPRESSIONS.map((ex) => (
						<Button
							key={ex.expression}
							variant="outline"
							size="sm"
							onClick={() => setExpression(ex.expression)}
							className="text-xs"
						>
							{ex.label}
						</Button>
					))}
				</div>
			</div>
		</div>
	);
}
