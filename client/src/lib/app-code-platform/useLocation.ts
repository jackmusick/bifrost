import {
	useLocation as useRouterLocation,
	type Location,
} from "react-router-dom";
import { useAppBuilderStore } from "@/stores/app-builder.store";

export function appRelativePathname(pathname: string, basePath: string): string {
	if (!basePath || basePath === "/") return pathname;
	if (pathname === basePath) return "/";
	if (!pathname.startsWith(`${basePath}/`)) return pathname;
	return pathname.slice(basePath.length);
}

export function useLocation(): Location {
	const location = useRouterLocation();
	const basePath = useAppBuilderStore((state) => state.getBasePath());
	const pathname = appRelativePathname(location.pathname, basePath);

	if (pathname === location.pathname) return location;

	return {
		...location,
		pathname,
	};
}
