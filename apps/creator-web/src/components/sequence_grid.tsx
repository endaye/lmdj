import {memo, useEffect, useRef, useState} from "react";

import {ModalDialog} from "./modal_dialog";
import "./sequence_grid_tools.css";

import type {PadColour} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import {padColourAttribute} from "../state/pad_colour";
import {slotAddress} from "../state/view_model";
import {
  createSequenceGridModel,
  sameSequenceGridKey,
  SEQUENCE_BANK_PADS,
  SEQUENCE_GRID_SNAPS,
  sequenceGridAddNote,
  sequenceGridBatchDelete,
  sequenceGridBatchMove,
  sequenceGridMoveNote,
  sequenceGridNotesInBox,
  sequenceGridRemoveNote,
  sequenceGridResizeNote,
  sequenceGridVelocityNote,
  sequenceGridViewportForWindow,
  type SequenceGridEdit,
  type SequenceGridEditMode,
  type SequenceGridEventKey,
  type SequenceGridModel,
  type SequenceGridNote,
  type SequenceGridPattern,
  type SequenceGridSnap,
  type SequenceGridViewport,
} from "../state/sequence_grid_model";

interface SequenceGridEditing {
  readonly enabled: boolean;
  readonly reason: string | null;
}

interface SequenceGridProps {
  pattern: SequenceGridPattern;
  bank: Bank;
  snap: SequenceGridSnap;
  editMode: SequenceGridEditMode;
  editing: SequenceGridEditing;
  selection: readonly SequenceGridEventKey[];
  defaultVelocity: number;
  currentPad?: number;
  onScrollReady?(scroll: ((bars: number) => void) | null): void;
  onSnapChange(snap: SequenceGridSnap): void;
  onEditModeChange(mode: SequenceGridEditMode): void;
  onViewportChange(viewport: SequenceGridViewport): void;
  // One gesture ends in one edit; a no-op gesture never reaches this callback.
  onEdit(edit: SequenceGridEdit): void;
  onSelectionChange(selection: readonly SequenceGridEventKey[]): void;
  onVelocityChange(velocity: number): void;
  // The effective Pad colour from Project Truth for a flat slot (#1207);
  // absent or null draws the neutral note.
  padColour?: (slot: number) => PadColour | null;
}

interface GridRect {
  readonly element: Element | null;
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
  readonly rotated: boolean;
  readonly layoutWidth: number;
  readonly layoutHeight: number;
  readonly rowStarts: readonly number[] | null;
}

type GridGesture =
  | Readonly<{kind: "add"; pointerId: number; originX: number; originY: number;
      pad: number; tick: number; laneRect: GridRect; bodyRect: GridRect}>
  | Readonly<{kind: "box"; pointerId: number; originX: number; originY: number;
      currentX: number; currentY: number; fromPad: number; fromTick: number;
      laneRect: GridRect; bodyRect: GridRect}>
  | Readonly<{kind: "press"; pointerId: number; originX: number; originY: number;
      note: SequenceGridNote; zone: "body" | "end"; originTick: number;
      pressPad: number; pressTick: number;
      laneRect: GridRect; bodyRect: GridRect}>
  | Readonly<{kind: "move"; pointerId: number; originX: number; originY: number;
      notes: readonly SequenceGridNote[]; originPad: number; originTick: number;
      pressPad: number; pressTick: number;
      deltaPads: number; deltaTicks: number;
      laneRect: GridRect; bodyRect: GridRect}>
  | Readonly<{kind: "resize"; pointerId: number; originX: number; originY: number;
      note: SequenceGridNote; endTick: number; laneRect: GridRect}>
  | Readonly<{kind: "velocity"; pointerId: number; originX: number; originY: number;
      note: SequenceGridNote; velocity: number; laneRect: GridRect}>;

// A press within this distance stays a tap; past it the gesture becomes a
// drag (box-select, move or resize).
const DRAG_THRESHOLD_PX = 4;

