/**
 * ESM Loader — loads npm packages from esm.sh CDN at runtime.
 *
 * React-based packages use `?external=` so they emit bare `import "react"`
 * specifiers, which the browser resolves via the import map injected by
 * esm-react-shim.ts — guaranteeing a single React instance.
 */

const ESM_SH = "https://esm.sh";

const EXTERNAL_SPECIFIERS = [
	"react",
	"react-dom",
	"react/jsx-runtime",
	"react/jsx-dev-runtime",
	"react-dom/client",
].join(",");

/** Module-level cache: loaded once per session */
const moduleCache = new Map<string, Record<string, unknown>>();

/**
 * Build esm.sh URL for a package, externalizing React so the import map
 * redirects to the platform's single React instance.
 */
function buildUrl(name: string, version: string): string {
	return `${ESM_SH}/${name}@${version}?external=${EXTERNAL_SPECIFIERS}`;
}

/**
 * Load all dependencies from esm.sh in parallel.
 *
 * @param deps - Map of {packageName: version} from app dependencies
 * @returns Map of {packageName: moduleExports} for injection as $deps
 */
export async function loadDependencies(
	deps: Record<string, string>,
): Promise<Record<string, Record<string, unknown>>> {
	const result: Record<string, Record<string, unknown>> = {};
	const entries = Object.entries(deps);

	if (entries.length === 0) {
		return result;
	}

	await Promise.all(
		entries.map(async ([name, version]) => {
			const key = `${name}@${version}`;
			if (moduleCache.has(key)) {
				result[name] = moduleCache.get(key)!;
				return;
			}
			try {
				const url = buildUrl(name, version);
				const mod = await import(/* @vite-ignore */ url);
				// Copy module exports. Use the module directly to preserve
				// getter behavior on namespace objects.
				const exports: Record<string, unknown> = {};
				for (const k of Object.keys(mod)) {
					exports[k] = mod[k];
				}
				moduleCache.set(key, exports);
				result[name] = exports;
			} catch (err) {
				console.error(`Failed to load dependency ${name}@${version}:`, err);
				// Return a proxy that throws on access — surfaces load failures
				// visibly instead of silent undefined values.
				// SafeComponent in app-code-runtime.ts catches these errors.
				result[name] = new Proxy(
					{},
					{
						get(_, prop) {
							if (typeof prop === "symbol" || prop === "then")
								return undefined;
							throw new Error(
								`Package "${name}@${version}" failed to load from esm.sh. ` +
									`The "${String(prop)}" export is unavailable. ` +
									`Check the browser console for details.`,
							);
						},
					},
				);
			}
		}),
	);

	return result;
}
