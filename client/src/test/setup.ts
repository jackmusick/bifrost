import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Start every test from a clean DOM even if a previous file timed out before
// its own afterEach cleanup could run.
beforeEach(() => {
	cleanup();
});

// Unmount after every test so DOM state doesn't leak between cases.
afterEach(() => {
	cleanup();
});
