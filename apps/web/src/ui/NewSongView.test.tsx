import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewSongView } from "./NewSongView";

describe("NewSongView", () => {
  it("keeps the song upload primary and local packages under Advanced", async () => {
    render(
      <NewSongView
        onFiles={vi.fn()}
        onExample={vi.fn()}
        onUpload={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "上传新歌" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("上传限制")).toHaveTextContent("最大 200 MiB");
    expect(screen.getByTestId("api-panel")).toBeInTheDocument();
    expect(screen.getByTestId("advanced-source-actions")).not.toHaveAttribute(
      "open",
    );

    await userEvent.click(screen.getByText("高级 · 导入 Patch 包"));
    expect(screen.getByTestId("drop-zone")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "加载示例 patch" }),
    ).toBeVisible();
  });
});
