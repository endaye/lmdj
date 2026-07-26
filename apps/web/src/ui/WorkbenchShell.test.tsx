import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../patch/loader";
import { buildWorkbenchViewModel } from "./workbench/model";
import { WorkbenchShell } from "./WorkbenchShell";

function model(selectedPadIndex = 0) {
  const patch = structuredClone(golden) as unknown as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(),
    playableElementIds: new Set(),
    missingElementIds: new Set(),
    warnings: [],
  };
  return buildWorkbenchViewModel(bundle, selectedPadIndex);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WorkbenchShell", () => {
  it("keeps the instrument-first landmark order fixed", () => {
    render(
      <WorkbenchShell
        model={model()}
        mode="source"
        onModeChange={() => undefined}
        availableModes={["source", "performance", "export"]}
        appBar={<span>app bar</span>}
        instrumentCanvas={<span>instrument canvas</span>}
        contextInspector={<span>context inspector</span>}
        statusBar={<span>status bar</span>}
      />,
    );

    const landmarks = ["app-bar", "creator-tools", "instrument-canvas", "context-inspector", "status-bar"]
      .map((id) => screen.getByTestId(id));
    for (let index = 0; index < landmarks.length - 1; index += 1) {
      expect(landmarks[index].compareDocumentPosition(landmarks[index + 1])).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    }
  });

  it("uses measured container layout and traps focus inside the modal Inspector", async () => {
    class TestResizeObserver {
      constructor(
        private readonly callback: ResizeObserverCallback,
      ) {}

      observe() {
        this.callback(
          [{ contentRect: { width: 676 } } as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
      }

      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", TestResizeObserver);

    render(
      <WorkbenchShell
        model={model(7)}
        mode="source"
        onModeChange={() => undefined}
        availableModes={["source", "performance", "export"]}
        appBar={<span>app bar</span>}
        instrumentCanvas={<button>canvas action</button>}
        contextInspector={
          <>
            <button>first inspector action</button>
            <button>last inspector action</button>
          </>
        }
        statusBar={<span>status bar</span>}
      />,
    );

    const shell = screen.getByTestId("workbench-shell");
    await waitFor(() => expect(shell).toHaveAttribute("data-layout", "tablet"));
    const toggle = screen.getByTestId("inspector-toggle");
    await userEvent.click(toggle);

    expect(screen.getByTestId("context-inspector")).toHaveAttribute(
      "data-side",
      "left",
    );
    for (const id of ["app-bar", "creator-tools", "instrument-canvas", "status-bar"]) {
      expect(screen.getByTestId(id)).toHaveAttribute("inert");
    }
    expect(screen.getByTestId("inspector-close")).toHaveFocus();

    await userEvent.keyboard("{Shift>}{Tab}{/Shift}");
    expect(screen.getByRole("button", { name: "last inspector action" })).toHaveFocus();
    await userEvent.keyboard("{Tab}");
    expect(screen.getByTestId("inspector-close")).toHaveFocus();

    await userEvent.click(screen.getByTestId("inspector-close"));
    await waitFor(() => expect(toggle).toHaveFocus());
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
