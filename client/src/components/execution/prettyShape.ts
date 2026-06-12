/**
 * Pure shape-classification heuristics for the execution Pretty View.
 *
 * The Pretty View renders structured data with JSON as the LAST resort,
 * walking this ladder for every value:
 *
 *   1. scalar       → label/value row
 *   2. flat-object  → nested label/value rows (recurses to MAX_OBJECT_DEPTH)
 *   3. scalar-array → compact inline comma list
 *   4. object-table → mini table (array of same-shaped flat objects)
 *   5. json         → syntax-highlighted JSON block (deep / mixed / large)
 *
 * No React in here — everything is unit-testable pure logic.
 */

export type PrettyShape =
	| "scalar"
	| "flat-object"
	| "scalar-array"
	| "object-table"
	| "json";

/** Object values render as nested rows at most this many levels deep. */
export const MAX_OBJECT_DEPTH = 3;
/** Objects with more keys than this fall back to JSON. */
export const MAX_OBJECT_KEYS = 20;
/** Arrays with more rows than this are too big for a mini table. */
export const MAX_TABLE_ROWS = 50;
/** Tables with more columns than this fall back to JSON. */
export const MAX_TABLE_COLUMNS = 8;
/** Scalar arrays longer than this fall back to JSON. */
export const MAX_SCALAR_ARRAY_ITEMS = 30;
/** Every table column must be present on at least this share of rows. */
export const TABLE_KEY_COVERAGE = 0.8;

/** Scalars are the leaf values a label/value row (or table cell) can hold. */
export function isScalar(value: unknown): boolean {
	return (
		value === null ||
		value === undefined ||
		typeof value === "string" ||
		typeof value === "number" ||
		typeof value === "boolean"
	);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Derive the column set for an array that should render as a mini table.
 *
 * Returns the columns in first-seen key order, or null when the array is not
 * table-shaped: any non-object item, any non-scalar cell, an empty/oversized
 * array, too many columns, or a column present on fewer than
 * TABLE_KEY_COVERAGE of the rows (ragged shapes).
 */
export function tableColumns(value: unknown): string[] | null {
	if (!Array.isArray(value)) return null;
	if (value.length === 0 || value.length > MAX_TABLE_ROWS) return null;

	const columns: string[] = [];
	const counts = new Map<string, number>();

	for (const item of value) {
		if (!isPlainObject(item)) return null;
		const keys = Object.keys(item);
		if (keys.length === 0) return null;
		for (const key of keys) {
			// Cells must be scalar — otherwise the array isn't table-shaped.
			if (!isScalar(item[key])) return null;
			if (!counts.has(key)) {
				columns.push(key);
				if (columns.length > MAX_TABLE_COLUMNS) return null;
			}
			counts.set(key, (counts.get(key) ?? 0) + 1);
		}
	}

	for (const key of columns) {
		if ((counts.get(key) ?? 0) / value.length < TABLE_KEY_COVERAGE) {
			return null;
		}
	}

	return columns;
}

/**
 * Classify a value onto the rendering ladder.
 *
 * `depth` is how many object-nesting levels sit between the top-level entry
 * and this value (a top-level entry's value is depth 0). An object renders
 * as nested rows only when every one of its values (recursively) also lands
 * on a non-JSON rung within the depth budget — a single too-deep or mixed
 * branch sends the whole object to the JSON fallback, where the Tree View
 * toggle remains the spelunking tool.
 */
export function classify(value: unknown, depth = 0): PrettyShape {
	if (isScalar(value)) return "scalar";

	if (Array.isArray(value)) {
		if (value.length === 0) return "scalar-array";
		if (value.every(isScalar)) {
			return value.length <= MAX_SCALAR_ARRAY_ITEMS
				? "scalar-array"
				: "json";
		}
		return tableColumns(value) !== null ? "object-table" : "json";
	}

	if (isPlainObject(value)) {
		if (depth >= MAX_OBJECT_DEPTH) return "json";
		const values = Object.values(value);
		if (values.length > MAX_OBJECT_KEYS) return "json";
		const allRenderable = values.every(
			(v) => classify(v, depth + 1) !== "json",
		);
		return allRenderable ? "flat-object" : "json";
	}

	// Non-JSON-able values (functions, symbols) never appear in execution
	// data, but classify them safely anyway.
	return "json";
}
