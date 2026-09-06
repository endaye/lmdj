import {cleanup, configure} from "@testing-library/react";
import {afterEach} from "vitest";

// `findBy*` / `waitFor` default to 1000 ms, a bound calibrated for an idle
// laptop. On a saturated CI host the first render of the workspace can take
// longer than that with nothing wrong (#690: 7 failures in one evening, every
// one between 1.2 s and 2.0 s). The wait is a load proxy, not a correctness
// assertion, so it gets headroom; `testTimeout` in vite.config.ts is raised
// with it so a slow wait fails as "not found", not as a test timeout.
configure({asyncUtilTimeout: 4000});

afterEach(() => cleanup());
