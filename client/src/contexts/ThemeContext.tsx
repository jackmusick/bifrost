/**
 * Theme Context Provider
 * Manages dark/light mode with localStorage persistence
 */

import {
	createContext,
	useContext,
	useState,
	useEffect,
	ReactNode,
} from "react";

type Theme = "dark" | "light";

interface ThemeContextType {
	theme: Theme;
	toggleTheme: () => void;
	setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
	children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
	// Use lazy initializer to read from localStorage on first render
	const [theme, setThemeState] = useState<Theme>(() => {
		const storedTheme = localStorage.getItem("theme") as Theme | null;
		if (storedTheme) {
			return storedTheme;
		}
		// Set default to dark
		localStorage.setItem("theme", "dark");
		return "dark";
	});

	useEffect(() => {
		// Apply theme to document
		const root = document.documentElement;
		if (theme === "dark") {
			root.classList.add("dark");
		} else {
			root.classList.remove("dark");
		}
	}, [theme]);

	const setTheme = (newTheme: Theme, skipTransition = false) => {
		if (skipTransition || !document.startViewTransition) {
			// No animation support or explicitly skipped
			setThemeState(newTheme);
			localStorage.setItem("theme", newTheme);
			return;
		}

		// Use View Transitions API for smooth animation
		document.startViewTransition(() => {
			setThemeState(newTheme);
			localStorage.setItem("theme", newTheme);
		});
	};

	const toggleTheme = () => {
		const newTheme = theme === "dark" ? "light" : "dark";
		setTheme(newTheme);
	};

	return (
		<ThemeContext.Provider
			value={{
				theme,
				toggleTheme,
				setTheme,
			}}
		>
			{children}
		</ThemeContext.Provider>
	);
}

export function useTheme() {
	const context = useContext(ThemeContext);
	if (context === undefined) {
		throw new Error("useTheme must be used within a ThemeProvider");
	}
	return context;
}
