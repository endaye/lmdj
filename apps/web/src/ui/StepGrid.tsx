import { useEffect, useMemo, useRef } from "react";
import {
  padElementIds,
  scenePatterns,
  type Note,
  type PatchBundle,
  type PatchElement,
} from "../patch/loader";

const STEPS_PER_BEAT = 4;
const STEPS_PER_BAR = 16;

export interface TimelineCell {
  active: boolean;
  start: boolean;
  end: boolean;
  durationSteps: number;
}

function explicitDuration(note: Note): number | null {
  const value = note.duration_steps;
  return typeof value === "number" && Number.isInteger(value) && value > 0
    ? value
    : null;
}

export function buildTimelineCells(
  notes: readonly Note[],
  lengthSteps: number,
  loops: boolean,
): TimelineCell[] {
  const cells = Array.from({ length: lengthSteps }, (): TimelineCell => ({
    active: false,
    start: false,
    end: false,
    durationSteps: 0,
  }));
  const notesByStep = new Map<number, Note[]>();

  for (const note of notes) {
    if (note.step < 0 || note.step >= lengthSteps) continue;
    const atStep = notesByStep.get(note.step) ?? [];
    atStep.push(note);
    notesByStep.set(note.step, atStep);
  }

  const starts = [...notesByStep.keys()].sort((left, right) => left - right);
  starts.forEach((start, index) => {
    const explicit = Math.max(
      0,
      ...(notesByStep.get(start) ?? []).map((note) => explicitDuration(note) ?? 0),
    );
    const nextStart = starts[index + 1] ?? lengthSteps;
    const requestedDuration = explicit || (loops ? nextStart - start : 1);
    const durationSteps = Math.max(1, Math.min(requestedDuration, lengthSteps - start));

    for (let offset = 0; offset < durationSteps; offset += 1) {
      const cell = cells[start + offset];
      cell.active = true;
      cell.start ||= offset === 0;
      cell.end ||= offset === durationSteps - 1;
      if (offset === 0) cell.durationSteps = durationSteps;
    }
  });

  return cells;
}

function laneClass(element: PatchElement): string {
  const role = element.role?.toLowerCase() ?? "";
  if (role === "drums" || role === "kick") return "step-row-drums";
  if (role === "snare" || role === "bass") return "step-row-bass";
  if (role === "hat" || role === "harmony" || role === "melody") {
    return "step-row-harmony";
  }
  if (
    role === "percussion"
    || role === "lead"
    || role === "vocal"
    || role === "full_mix_phrase"
  ) {
    return "step-row-lead";
  }
  return element.kind === "drum" || element.kind === "one_shot"
    ? "step-row-drums"
    : "step-row-harmony";
}

function boundaryClass(step: number): string {
  if (step > 0 && step % STEPS_PER_BAR === 0) return "step-bar-start";
  if (step > 0 && step % STEPS_PER_BEAT === 0) return "step-beat-start";
  return "";
}

