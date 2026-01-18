/**
 * JSX Error Boundary
 *
 * Catches render errors in JSX components and displays a friendly
 * error message with source location hints.
 */

import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface JsxErrorBoundaryProps {
	children: ReactNode;
	/** Optional file path to show in error display */
	filePath?: string;
	/** Callback when reset is clicked */
	onReset?: () => void;
	/** Custom fallback UI */
	fallback?: ReactNode;
}

interface JsxErrorBoundaryState {
	hasError: boolean;
	error: Error | null;
	errorInfo: ErrorInfo | null;
}

/**
 * Parse error message to extract helpful location hints
 */
function parseErrorLocation(
	error: Error | null,
): { line?: number; column?: number; hint?: string } | null {
	if (!error) return null;

	const message = error.message;

	// Try to extract line/column from common patterns
	// Pattern: "at line X, column Y"
	const lineColMatch = message.match(/at line (\d+),?\s*column (\d+)/i);
	if (lineColMatch) {
		return {
			line: parseInt(lineColMatch[1], 10),
			column: parseInt(lineColMatch[2], 10),
		};
	}

	// Pattern: "(X:Y)" at end of message
	const parenMatch = message.match(/\((\d+):(\d+)\)\s*$/);
	if (parenMatch) {
		return {
			line: parseInt(parenMatch[1], 10),
			column: parseInt(parenMatch[2], 10),
		};
	}

	// Pattern: "line X" standalone
	const lineMatch = message.match(/line (\d+)/i);
	if (lineMatch) {
		return {
			line: parseInt(lineMatch[1], 10),
		};
	}

	// Common error hints
	if (message.includes("is not defined")) {
		const varMatch = message.match(/(\w+) is not defined/);
		if (varMatch) {
			return {
				hint: `The variable "${varMatch[1]}" is not defined. Check for typos or missing imports.`,
			};
		}
	}

	if (message.includes("is not a function")) {
		return {
			hint: "You're trying to call something that isn't a function. Check your function names and imports.",
		};
	}

	if (message.includes("Cannot read properties of undefined")) {
		return {
			hint: "You're trying to access a property on an undefined value. Check that your data is loaded before accessing it.",
		};
	}

	if (message.includes("Cannot read properties of null")) {
		return {
			hint: "You're trying to access a property on a null value. Add null checks before accessing nested properties.",
		};
	}

	return null;
}

/**
 * Error boundary for JSX app components
 *
 * Catches runtime errors and displays a friendly error message
 * with source location hints when available.
 */
export class JsxErrorBoundary extends Component<
	JsxErrorBoundaryProps,
	JsxErrorBoundaryState
> {
	constructor(props: JsxErrorBoundaryProps) {
		super(props);
		this.state = {
			hasError: false,
			error: null,
			errorInfo: null,
		};
	}

	static getDerivedStateFromError(error: Error): Partial<JsxErrorBoundaryState> {
		return { hasError: true, error };
	}

	componentDidCatch(error: Error, errorInfo: ErrorInfo) {
		if (import.meta.env.DEV) {
			console.error("JsxErrorBoundary caught an error:", error, errorInfo);
		}
		this.setState({ errorInfo });
	}

	handleReset = () => {
		this.setState({
			hasError: false,
			error: null,
			errorInfo: null,
		});
		this.props.onReset?.();
	};

	render() {
		if (this.state.hasError) {
			if (this.props.fallback) {
				return this.props.fallback;
			}

			const location = parseErrorLocation(this.state.error);
			const errorMessage =
				this.state.error?.message || "An unknown error occurred";

			return (
				<div className="flex items-center justify-center min-h-[400px] p-4">
					<Card className="w-full max-w-xl">
						<CardHeader>
							<div className="flex items-center gap-3">
								<div className="flex h-10 w-10 items-center justify-center rounded-lg bg-destructive/10">
									<AlertTriangle className="h-5 w-5 text-destructive" />
								</div>
								<div>
									<CardTitle className="text-lg">
										Component Error
									</CardTitle>
									<CardDescription>
										{this.props.filePath
											? `Error in ${this.props.filePath}`
											: "An error occurred while rendering"}
									</CardDescription>
								</div>
							</div>
						</CardHeader>
						<CardContent className="space-y-4">
							<Alert variant="destructive">
								<AlertDescription className="font-mono text-sm break-words">
									{errorMessage}
								</AlertDescription>
							</Alert>

							{location && (location.line || location.hint) && (
								<div className="rounded-lg bg-muted p-3 text-sm">
									{location.line && (
										<p className="text-muted-foreground">
											<span className="font-medium">
												Location:
											</span>{" "}
											Line {location.line}
											{location.column &&
												`, Column ${location.column}`}
										</p>
									)}
									{location.hint && (
										<p className="text-muted-foreground mt-1">
											<span className="font-medium">
												Hint:
											</span>{" "}
											{location.hint}
										</p>
									)}
								</div>
							)}

							{import.meta.env.DEV && this.state.errorInfo && (
								<details className="text-sm">
									<summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">
										Stack Trace (Development Only)
									</summary>
									<pre className="mt-2 overflow-auto rounded-lg bg-muted p-3 text-xs max-h-48">
										{this.state.error?.stack}
									</pre>
								</details>
							)}
						</CardContent>
						<CardFooter>
							<Button onClick={this.handleReset} size="sm">
								<RotateCcw className="mr-2 h-4 w-4" />
								Try Again
							</Button>
						</CardFooter>
					</Card>
				</div>
			);
		}

		return this.props.children;
	}
}
