import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve("src/ui/theme.css"), "utf8");

function declarationRules(source: string, name: string): Array<{
  selector: string;
  value: string;
}> {
  return source.split("}").flatMap((chunk) => {
    const open = chunk.lastIndexOf("{");
    if (open === -1) return [];
    const selectorBlock =
      chunk.slice(0, open).trim().split("{").at(-1)?.trim() ?? "";
    const selectors = selectorBlock
      .split(",")
      .map((selector) => selector.trim())
      .filter(Boolean);
    const body = chunk.slice(open + 1);
    const expression = new RegExp(`${name}:\\s*([^;]+)`, "g");
    return [...body.matchAll(expression)].flatMap((match) =>
      selectors.map((selector) => ({
        selector,
        value: match[1].trim(),
      })),
    );
  });
}

describe("Polanyi flat UI contract", () => {
  it("does not use shadows anywhere in the product theme", () => {
    const shadows = declarationRules(css, "box-shadow");
    expect(shadows.length).toBeGreaterThan(0);
    expect(shadows.every(({ value }) => value === "none")).toBe(true);
  });

  it("allows rounded geometry only inside decorative generative marks", () => {
    const allowed =
      /pad-geometry|project-signature__motif|performance-trace__mark/;
    const rounded = declarationRules(css, "border-radius").filter(
      ({ value }) => value !== "0" && value !== "0px",
    );
    expect(rounded.length).toBeGreaterThan(0);
    expect(rounded.every(({ selector }) => allowed.test(selector))).toBe(true);
  });

  it("evaluates every selector member in a comma-separated radius rule", () => {
    const allowed =
      /pad-geometry|project-signature__motif|performance-trace__mark/;
    const syntheticCss = `
      .delete-dialog,
      .performance-trace__mark {
        border-radius: 12px;
      }
    `;
    const rounded = declarationRules(syntheticCss, "border-radius");

    expect(rounded).toEqual([
      { selector: ".delete-dialog", value: "12px" },
      { selector: ".performance-trace__mark", value: "12px" },
    ]);
    expect(rounded.every(({ selector }) => allowed.test(selector))).toBe(false);
  });

  it("keeps keyboard focus visible around pads", () => {
    const focusOutline = declarationRules(css, "outline").find(
      ({ selector }) => selector === ".pad:focus-visible",
    );

    expect(focusOutline?.value).toBe("3px solid var(--ink)");
  });

  it("keeps the selected marker visible while a pad is hovered", () => {
    const selectedHoverBorder = declarationRules(css, "border-color").find(
      ({ selector }) => selector === '.pad[data-selected="true"]:hover::after',
    );

    expect(selectedHoverBorder?.value).toBe("var(--paper)");
  });

  it("removes active pad motion when reduced motion is preferred", () => {
    const reducedMotionStart = css.indexOf(
      "@media (prefers-reduced-motion: reduce)",
    );
    const reducedMotionEnd = css.indexOf(
      "/* --- Instrument-first workbench shell",
      reducedMotionStart,
    );
    const reducedMotionCss = css.slice(reducedMotionStart, reducedMotionEnd);

    expect(reducedMotionCss).toContain(
      '.pad:hover,\n  .pad:active,\n  .pad[data-pressed="true"]',
    );
  });
});