// fitStage is the sole transform writer: uniform scale, optionally preceded
// by rotate(-90deg). Read that actual producer, never infer it from viewport
// shape (compact portrait remains upright).
function gridRotated(element: Element | null): boolean {
  return element?.closest<HTMLElement>(".hardware-workspace")
    ?.style.transform.includes("rotate(-90deg)") ?? false;
}

function gridRectOf(element: Element | null): GridRect {
  const rect = element?.getBoundingClientRect();
  const rotated = gridRotated(element);
  const rowStarts = element?.classList.contains("sequence-grid-body")
    ? Array.from(element.querySelectorAll(".sequence-grid-row"), (row) => {
        const bounds = row.getBoundingClientRect();
        return rotated ? bounds.left : bounds.top;
      }) : [];
  return {
    element,
    left: rect?.left ?? 0,
    top: rect?.top ?? 0,
    width: rect?.width ?? 0,
    height: rect?.height ?? 0,
    rotated,
    layoutWidth: (element as HTMLElement | null)?.offsetWidth ||
      (rotated ? rect?.height : rect?.width) || 0,
    layoutHeight: (element as HTMLElement | null)?.offsetHeight ||
      (rotated ? rect?.width : rect?.height) || 0,
    // Actual row starts include CSS gaps/padding. Hidden or synthetic zero
    // rectangles have no usable row geometry; retain the uniform fallback.
    rowStarts: rowStarts.length === SEQUENCE_BANK_PADS && rowStarts.every(
      (start, index) => index === 0 || start > rowStarts[index - 1]!,
    ) ? rowStarts : null,
  };
}

function gridPoint(rect: GridRect, clientX: number, clientY: number) {
  return rect.rotated ? {
    x: rect.height <= 0 ? 0 : (rect.top + rect.height - clientY) / rect.height,
    y: rect.width <= 0 ? 0.5 : (clientX - rect.left) / rect.width,
  } : {
    x: rect.width <= 0 ? 0 : (clientX - rect.left) / rect.width,
    y: rect.height <= 0 ? 0.5 : (clientY - rect.top) / rect.height,
  };
}

function tickAtPoint(rect: GridRect, clientX: number, clientY: number, lengthTicks: number) {
  return gridPoint(rect, clientX, clientY).x * lengthTicks;
}

function padAtPoint(rect: GridRect, clientX: number, clientY: number): number {
  if (rect.rowStarts !== null) {
    const axis = rect.rotated ? clientX : clientY;
    const next = rect.rowStarts.findIndex((start) => start > axis);
    return next < 0 ? SEQUENCE_BANK_PADS - 1 : Math.max(0, next - 1);
  }
  if (rect.width <= 0 || rect.height <= 0) return 0;
  return Math.max(0, Math.min(
    Math.floor(gridPoint(rect, clientX, clientY).y * SEQUENCE_BANK_PADS),
    SEQUENCE_BANK_PADS - 1,
  ));
}

function velocityAtPoint(rect: GridRect, clientX: number, clientY: number): number {
  const fraction = Math.max(0, Math.min(gridPoint(rect, clientX, clientY).y, 1));
  return Math.round((1 - fraction) * 126) + 1;
}

function gridRectUnchanged(rect: GridRect): boolean {
  const now = rect.element?.getBoundingClientRect();
  return now !== undefined && gridRotated(rect.element) === rect.rotated &&
    now.left === rect.left && now.top === rect.top &&
    now.width === rect.width && now.height === rect.height;
}

function selectionBoxStyle(gesture: Extract<GridGesture, {kind: "box"}>) {
  const from = gridPoint(gesture.bodyRect, gesture.originX, gesture.originY);
  const to = gridPoint(gesture.bodyRect, gesture.currentX, gesture.currentY);
  return {
    left: Math.min(from.x, to.x) * gesture.bodyRect.layoutWidth,
    top: Math.min(from.y, to.y) * gesture.bodyRect.layoutHeight,
    width: Math.abs(from.x - to.x) * gesture.bodyRect.layoutWidth,
    height: Math.abs(from.y - to.y) * gesture.bodyRect.layoutHeight,
  };
}

