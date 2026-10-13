import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {useLayoutEffect, useReducer} from "react";
import {expect, test, vi} from "vitest";

import {createKeyboardAdapter, DEFAULT_KEYBOARD_MAPPING} from "@lmdj/web-runtime-platform/input_adapters.mjs";
import {SampleControls} from "../src/components/sample_controls";
import {SampleSurface} from "../src/components/sample_surface";
import {creatorReducer, initialCreatorState, type CreatorState} from "../src/state/creator_state";
import type {CreatorSampleRuntimeSession, PadPlayback, ProjectView, SampleInspect, WaveformQuery} from "../src/runtime/runtime_types";

const playback: Readonly<PadPlayback> = {
  trimStartFrame: 0, trimEndFrame: 8, triggerMode: "gate", gainMillidb: 0,
  muted: false, reverse: false, pitchCents: 0, pan: 0, loopMode: "forward",
  loopStartFrame: null, loopCrossfadeFrames: 0, attackMs: 0, releaseMs: 0,
  tone: 0, eq: {low: null, mid: null, high: null},
};

function controls(overrides: Partial<React.ComponentProps<typeof SampleControls>> = {}) {
  const props = {
    page: "playback" as const, padLabel: "Pad A01", playback,
    audioSuspended: false, onPreview: vi.fn(), onCommit: vi.fn(),
    onCancel: vi.fn(), onReset: vi.fn(), ...overrides,
  };
  const view = render(<SampleControls {...props} />);
  return {...view, props};
}

async function openValue(label = "Volume") {
  await userEvent.click(screen.getByRole("button", {name: `Edit Pad A01 ${label}`}));
  return screen.getByRole("spinbutton", {name: `Pad A01 ${label} value`});
}

