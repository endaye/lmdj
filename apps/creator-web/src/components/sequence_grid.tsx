import {useEffect, useRef, useState} from "react";

import type {Bank} from "../state/creator_state";
import {bankName} from "../state/view_model";
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
  onSnapChange(snap: SequenceGridSnap): void;
  onEditModeChange(mode: SequenceGridEditMode): void;
  onViewportChange(viewport: SequenceGridViewport): void;
  // One gesture ends in one edit; a no-op gesture never reaches this callback.
  onEdit(edit: SequenceGridEdit): void;
  onSelectionChange(selection: readonly SequenceGridEventKey[]): void;
  onVelocityChange(velocity: number): void;
}

interface GridRect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
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

function gridRectOf(element: Element | null): GridRect {
  const rect = element?.getBoundingClientRect();
  return {
    left: rect?.left ?? 0,
    top: rect?.top ?? 0,
    width: rect?.width ?? 0,
    height: rect?.height ?? 0,
  };
}

function tickAtClientX(rect: GridRect, clientX: number, lengthTicks: number): number {
  return rect.width <= 0
    ? 0
    : (clientX - rect.left) / rect.width * lengthTicks;
}

function padAtClientY(rect: GridRect, clientY: number): number {
  if (rect.height <= 0) return 0;
  return Math.max(0, Math.min(
    Math.floor((clientY - rect.top) / rect.height * SEQUENCE_BANK_PADS),
    SEQUENCE_BANK_PADS - 1,
  ));
}

function velocityAtClientY(rect: GridRect, clientY: number): number {
  const fraction = rect.height <= 0
    ? 0.5
    : Math.max(0, Math.min((clientY - rect.top) / rect.height, 1));
  return Math.round((1 - fraction) * 126) + 1;
}

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
      const lane = scroller?.querySelector(".sequence-grid-lane") ?? null;
      if (scroller === null || lane === null) return;
      // The lane is the timeline: the scroll port also holds the Pad label
      // column, so scroller totals would shift the reported window.
      const window_ = scroller.getBoundingClientRect();
      const laneRect = lane.getBoundingClientRect();
      const viewport = sequenceGridViewportForWindow({
        windowStart: window_.left,
        windowEnd: window_.right,
        timelineStart: laneRect.left,
        timelineWidth: laneRect.width,
        lengthTicks: model.lengthTicks,
      });
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
    return () => scroller?.removeEventListener("scroll", report);
  }, [model.lengthTicks, onViewportChange]);

  const finishGesture = (pointerId: number, cancelled: boolean) => {
    const current = gestureRef.current;
    if (current === null || current.pointerId !== pointerId) return;
    setGesture(null);
    if (cancelled) return;
    const currentProps = latestRef.current;
    const currentModel = modelRef.current;
    if (current.kind === "box") {
      const notes = sequenceGridNotesInBox({
        notes: currentModel.rows.flatMap((row) => row.notes),
        fromPad: current.fromPad,
        toPad: padAtClientY(current.bodyRect, current.currentY),
        fromTick: current.fromTick,
        toTick: tickAtClientX(current.laneRect, current.currentX, currentModel.lengthTicks),
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
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", cancel);
    return () => {
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
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
      tick: tickAtClientX(laneRect, event.clientX, model.lengthTicks),
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
      pressPad: padAtClientY(bodyRect, event.clientY),
      pressTick: tickAtClientX(laneRect, event.clientX, model.lengthTicks),
      laneRect,
      bodyRect,
    });
  };

  const bodyPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const current = gestureRef.current;
    if (current === null || current.pointerId !== event.pointerId) return;
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
          endTick: tickAtClientX(current.laneRect, event.clientX, lengthTicks),
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
          velocity: velocityAtClientY(current.laneRect, event.clientY),
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
        deltaPads: padAtClientY(current.bodyRect, event.clientY) - current.pressPad,
        deltaTicks: tickAtClientX(current.laneRect, event.clientX, lengthTicks) -
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
        tickAtClientX(current.laneRect, event.clientX, lengthTicks) - current.pressTick;
      const deltaPads =
        padAtClientY(current.bodyRect, event.clientY) - current.pressPad;
      if (deltaTicks === current.deltaTicks && deltaPads === current.deltaPads) return;
      setGesture({...current, deltaTicks, deltaPads});
      return;
    }
    if (current.kind === "resize") {
      setGesture({
        ...current,
        endTick: tickAtClientX(current.laneRect, event.clientX, lengthTicks),
      });
      return;
    }
    const velocity = velocityAtClientY(current.laneRect, event.clientY);
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
  return (
    <section className="sequence-grid" aria-label="Sequence grid"
      data-testid="sequence-grid"
      {...(editing.enabled ? {} : {"data-editing-disabled": "true"})}>
      <div className="sequence-grid-toolbar">
        <div className="sequence-segment" role="group" aria-label="Snap">
          <span>SNAP</span>
          {SEQUENCE_GRID_SNAPS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={snap === option}
              aria-label={`Snap ${option}`}
              onClick={() => props.onSnapChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <div className="sequence-segment sequence-grid-mode" role="group" aria-label="Edit mode">
          <span>MODE</span>
          <button
            type="button"
            aria-pressed={editMode === "note"}
            aria-label="Note mode"
            onClick={() => props.onEditModeChange("note")}
          >
            NOTE
          </button>
          <button
            type="button"
            aria-pressed={editMode === "vel"}
            aria-label="Velocity mode"
            onClick={() => props.onEditModeChange("vel")}
          >
            VEL
          </button>
        </div>
      </div>
      {editing.enabled || editing.reason === null ? null : (
        <p className="sequence-grid-reason" role="status">{editing.reason}</p>
      )}
      <div className="sequence-grid-scroll" ref={scrollRef}>
        <div className="sequence-grid-body"
          style={{width: `${model.bars * 24}rem`, minWidth: "100%"}}
          onPointerMove={bodyPointerMove}
          onPointerUp={bodyPointerUp}
        >
          {displayRows.map((row) => (
            <div className="sequence-grid-row" data-pad={row.pad} key={row.pad}>
              <span className="sequence-grid-pad">{bankName(bank)}{row.pad + 1}</span>
              <div
                className="sequence-grid-lane"
                onPointerDown={lanePointerDown(row.pad)}
                style={{
                  backgroundImage: columnPercent === null
                    ? `repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), #3a4150 calc(${barPercent}% - 1px), #3a4150 ${barPercent}%)`
                    : `repeating-linear-gradient(to right, transparent 0, transparent calc(${columnPercent}% - 1px), #2c333f calc(${columnPercent}% - 1px), #2c333f ${columnPercent}%), repeating-linear-gradient(to right, transparent 0, transparent calc(${barPercent}% - 1px), #3a4150 calc(${barPercent}% - 1px), #3a4150 ${barPercent}%)`,
                }}
              >
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
                    aria-label={`Pad ${bankName(bank)}${note.pad + 1} note · onset ${note.onsetTick} · length ${note.durationTick} · velocity ${note.velocity}`}
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
              style={{
                left: Math.min(gesture.originX, gesture.currentX) - gesture.bodyRect.left,
                top: Math.min(gesture.originY, gesture.currentY) - gesture.bodyRect.top,
                width: Math.abs(gesture.currentX - gesture.originX),
                height: Math.abs(gesture.currentY - gesture.originY),
              }}
            />
          ) : null}
        </div>
      </div>
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