// Decorative cells follow the live snap/Pattern, never prototype event data.
// Keep their potentially large subtree out of each pointer-preview render.
const GridCells = memo(function GridCells({columns}: {columns: number}) {
  return columns === 0 ? null : <div className="sequence-grid-cells" aria-hidden="true"
    style={{gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`}}>
    {Array.from({length: columns}, (_, index) => <span key={index} />)}
  </div>;
});

function keyOf(bank: Bank, note: SequenceGridNote): SequenceGridEventKey {
  return {bank, pad: note.pad, onsetTick: note.onsetTick};
}

// The edit a gesture would commit if it ended now; the drag preview and the
// gesture-end command run through the same mapping so they can never differ.
function gestureEdit(
  gesture: GridGesture,
  model: SequenceGridModel,
  bank: Bank,
  defaultVelocity: number,
): SequenceGridEdit | null {
  const lengthTicks = model.lengthTicks;
  const snapTicks = model.snapTicks;
  switch (gesture.kind) {
    case "add":
      return sequenceGridAddNote({
        bank, pad: gesture.pad, tick: gesture.tick, snapTicks,
        velocity: defaultVelocity, lengthTicks,
      });
    case "press":
      return sequenceGridRemoveNote(keyOf(bank, gesture.note));
    case "move":
      return gesture.notes.length === 1
        ? sequenceGridMoveNote({
            bank, note: gesture.notes[0]!,
            toPad: gesture.originPad + gesture.deltaPads,
            toTick: gesture.originTick + gesture.deltaTicks,
            snapTicks, lengthTicks,
          })
        : sequenceGridBatchMove({
            bank, notes: gesture.notes,
            deltaTicks: gesture.deltaTicks, deltaPads: gesture.deltaPads,
            snapTicks, lengthTicks,
          });
    case "resize":
      return sequenceGridResizeNote({
        bank, note: gesture.note, toEndTick: gesture.endTick,
        snapTicks, lengthTicks,
      });
    case "velocity":
      return sequenceGridVelocityNote({
        bank, note: gesture.note, velocity: gesture.velocity,
      });
    case "box":
      return null;
  }
}

// The Sequence Pattern grid edits Project Truth one gesture at a time: a tap
// on an empty cell adds a note, a tap on a note removes it, a body drag moves
// (the whole selection when the dragged note is selected), an end drag
// resizes, a vertical drag in VEL mode sets velocity, and a drag on empty
// space box-selects. Rows are the active Bank's sixteen Pads; the horizontal
// axis is the whole Pattern under a scroll port.
export function SequenceGrid(props: SequenceGridProps) {
  const {pattern, bank, snap, editMode, editing, selection} = props;
  const model = createSequenceGridModel(pattern, bank, snap);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [visibleRange, setVisibleRange] = useState({startTick: 0, endTick: model.lengthTicks / model.bars});
  const [panel, setPanel] = useState<"bars" | "tools" | null>(null);
  const panelTrigger = useRef<HTMLButtonElement | null>(null);
  const scrollCommand = useRef<(value: number, absolute?: boolean) => void>(() => {});
  const reportedRef = useRef<SequenceGridViewport | null>(null);
  const [gesture, setGesture] = useState<GridGesture | null>(null);
  const gestureRef = useRef<GridGesture | null>(null);
  gestureRef.current = gesture;
  const latestRef = useRef(props);
  latestRef.current = props;
  const modelRef = useRef(model);
  modelRef.current = model;
  // A gesture's notes and pads come from the Bank it was drawn on; a Bank
  // switch mid-gesture cancels it rather than naming the new Bank's keys.
  // React runs this effect before it dispatches the next pointer event.
  useEffect(() => {
    setGesture(null);
  }, [bank]);
  const onViewportChange = props.onViewportChange;
  useEffect(() => {
    const report = () => {
      const scroller = scrollRef.current;
      const lane = scroller?.querySelector<HTMLElement>(".sequence-grid-lane") ?? null;
      if (scroller === null || lane === null) return;
      // Use the same unscaled layout coordinates as scrollLeft/ENC1. Rounded
      // transformed DOMRects can put an aligned boundary one tick into the
      // next bar. The fixed Pad column is outside this one-bar lane window.
      const window_ = scroller.getBoundingClientRect();
      const laneRect = lane.getBoundingClientRect();
      const viewport = sequenceGridViewportForWindow(lane.clientWidth > 0 ? {
        windowStart: scroller.scrollLeft,
        windowEnd: scroller.scrollLeft + lane.clientWidth / model.bars,
        timelineStart: 0,
        timelineWidth: lane.clientWidth,
        lengthTicks: model.lengthTicks,
      } : {
        windowStart: Math.max(window_.left, window_.right - laneRect.width / model.bars),
        windowEnd: window_.right,
        timelineStart: laneRect.left,
        timelineWidth: laneRect.width,
        lengthTicks: model.lengthTicks,
      });
      if (laneRect.width > 0) setVisibleRange((previous) =>
        previous.startTick === viewport.startTick && previous.endTick === viewport.endTick
          ? previous : viewport);
      const last = reportedRef.current;
      if (last !== null && last.startTick === viewport.startTick &&
          last.endTick === viewport.endTick) {
        return;
      }
      reportedRef.current = viewport;
      onViewportChange(viewport);
    };
    report();
    const scroller = scrollRef.current;
    scroller?.addEventListener("scroll", report);
    scrollCommand.current = (bars, absolute = false) => {
      const lane = scroller?.querySelector<HTMLElement>(".sequence-grid-lane");
      if (scroller === null || lane == null || gestureRef.current !== null) return;
      // scrollLeft uses layout pixels; DOM rectangles also contain the
      // responsive console's CSS scale and would under-scroll a bar.
      const barWidth = lane.clientWidth / model.bars;
      scroller.scrollLeft = Math.max(0, Math.min(scroller.scrollWidth - scroller.clientWidth,
        (absolute ? 0 : scroller.scrollLeft) + bars * barWidth));
      report();
    };
    props.onScrollReady?.((bars) => scrollCommand.current(bars));
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(report);
    if (scroller !== null) observer?.observe(scroller);
    return () => {
      observer?.disconnect();
      scrollCommand.current = () => {};
      scroller?.removeEventListener("scroll", report);
      props.onScrollReady?.(null);
    };
  }, [model.lengthTicks, model.bars, onViewportChange, props.onScrollReady]);

  const finishGesture = (pointerId: number, cancelled: boolean) => {
    const current = gestureRef.current;
    if (current === null || current.pointerId !== pointerId) return;
    setGesture(null);
    if (cancelled || !gridRectUnchanged(current.laneRect)) return;
    const currentProps = latestRef.current;
    const currentModel = modelRef.current;
    if (current.kind === "box") {
      const notes = sequenceGridNotesInBox({
        notes: currentModel.rows.flatMap((row) => row.notes),
        fromPad: current.fromPad,
        toPad: padAtPoint(current.bodyRect, current.currentX, current.currentY),
        fromTick: current.fromTick,
        toTick: tickAtPoint(current.laneRect, current.currentX, current.currentY, currentModel.lengthTicks),
      });
      currentProps.onSelectionChange(notes.map((note) => keyOf(bank, note)));
      return;
    }
    // In VEL mode a moveless press is no edit at all; in NOTE mode it removes.
    if (current.kind === "press" && currentProps.editMode === "vel") return;
    const edit = gestureEdit(current, currentModel, bank, currentProps.defaultVelocity);
    if (edit === null) return;
    if (current.kind === "press") {
      const removed = keyOf(bank, current.note);
      if (currentProps.selection.some((key) => sameSequenceGridKey(key, removed))) {
        currentProps.onSelectionChange(
          currentProps.selection.filter((key) => !sameSequenceGridKey(key, removed)));
      }
    }
    if (current.kind === "add" && currentProps.selection.length > 0) {
      currentProps.onSelectionChange([]);
    }
    if (current.kind === "velocity") {
      currentProps.onVelocityChange(current.velocity);
    }
    currentProps.onEdit(edit);
  };
  const finishGestureRef = useRef(finishGesture);
  finishGestureRef.current = finishGesture;
  useEffect(() => {
    const finish = (event: PointerEvent) => {
      finishGestureRef.current(event.pointerId, false);
    };
    const cancel = (event: PointerEvent) => {
      finishGestureRef.current(event.pointerId, true);
    };
    const resize = () => setGesture(null);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("resize", resize);
    };
  }, []);

  const capturePointer = (event: React.PointerEvent<HTMLElement>) => {
    if (typeof event.currentTarget.setPointerCapture === "function") {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // The window-level release listener remains authoritative fallback.
      }
    }
  };

  const lanePointerDown = (pad: number) => (event: React.PointerEvent<HTMLElement>) => {
    if (!editing.enabled || editMode !== "note" || event.button !== 0 ||
        gestureRef.current !== null) {
      return;
    }
    event.preventDefault();
    capturePointer(event);
    const laneRect = gridRectOf(event.currentTarget);
    setGesture({
      kind: "add",
      pointerId: event.pointerId,
      originX: event.clientX,
      originY: event.clientY,
      pad,
      tick: tickAtPoint(laneRect, event.clientX, event.clientY, model.lengthTicks),
      laneRect,
      bodyRect: gridRectOf(event.currentTarget.closest(".sequence-grid-body")),
    });
  };

  const notePointerDown = (
    note: SequenceGridNote,
    zone: "body" | "end",
  ) => (event: React.PointerEvent<HTMLElement>) => {
    if (!editing.enabled || event.button !== 0 || gestureRef.current !== null) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    capturePointer(event);
    const laneRect = gridRectOf(event.currentTarget.closest(".sequence-grid-lane"));
    const bodyRect = gridRectOf(event.currentTarget.closest(".sequence-grid-body"));
    setGesture({
      kind: "press",
      pointerId: event.pointerId,
      originX: event.clientX,
      originY: event.clientY,
      note,
      zone,
      originTick: note.onsetTick,
      pressPad: padAtPoint(bodyRect, event.clientX, event.clientY),
      pressTick: tickAtPoint(laneRect, event.clientX, event.clientY, model.lengthTicks),
      laneRect,
      bodyRect,
    });
  };

  const bodyPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const current = gestureRef.current;
    if (current === null || current.pointerId !== event.pointerId) return;
    if (!gridRectUnchanged(current.laneRect)) {
      setGesture(null);
      return;
    }
    const lengthTicks = modelRef.current.lengthTicks;
    if (current.kind === "add" || current.kind === "press") {
      const distance = Math.hypot(
        event.clientX - current.originX, event.clientY - current.originY);
      if (distance < DRAG_THRESHOLD_PX) return;
      if (current.kind === "add") {
        setGesture({
          ...current,
          kind: "box",
          currentX: event.clientX,
          currentY: event.clientY,
          fromPad: current.pad,
          fromTick: current.tick,
        });
        return;
      }
      if (current.zone === "end" && latestRef.current.editMode === "note") {
        setGesture({
          kind: "resize",
          pointerId: current.pointerId,
          originX: current.originX,
          originY: current.originY,
          note: current.note,
          endTick: tickAtPoint(current.laneRect, event.clientX, event.clientY, lengthTicks),
          laneRect: current.laneRect,
        });
        return;
      }
      if (latestRef.current.editMode === "vel") {
        setGesture({
          kind: "velocity",
          pointerId: current.pointerId,
          originX: current.originX,
          originY: current.originY,
          note: current.note,
          velocity: velocityAtPoint(current.laneRect, event.clientX, event.clientY),
          laneRect: current.laneRect,
        });
        return;
      }
      const pressed = keyOf(bank, current.note);
      const currentSelection = latestRef.current.selection;
      const batch = currentSelection.length > 1 &&
        currentSelection.some((key) => sameSequenceGridKey(key, pressed));
      const notes = batch
        ? modelRef.current.rows.flatMap((row) => row.notes)
            .filter((note) => currentSelection.some(
              (key) => sameSequenceGridKey(key, keyOf(bank, note))))
        : [current.note];
      setGesture({
        kind: "move",
        pointerId: current.pointerId,
        originX: current.originX,
        originY: current.originY,
        notes,
        originPad: current.note.pad,
        originTick: current.originTick,
        pressPad: current.pressPad,
        pressTick: current.pressTick,
        deltaPads: padAtPoint(current.bodyRect, event.clientX, event.clientY) - current.pressPad,
        deltaTicks: tickAtPoint(current.laneRect, event.clientX, event.clientY, lengthTicks) -
          current.pressTick,
        laneRect: current.laneRect,
        bodyRect: current.bodyRect,
      });
      return;
    }
    if (current.kind === "box") {
      setGesture({...current, currentX: event.clientX, currentY: event.clientY});
      return;
    }
    if (current.kind === "move") {
      const deltaTicks =
        tickAtPoint(current.laneRect, event.clientX, event.clientY, lengthTicks) - current.pressTick;
      const deltaPads =
        padAtPoint(current.bodyRect, event.clientX, event.clientY) - current.pressPad;
      if (deltaTicks === current.deltaTicks && deltaPads === current.deltaPads) return;
      setGesture({...current, deltaTicks, deltaPads});
      return;
    }
    if (current.kind === "resize") {
      setGesture({
        ...current,
        endTick: tickAtPoint(current.laneRect, event.clientX, event.clientY, lengthTicks),
      });
      return;
    }
    const velocity = velocityAtPoint(current.laneRect, event.clientX, event.clientY);
    if (velocity !== current.velocity) setGesture({...current, velocity});
  };

  const bodyPointerUp = (event: React.PointerEvent<HTMLElement>) => {
    finishGesture(event.pointerId, false);
  };

  const previewEdit = gesture === null || gesture.kind === "add" ||
      gesture.kind === "press" || gesture.kind === "box"
    ? null
    : gestureEdit(gesture, model, bank, props.defaultVelocity);
  interface DisplayNote extends SequenceGridNote {readonly preview: boolean}
  const displayRows: {pad: number; notes: DisplayNote[]}[] = model.rows.map((row) => ({
    pad: row.pad,
    notes: row.notes.map((note) => ({...note, preview: false})),
  }));
  if (previewEdit !== null) {
    const replaced = (note: DisplayNote) =>
      previewEdit.remove.some((key) => sameSequenceGridKey(key, keyOf(bank, note))) ||
      previewEdit.put.some((event) => sameSequenceGridKey(event, keyOf(bank, note)));
    for (const row of displayRows) {
      row.notes = row.notes.filter((note) => !replaced(note));
    }
    for (const event of previewEdit.put) {
      displayRows[event.pad]?.notes.push({
        pad: event.pad,
        onsetTick: event.onsetTick,
        durationTick: event.durationTick,
        velocity: event.velocity,
        preview: true,
      });
    }
  }

  const deleteSelection = () => {
    const edit = sequenceGridBatchDelete(
      selection.filter((key) => key.bank === bank));
    props.onSelectionChange([]);
    if (edit !== null) props.onEdit(edit);
  };

  const columnPercent = model.columnCount === 0
    ? null
    : 100 / model.columnCount;
  const barPercent = 100 / model.bars;
  const ticksPerBar = model.lengthTicks / model.bars;
  const firstBar = Math.min(model.bars, Math.floor(visibleRange.startTick / ticksPerBar + 1e-6) + 1);
  const lastBar = Math.min(model.bars, Math.max(firstBar, Math.ceil(visibleRange.endTick / ticksPerBar - 1e-6)));
  return (
    <section className="sequence-grid" aria-label="Sequence grid"
      data-testid="sequence-grid"
      {...(editing.enabled ? {} : {"data-editing-disabled": "true"})}>
      <div className="sequence-grid-navigation" role="group" aria-label="Bar navigation">
        <button type="button" className="touch-control" aria-label="Previous bar"
          disabled={gesture !== null || visibleRange.startTick <= 0}
          onClick={() => scrollCommand.current(-1)}>‹</button>
        <button type="button" className="touch-control" aria-label="Choose bar"
          aria-haspopup="dialog" disabled={gesture !== null}
          onClick={(event) => { panelTrigger.current = event.currentTarget; setPanel("bars"); }}>
          BAR {firstBar === lastBar ? String(firstBar).padStart(2, "0")
            : `${String(firstBar).padStart(2, "0")}–${String(lastBar).padStart(2, "0")}`} / {String(model.bars).padStart(2, "0")}
        </button>
        <button type="button" className="touch-control" aria-label="Next bar"
          disabled={gesture !== null || visibleRange.endTick >= model.lengthTicks}
          onClick={() => scrollCommand.current(1)}>›</button>
        <button type="button" className="touch-control" aria-label="Grid tools"
          aria-haspopup="dialog" disabled={gesture !== null}
          onClick={(event) => { panelTrigger.current = event.currentTarget; setPanel("tools"); }}>
          Tools
        </button>
      </div>
      {panel === null ? null : <ModalDialog returnFocus={panelTrigger.current}
        onCancel={() => setPanel(null)} dialogClassName={panel === "tools"
          ? "sequence-picker-dialog sequence-grid-tools-dialog" : "sequence-picker-dialog"}
        label={panel === "bars" ? "Choose bar" : "Grid tools"}>
        {panel === "bars" ? <h2>CHOOSE BAR</h2> : (
          <header className="sequence-grid-tools-heading">
            <h2>GRID TOOLS</h2>
            <span>EDIT VIEW</span>
          </header>
        )}
        {panel === "bars" ? <div className="sequence-bar-options">
          {Array.from({length: model.bars}, (_, index) => <button key={index}
            type="button" className="touch-control" aria-label={`Bar ${index + 1}`}
            aria-pressed={firstBar === index + 1}
            onClick={() => { scrollCommand.current(index, true); setPanel(null); }}>{index + 1}</button>)}
        </div> : (
      <div className="sequence-grid-tools-controls">
        <h3>EDIT MODE</h3>
        <div className="sequence-grid-tools-mode" role="group" aria-label="Edit mode">
          <button
            type="button"
            className="touch-control"
            aria-pressed={editMode === "note"}
            aria-label="Note mode"
            onClick={() => props.onEditModeChange("note")}
          >
            NOTE
          </button>
          <button
            type="button"
            className="touch-control"
            aria-pressed={editMode === "vel"}
            aria-label="Velocity mode"
            onClick={() => props.onEditModeChange("vel")}
          >
            VEL
          </button>
        </div>
        <h3>GRID SNAP</h3>
        <div className="sequence-grid-tools-snap" role="group" aria-label="Snap">
          {SEQUENCE_GRID_SNAPS.map((option) => (
            <button
              key={option}
              type="button"
              className="touch-control"
              aria-pressed={snap === option}
              aria-label={`Snap ${option}`}
              onClick={() => props.onSnapChange(option)}
            >
              {option === "off" ? "Off" : option}
            </button>
          ))}
        </div>
        <p className="sequence-grid-tools-help">
          NOTE: tap a note to delete. VEL: drag to edit velocity.
        </p>
      </div>
        )}
        <button type="button" className={panel === "tools"
          ? "touch-control is-primary" : "touch-control"}
          onClick={() => setPanel(null)}>Done</button>
      </ModalDialog>}
      {editing.enabled || editing.reason === null ? null : (
        <p className="sequence-grid-reason" role="status">{editing.reason}</p>
      )}
      <div className="sequence-grid-scroll" ref={scrollRef}>
        <div className="sequence-grid-body"
          // One bar fills the visible lane width (2026-10-04 decision, item 7);
          // the Pad column and its gap (styles.css) stay outside it.
          style={{
            width: `calc(${model.bars} * (100% - var(--sequence-grid-pad-column) - ` +
              `var(--sequence-grid-pad-gap)) + var(--sequence-grid-pad-column) + ` +
              `var(--sequence-grid-pad-gap))`,
            minWidth: "100%",
          }}
          onPointerMove={bodyPointerMove}
          onPointerUp={bodyPointerUp}
        >
          {displayRows.map((row) => (
            // The row carries the Pad colour; its label and notes inherit it.
            <div className="sequence-grid-row" data-pad={row.pad} key={row.pad}
              data-current-pad={props.currentPad === bank * 16 + row.pad ? "true" : undefined}
              data-pad-colour={padColourAttribute(props.padColour?.(bank * 16 + row.pad) ?? null)}>
              <span className="sequence-grid-pad">{slotAddress(bank * 16 + row.pad)}</span>
              <div
                className="sequence-grid-lane"
                onPointerDown={lanePointerDown(row.pad)}
                style={{
                  backgroundImage: columnPercent === null
                    ? `repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), rgb(173 182 170 / 45%) calc(${barPercent}% - 1px), rgb(173 182 170 / 45%) ${barPercent}%)`
                    : `repeating-linear-gradient(to right, transparent 0, transparent calc(${columnPercent}% - 1px), rgb(80 88 79 / 70%) calc(${columnPercent}% - 1px), rgb(80 88 79 / 70%) ${columnPercent}%), repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), rgb(173 182 170 / 45%) calc(${barPercent}% - 1px), rgb(173 182 170 / 45%) ${barPercent}%)`,
                }}
              >
                <GridCells columns={model.columnCount} />
                {row.notes.map((note, index) => (
                  <div
                    className={`sequence-grid-note${
                      note.preview ? " sequence-grid-note-preview" : ""
                    }${
                      selection.some((key) => sameSequenceGridKey(key, keyOf(bank, note)))
                        ? " sequence-grid-note-selected"
                        : ""
                    }`}
                    data-testid="sequence-grid-note"
                    data-onset-tick={note.onsetTick}
                    data-duration-tick={note.durationTick}
                    data-velocity={note.velocity}
                    {...(note.preview ? {"data-preview": "true"} : {})}
                    role="img"
                    aria-label={`Pad ${slotAddress(bank * 16 + note.pad)} note · onset ${note.onsetTick} · length ${note.durationTick} · velocity ${note.velocity}`}
                    key={`${note.onsetTick}:${index}`}
                    {...(note.preview ? {} : {onPointerDown: notePointerDown(note, "body")})}
                    style={{
                      left: `${note.onsetTick / model.lengthTicks * 100}%`,
                      width: `${note.durationTick / model.lengthTicks * 100}%`,
                      opacity: 0.45 + note.velocity / 127 * 0.55,
                    }}
                  >
                    {note.preview ? null : (
                      <div
                        className="sequence-grid-note-end"
                        data-testid="sequence-grid-note-end"
                        aria-hidden="true"
                        {...(editMode === "note"
                          ? {onPointerDown: notePointerDown(note, "end")}
                          : {})}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
          {gesture?.kind === "box" ? (
            <div
              className="sequence-grid-box"
              data-testid="sequence-grid-box"
              style={selectionBoxStyle(gesture)}
            />
          ) : null}
        </div>
      </div>
      <p className="sequence-grid-help" data-testid="sequence-grid-help">
        {editMode.toUpperCase()} · {snap === "off" ? "FREE" : `${snap} SNAP`} · {editMode === "vel"
          ? "Drag a note to edit velocity" : "Tap empty space to add"}
      </p>
      {selection.length === 0 ? null : (
        <div className="sequence-grid-batch" role="group" aria-label="Note selection">
          <span>{selection.length} selected</span>
          <button type="button" disabled={!editing.enabled} onClick={deleteSelection}>
            Delete
          </button>
          <button type="button" onClick={() => props.onSelectionChange([])}>
            Clear
          </button>
        </div>
      )}
    </section>
  );
}
