import { useEffect, useMemo, useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, scenePatterns, type PatchBundle } from "../patch/loader";

/** pad 0-3 的语义槽 → 步进格 LED 的 lane 配色（与 PadMatrix16 角色色对齐） */
const PAD_LANE_CLASS = ["step-row-drums", "step-row-bass", "step-row-harmony", "step-row-lead"];
const STEPS_PER_BEAT = 4;
const STEPS_PER_BAR = 16;

export function StepGrid({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  const pattern = scenePatterns(bundle.patch)[0]; // scene 契约路径；v1 单 pattern
  const [playhead, setPlayhead] = useState<number | null>(null);

  useEffect(() => {
    const id = setInterval(() => setPlayhead(engine.playhead()), 50);
    return () => clearInterval(id);
  }, [engine]);

  // element_id → lane 配色类;由 pad 0-3 的归属决定(数字 lane 字段不带语义)
  const laneClass = useMemo(() => {
    const m = new Map<string, string>();
    for (const pad of bundle.patch.pads) {
      const cls = PAD_LANE_CLASS[pad.index];
      if (cls) for (const id of padElementIds(pad)) m.set(id, cls);
    }
    return (id: string) => m.get(id) ?? "step-row-harmony";
  }, [bundle.patch]);

  const rows = useMemo(() => {
    const byElement = new Map<string, Set<number>>();
    for (const note of pattern.notes) {
      if (!byElement.has(note.element_id)) byElement.set(note.element_id, new Set());
      byElement.get(note.element_id)!.add(note.step);
    }
    return bundle.patch.elements
      .filter((el) => byElement.has(el.element_id))
      .map((el) => ({ element: el, steps: byElement.get(el.element_id)! }));
  }, [bundle.patch, pattern]);
  const steps = Array.from({ length: pattern.length_steps }, (_, step) => step);
  const bars = Array.from(
    { length: Math.ceil(pattern.length_steps / STEPS_PER_BAR) },
    (_, bar) => ({
      number: bar + 1,
      steps: Math.min(STEPS_PER_BAR, pattern.length_steps - bar * STEPS_PER_BAR),
    }),
  );

  return (
    <div className="step-grid" data-testid="step-grid">
      <table aria-label={`Pattern ${pattern.name} step grid`}>
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
                  className={`${step % STEPS_PER_BAR === 0 ? "step-bar-start" : ""}${
                    step % STEPS_PER_BAR !== 0 && isBeatStart ? " step-beat-start" : ""
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
          {rows.map(({ element, steps }) => (
            <tr
              key={element.element_id}
              data-testid={`step-row-${element.element_id}`}
              className={`${laneClass(element.element_id)}${
                bundle.missingElementIds.has(element.element_id) ? " step-missing" : ""
              }`}
            >
              <th scope="row">{element.name}</th>
              {Array.from({ length: pattern.length_steps }, (_, step) => {
                const on = steps.has(step);
                return (
                  <td
                    key={step}
                    data-step={step}
                    className={`${step % STEPS_PER_BAR === 0 ? "step-bar-start " : ""}${
                      step % STEPS_PER_BAR !== 0 && step % STEPS_PER_BEAT === 0
                        ? "step-beat-start "
                        : ""
                    }${on ? "step-on" : ""}${
                      step === playhead ? " step-playhead" : ""
                    }`}
                  >
                    {on ? "█" : "·"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
