/**
 * App Code Compiler
 *
 * Browser-based JSX/TSX compilation using Babel standalone.
 * Compiles user-authored JSX source into executable JavaScript.
 *
 * Handles ES module syntax (import/export) by transforming them
 * to work with the runtime's injected scope.
 */

import { transform } from "@babel/standalone";

/**
 * Result of code compilation
 */
export interface CompileResult {
	/** Whether compilation succeeded */
	success: boolean;
	/** Compiled JavaScript code (if successful) */
	compiled?: string;
	/** Default export variable name (if found) */
	defaultExport?: string;
	/** Named export variable names (if any) */
	namedExports?: string[];
	/** Error message (if failed) */
	error?: string;
}

/**
 * Pre-process source to transform imports from "bifrost"
 *
 * Transforms:
 *   import { Outlet, Link } from "bifrost";
 * To:
 *   const { Outlet, Link } = $;
 *
 * The runtime provides a $ object containing everything.
 * Using destructuring means users get clear errors if they
 * try to use something that doesn't exist.
 */
function preprocessImports(source: string): string {
	// Transform named imports: import { X, Y } from "bifrost" → const { X, Y } = $;
	let result = source.replace(
		/^\s*import\s+(\{[^}]*\})\s+from\s+["']bifrost["']\s*;?\s*$/gm,
		"const $1 = $;",
	);

	// Transform default imports: import X from "bifrost" → const X = $.default || $;
	// (Though we don't really have a default export, this handles the case)
	result = result.replace(
		/^\s*import\s+(\w+)\s+from\s+["']bifrost["']\s*;?\s*$/gm,
		"const $1 = $.default || $;",
	);

	// Transform mixed imports: import X, { Y, Z } from "bifrost"
	result = result.replace(
		/^\s*import\s+(\w+)\s*,\s*(\{[^}]*\})\s+from\s+["']bifrost["']\s*;?\s*$/gm,
		"const $1 = $.default || $;\nconst $2 = $;",
	);

	return result;
}

/**
 * Post-process compiled code to handle exports
 *
 * Transforms ES module exports to assignments that we can capture:
 *   export default function Foo() { ... }
 * To:
 *   function Foo() { ... }
 *   __defaultExport__ = Foo;
 *
 * For named exports without a default:
 *   export function Button() { ... }
 * To:
 *   function Button() { ... }
 *   __exports__.Button = Button;
 *   __defaultExport__ = Button; // First named export becomes default
 */
function postprocessExports(compiled: string): {
	code: string;
	defaultExport: string | null;
	namedExports: string[];
} {
	let code = compiled;
	let defaultExport: string | null = null;
	const namedExports: string[] = [];

	// Handle: export default function Name() { ... }
	const defaultFuncMatch = code.match(
		/export\s+default\s+function\s+(\w+)/,
	);
	if (defaultFuncMatch) {
		const funcName = defaultFuncMatch[1];
		code = code.replace(/export\s+default\s+function\s+(\w+)/, "function $1");
		code += `\n__defaultExport__ = ${funcName};`;
		defaultExport = funcName;
	}

	// Handle: export default function() { ... } (anonymous)
	if (!defaultExport && code.includes("export default function(")) {
		code = code.replace(
			/export\s+default\s+function\s*\(/,
			"__defaultExport__ = function(",
		);
		defaultExport = "__defaultExport__";
	}

	// Handle: export default SomeVariable;
	const defaultVarMatch = code.match(/export\s+default\s+(\w+)\s*;/);
	if (!defaultExport && defaultVarMatch) {
		const varName = defaultVarMatch[1];
		code = code.replace(/export\s+default\s+\w+\s*;/, "");
		code += `\n__defaultExport__ = ${varName};`;
		defaultExport = varName;
	}

	// Handle named exports: export function Name() { ... }
	// Capture the names before removing export keyword
	const namedFuncMatches = code.matchAll(/export\s+function\s+(\w+)/g);
	for (const match of namedFuncMatches) {
		namedExports.push(match[1]);
	}

	// Handle named exports: export const Name = ...
	const namedConstMatches = code.matchAll(/export\s+(?:const|let|var)\s+(\w+)/g);
	for (const match of namedConstMatches) {
		namedExports.push(match[1]);
	}

	// Remove export { ... } statements
	code = code.replace(/export\s+\{[^}]*\}\s*;?/g, "");

	// Remove export keyword from declarations (keeping the declaration)
	code = code.replace(/export\s+(const|let|var|function|class)\s+/g, "$1 ");

	// Add named exports to __exports__ object
	if (namedExports.length > 0) {
		code += "\n__exports__ = {};";
		for (const name of namedExports) {
			code += `\n__exports__.${name} = ${name};`;
		}
	}

	// If no default export but we have named exports, use the first named export as default
	// This handles the common case: export function Button() { ... }
	if (!defaultExport && namedExports.length > 0) {
		defaultExport = namedExports[0];
		code += `\n__defaultExport__ = ${defaultExport};`;
	}

	return { code, defaultExport, namedExports };
}

/**
 * Compile JSX/TSX source to executable JavaScript
 *
 * Uses Babel standalone with React preset and modern JS plugins.
 * Strips TypeScript annotations while preserving runtime behavior.
 * Transforms ES module syntax to work with Function() execution.
 *
 * @param source - JSX/TSX source code
 * @returns Compilation result with success status and compiled code or error
 *
 * @example
 * ```typescript
 * const result = compileAppCode(`
 *   import { Outlet } from "bifrost";
 *   export default function Layout() {
 *     return <div><Outlet /></div>;
 *   }
 * `);
 *
 * if (result.success) {
 *   console.log(result.compiled);
 *   console.log(result.defaultExport); // "Layout"
 * }
 * ```
 */
export function compileAppCode(source: string): CompileResult {
	try {
		// Step 1: Pre-process to transform bifrost imports to $ destructuring
		const preprocessed = preprocessImports(source);

		// Step 2: Compile with Babel
		const result = transform(preprocessed, {
			// Filename required by TypeScript preset to determine file type
			filename: "component.tsx",
			presets: ["react", "typescript"],
			plugins: [
				// Modern JavaScript features
				"proposal-optional-chaining",
				"proposal-nullish-coalescing-operator",
			],
			// Support import/export statements (we'll transform exports after)
			sourceType: "module",
		});

		if (!result.code) {
			return {
				success: false,
				error: "Compilation produced no output",
			};
		}

		// Step 3: Post-process to transform exports
		const { code, defaultExport, namedExports } = postprocessExports(result.code);

		return {
			success: true,
			compiled: code,
			defaultExport: defaultExport || undefined,
			namedExports: namedExports.length > 0 ? namedExports : undefined,
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
 * The compiled code defines components and sets __defaultExport__.
 * This wrapper executes the code and returns the default export.
 *
 * @param compiled - Babel-compiled JavaScript code (with exports transformed)
 * @returns Code wrapped as a component factory that returns the default export
 *
 * @example
 * ```typescript
 * const wrapped = wrapAsComponent(compiledCode);
 * // Executes compiled code and returns __defaultExport__
 * ```
 */
export function wrapAsComponent(compiled: string): string {
	// The compiled code defines functions and sets __defaultExport__ and __exports__
	// We execute it and return the default export
	return `
    var __defaultExport__;
    var __exports__ = {};
    ${compiled}
    return __defaultExport__;
  `;
}
