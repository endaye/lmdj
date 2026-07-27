import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProjectSignature } from "./ProjectSignature";

describe("ProjectSignature", () => {
  it("renders a deterministic decorative band from the public seed", () => {
    render(
      <ProjectSignature
        seed="submission-a"
        phase="separating"
        variant="band"
        testId="signature"
      />,
    );

    const signature = screen.getByTestId("signature");
    expect(signature).toHaveAttribute("aria-hidden", "true");
    expect(signature).toHaveAttribute(
      "data-signature",
      "wave-173-71-6-84",
    );
    expect(signature).toHaveAttribute("data-phase", "separating");
    expect(signature).toHaveAttribute("data-variant", "band");
    expect(
      signature.querySelectorAll('[data-active="true"]'),
    ).toHaveLength(2);
  });

  it.each([
    ["idle", 0],
    ["preflight", 1],
    ["queued", 1],
    ["extracting", 3],
    ["patchifying", 4],
    ["review", 5],
    ["ready", 6],
    ["error", 2],
  ] as const)(
    "uses discrete %s state without inventing a percent",
    (phase, active) => {
      render(
        <ProjectSignature
          seed="submission-b"
          phase={phase}
          variant="stage"
          testId={`signature-${phase}`}
        />,
      );
      const signature = screen.getByTestId(`signature-${phase}`);
      expect(signature.querySelectorAll('[data-active="true"]')).toHaveLength(
        active,
      );
      expect(signature).not.toHaveTextContent(/%/);
    },
  );
});
