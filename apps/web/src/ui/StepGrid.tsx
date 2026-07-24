import { useEffect, useMemo, useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, scenePatterns, type PatchBundle } from "../patch/loader";

/** pad 0-3 的语义槽 → 步进格 LED 的 lane 配色（与 PadMatrix16 角色色对齐） */
const PAD_LANE_CLASS = ["step-row-drums", "step-row-bass", "step-row-harmony", "step-row-lead"];

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

  return (
    <div className="step-grid" data-testid="step-grid">
      <table>
        <tbody>
          {rows.map(({ element, steps }) => (
            <tr
              key={element.element_id}
              data-testid={`step-row-${element.element_id}`}
              className={`${laneClass(element.element_id)}${
                bundle.missingElementIds.has(element.element_id) ? " step-missing" : ""
              }`}
            >
              <th>{element.name}</th>
              {Array.from({ length: pattern.length_steps }, (_, step) => {
                const on = steps.has(step);
                return (
                  <td
                    key={step}
                    className={`${on ? "step-on" : ""}${
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
