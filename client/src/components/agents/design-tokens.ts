/**
 * Agent-surfaces design tokens.
 *
 * Central source of truth for typography, spacing, radius, and color classes
 * used across FleetPage, AgentDetailPage, AgentRunDetailPage, AgentReviewPage,
 * AgentTunePage and their supporting primitives (StatCard, PillTabs, Sparkline,
 * MetaLine, KVList, Chip, ChatBubble).
 *
 * These exist to prevent visual drift across the growing set of agent pages —
 * the mockup relies on a tight, consistent type / spacing grid that shadcn's
 * default classes don't encode. Every primitive and page composition in
 * `client/src/components/agents/` and `client/src/pages/agents/` should import
 * from here instead of hand-rolling class strings.
 *
 * Composable with `cn()`. Do NOT hand-roll hex colors — use semantic tokens
 * (`bg-card`, `border-border`, `text-muted-foreground`, `text-emerald-500`,
 * `text-rose-500`, `text-yellow-500`).
 */

// ──────────────────────────────────────────────────────────────────────────
// Type scale — exact px values from /tmp/agent-mockup/src/styles.css
// ──────────────────────────────────────────────────────────────────────────

/** 20px page title — `.page-title` */
export const TYPE_PAGE_TITLE =
	"text-[20px] font-semibold leading-tight tracking-tight";

/** 14.5px card / section title — `.card-title` */
export const TYPE_CARD_TITLE = "text-[14.5px] font-semibold";

/** 13.5px body / default — page subtitle, descriptions, nav items */
export const TYPE_BODY = "text-[13.5px]";

/** 13px muted strip — run meta, sidebar body text */
export const TYPE_MUTED = "text-[13px] text-muted-foreground";

/** 12.5px small — button-sm, mono cells, muted inline spans */
export const TYPE_SMALL = "text-[12.5px]";

/** 11.5px uppercase label — `.stat-label` / `.form-section-title` */
export const TYPE_LABEL_UPPERCASE =
	"text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground";

/** Pane label within a workbench column (slightly larger than `TYPE_LABEL_UPPERCASE`). */
export const TYPE_PANE_LABEL =
	"text-xs font-semibold uppercase tracking-wider text-muted-foreground";

/** 22px stat value — `.stat-value` */
export const TYPE_STAT_VALUE =
	"text-[22px] font-semibold leading-tight tracking-tight tabular-nums";

/** 15px mini-stat value — used inside agent grid cards */
export const TYPE_MINI_STAT_VALUE =
	"text-[15px] font-semibold leading-tight tabular-nums";

/** 12px stat delta / helper text */
export const TYPE_STAT_DELTA = "text-[12px]";

/** Mono font family for keys, IDs, hashes — matches `.mono` at 12.5px */
export const TYPE_MONO = "font-mono text-[12.5px]";

// ──────────────────────────────────────────────────────────────────────────
// Gap scale — whitespace between cards/sections
// ──────────────────────────────────────────────────────────────────────────

/** 16px — between cards in a column (`.grid { gap: 16px }`) */
export const GAP_CARD = "gap-4";

/** 12px — between card subsections (header → body, 3-col mini-stat grid) */
export const GAP_SUBSECTION = "gap-3";

/** 6px — between label and value (stat label → stat value) */
export const GAP_LABEL_VALUE = "gap-1.5";

/** 4px — between value and delta line */
export const GAP_VALUE_DELTA = "gap-1";

// ──────────────────────────────────────────────────────────────────────────
// Radius
// ──────────────────────────────────────────────────────────────────────────

/** 10px — primary card radius (`.card { border-radius: 10px }`) */
export const RADIUS_CARD = "rounded-[10px]";

/** 8px — secondary elements (verdict bar, tool step, advanced details) */
export const RADIUS_INNER = "rounded-lg";

/** 6px — small buttons, inputs, tab items */
export const RADIUS_BUTTON = "rounded-md";

// ──────────────────────────────────────────────────────────────────────────
// Card surface — the repeated base container
// ──────────────────────────────────────────────────────────────────────────

/** Base card surface: 10px radius + border + card bg. Add padding separately. */
export const CARD_SURFACE = `${RADIUS_CARD} border bg-card`;

/** Hoverable card — lifts 1px on hover, warms border. */
export const CARD_HOVER =
	"transition-colors hover:border-border/80 hover:-translate-y-px";

/** Card header strip — 14px/16px vertical/horizontal, border-b. */
export const CARD_HEADER = "border-b px-4 py-3";

/** Card body — 16px padding. */
export const CARD_BODY = "p-4";

// ──────────────────────────────────────────────────────────────────────────
// Color tones — delta / tag / icon accent classes
// ──────────────────────────────────────────────────────────────────────────

/** Up/success delta — emerald. */
export const TONE_UP = "text-emerald-500";
/** Down/error delta — rose. */
export const TONE_DOWN = "text-rose-500";
/** Warning — yellow. */
export const TONE_WARN = "text-yellow-500";
/** Muted — default delta tone. */
export const TONE_MUTED = "text-muted-foreground";

/** Status pill — soft green (Active badge). */
export const PILL_ACTIVE =
	"inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11.5px] font-medium text-emerald-500";

/** Status pill — soft rose (Failed / flagged). */
export const PILL_ROSE =
	"inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[11.5px] font-medium text-rose-500";

/** Status pill — soft yellow (Queued / in-progress). */
export const PILL_YELLOW =
	"inline-flex items-center gap-1 rounded-full bg-yellow-500/15 px-2 py-0.5 text-[11.5px] font-medium text-yellow-500";

/** Outlined channel / meta chip — transparent bg, muted text. */
export const CHIP_OUTLINE =
	"inline-flex items-center gap-1 rounded-full border border-border bg-transparent px-2 py-0.5 text-[11.5px] font-medium text-muted-foreground";

// ──────────────────────────────────────────────────────────────────────────
// Color helpers
// ──────────────────────────────────────────────────────────────────────────

/**
 * Success-rate color — emerald / yellow / rose by threshold.
 * Used on sparklines + mini-stat success % across fleet + detail.
 */
export function successRateTone(rate: number): string {
	if (rate >= 0.9) return TONE_UP;
	if (rate >= 0.75) return TONE_WARN;
	return TONE_DOWN;
}
