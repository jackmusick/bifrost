/**
 * Custom error class for API errors
 * Preserves the structured error response from the API
 * Handles both custom error format and FastAPI validation errors
 */

export interface ApiErrorResponse {
	error: string;
	message: string;
	details?: Record<string, unknown>;
}

/**
 * FastAPI validation error format (Pydantic v2)
 */
interface FastAPIValidationError {
	detail: Array<{
		type: string;
		loc: (string | number)[];
		msg: string;
		input?: unknown;
	}>;
}

/**
 * Check if error is a FastAPI validation error
 */
function isFastAPIValidationError(
	error: unknown,
): error is FastAPIValidationError {
	return (
		error !== null &&
		typeof error === "object" &&
		"detail" in error &&
		Array.isArray((error as FastAPIValidationError).detail) &&
		(error as FastAPIValidationError).detail.length > 0 &&
		typeof (error as FastAPIValidationError).detail[0] === "object" &&
		"msg" in (error as FastAPIValidationError).detail[0]
	);
}

/**
 * Convert FastAPI validation errors to a human-readable message
 */
function formatValidationErrors(error: FastAPIValidationError): string {
	const messages = error.detail.map((err) => {
		// Get the field name from location (skip 'body' prefix)
		const fieldPath = err.loc.filter((part) => part !== "body").join(".");
		const fieldName = fieldPath || "request";
		return `${fieldName}: ${err.msg}`;
	});

	if (messages.length === 1) {
		return messages[0];
	}
	return `Validation failed: ${messages.join("; ")}`;
}

/**
 * Rate limit error with retry information
 */
export class RateLimitError extends Error {
	public readonly retryAfter: number;
	public readonly statusCode = 429;

	constructor(retryAfter: number, message?: string) {
		super(
			message || `Too many requests. Please wait ${retryAfter} seconds.`,
		);
		this.retryAfter = retryAfter;
		this.name = "RateLimitError";
	}

	/**
	 * Get user-friendly message with wait time
	 */
	getUserMessage(): string {
		if (this.retryAfter <= 60) {
			return `Too many requests. Please wait ${this.retryAfter} seconds.`;
		}
		const minutes = Math.ceil(this.retryAfter / 60);
		return `Too many requests. Please wait ${minutes} minute${minutes > 1 ? "s" : ""}.`;
	}
}

export class ApiError extends Error {
	public readonly errorCode: string;
	public readonly details?: Record<string, unknown>;
	public readonly statusCode?: number;

	constructor(errorResponse: ApiErrorResponse | string, statusCode?: number) {
		// If it's a string, use it as the message
		if (typeof errorResponse === "string") {
			super(errorResponse);
			this.errorCode = "UnknownError";
			// Don't set optional properties - leave them undefined
		} else {
			// Use the message field from the API response
			super(errorResponse.message);
			this.errorCode = errorResponse.error;
			if (errorResponse.details !== undefined) {
				this.details = errorResponse.details;
			}
		}

		if (statusCode !== undefined) {
			this.statusCode = statusCode;
		}
		this.name = "ApiError";
	}

	/**
	 * Check if this is a rate limit error
	 */
	isRateLimitError(): boolean {
		return this.statusCode === 429;
	}

	/**
	 * Get a user-friendly error message
	 */
	getUserMessage(): string {
		return this.message;
	}

	/**
	 * Get the full error details for debugging
	 */
	getDebugInfo(): string {
		const parts = [`${this.errorCode}: ${this.message}`];

		if (this.details) {
			parts.push(`Details: ${JSON.stringify(this.details, null, 2)}`);
		}

		if (this.statusCode) {
			parts.push(`Status: ${this.statusCode}`);
		}

		return parts.join("\n");
	}
}

/**
 * Helper to parse error responses from openapi-fetch
 * Handles both custom error format and FastAPI validation errors
 */
export function parseApiError(error: unknown, statusCode?: number): ApiError {
	// If it's already an ApiError, return it
	if (error instanceof ApiError) {
		return error;
	}

	// Handle FastAPI validation errors (422 Unprocessable Entity)
	if (isFastAPIValidationError(error)) {
		const message = formatValidationErrors(error);
		return new ApiError(
			{
				error: "ValidationError",
				message,
				details: { validation_errors: error.detail },
			},
			statusCode ?? 422,
		);
	}

	// Handle FastAPI HTTPException with string detail
	if (
		error &&
		typeof error === "object" &&
		"detail" in error &&
		typeof (error as { detail: unknown }).detail === "string"
	) {
		return new ApiError(
			{
				error: "RequestError",
				message: (error as { detail: string }).detail,
			},
			statusCode,
		);
	}

	// If it's a structured error response with error/message fields
	if (
		error &&
		typeof error === "object" &&
		"error" in error &&
		"message" in error
	) {
		return new ApiError(error as ApiErrorResponse, statusCode);
	}

	// If it's a regular Error object
	if (error instanceof Error) {
		return new ApiError(error.message, statusCode);
	}

	// Fallback for unknown error types
	return new ApiError(String(error), statusCode);
}

/**
 * Extract a human-readable error message from any error type
 * Useful for displaying errors in toasts or UI components
 *
 * @param error - The error to extract message from
 * @param fallback - Fallback message if no message can be extracted
 * @returns A human-readable error message
 */
export function getErrorMessage(error: unknown, fallback: string): string {
	if (error instanceof ApiError) {
		return error.message;
	}
	if (error instanceof RateLimitError) {
		return error.getUserMessage();
	}
	if (error instanceof Error) {
		return error.message;
	}
	if (error && typeof error === "object" && "message" in error) {
		return String((error as { message: unknown }).message);
	}
	// Handle FastAPI HTTPException format: { detail: "error message" }
	if (
		error &&
		typeof error === "object" &&
		"detail" in error &&
		typeof (error as { detail: unknown }).detail === "string"
	) {
		return (error as { detail: string }).detail;
	}
	return fallback;
}