test.each([
  ["Volume", "playback", "-3.2", "gainMillidb", -3_200, "-60", "6", "0.1"],
  ["Pitch", "playback", "1.3", "pitchCents", 130, "-24", "24", "0.1"],
  ["Pan", "playback", "-27", "pan", -27, "-100", "100", "1"],
  ["Attack", "playback", "35", "attackMs", 35, "0", "2000", "1"],
  ["Release", "playback", "80", "releaseMs", 80, "0", "4000", "1"],
  ["Tone", "tone", "-41", "tone", -41, "-100", "100", "1"],
] as const)("%s precise input retains units, bounds and stored scale", async (
  label, page, text, field, stored, min, max, step,
) => {
  const {props} = controls({page});
  const input = await openValue(label);
  expect(document.activeElement).toBe(input);
  expect([input.getAttribute("min"), input.getAttribute("max"), input.getAttribute("step")])
    .toEqual([min, max, step]);
  fireEvent.change(input, {target: {value: text}});
  expect(props.onPreview).toHaveBeenLastCalledWith({...playback, [field]: stored});
  expect(props.onCommit).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: `Apply ${label}`}));
  expect(props.onCommit).toHaveBeenCalledExactlyOnceWith({...playback, [field]: stored});
  expect(props.onCancel).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("Enter confirms once after several legal previews", async () => {
  const {props} = controls();
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-1"}});
  fireEvent.change(input, {target: {value: "-2.5"}});
  expect(props.onPreview).toHaveBeenCalledTimes(2);
  await userEvent.keyboard("{Enter}");
  expect(props.onCommit).toHaveBeenCalledExactlyOnceWith({...playback, gainMillidb: -2_500});
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("neither a typing pause nor input blur saves a precise draft", async () => {
  const {props} = controls();
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-2.5"}});
  vi.useFakeTimers();
  try {
    act(() => vi.advanceTimersByTime(1_000));
    fireEvent.blur(input);
    expect(props.onCommit).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});

test.each(["", "6.1", "-60.1", "0.05"])("refuses invalid Volume %j without preview or commit", async (value) => {
  const {props} = controls();
  const input = await openValue();
  fireEvent.change(input, {target: {value}});
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(screen.getByRole("button", {name: "Apply Volume"})).toHaveProperty("disabled", true);
  expect(props.onPreview).not.toHaveBeenCalled();
  await userEvent.keyboard("{Enter}");
  expect(props.onCommit).not.toHaveBeenCalled();
});

test("invalid replacement clears the prior legal audition without saving", async () => {
  const {props} = controls();
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  fireEvent.change(input, {target: {value: "9"}});
  expect(props.onCancel).toHaveBeenCalledTimes(1);
  expect(props.onCommit).not.toHaveBeenCalled();
});

test.each(["unchanged", "returned"])("%s value does not create an authoring operation", async (kind) => {
  const {props} = controls();
  const input = await openValue();
  if (kind === "returned") {
    fireEvent.change(input, {target: {value: "-3"}});
    fireEvent.change(input, {target: {value: "0"}});
  }
  await userEvent.click(screen.getByRole("button", {name: "Apply Volume"}));
  expect(props.onCommit).not.toHaveBeenCalled();
  expect(props.onCancel).toHaveBeenCalledTimes(kind === "returned" ? 1 : 0);
});

test.each(["Escape", "Cancel", "unmount"])("%s discards precise preview without saving", async (kind) => {
  const view = controls();
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  if (kind === "unmount") view.unmount();
  else if (kind === "Escape") await userEvent.keyboard("{Escape}");
  else await userEvent.click(screen.getByRole("button", {name: "Cancel Volume"}));
  expect(view.props.onCancel).toHaveBeenCalledTimes(1);
  expect(view.props.onCommit).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
  if (kind !== "unmount") {
    expect(document.activeElement).toBe(screen.getByRole("button", {name: "Edit Pad A01 Volume"}));
  }
});

test.each(["context", "pad", "page", "disabled", "audio"])("changed %s closes and cancels the prior target", async (change) => {
  const view = controls({numericEditingContext: {project: "first"}});
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  const changes = change === "context" ? {numericEditingContext: {project: "second"}}
    : change === "pad" ? {padLabel: "Pad A02"}
    : change === "page" ? {page: "tone" as const}
    : change === "audio" ? {audioSuspended: true}
    : {numericEditingDisabled: true};
  view.rerender(<SampleControls {...view.props} {...changes} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(view.props.onCancel).toHaveBeenCalledTimes(1);
  expect(view.props.onCommit).not.toHaveBeenCalled();
});

test("external cancellation clears audition before returning to its caller", async () => {
  let cancel: (() => void) | null = null;
  const view = controls({onNumericEditorReady: (callback) => {cancel = callback;}});
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  expect(cancel).not.toBeNull();
  act(() => {
    cancel!();
    expect(view.props.onCancel).toHaveBeenCalledTimes(1);
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(view.props.onCommit).not.toHaveBeenCalled();
});

test("a queued submit during target replacement cannot save the prior target", async () => {
  const props = {page: "playback" as const, padLabel: "Pad A01", playback,
    audioSuspended: false, onPreview: vi.fn(), onCommit: vi.fn(), onCancel: vi.fn(), onReset: vi.fn()};
  const first = {project: "first"};
  const second = {project: "second"};
  function QueuedSubmit({attempt}: {attempt: boolean}) {
    useLayoutEffect(() => {
      if (!attempt) return;
      // Submit before passive context cleanup runs. This controlled interleave
      // proves the callback boundary, independently of whether the dialog closes.
      fireEvent.submit(document.querySelector(".sample-parameter-editor form")!);
    }, [attempt]);
    return null;
  }
  const view = render(<><SampleControls {...props} numericEditingContext={first} />
    <QueuedSubmit attempt={false} /></>);
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  view.rerender(<><SampleControls {...props} numericEditingContext={second} />
    <QueuedSubmit attempt={true} /></>);
  expect(props.onCommit).not.toHaveBeenCalled();
  expect(props.onCancel).toHaveBeenCalledTimes(1);
});

test("a queued submit during audio suspension cannot save its cancelled draft", async () => {
  const props = {page: "playback" as const, padLabel: "Pad A01", playback,
    onPreview: vi.fn(), onCommit: vi.fn(), onCancel: vi.fn(), onReset: vi.fn()};
  function QueuedSubmit({attempt}: {attempt: boolean}) {
    useLayoutEffect(() => {
      if (attempt) fireEvent.submit(document.querySelector(".sample-parameter-editor form")!);
    }, [attempt]);
    return null;
  }
  const view = render(<><SampleControls {...props} audioSuspended={false} />
    <QueuedSubmit attempt={false} /></>);
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  view.rerender(<><SampleControls {...props} audioSuspended={true} />
    <QueuedSubmit attempt={true} /></>);
  expect(props.onCommit).not.toHaveBeenCalled();
  expect(props.onCancel).toHaveBeenCalledTimes(1);
});

test("a precise editor opened while audio is suspended can still save once", async () => {
  const view = controls({audioSuspended: true});
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  await userEvent.click(screen.getByRole("button", {name: "Apply Volume"}));
  expect(view.props.onCommit).toHaveBeenCalledExactlyOnceWith({...playback, gainMillidb: -3_000});
});

test("precise editor starts from saved Truth instead of an encoder draft", async () => {
  const onBeginNumericEdit = vi.fn();
  controls({playback: {...playback, gainMillidb: -1_000}, savedPlayback: playback, onBeginNumericEdit});
  const input = await openValue();
  expect(onBeginNumericEdit).toHaveBeenCalledTimes(1);
  expect(input).toHaveProperty("value", "0");
});

test("one-shot Release remains unavailable to precise editing", () => {
  controls({playback: {...playback, triggerMode: "one_shot"}});
  expect(screen.getByRole("button", {name: "Edit Pad A01 Release"})).toHaveProperty("disabled", true);
});

test("the range label has one associated control and contains no edit button", () => {
  controls();
  const slider = screen.getByRole("slider", {name: "Pad A01 Volume"}) as HTMLInputElement;
  const label = slider.labels![0]!;
  expect(label.control).toBe(slider);
  expect(label.contains(screen.getByRole("button", {name: "Edit Pad A01 Volume"}))).toBe(false);
});

test("non-finite numeric input cannot preview or save", async () => {
  const {props} = controls();
  const input = await openValue();
  Object.defineProperty(input, "valueAsNumber", {configurable: true, get: () => Number.NaN});
  fireEvent.change(input, {target: {value: "3"}});
  expect(screen.getByRole("button", {name: "Apply Volume"})).toHaveProperty("disabled", true);
  expect(props.onPreview).not.toHaveBeenCalled();
  await userEvent.keyboard("{Enter}");
  expect(props.onCommit).not.toHaveBeenCalled();
});

test("focused precise input does not trigger keyboard Pads", async () => {
  const trigger = vi.fn();
  const keyboard = createKeyboardAdapter({trigger, velocity: 127, mapping: DEFAULT_KEYBOARD_MAPPING});
  const listener = (event: KeyboardEvent) => {keyboard.keyDown(event);};
  window.addEventListener("keydown", listener);
  try {
    fireEvent.keyDown(document.body, {key: "q", code: "KeyQ"});
    expect(trigger).toHaveBeenCalledTimes(1);
    keyboard.clearPressed();
    trigger.mockClear();
    controls();
    const input = await openValue();
    expect(document.activeElement).toBe(input);
    // Synthetic key events keep their real focus target. They do not prove
    // trusted browser activation or audible PCM, which remain acceptance gaps.
    fireEvent.keyDown(input, {key: "q", code: "KeyQ"});
    fireEvent.keyDown(input, {key: "w", code: "KeyW"});
    expect(trigger).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener("keydown", listener);
  }
});

function surfaceFixture() {
  const assetId = "33333333-3333-4333-8333-333333333333";
  const project: ProjectView = {
    projectId: "11111111-1111-4111-8111-111111111111",
    patternId: "22222222-2222-4222-8222-222222222222", revision: 3,
    bpm: 120, assetCount: 1, assignedPadCount: 2, bundleDigest: "a".repeat(64), key: "—",
    pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: slot < 2 ? assetId : null,
      category: null, colourOverride: null, colour: null})),
    patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 1, events: []}],
    patternSlots: Array<string | null>(16).fill(null),
    sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
  };
  let stored: Readonly<PadPlayback> = playback;
  let revision = 3;
  let previewResolve: ((result: boolean) => void) | null = null;
  const inspect = (slot: number): SampleInspect => ({projectRevision: revision,
    slot, assetId, playback: stored,
    metadata: {sampleRate: 48_000, channels: 1, sourceFrames: 8},
    waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/1`});
  const setSamplePreview = vi.fn(async () => true);
  const clearSamplePreview = vi.fn(async () => true);
  const updatePad = vi.fn(async (request: {slot: number; expectedRevision: number; playback: Readonly<PadPlayback>}) => {
    stored = request.playback;
    revision += 1;
    return {committedRevision: revision, runtimeRevision: revision, runtimePublished: true, snapshotError: null};
  });
  // Only the capabilities SampleSurface actually invokes are supplied. This
  // is a component facade seam, not a native authoring journal or hearing proof.
  const session = {
    inspectSample: async (slot: number) => inspect(slot), setSamplePreview, clearSamplePreview, updatePad,
    queryWaveform: async ({window}: WaveformQuery) => ({metadata: inspect(0).metadata,
      algorithmVersion: 1, projectRevision: revision,
      buckets: Array.from({length: window.endFrame - window.startFrame}, (_, index) => ({
        startFrame: window.startFrame + index, endFrame: window.startFrame + index + 1, peakMagnitude: 0,
      })),
    }),
    inspectProject: async () => ({project_revision: revision, project: {
      contract: "lmdj.project.v5", project_id: project.projectId, revision, bpm: 120,
      assets: {[assetId]: {}}, patterns: {[project.patternId]: {bars: 1, events: []}},
      pattern_slots: Array(16).fill(null), sequence_settings: {quantize_enabled: true, swing_percent: 50},
      banks: Array.from({length: 4}, (_, bank) => ({bank, pads: project.pads.slice(bank * 16, bank * 16 + 16)
        .map((pad, index) => ({pad: index, asset_id: pad.assetId, category: null, colour_override: null, colour: null}))})),
    }}),
    listLocalProjects: async () => [{...project, revision}],
  } as unknown as CreatorSampleRuntimeSession;
  const state: CreatorState = {...initialCreatorState,
    project: {phase: "ready", projects: [project], current: project},
    runtime: {phase: "ready", errorCode: null}, audio: {phase: "running"},
    sample: {...initialCreatorState.sample, selectedSlot: 0, inspect: inspect(0), savedRevision: 3, runtimeRevision: 3},
  };
  function ControlledSurface() {
    const [current, dispatch] = useReducer(creatorReducer, state);
    return <><output aria-label="Authoring revision">{current.project.current?.revision}</output>
      <SampleSurface state={current} session={session} dispatch={dispatch} filePickIntent={{current: () => {}}} />
    </>;
  }
  return {session, state, setSamplePreview, clearSamplePreview, updatePad, ControlledSurface,
    deferPreview() {
      setSamplePreview.mockImplementation(() => new Promise<boolean>((resolve) => {previewResolve = resolve;}));
    },
    resolvePreview() {previewResolve!(true);},
  };
}

test("Sample surface saves the final precise value through one revision-fenced update and refresh", async () => {
  const fixture = surfaceFixture();
  render(<fixture.ControlledSurface />);
  await userEvent.click(screen.getByRole("button", {name: "Playback"}));
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3.2"}});
  await waitFor(() => expect(fixture.setSamplePreview).toHaveBeenCalledWith(0, {...playback, gainMillidb: -3_200}));
  expect(fixture.updatePad).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Apply Volume"}));
  await waitFor(() => expect(screen.getByLabelText("Authoring revision").textContent).toBe("4"));
  expect(fixture.updatePad).toHaveBeenCalledExactlyOnceWith({slot: 0, expectedRevision: 3,
    playback: {...playback, gainMillidb: -3_200}});
  expect(screen.getByRole("button", {name: "Edit Pad A01 Volume"}).textContent).toBe("-3.2 dB");
});

test.each(["Pad", "Project", "Asset", "revision", "session", "page exit", "Escape"])(
  "late preview completion after %s change cannot revive or save the old numeric draft", async (change) => {
  const fixture = surfaceFixture();
  fixture.deferPreview();
  const dispatch = vi.fn();
  const props = {session: fixture.session, dispatch, filePickIntent: {current: () => {}}};
  const view = render(<SampleSurface {...props} state={fixture.state} />);
  await userEvent.click(screen.getByRole("button", {name: "Playback"}));
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3.2"}});
  expect(fixture.setSamplePreview).toHaveBeenCalledTimes(1);
  if (change === "Escape") await userEvent.keyboard("{Escape}");
  else {
    const state = change === "Pad" ? {...fixture.state,
      sample: {...fixture.state.sample, selectedSlot: 1, inspect: {...fixture.state.sample.inspect!, slot: 1}}}
      : change === "Project" ? {...fixture.state, project: {...fixture.state.project,
        current: {...fixture.state.project.current!, projectId: "44444444-4444-4444-8444-444444444444"}}}
      : change === "Asset" ? {...fixture.state, sample: {...fixture.state.sample,
        inspect: {...fixture.state.sample.inspect!, assetId: "55555555-5555-4555-8555-555555555555"}}}
      : change === "revision" ? {...fixture.state, project: {...fixture.state.project,
        current: {...fixture.state.project.current!, revision: 4}}, sample: {...fixture.state.sample,
        inspect: {...fixture.state.sample.inspect!, projectRevision: 4}}}
      : fixture.state;
    view.rerender(<SampleSurface {...props} state={state}
      session={change === "session" ? {...fixture.session} : fixture.session}
      encodersActive={change !== "page exit"} />);
  }
  expect(screen.queryByRole("dialog")).toBeNull();
  await waitFor(() => expect(fixture.clearSamplePreview).toHaveBeenCalledWith(0));
  dispatch.mockClear();
  await act(async () => {fixture.resolvePreview(); await Promise.resolve();});
  expect(dispatch).not.toHaveBeenCalledWith({type: "sample-action",
    action: {type: "preview-applied", playback: {...playback, gainMillidb: -3_200}}});
  expect(fixture.updatePad).not.toHaveBeenCalled();
});

test("a rejected numeric save clears audition and keeps the saved value visible", async () => {
  const fixture = surfaceFixture();
  fixture.updatePad.mockRejectedValueOnce(Object.assign(new Error("Update refused"), {code: "HOST_STATE_INVALID"}));
  render(<fixture.ControlledSurface />);
  await userEvent.click(screen.getByRole("button", {name: "Playback"}));
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3.2"}});
  await userEvent.click(screen.getByRole("button", {name: "Apply Volume"}));
  await screen.findByRole("alert");
  expect(fixture.updatePad).toHaveBeenCalledExactlyOnceWith({slot: 0, expectedRevision: 3,
    playback: {...playback, gainMillidb: -3_200}});
  expect(fixture.clearSamplePreview).toHaveBeenCalledWith(0);
  expect(screen.getByLabelText("Authoring revision").textContent).toBe("3");
  expect(screen.getByRole("button", {name: "Edit Pad A01 Volume"}).textContent).toBe("0.0 dB");
});

test("a queued input during target replacement cannot preview the retired numeric draft", async () => {
  const props = {page: "playback" as const, padLabel: "Pad A01", playback,
    audioSuspended: false, onPreview: vi.fn(), onCommit: vi.fn(), onCancel: vi.fn(), onReset: vi.fn()};
  const first = {project: "first"};
  const second = {project: "second"};
  function QueuedInput({attempt}: {attempt: boolean}) {
    useLayoutEffect(() => {
      if (attempt) fireEvent.change(document.querySelector(".sample-parameter-editor input")!,
        {target: {value: "-4.8"}});
    }, [attempt]);
    return null;
  }
  const view = render(<><SampleControls {...props} numericEditingContext={first} />
    <QueuedInput attempt={false} /></>);
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3.2"}});
  expect(props.onPreview).toHaveBeenCalledExactlyOnceWith({...playback, gainMillidb: -3_200});
  view.rerender(<><SampleControls {...props} numericEditingContext={second} />
    <QueuedInput attempt /></>);
  expect(props.onPreview).toHaveBeenCalledTimes(1);
  expect(props.onCommit).not.toHaveBeenCalled();
  expect(props.onCancel).toHaveBeenCalledTimes(1);
});

test.each([
  ["Volume", "playback", "-3.2", "gainMillidb", -3_200, "-60", "6", "0.1"],
  ["Pitch", "playback", "1.3", "pitchCents", 130, "-24", "24", "0.1"],
  ["Pan", "playback", "-27", "pan", -27, "-100", "100", "1"],
  ["Attack", "playback", "35", "attackMs", 35, "0", "2000", "1"],
  ["Release", "playback", "80", "releaseMs", 80, "0", "4000", "1"],
  ["Tone", "tone", "-41", "tone", -41, "-100", "100", "1"],
] as const)("%s Numeric range shares the exact draft without release-save", async (
  label, page, text, field, stored, min, max, step,
) => {
  const {props} = controls({page});
  const input = await openValue(label);
  const range = screen.getByRole("slider", {name: `Pad A01 ${label} preview`});
  expect([range.getAttribute("min"), range.getAttribute("max"), range.getAttribute("step")])
    .toEqual([min, max, step]);
  fireEvent.change(range, {target: {value: text}});
  expect(input).toHaveProperty("value", text);
  expect(props.onPreview).toHaveBeenLastCalledWith({...playback, [field]: stored});
  fireEvent.pointerUp(range);
  fireEvent.keyUp(range, {key: "ArrowRight"});
  fireEvent.blur(range);
  expect(props.onCommit).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: `Apply ${label}`}));
  expect(props.onCommit).toHaveBeenCalledExactlyOnceWith({...playback, [field]: stored});
});

test("Numeric header and saved readout retain the opening Pad and authoring value", async () => {
  const view = controls({playback: {...playback, gainMillidb: -6_000}});
  const input = await openValue();
  fireEvent.change(input, {target: {value: "-3"}});
  view.rerender(<SampleControls {...view.props} playback={{...playback, gainMillidb: -3_000}} />);
  expect(screen.getByRole("heading", {name: "PAD VOLUME"})).toBeTruthy();
  expect(screen.getByText("A01", {selector: ".sample-parameter-target"})).toBeTruthy();
  expect(screen.getByText("Saved value: −6.0 dB")).toBeTruthy();
  expect(input).toHaveProperty("value", "-3");
  expect(screen.getByRole("slider", {name: "Pad A01 Volume preview"})).toHaveProperty("value", "-3");
  expect(view.props.onCommit).not.toHaveBeenCalled();
});

test("invalid exact text clears preview and a legal range gesture replaces that invalid draft", async () => {
  const {props} = controls();
  const input = await openValue();
  const range = screen.getByRole("slider", {name: "Pad A01 Volume preview"});
  fireEvent.change(input, {target: {value: "-3"}});
  fireEvent.change(input, {target: {value: "9"}});
  expect(props.onCancel).toHaveBeenCalledTimes(1);
  expect(input).toHaveProperty("value", "9");
  expect(range).toHaveProperty("value", "0");
  expect(screen.getByRole("button", {name: "Apply Volume"})).toHaveProperty("disabled", true);
  fireEvent.change(range, {target: {value: "-4.8"}});
  expect(input).toHaveProperty("value", "-4.8");
  expect(input.getAttribute("aria-invalid")).toBe("false");
  expect(props.onPreview).toHaveBeenLastCalledWith({...playback, gainMillidb: -4_800});
  expect(props.onCommit).not.toHaveBeenCalled();
});

test("Enter on the Numeric range saves the final draft exactly once", async () => {
  const {props} = controls();
  await openValue();
  const range = screen.getByRole("slider", {name: "Pad A01 Volume preview"});
  range.focus();
  fireEvent.change(range, {target: {value: "-3"}});
  fireEvent.change(range, {target: {value: "-4.8"}});
  await userEvent.keyboard("{Enter}");
  expect(props.onCommit).toHaveBeenCalledExactlyOnceWith({...playback, gainMillidb: -4_800});
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole("button", {name: "Edit Pad A01 Volume"}));
});

test.each(["Escape", "Cancel", "unmount", "returned"])("Numeric range %s preserves authoring", async (kind) => {
  const view = controls();
  await openValue();
  const range = screen.getByRole("slider", {name: "Pad A01 Volume preview"});
  range.focus();
  fireEvent.change(range, {target: {value: "-3"}});
  if (kind === "unmount") view.unmount();
  else if (kind === "Escape") await userEvent.keyboard("{Escape}");
  else if (kind === "returned") {
    fireEvent.change(range, {target: {value: "0"}});
    await userEvent.click(screen.getByRole("button", {name: "Apply Volume"}));
  } else await userEvent.click(screen.getByRole("button", {name: "Cancel Volume"}));
  expect(view.props.onCancel).toHaveBeenCalledTimes(1);
  expect(view.props.onCommit).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("Numeric focus follows number, range, Apply, Cancel and stays inside the modal", async () => {
  controls();
  const input = await openValue();
  expect(document.activeElement).toBe(input);
  await userEvent.tab();
  expect(document.activeElement).toBe(screen.getByRole("slider", {name: "Pad A01 Volume preview"}));
  await userEvent.tab();
  expect(document.activeElement).toBe(screen.getByRole("button", {name: "Apply Volume"}));
  await userEvent.tab();
  expect(document.activeElement).toBe(screen.getByRole("button", {name: "Cancel Volume"}));
  await userEvent.tab();
  expect(document.activeElement).toBe(input);
});
