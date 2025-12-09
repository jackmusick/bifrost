/**
 * Monaco Editor Setup and Configuration
 * Ensures all language features (comments, formatting, etc.) are properly loaded
 */
import { loader } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";

let setupComplete = false;

/**
 * Configure Monaco editor before it loads
 * This must be called before any editor instances are created
 */
export function configureMonaco() {
	if (setupComplete) return;

	// Configure Monaco loader to use CDN or local worker files
	loader.config({
		paths: {
			vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.54.0/min/vs",
		},
	});

	setupComplete = true;
}

/**
 * Initialize Monaco editor features after it loads
 * This is called when the first editor instance mounts
 */
export async function initializeMonaco(monaco: typeof Monaco) {
	// Ensure Python language configuration is loaded
	// Monaco should have this by default, but we'll verify
	const pythonLang = monaco.languages
		.getLanguages()
		.find((lang) => lang.id === "python");

	if (!pythonLang) {
		console.warn("Python language not found in Monaco");
		return;
	}

	// Register Python language configuration for comments
	// This ensures Cmd+/ works for Python files
	monaco.languages.setLanguageConfiguration("python", {
		comments: {
			lineComment: "#",
			blockComment: ['"""', '"""'],
		},
		brackets: [
			["{", "}"],
			["[", "]"],
			["(", ")"],
		],
		autoClosingPairs: [
			{ open: "{", close: "}" },
			{ open: "[", close: "]" },
			{ open: "(", close: ")" },
			{ open: '"', close: '"', notIn: ["string"] },
			{ open: "'", close: "'", notIn: ["string", "comment"] },
		],
		surroundingPairs: [
			{ open: "{", close: "}" },
			{ open: "[", close: "]" },
			{ open: "(", close: ")" },
			{ open: '"', close: '"' },
			{ open: "'", close: "'" },
		],
		folding: {
			offSide: true,
			markers: {
				start: new RegExp("^\\s*#region\\b"),
				end: new RegExp("^\\s*#endregion\\b"),
			},
		},
	});

	// Configure JavaScript/TypeScript
	monaco.languages.setLanguageConfiguration("javascript", {
		comments: {
			lineComment: "//",
			blockComment: ["/*", "*/"],
		},
	});

	monaco.languages.setLanguageConfiguration("typescript", {
		comments: {
			lineComment: "//",
			blockComment: ["/*", "*/"],
		},
	});

	// Configure YAML
	monaco.languages.setLanguageConfiguration("yaml", {
		comments: {
			lineComment: "#",
		},
	});

	// Configure JSON (doesn't support comments but we'll configure brackets)
	monaco.languages.setLanguageConfiguration("json", {
		brackets: [
			["{", "}"],
			["[", "]"],
		],
		autoClosingPairs: [
			{ open: "{", close: "}" },
			{ open: "[", close: "]" },
			{ open: '"', close: '"' },
		],
	});
}
