/**
 * Expression Parser for App Builder
 *
 * Handles evaluation of template expressions using {{ }} syntax.
 * Supports dot notation for nested property access and basic operators.
 */

import type { ExpressionContext } from "./app-builder-types";

/**
 * Regular expression to match template expressions {{ ... }}
 */
const EXPRESSION_REGEX = /\{\{\s*(.+?)\s*\}\}/g;

/**
 * Safely access a nested property using dot notation
 *
 * @param obj - The object to access
 * @param path - Dot-separated path (e.g., "user.profile.name")
 * @returns The value at the path, or undefined if not found
 */
function getNestedValue(obj: unknown, path: string): unknown {
	if (obj === null || obj === undefined) {
		return undefined;
	}

	const parts = path.split(".");
	let current: unknown = obj;

	for (const part of parts) {
		if (current === null || current === undefined) {
			return undefined;
		}

		if (typeof current !== "object") {
			return undefined;
		}

		// Handle array access (e.g., "items.0.name")
		const arrayMatch = part.match(/^(\w+)\[(\d+)\]$/);
		if (arrayMatch) {
			const [, key, index] = arrayMatch;
			const intermediate = (current as Record<string, unknown>)[key];
			if (Array.isArray(intermediate)) {
				current = intermediate[parseInt(index, 10)];
			} else {
				return undefined;
			}
		} else {
			current = (current as Record<string, unknown>)[part];
		}
	}

	return current;
}

/**
 * Build a context object for expression evaluation
 *
 * Follows documented expression conventions:
 * - {{ user.name }} - user info
 * - {{ variables.selectedId }} - page variables
 * - {{ data.customers }} - data from data sources
 * - {{ field.customerName }} - form field values
 * - {{ workflow.result.id }} - workflow result
 * - {{ row.id }} - current row in table row click handlers
 * - {{ params.id }} - route parameters from URL
 */
function buildEvaluationContext(
	context: ExpressionContext,
): Record<string, unknown> {
	return {
		user: context.user,
		variables: context.variables,
		data: context.data,
		field: context.field,
		workflow: context.workflow,
		row: context.row,
		params: context.params,
	};
}

/**
 * Parse and evaluate a comparison expression
 */
function evaluateComparison(
	left: unknown,
	operator: string,
	right: unknown,
): boolean {
	switch (operator) {
		case "==":
		case "===":
			return left === right;
		case "!=":
		case "!==":
			return left !== right;
		case ">":
			return (
				typeof left === "number" &&
				typeof right === "number" &&
				left > right
			);
		case ">=":
			return (
				typeof left === "number" &&
				typeof right === "number" &&
				left >= right
			);
		case "<":
			return (
				typeof left === "number" &&
				typeof right === "number" &&
				left < right
			);
		case "<=":
			return (
				typeof left === "number" &&
				typeof right === "number" &&
				left <= right
			);
		default:
			return false;
	}
}

/**
 * Parse a value from an expression string
 */
function parseValue(
	valueStr: string,
	evalContext: Record<string, unknown>,
): unknown {
	const trimmed = valueStr.trim();

	// String literal (single or double quotes)
	if (
		(trimmed.startsWith("'") && trimmed.endsWith("'")) ||
		(trimmed.startsWith('"') && trimmed.endsWith('"'))
	) {
		return trimmed.slice(1, -1);
	}

	// Boolean literals
	if (trimmed === "true") return true;
	if (trimmed === "false") return false;

	// Null literal
	if (trimmed === "null") return null;

	// Undefined literal
	if (trimmed === "undefined") return undefined;

	// Number literal
	const numValue = Number(trimmed);
	if (!isNaN(numValue) && trimmed !== "") {
		return numValue;
	}

	// Variable reference (dot notation)
	return getNestedValue(evalContext, trimmed);
}

/**
 * Evaluate a simple expression (single variable or comparison)
 */
function evaluateSimpleExpression(
	expression: string,
	evalContext: Record<string, unknown>,
): unknown {
	const trimmed = expression.trim();

	// Handle negation
	if (trimmed.startsWith("!")) {
		const innerValue = evaluateSimpleExpression(
			trimmed.slice(1),
			evalContext,
		);
		return !innerValue;
	}

	// Check for comparison operators
	const comparisonMatch = trimmed.match(
		/^(.+?)\s*(===|!==|==|!=|>=|<=|>|<)\s*(.+)$/,
	);
	if (comparisonMatch) {
		const [, leftStr, operator, rightStr] = comparisonMatch;
		const leftValue = parseValue(leftStr, evalContext);
		const rightValue = parseValue(rightStr, evalContext);
		return evaluateComparison(leftValue, operator, rightValue);
	}

	// Simple value lookup
	return parseValue(trimmed, evalContext);
}

/**
 * Evaluate a compound expression with && and || operators
 */
