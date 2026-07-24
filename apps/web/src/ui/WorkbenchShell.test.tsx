import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../patch/loader";
import { buildWorkbenchViewModel } from "./workbench/model";
import { WorkbenchShell } from "./WorkbenchShell";

function model() {
  const patch = structuredClone(golden) as unknown as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(),
    playableElementIds: new Set(),
    missingElementIds: new Set(),
    warnings: [],
  };
  return buildWorkbenchViewModel(bundle, 0);
}

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
});
