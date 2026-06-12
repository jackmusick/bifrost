/**
 * BifrostHeader — platform chrome for a standalone_v2 app, shipped in the
 * installable `bifrost` SDK. Mirrors the platform's own top header as closely
 * as a self-contained component can: optional app LOGO + title on the left, an
 * optional action slot, and a USER MENU on the right (avatar/initials + name →
 * dropdown with name/email, Back to Bifrost, Log out).
 *
 * v2 apps own their layout; the platform imposes no shell. This header is a
 * LIBRARY component an author composes if they want the familiar affordances.
 *
 * SELF-CONTAINED by necessity: the in-client header uses shadcn DropdownMenu /
 * Avatar / Button via `@/` aliases that don't resolve outside the client
 * project (and would drag shadcn + Tailwind into every v2 bundle). So this copy
 * rebuilds the SAME UX with inline styles + a tiny scoped <style> for hover and
 * the dropdown. It does NOT depend on Tailwind or the platform CSS-variable
 * theme — drop-in correct in `npm run dev`, deployed, or any standalone bundle.
 *
 * User identity + app logo are fetched lazily from the authed context the
 * provider already supplies (`authedFetch` + `appId`) — no new bootstrap
 * fields, no provider change. `GET /api/auth/me` → name/email/avatar;
 * `GET /api/applications/{appId}` → logo data URL. Both degrade gracefully
 * (initials fallback, no logo) if unavailable.
 */
import { ArrowLeft, ChevronDown, LogOut } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { useBifrostContext } from "./provider";

export interface BifrostHeaderProps {
  /** App title shown next to the logo on the left. */
  title: string;
  /**
   * App logo. Pass a URL/data-URL to control it explicitly; omit to let the
   * header fetch the deployed app's logo via `appId`. Pass `null` to force no
   * logo even if the app has one.
   */
  logo?: string | null;
  /** Optional action slot rendered at the right (before the user menu). */
  action?: ReactNode;
  className?: string;
}

// Self-contained palette (neutral, matches Bifrost's light chrome).
const C = {
  border: "#e4e4e7",
  fg: "#18181b",
  muted: "#71717a",
  faint: "#a1a1aa",
  accent: "#f4f4f5",
  surface: "#ffffff",
  danger: "#dc2626",
  brand: "#2563eb",
} as const;

interface Me {
  name?: string;
  email?: string;
  avatar_url?: string;
}

const STYLE_ID = "bifrost-header-style";
const SCOPED_CSS = `
[data-bifrost-header] .bfh-link,[data-bifrost-header] .bfh-trigger{color:${C.muted};transition:color .12s,background-color .12s}
[data-bifrost-header] .bfh-link:hover{color:${C.fg}}
[data-bifrost-header] .bfh-trigger:hover{color:${C.fg};background-color:${C.accent}}
[data-bifrost-header] .bfh-item:hover{background-color:${C.accent}}
`;

function ensureStyle(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;
  const el = document.createElement("style");
  el.id = STYLE_ID;
  el.textContent = SCOPED_CSS;
  document.head.appendChild(el);
}

function initials(me: Me | null): string {
  const src = me?.name || me?.email || "";
  if (!src) return "?";
  const parts = src.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src[0].toUpperCase();
}

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "1rem",
  borderBottom: `1px solid ${C.border}`,
  padding: "0.5rem 1rem",
  background: C.surface,
  fontFamily: "ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif",
  position: "relative",
};
const leftStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.7rem", minWidth: 0 };
const backLinkStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.25rem",
  fontSize: "0.8125rem",
  textDecoration: "none",
  paddingRight: "0.7rem",
  borderRight: `1px solid ${C.border}`,
};
const logoStyle: CSSProperties = { height: 26, width: "auto", borderRadius: 5, display: "block" };
const titleStyle: CSSProperties = { fontSize: "0.95rem", fontWeight: 600, color: C.fg, whiteSpace: "nowrap" };
const rightStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.5rem" };
const iconStyle: CSSProperties = { width: "1rem", height: "1rem" };

const triggerStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.5rem",
  border: "none",
  background: "transparent",
  cursor: "pointer",
  borderRadius: "0.5rem",
  padding: "0.25rem 0.5rem",
  fontSize: "0.875rem",
  fontFamily: "inherit",
};
const avatarStyle = (size: number): CSSProperties => ({
  width: size,
  height: size,
  borderRadius: "9999px",
  background: C.accent,
  color: C.fg,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: size < 32 ? "0.7rem" : "0.85rem",
  fontWeight: 600,
  flexShrink: 0,
  overflow: "hidden",
});
const menuStyle: CSSProperties = {
  position: "absolute",
  top: "calc(100% - 2px)",
  right: "1rem",
  width: 232,
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: "0.625rem",
  boxShadow: "0 12px 32px rgba(24,24,27,0.14)",
  padding: 6,
  zIndex: 70,
};
const menuItemStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  width: "100%",
  border: "none",
  background: "transparent",
  cursor: "pointer",
  borderRadius: "0.375rem",
  padding: "0.5rem 0.625rem",
  fontSize: "0.875rem",
  fontFamily: "inherit",
  color: C.fg,
  textAlign: "left",
};

export function BifrostHeader({ title, logo, action, className }: BifrostHeaderProps) {
  const { baseUrl, appId, authedFetch, logout } = useBifrostContext();
  const platformRoot = `${baseUrl.replace(/\/$/, "")}/`;
  ensureStyle();

  const [me, setMe] = useState<Me | null>(null);
  const [fetchedLogo, setFetchedLogo] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Fetch the signed-in user once.
  useEffect(() => {
    let cancelled = false;
    authedFetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => !cancelled && d && setMe(d))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [authedFetch]);

  // Fetch the deployed app's logo when not explicitly provided.
  useEffect(() => {
    if (logo !== undefined || !appId) return;
    let cancelled = false;
    authedFetch(`/api/applications/${appId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => !cancelled && d?.logo && setFetchedLogo(d.logo))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [authedFetch, appId, logo]);

  // Close the menu on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const effectiveLogo = logo !== undefined ? logo : fetchedLogo;
  const name = me?.name || me?.email?.split("@")[0] || "Account";
  const email = me?.email || "";

  return (
    <header data-bifrost-header style={headerStyle} className={className}>
      <div style={leftStyle}>
        <a href={platformRoot} className="bfh-link" style={backLinkStyle}>
          <ArrowLeft style={iconStyle} />
          Bifrost
        </a>
        {effectiveLogo ? <img src={effectiveLogo} alt="" style={logoStyle} /> : null}
        <span style={titleStyle}>{title}</span>
      </div>

      <div style={rightStyle}>
        {action}
        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            type="button"
            className="bfh-trigger"
            onClick={() => setOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={open}
            style={triggerStyle}
          >
            <span style={avatarStyle(26)}>
              {me?.avatar_url ? (
                <img src={me.avatar_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                initials(me)
              )}
            </span>
            <span style={{ color: C.fg, fontWeight: 500 }}>{name}</span>
            <ChevronDown style={{ ...iconStyle, color: C.faint }} />
          </button>

          {open && (
            <div role="menu" style={menuStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "0.5rem 0.625rem" }}>
                <span style={avatarStyle(36)}>
                  {me?.avatar_url ? (
                    <img src={me.avatar_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    initials(me)
                  )}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "0.875rem", fontWeight: 600, color: C.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {name}
                  </div>
                  {email ? (
                    <div style={{ fontSize: "0.75rem", color: C.muted, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {email}
                    </div>
                  ) : null}
                </div>
              </div>
              <div style={{ height: 1, background: C.border, margin: "4px 0" }} />
              <a href={platformRoot} className="bfh-item" role="menuitem" style={{ ...menuItemStyle, textDecoration: "none" }}>
                <ArrowLeft style={iconStyle} />
                Back to Bifrost
              </a>
              <button
                type="button"
                className="bfh-item"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  logout();
                }}
                style={{ ...menuItemStyle, color: C.danger }}
              >
                <LogOut style={iconStyle} />
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
