/**
 * JSX Compiler
 *
 * Browser-based JSX/TSX compilation using Babel standalone.
 * Compiles user-authored JSX source into executable JavaScript.
 */

import { transform } from "@babel/standalone";

/**
 * Result of JSX compilation
 */
export interface CompileResult {
	/** Whether compilation succeeded */
	success: boolean;
	/** Compiled JavaScript code (if successful) */
	compiled?: string;
	/** Error message (if failed) */
	error?: string;
}

/**
 * Compile JSX/TSX source to executable JavaScript
 *
 * Uses Babel standalone with React preset and modern JS plugins.
 * Strips TypeScript annotations while preserving runtime behavior.
 *
 * @param source - JSX/TSX source code
 * @returns Compilation result with success status and compiled code or error
 *
 * @example
 * ```typescript
 * const result = compileJsx(`
 *   const [count, setCount] = useState(0);
 *   return <Button onClick={() => setCount(c => c + 1)}>{count}</Button>;
 * `);
 *
 * if (result.success) {
 *   console.log(result.compiled);
 * } else {
 *   console.error(result.error);
 * }
 * ```
 */
export function compileJsx(source: string): CompileResult {
	try {
		const result = transform(source, {
			presets: ["react", "typescript"],
			plugins: [
				// Modern JavaScript features
				"proposal-optional-chaining",
				"proposal-nullish-coalescing-operator",
			],
			// Don't add "use strict" or module wrapper
			sourceType: "script",
		});

		if (!result.code) {
			return {
				success: false,
				error: "Compilation produced no output",
			};
		}

		return {
			success: true,
			compiled: result.code,
		};
	} catch (err) {
		// Extract useful error information
		let errorMessage = "Compilation failed";

		if (err instanceof Error) {
			errorMessage = err.message;

			// Babel errors often include location info in the message
			// Format: "path: message (line:column)"
			// We want to preserve this for debugging
		} else if (typeof err === "string") {
			errorMessage = err;
		}

		return {
			success: false,
			error: errorMessage,
		};
	}
}

/**
 * Wrap compiled code in a component factory function
 *
 * The compiled code is expected to be the body of a component function.
 * This wrapper creates a function that takes props and executes the body.
 *
 * @param compiled - Babel-compiled JavaScript code
 * @returns Code wrapped as a component factory
 *
 * @example
 * ```typescript
 * const wrapped = wrapAsComponent(compiledCode);
 * // Returns:
 * // "return function DynamicComponent(props) { ...compiled... }"
 * ```
 */
export function wrapAsComponent(compiled: string): string {
	// The compiled code should be the body of a component
	// We wrap it in a function that receives props
	return `
    return function DynamicComponent(props) {
      ${compiled}
    }
  `;
}
