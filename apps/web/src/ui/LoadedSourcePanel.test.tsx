import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  LoadedSourceInspector,
  LoadedSourcePanel,
  type LoadedSourceSummary,
} from "./LoadedSourcePanel";

const source: LoadedSourceSummary = {
  kind: "API Job",
  name: "beat.wav",
  detail: "Job job-123 · http://localhost:8000",
};
const facts = {
  patchId: "beat-a1b2c3d4",
  padCount: 16,
  elementCount: 5,
  playableElementCount: 4,
  missingElementCount: 1,
};

describe("LoadedSourcePanel", () => {
  it("reports only known loaded-source facts and makes replacement explicit", async () => {
    const onReplace = vi.fn();
    render(
      <LoadedSourcePanel
        source={source}
        facts={facts}
        onReplace={onReplace}
      />,
    );

    expect(screen.getByRole("heading", { name: "已加载来源" })).toBeInTheDocument();
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent("API Job");
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent("beat.wav");
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent("16 个数据 Pad");
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent("4/5 可播放");
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent("Missing1");
    expect(screen.queryByText(/Stem/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "更换音频" }));
    expect(onReplace).toHaveBeenCalledOnce();
  });

  it("uses loaded source facts instead of Pad details in the Source inspector", () => {
    render(<LoadedSourceInspector source={source} facts={facts} />);

    expect(screen.getByTestId("loaded-source-inspector")).toHaveTextContent(
      "beat-a1b2c3d4",
    );
    expect(screen.getByTestId("loaded-source-inspector")).toHaveTextContent(
      "4/5 assets",
    );
    expect(screen.getByTestId("loaded-source-inspector")).toHaveTextContent(
      "Patch retained",
    );
  });
});
