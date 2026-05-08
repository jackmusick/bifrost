#!/usr/bin/env node
/**
 * Tailwind CSS pipeline for Bifrost apps. Wraps @tailwindcss/node v4.
 *
 * Two modes:
 *
 *  1. candidates-only (legacy app_compiler path):
 *       Input  (stdin): {"candidates": ["flex", "p-4", ...]}
 *       Output (stdout): {"css": "...", "error": null}
 *     Compiles utilities for the listed candidates against the default
 *     theme/utilities import. No user CSS, no @apply, no @layer.
 *
 *  2. pipeline (modern bundler path):
 *       Input  (stdin): {
 *         "candidates": ["flex", ...],
 *         "user_css": [{"path": "styles.css", "content": "..."}, ...],
 *         "config_path": "/abs/path/to/tailwind.config.js" | null
 *       }
 *       Output (stdout): {"css": "...", "error": null}
 *     Concatenates user CSS into the input, threads it through Tailwind so
 *     @apply / @layer / @theme directives are processed, optionally honors
 *     a per-app tailwind.config.js via @config.
 *
 * The mode is determined by presence of "user_css" in the input.
 */
const { compile } = require("@tailwindcss/node");

const BASELINE_IMPORTS =
  "@import 'tailwindcss/theme' layer(theme);\n" +
  "@import 'tailwindcss/utilities';\n";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", async () => {
  try {
    const cfg = JSON.parse(input);
    const candidates = cfg.candidates || [];
    const userCss = cfg.user_css;
    const configPath = cfg.config_path || null;

    // Build the entry CSS — what we hand to compile() as the input string.
    // @config must come before user CSS so per-app theme tokens are
    // available when user @apply pulls them in.
    let entryCss = BASELINE_IMPORTS;
    if (configPath) {
      // @tailwindcss/node accepts absolute paths in @config but expects
      // them quoted. Forward-slash even on Linux for portability.
      entryCss += `@config '${configPath.replace(/\\/g, "/")}';\n`;
    }
    if (userCss && Array.isArray(userCss)) {
      for (const f of userCss) {
        // Inline user CSS rather than @import it, so @apply rules in user
        // CSS see the utility layer that's defined above. @import order
        // matters in PostCSS-style layering; inlining sidesteps the issue
        // and makes failures easier to debug.
        entryCss += `\n/* === ${f.path} === */\n${f.content}\n`;
      }
    }

    // base: must be a directory where 'tailwindcss/theme' resolves. The
    // app_compiler's own node_modules has @tailwindcss/node which depends
    // on tailwindcss, so this directory works for resolution.
    const compiler = await compile(entryCss, {
      base: __dirname,
      onDependency: () => {},
    });
    const css = compiler.build(candidates);

    process.stdout.write(JSON.stringify({ css, error: null }));
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ css: null, error: err.message || String(err) })
    );
    process.exit(1);
  }
});