function evaluateCompoundExpression(
	expression: string,
	evalContext: Record<string, unknown>,
): unknown {
	const trimmed = expression.trim();

	// Handle || (OR) - lowest precedence
	const orParts = splitByOperator(trimmed, "||");
	if (orParts.length > 1) {
		for (const part of orParts) {
			const result = evaluateCompoundExpression(part, evalContext);
			if (result) return result;
		}
		return false;
	}

	// Handle && (AND)
	const andParts = splitByOperator(trimmed, "&&");
	if (andParts.length > 1) {
		let result: unknown = true;
		for (const part of andParts) {
			result = evaluateCompoundExpression(part, evalContext);
			if (!result) return false;
		}
		return result;
	}

	// Handle parentheses
	if (trimmed.startsWith("(") && trimmed.endsWith(")")) {
		return evaluateCompoundExpression(trimmed.slice(1, -1), evalContext);
	}

	// Evaluate simple expression
	return evaluateSimpleExpression(trimmed, evalContext);
}

/**
 * Split an expression by an operator, respecting parentheses
 */
function splitByOperator(expression: string, operator: string): string[] {
	const parts: string[] = [];
	let current = "";
	let parenDepth = 0;

	for (let i = 0; i < expression.length; i++) {
		const char = expression[i];

		if (char === "(") {
			parenDepth++;
			current += char;
		} else if (char === ")") {
			parenDepth--;
			current += char;
		} else if (
			parenDepth === 0 &&
			expression.slice(i, i + operator.length) === operator
		) {
			parts.push(current.trim());
			current = "";
			i += operator.length - 1;
		} else {
			current += char;
		}
	}

	if (current.trim()) {
		parts.push(current.trim());
	}

	return parts;
}

/**
 * Evaluate a single expression (content inside {{ }})
 *
 * @param expression - The expression to evaluate (without {{ }})
 * @param context - The expression context containing variables, user, and data
 * @returns The evaluated value
 */
export function evaluateSingleExpression(
	expression: string,
	context: ExpressionContext,
): unknown {
	const evalContext = buildEvaluationContext(context);
	return evaluateCompoundExpression(expression, evalContext);
}

/**
 * Evaluate a template string with {{ }} expressions
 *
 * Replaces all {{ expression }} patterns with their evaluated values.
 * If the entire string is a single expression, returns the raw value.
 * Otherwise, returns a string with interpolated values.
 *
 * @param template - The template string containing expressions
 * @param context - The expression context containing variables, user, and data
 * @returns The evaluated result (string or raw value for single expressions)
 *
 * @example
 * evaluateExpression("{{ user.name }}", { user: { name: "John" } })
 * // Returns: "John"
 *
 * @example
 * evaluateExpression("Hello, {{ user.name }}!", { user: { name: "John" } })
 * // Returns: "Hello, John!"
 *
 * @example
 * evaluateExpression("{{ count }}", { variables: { count: 42 } })
 * // Returns: 42 (number, not string)
 */
export function evaluateExpression(
	template: string,
	context: ExpressionContext,
): unknown {
	// Handle non-string inputs gracefully
	if (template === null || template === undefined) {
		return template;
	}
	if (typeof template !== "string") {
		// Non-string values pass through as-is (numbers, booleans, objects)
		return template;
	}

	// Check if the entire template is a single expression
	const singleExprMatch = template.match(/^\{\{\s*(.+?)\s*\}\}$/);
	if (singleExprMatch) {
		return evaluateSingleExpression(singleExprMatch[1], context);
	}

	// Multiple expressions or mixed content - interpolate as string
	return template.replace(EXPRESSION_REGEX, (_, expression) => {
		const result = evaluateSingleExpression(expression, context);
		if (result === null || result === undefined) {
			return "";
		}
		return String(result);
	});
}

/**
 * Evaluate a visibility condition
 *
 * @param condition - The visibility condition (e.g., "{{ user.role == 'admin' }}")
 * @param context - The expression context
 * @returns Boolean indicating visibility (true if visible, false if hidden)
 *
 * @example
 * evaluateVisibility("{{ user.role == 'admin' }}", { user: { role: 'admin' } })
 * // Returns: true
 *
 * @example
 * evaluateVisibility(undefined, context)
 * // Returns: true (undefined means always visible)
 */
export function evaluateVisibility(
	condition: string | undefined,
	context: ExpressionContext,
): boolean {
	// No condition means always visible
	if (condition === undefined || condition === null || condition === "") {
		return true;
	}

	const result = evaluateExpression(condition, context);

	// Truthy check
	return Boolean(result);
}

/**
 * Check if a string contains template expressions
 *
 * @param str - The string to check
 * @returns True if the string contains {{ }} expressions
 */
export function hasExpressions(str: string): boolean {
	return EXPRESSION_REGEX.test(str);
}

/**
 * Extract all variable paths referenced in a template
 *
 * @param template - The template string to analyze
 * @returns Array of variable paths (e.g., ["user.name", "data.items"])
 */
export function extractVariablePaths(template: string): string[] {
	const paths: string[] = [];
	const regex = new RegExp(EXPRESSION_REGEX);
	let match;

	while ((match = regex.exec(template)) !== null) {
		const expression = match[1];
		// Extract simple variable references (excluding operators and literals)
		const varMatches = expression.match(
			/[a-zA-Z_][a-zA-Z0-9_.[\]]*(?![=('"<>!&|])/g,
		);
		if (varMatches) {
			for (const varMatch of varMatches) {
				const cleaned = varMatch.trim();
				// Skip boolean literals and other keywords
				if (!["true", "false", "null", "undefined"].includes(cleaned)) {
					paths.push(cleaned);
				}
			}
		}
	}

	return [...new Set(paths)];
}
