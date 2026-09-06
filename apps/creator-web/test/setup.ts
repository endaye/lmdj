import {cleanup, configure} from "@testing-library/react";
import {afterEach} from "vitest";

// Testing Library defaults `findBy*` to a 1000 ms budget. That is generous on
// an idle laptop — this suite's slowest file finishes in about 2.3 s total —
// and too tight on a saturated CI runner, where the same file has taken over
// 7 s and `findByRole("button", {name: "Open Project 11111111"})` timed out
// twice in a row on an unrelated Pull Request (#690).
//
// The budget is not the property under test: these assertions require that an
// element eventually appears, not that it appears within one second. Raising
// it weakens nothing, and a genuinely missing element still fails — just with
// the useful "unable to find role" message rather than a timing artefact.
// Vitest's own per-test timeout stays well above this, so a real hang is still
// caught. See the escalation in #657 for this class of fixed budget.
configure({asyncUtilTimeout: 5_000});

afterEach(() => cleanup());
