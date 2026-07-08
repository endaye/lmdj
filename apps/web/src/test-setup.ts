import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest.config.ts does not set test.globals, so RTL's automatic afterEach
// cleanup (which only registers if it finds a global `afterEach`) never
// fires; without this, DOM from one test's render() leaks into the next.
afterEach(() => {
  cleanup();
});
