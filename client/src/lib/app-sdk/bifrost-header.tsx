/**
 * BifrostHeader — optional platform chrome for a standalone_v2 app, shipped in
 * the installable `bifrost` SDK.
 *
 * v2 apps own their layout; the platform imposes no shell (it renders v2 apps
 * full-page). This header is a LIBRARY component an author composes if they want
 * the familiar affordances — app title, back-to-Bifrost link, logout. Base URL +
 * logout come from `<BifrostProvider>` context, so it works identically in
 * `npm run dev` and deployed.
 *
 * This is a SELF-CONTAINED copy (no `@/components/ui/button`, no `@/lib/utils`):
 * the in-client BifrostHeader pulls shadcn `Button` + `cn` via `@/` aliases that
 * don't resolve outside the client project, so shipping that one would drag
 * shadcn into every v2 app bundle.
 *
 * STYLING IS SELF-CONTAINED TOO. The header styles itself with inline styles
 * plus a one-time scoped `<style>` for hover/focus — it does NOT depend on
 * Tailwind being configured or on the platform's CSS-variable theme
 * (`--muted-foreground`, `--accent`, …). Earlier this used Tailwind semantic
 * tokens, so a standalone app without the platform's theme rendered the header
 * UNSTYLED. Inline styling makes it drop-in correct in `npm run dev`, deployed,
 * or any standalone bundle. Authors who DO have Tailwind can still extend via
 * `className` (applied after, so their classes win). Only new dep is
 * `lucide-react` (a peer the app already has). Codex R4.
 */
import { ArrowLeft, LogOut } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { useBifrostContext } from "./provider";

export interface BifrostHeaderProps {
  /** App title shown at the left of the header. */
  title: string;
  /** Optional action slot rendered at the right (before logout). */
  action?: ReactNode;
  className?: string;
}

// Self-contained palette (neutral, matches Bifrost's light chrome). Kept as
// concrete values so the header never depends on theme CSS variables.
const C = {
  border: "#e4e4e7",
  fg: "#18181b",
  muted: "#71717a",
  accent: "#f4f4f5",
} as const;

// Hover/focus can't be expressed inline, so inject a tiny scoped stylesheet
// once. Scoped to data-bifrost-header so it can't leak into the host app.
const HOVER_STYLE_ID = "bifrost-header-style";
const HOVER_CSS = `
[data-bifrost-header] .bfh-link,[data-bifrost-header] .bfh-logout{color:${C.muted};transition:color .12s,background-color .12s}
[data-bifrost-header] .bfh-link:hover{color:${C.fg}}
[data-bifrost-header] .bfh-logout:hover{color:${C.fg};background-color:${C.accent}}
`;

function ensureHoverStyle(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(HOVER_STYLE_ID)) return;
  const el = document.createElement("style");
  el.id = HOVER_STYLE_ID;
  el.textContent = HOVER_CSS;
  document.head.appendChild(el);
}

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "1rem",
  borderBottom: `1px solid ${C.border}`,
  padding: "0.5rem 1rem",
  fontFamily:
    "ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif",
};
const leftStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.75rem" };
const linkStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.25rem",
  fontSize: "0.875rem",
  textDecoration: "none",
};
const titleStyle: CSSProperties = { fontSize: "1rem", fontWeight: 600, color: C.fg };
const rightStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.5rem" };
const logoutStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.25rem",
  borderRadius: "0.375rem",
  border: "none",
  background: "transparent",
  cursor: "pointer",
  padding: "0.25rem 0.5rem",
  fontSize: "0.875rem",
};
const iconStyle: CSSProperties = { width: "1rem", height: "1rem" };

export function BifrostHeader({ title, action, className }: BifrostHeaderProps) {
  const { baseUrl, logout } = useBifrostContext();
  const platformRoot = `${baseUrl.replace(/\/$/, "")}/`;
  ensureHoverStyle();

  return (
    <header data-bifrost-header style={headerStyle} className={className}>
      <div style={leftStyle}>
        <a href={platformRoot} className="bfh-link" style={linkStyle}>
          <ArrowLeft style={iconStyle} />
          Bifrost
        </a>
        <span style={titleStyle}>{title}</span>
      </div>
      <div style={rightStyle}>
        {action}
        <button
          type="button"
          onClick={() => logout()}
          aria-label="Log out"
          className="bfh-logout"
          style={logoutStyle}
        >
          <LogOut style={iconStyle} />
          Log out
        </button>
      </div>
    </header>
  );
}
