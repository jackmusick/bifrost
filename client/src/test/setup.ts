import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount after every test so DOM state doesn't leak between cases.
afterEach(() => {
	cleanup();
});
