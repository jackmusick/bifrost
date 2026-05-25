import { useEffect } from "react";

/**
 * Drives the browser tab's "chrome" — the document <title> and the favicon —
 * from the currently-open entity (e.g. a Bifrost app), restoring the prior
 * values on unmount or when the inputs change.
 *
 * The favicon is set from `logo`, which is an inline data URL
 * (`data:image/...;base64,...`) as served by the API's `logo` field. Because a
 * data URL carries its own MIME type, this works uniformly for SVG, PNG, and
 * JPEG logos without any format detection — we just drop the hardcoded `type`
 * attribute on the <link> so the data URL's own type drives it.
 *
 * When `logo` is null/empty the favicon is left untouched (the default Bifrost
 * favicon stays). When `enabled` is false (e.g. embed mode, where the host page
 * owns its own chrome) the hook is a no-op.
 */
export function useDocumentChrome({
	title,
	logo,
	enabled = true,
}: {
	/** Tab title to set. Falsy values leave the title untouched. */
	title: string | null | undefined;
	/** Favicon source as a data URL. Falsy values leave the favicon untouched. */
	logo: string | null | undefined;
	/** When false, the hook does nothing. */
	enabled?: boolean;
}): void {
	useEffect(() => {
		if (!enabled || !title) return;
		const prev = document.title;
		document.title = title;
		return () => {
			document.title = prev;
		};
	}, [enabled, title]);

	useEffect(() => {
		if (!enabled || !logo) return;
		const link =
			document.querySelector<HTMLLinkElement>("link[rel='icon']");
		if (!link) return;
		const prevHref = link.getAttribute("href");
		const prevType = link.getAttribute("type");
		// Let the data URL's own MIME type drive the favicon, so a PNG/JPEG logo
		// is not mislabeled by the default `type="image/svg+xml"`.
		link.removeAttribute("type");
		link.setAttribute("href", logo);
		return () => {
			if (prevHref === null) link.removeAttribute("href");
			else link.setAttribute("href", prevHref);
			if (prevType === null) link.removeAttribute("type");
			else link.setAttribute("type", prevType);
		};
	}, [enabled, logo]);
}
