import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
	plugins: [tailwindcss(), react()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	build: {
		rollupOptions: {
			output: {
				manualChunks: {
					// React core - always needed
					"react-vendor": ["react", "react-dom", "react-router-dom"],

					// Monaco Editor - large dependency, split separately
					monaco: ["monaco-editor", "@monaco-editor/react"],

					// Babel standalone - only for JSX template rendering (used in FormRenderer)
					babel: ["@babel/standalone"],

					// UI framework - Radix UI primitives
					"ui-primitives": [
						"@radix-ui/react-dialog",
						"@radix-ui/react-dropdown-menu",
						"@radix-ui/react-label",
						"@radix-ui/react-slot",
						"@radix-ui/react-tooltip",
						"@radix-ui/react-select",
						"@radix-ui/react-separator",
						"@radix-ui/react-tabs",
						"@radix-ui/react-alert-dialog",
						"@radix-ui/react-popover",
						"@radix-ui/react-checkbox",
						"@radix-ui/react-context-menu",
						"@radix-ui/react-radio-group",
						"@radix-ui/react-switch",
						"@radix-ui/react-toggle",
						"@radix-ui/react-toggle-group",
					],

					// Animation libraries
					animations: [
						"framer-motion",
						"@atlaskit/pragmatic-drag-and-drop",
						"@atlaskit/pragmatic-drag-and-drop-auto-scroll",
						"@atlaskit/pragmatic-drag-and-drop-hitbox",
					],

					// Data fetching and state
					data: ["@tanstack/react-query", "zustand"],

					// Syntax highlighting
					"syntax-highlighter": ["react-syntax-highlighter"],

					// Forms
					forms: ["react-hook-form", "@hookform/resolvers", "zod"],

					// UI Utils
					"ui-utils": [
						"lucide-react",
						"sonner",
						"clsx",
						"tailwind-merge",
						"class-variance-authority",
					],

					// Content rendering
					"content-rendering": [
						"dompurify",
						"react-markdown",
						"date-fns",
						"react-day-picker",
					],
				},
			},
		},
		chunkSizeWarningLimit: 3000, // Increase limit - babel-standalone is inherently large (2.9MB) but lazy-loaded only when needed for JSX templates
	},
	optimizeDeps: {
		include: [
			// React core
			"react",
			"react-dom",
			"react-dom/client",
			"react-router-dom",

			// State management
			"zustand",
			"zustand/middleware",
			"zustand/react/shallow",

			// Data fetching
			"@tanstack/react-query",
			"openapi-fetch",
			"openapi-react-query",

			// UI utilities
			"lucide-react",
			"sonner",
			"clsx",
			"tailwind-merge",
			"class-variance-authority",
			"cmdk",

			// Radix UI primitives
			"@radix-ui/react-dialog",
			"@radix-ui/react-dropdown-menu",
			"@radix-ui/react-label",
			"@radix-ui/react-slot",
			"@radix-ui/react-tooltip",
			"@radix-ui/react-select",
			"@radix-ui/react-separator",
			"@radix-ui/react-tabs",
			"@radix-ui/react-alert-dialog",
			"@radix-ui/react-popover",
			"@radix-ui/react-checkbox",
			"@radix-ui/react-context-menu",
			"@radix-ui/react-collapsible",
			"@radix-ui/react-avatar",
			"@radix-ui/react-progress",
			"@radix-ui/react-radio-group",
			"@radix-ui/react-switch",
			"@radix-ui/react-toggle",
			"@radix-ui/react-toggle-group",

			// Animation and drag-drop
			"framer-motion",
			"@atlaskit/pragmatic-drag-and-drop/element/adapter",
			"@atlaskit/pragmatic-drag-and-drop/combine",

			// Content rendering
			"react-markdown",
			"remark-gfm",
			"rehype-raw",
			"react-syntax-highlighter",
			"react-syntax-highlighter/dist/esm/styles/prism",
			"dompurify",
			"date-fns",

			// Charts
			"recharts",

			// Monaco editor
			"@monaco-editor/react",

			// Auth
			"@simplewebauthn/browser",
		],
	},
	server: {
		host: "0.0.0.0",
		port: 3000,
		strictPort: true, // Fail if port is already in use
		// Allow all hosts in development (ngrok, tunnels, etc.)
		allowedHosts: true,
		hmr: {
			// When VITE_HMR_HOST is set (e.g., for ngrok), use WSS on port 443
			// Otherwise, let Vite auto-detect (works for localhost and Docker)
			...(process.env.VITE_HMR_HOST && {
				protocol: "wss",
				host: process.env.VITE_HMR_HOST,
				port: 443,
			}),
		},
		watch: {
			usePolling: true,
			interval: 1000,
		},
		proxy: {
			// Use API_URL env var for Docker (api:8000) or default to localhost:8000 for local dev
			// OAuth discovery endpoints for MCP clients (Claude Desktop)
			"/.well-known": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			// MCP OAuth endpoints for external LLM clients
			"/register": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			"/authorize": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			"/token": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			// MCP protocol endpoint for external LLM clients (Claude Desktop)
			"/mcp": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			// Proxy OpenAPI spec for type generation
			"/openapi.json": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			// Rewrite /api/auth/* to /auth/* since backend auth routes don't have /api prefix
			"/api/auth": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api\/auth/, "/auth"),
			},
			// Chat WebSocket streaming endpoint
			"/api/chat": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
				ws: true,
			},
			"/api": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
			},
			// Proxy /auth/* to backend EXCEPT /auth/callback/* which is handled client-side
			"/auth": {
				target: process.env.API_URL || "http://localhost:8000",
				changeOrigin: true,
				bypass: (req) => {
					// Let /auth/callback/* be handled by React Router (client-side)
					if (req.url?.startsWith("/auth/callback")) {
						return req.url;
					}
					return undefined;
				},
			},
			"/ws": {
				target: process.env.WS_URL || "ws://localhost:8000",
				ws: true,
			},
		},
	},
});
