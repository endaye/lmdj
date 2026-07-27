import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { padElementIds, type Patch, type PatchBundle } from "../patch/loader";
import { buildWorkbenchViewModel } from "./workbench/model";
import { ContextInspector } from "./ContextInspector";

function bundle(): PatchBundle<unknown> {
  const patch = structuredClone(golden) as unknown as Patch;
  return {
    patch,
    buffers: new Map(patch.elements.map((element) => [element.element_id, {}])),
    playableElementIds: new Set(patch.elements.map((element) => element.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
}

describe("ContextInspector", () => {
  it("keeps one header node while changing its role accent with selection", () => {
    const source = bundle();
    const { rerender } = render(
      <ContextInspector model={buildWorkbenchViewModel(source)} />,
    );
    const inspector = screen.getByTestId("context-inspector-content");
    const header = screen.getByTestId("context-inspector-header");
    expect(inspector).toHaveAttribute("data-inspector-accent", "patch");

    rerender(<ContextInspector model={buildWorkbenchViewModel(source, 1)} />);

    expect(screen.getByTestId("context-inspector-header")).toBe(header);
    expect(inspector).toHaveAttribute("data-inspector-accent", "bass");
    expect(header).toHaveTextContent("Pad 02 · bass");
  });

  it("shows patch quality, elements, unmapped ids, and warnings when nothing is selected", () => {
    const source = bundle();
    source.warnings.push("missing sample file: samples/ghost.wav (el_ghost)");
    (source.patch.metadata as Record<string, unknown>).unmapped_element_ids = ["el_orphan"];
    const model = buildWorkbenchViewModel(source);

    render(<ContextInspector model={model} />);

    const inspector = screen.getByTestId("context-inspector-content");
    expect(inspector).toHaveTextContent(source.patch.patch_id);
    expect(inspector).toHaveTextContent("passed");
    expect(inspector).toHaveTextContent("0.6556");
    expect(inspector).toHaveTextContent("el_orphan");
    expect(inspector).toHaveTextContent("ghost.wav");
    for (const element of source.patch.elements) {
      expect(inspector).toHaveTextContent(element.name);
    }
  });

  it("shows selected pad label, action, and ready source status", () => {
    const source = bundle();
    const model = buildWorkbenchViewModel(source, 0);

    render(<ContextInspector model={model} />);

    const inspector = screen.getByTestId("context-inspector-content");
    expect(within(inspector).getByRole("heading", { name: /Pad 01 · kick/i })).toBeInTheDocument();
    expect(inspector).toHaveTextContent("trigger_group");
    expect(inspector).toHaveTextContent("READY");
    for (const id of padElementIds(source.patch.pads[0])) {
      expect(inspector).toHaveTextContent(id);
    }
  });

  it("marks the selected pad source as missing without hiding its identity", () => {
    const source = bundle();
    const missing = padElementIds(source.patch.pads[2])[0];
    source.missingElementIds.add(missing);
    source.playableElementIds.delete(missing);
    const model = buildWorkbenchViewModel(source, 2);

    render(<ContextInspector model={model} />);

    const inspector = screen.getByTestId("context-inspector-content");
    expect(inspector).toHaveTextContent(missing);
    expect(inspector).toHaveTextContent("MISSING");
  });

  it("hosts MIDI settings outside export content", () => {
    const source = bundle();
    const midi = <button type="button">Connect MIDI</button>;
    const { rerender } = render(
      <ContextInspector
        model={buildWorkbenchViewModel(source)}
        midiContent={midi}
      />,
    );

    expect(screen.getByRole("heading", { name: "MIDI Setup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect MIDI" })).toBeVisible();

    rerender(
      <ContextInspector
        model={buildWorkbenchViewModel(source)}
        exportContent={<div>Export details</div>}
        midiContent={midi}
      />,
    );

    expect(screen.getByRole("button", { name: "Connect MIDI", hidden: true }))
      .not.toBeVisible();
  });
});
