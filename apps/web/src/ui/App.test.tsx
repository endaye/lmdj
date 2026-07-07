import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "../engine/AudioEngine";
import { App } from "./App";

const enc = (data: unknown) => new TextEncoder().encode(JSON.stringify(data)).buffer as ArrayBuffer;
const fakeDecode = async () => ({ fake: "buffer" });

function exampleFiles(patch: unknown): () => Promise<Map<string, ArrayBuffer>> {
  return async () => {
    const files = new Map<string, ArrayBuffer>([["patch.json", enc(patch)]]);
    for (const el of (patch as unknown as Patch).elements) files.set(el.source_path, new ArrayBuffer(8));
    return files;
  };
}

function renderApp(patch: unknown) {
  const engine = new AudioEngine(new FakeAudioContext());
  return render(
    <App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(patch)} />,
  );
}

describe("App", () => {
  it("starts on the landing screen with a drop zone and example button", () => {
    renderApp(golden);
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /示例/i })).toBeInTheDocument();
  });

  it("loads the example patch into the workstation view", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-grid")).toBeInTheDocument());
    expect(screen.getByText(/BPM/)).toBeInTheDocument();
  });

  it("shows the error panel on schema-invalid patch and stays on landing", async () => {
    const broken = structuredClone(golden) as unknown as Patch;
    (broken.pads[0] as { action: string }).action = "nope";
    renderApp(broken);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
    expect(screen.getByTestId("error-panel").textContent).toContain("/pads/0/action");
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
  });

  it("shows the rejected banner when metadata.status is rejected", async () => {
    const rejected = structuredClone(golden) as unknown as Patch;
    (rejected.metadata as Record<string, unknown>).status = "rejected";
    renderApp(rejected);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("banner-rejected")).toBeInTheDocument());
  });
});
