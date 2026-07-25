import { render, screen } from "@testing-library/react";
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

    expect(screen.getByRole("heading", { name: /feed it a sound/i })).toBeInTheDocument();
    expect(screen.getByText(/WAV \/ MP3/i)).toBeInTheDocument();
    expect(screen.getByText(/200 MiB/i)).toBeInTheDocument();
    expect(screen.getByText(/600 秒/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /加载示例 patch/i })).toBeInTheDocument();
    expect(screen.queryByText(/generate/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/line-in/i)).not.toBeInTheDocument();
  });
});
