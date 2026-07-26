import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SourcePanel } from "./SourcePanel";

describe("SourcePanel", () => {
  it("offers only available upload and example sources with visible limits", () => {
    render(
      <SourcePanel
        onFiles={vi.fn()}
        onExample={vi.fn()}
        onUpload={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /feed it\s+a sound/i }),
    ).toBeInTheDocument();
    // The Gallery stage trigger also reads "WAV / MP3", so scope the limits
    // assertion to the labelled limits region.
    const limits = screen.getByLabelText("Upload limits");
    expect(within(limits).getByText(/WAV \/ MP3/i)).toBeInTheDocument();
    expect(within(limits).getByText(/200 MiB/i)).toBeInTheDocument();
    expect(within(limits).getByText(/600 秒/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /加载示例 patch/i })).toBeInTheDocument();
    expect(screen.queryByText(/generate/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/line-in/i)).not.toBeInTheDocument();
  });

  it("makes the Chameleon the primary audio upload entrance", () => {
    render(
      <SourcePanel
        onFiles={vi.fn()}
        onExample={vi.fn()}
        onUpload={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Choose a WAV or MP3 to make a Patch",
      }),
    ).toBeEnabled();
    expect(screen.getByText(/AI MUSIC MATERIAL INSTRUMENT/i)).toBeInTheDocument();
    expect(screen.getByTestId("api-file-input")).toHaveAttribute(
      "accept",
      ".wav,.mp3,audio/wav,audio/mpeg",
    );
  });
});
