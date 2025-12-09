/**
 * Branding Hook
 *
 * Handles loading and caching of branding assets (logos, colors).
 * Separated from org scope to allow independent loading and caching.
 */

import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
	initializeBranding,
	applyBrandingTheme,
	type BrandingSettings,
} from "@/lib/branding";

export interface BrandingState {
	/** Whether branding data has been loaded */
	brandingLoaded: boolean;
	/** Whether logo images have been preloaded */
	logoLoaded: boolean;
	/** URL for square logo (sidebar icon) */
	squareLogoUrl: string | null;
	/** URL for rectangle logo (header) */
	rectangleLogoUrl: string | null;
	/** Refresh branding data (e.g., after upload) */
	refreshBranding: () => void;
}

/**
 * Preload an image and return when loaded
 */
function preloadImage(url: string, timeout = 5000): Promise<void> {
	return new Promise((resolve) => {
		const img = new Image();
		img.onload = () => resolve();
		img.onerror = () => resolve(); // Continue even on error
		img.src = url;
		// Timeout fallback
		setTimeout(() => resolve(), timeout);
	});
}

/**
 * Hook for loading and managing branding assets.
 *
 * @example
 * ```tsx
 * function Header() {
 *   const { rectangleLogoUrl, brandingLoaded } = useBranding();
 *
 *   if (!brandingLoaded) return <Skeleton />;
 *
 *   return <img src={rectangleLogoUrl || "/logo.svg"} />;
 * }
 * ```
 */
export function useBranding(): BrandingState {
	const queryClient = useQueryClient();
	const [logoLoaded, setLogoLoaded] = useState(false);
	const [squareLogoUrl, setSquareLogoUrl] = useState<string | null>(null);
	const [rectangleLogoUrl, setRectangleLogoUrl] = useState<string | null>(
		null,
	);
	const [brandingApplied, setBrandingApplied] = useState(false);

	// Fetch branding data (public endpoint)
	const { data: branding, isLoading } = useQuery<BrandingSettings | null>({
		queryKey: ["branding"],
		queryFn: async () => {
			const response = await fetch("/api/branding");
			if (!response.ok) {
				return null;
			}
			return response.json();
		},
		staleTime: 5 * 60 * 1000, // 5 minutes
		retry: 1,
	});

	// Process branding data when it changes
	useEffect(() => {
		async function processBranding() {
			setLogoLoaded(false);

			if (!branding) {
				// No branding data - apply defaults
				await initializeBranding();
				setBrandingApplied(true);
				setLogoLoaded(true);
				return;
			}

			// Preload logos
			const preloadPromises: Promise<void>[] = [];

			if (branding.rectangle_logo_url) {
				preloadPromises.push(preloadImage(branding.rectangle_logo_url));
			}

			if (branding.square_logo_url) {
				preloadPromises.push(preloadImage(branding.square_logo_url));
			}

			await Promise.all(preloadPromises);

			// Store logo URLs
			setSquareLogoUrl(branding.square_logo_url || null);
			setRectangleLogoUrl(branding.rectangle_logo_url || null);

			// Apply theme colors
			applyBrandingTheme(branding);
			setBrandingApplied(true);

			setLogoLoaded(true);
		}

		if (!isLoading) {
			processBranding();
		}
	}, [branding, isLoading]);

	const refreshBranding = useCallback(() => {
		setBrandingApplied(false);
		queryClient.invalidateQueries({ queryKey: ["branding"] });
	}, [queryClient]);

	return {
		brandingLoaded: !isLoading && brandingApplied,
		logoLoaded,
		squareLogoUrl,
		rectangleLogoUrl,
		refreshBranding,
	};
}