export function StepGrid({
  bundle,
  playheadStep,
}: {
  bundle: PatchBundle<unknown>;
  playheadStep: number | null;
}) {
  const pattern = scenePatterns(bundle.patch)[0]; // scene 契约路径；v1 单 pattern
  const scrollerRef = useRef<HTMLDivElement>(null);

  const loopElementIds = useMemo(() => {
    const ids = new Set<string>();
    for (const pad of bundle.patch.pads) {
      if (pad.behavior.trigger !== "loop") continue;
      for (const id of padElementIds(pad)) ids.add(id);
    }
    return ids;
  }, [bundle.patch]);

  const rows = useMemo(() => {
    const byElement = new Map<string, Note[]>();
    for (const note of pattern.notes) {
      const notes = byElement.get(note.element_id) ?? [];
      notes.push(note);
      byElement.set(note.element_id, notes);
    }
    return bundle.patch.elements
      .filter((element) => byElement.has(element.element_id))
      .map((element) => {
        const loops = loopElementIds.has(element.element_id);
        return {
          element,
          loops,
          cells: buildTimelineCells(
            byElement.get(element.element_id) ?? [],
            pattern.length_steps,
            loops,
          ),
        };
      });
  }, [bundle.patch.elements, loopElementIds, pattern]);

  useEffect(() => {
    if (playheadStep === null) return;
    const scroller = scrollerRef.current;
    const marker = scroller?.querySelector<HTMLElement>(
      `.step-grid__beat-ruler [data-step="${playheadStep}"]`,
    );
    if (!scroller || !marker) return;

    const laneWidth = Number.parseFloat(
      getComputedStyle(scroller).getPropertyValue("--lane-width"),
    ) || 72;
    const left = marker.offsetLeft - scroller.scrollLeft;
    const right = left + marker.offsetWidth;
    const margin = marker.offsetWidth * STEPS_PER_BEAT;
    if (left < laneWidth || right > scroller.clientWidth - margin) {
      const target = Math.max(0, marker.offsetLeft - laneWidth - marker.offsetWidth);
      if (typeof scroller.scrollTo === "function") {
        scroller.scrollTo({ left: target, behavior: "auto" });
      } else {
        scroller.scrollLeft = target;
      }
    }
  }, [playheadStep]);

  const steps = Array.from({ length: pattern.length_steps }, (_, step) => step);
  const bars = Array.from(
    { length: Math.ceil(pattern.length_steps / STEPS_PER_BAR) },
    (_, bar) => ({
      number: bar + 1,
      steps: Math.min(STEPS_PER_BAR, pattern.length_steps - bar * STEPS_PER_BAR),
    }),
  );

  return (
    <div className="pattern-timeline">
      <div className="step-grid" data-testid="step-grid" ref={scrollerRef}>
        <table aria-label={`Pattern ${pattern.name} timeline`}>
          <caption className="step-grid__caption">
            {pattern.name}, {pattern.length_steps} steps at {pattern.resolution}
          </caption>
          <thead>
            <tr className="step-grid__bar-ruler">
              <th className="step-grid__lane-heading" rowSpan={2} scope="col">
                Lane
              </th>
              {bars.map((bar) => (
                <th
                  className="step-grid__bar-label"
                  colSpan={bar.steps}
                  data-testid={`step-bar-${bar.number}`}
                  key={bar.number}
                  scope="colgroup"
                >
                  Bar {bar.number}
                </th>
              ))}
            </tr>
            <tr className="step-grid__beat-ruler">
              {steps.map((step) => {
                const isBeatStart = step % STEPS_PER_BEAT === 0;
                const beat = Math.floor((step % STEPS_PER_BAR) / STEPS_PER_BEAT) + 1;
                const bar = Math.floor(step / STEPS_PER_BAR) + 1;
                return (
                  <th
                    aria-label={`Bar ${bar}, beat ${beat}, step ${step + 1}`}
                    aria-current={step === playheadStep ? "true" : undefined}
                    className={`${boundaryClass(step)}${
                      step === playheadStep ? " step-playhead" : ""
                    }`}
                    data-step={step}
                    key={step}
                    scope="col"
                  >
                    {isBeatStart ? beat : ""}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ element, loops, cells }, rowIndex) => (
              <tr
                key={element.element_id}
                data-testid={`step-row-${element.element_id}`}
                data-lane-index={rowIndex + 1}
                data-duration-mode={loops ? "loop" : "hit"}
                className={`${laneClass(element)}${
                  bundle.missingElementIds.has(element.element_id) ? " step-missing" : ""
                }`}
              >
                <th scope="row">
                  <span className="step-grid__lane-index" aria-hidden="true">
                    {String(rowIndex + 1).padStart(2, "0")}
                  </span>
                  <span className="step-grid__lane-name">{element.name}</span>
                  <small><i aria-hidden="true" />{loops ? "LOOP" : "HIT"}</small>
                </th>
                {cells.map((cell, step) => {
                  const noteState = cell.start
                    ? "start"
                    : cell.end
                      ? "end"
                      : cell.active
                        ? "sustain"
                        : "empty";
                  return (
                    <td
                      aria-current={step === playheadStep ? "true" : undefined}
                      aria-label={
                        cell.start
                          ? `${element.name}, step ${step + 1}, ${cell.durationSteps} step${
                              cell.durationSteps === 1 ? "" : "s"
                            }`
                          : undefined
                      }
                      className={`${boundaryClass(step)}${
                        cell.active ? " note-active" : ""
                      }${cell.start ? " note-start" : ""}${
                        cell.end ? " note-end" : ""
                      }${cell.durationSteps === 1 ? " note-hit" : ""}${
                        step === playheadStep ? " step-playhead" : ""
                      }`}
                      data-note-length={cell.start ? cell.durationSteps : undefined}
                      data-note-state={noteState}
                      data-step={step}
                      key={step}
                    />
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
