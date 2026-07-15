import { useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, type Pad, type PatchBundle } from "../patch/loader";
import { useEngineTick } from "./useEngine";

export const PAD_KEYS = ["A", "S", "D", "F", "Z", "X", "C", "V"];

/** v1 契约:pad 0-3 是语义槽 drums/bass/harmony/lead —— 决定 pad 的 lane 配色 */
const PAD_LANES = ["drums", "bass", "harmony", "lead"];

type PadState = "normal" | "empty" | "reserved" | "muted" | "error";

function padState(pad: Pad, bundle: PatchBundle<unknown>, engine: AudioEngine): PadState {
  if (pad.action === "empty") return "empty";
  if (pad.action !== "trigger_element" && pad.action !== "trigger_group") return "reserved";
  if (padElementIds(pad).some((id) => bundle.missingElementIds.has(id))) return "error";
  if (engine.isPadMuted(pad.index)) return "muted";
  return "normal";
}

function PadCell({
  pad,
  bundle,
  engine,
}: {
  pad: Pad;
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
}) {
  const [flash, setFlash] = useState(false);
  const state = padState(pad, bundle, engine);
  const interactive = state === "normal" || state === "muted" || state === "error";

  return (
    <button
      data-testid={`pad-${pad.index}`}
      data-lane={PAD_LANES[pad.index]}
      className={`pad pad--${state}${flash ? " pad--flash" : ""}`}
      onClick={() => {
        if (!interactive) return;
        engine.triggerPad(pad.index);
        setFlash(true);
        setTimeout(() => setFlash(false), 120);
      }}
      onContextMenu={(e) => {
        e.preventDefault(); // 契约：右键静音，不弹浏览器菜单
        if (interactive) engine.toggleMutePad(pad.index);
      }}
    >
      <span className="pad-key">{PAD_KEYS[pad.index]}</span>
      <span className="pad-slot">{pad.slot}</span>
      <span className="pad-label">{pad.label}</span>
    </button>
  );
}

export function PadGrid({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  useEngineTick(engine);
  return (
    <div className="pad-grid" data-testid="pad-grid">
      {bundle.patch.pads.map((pad) => (
        <PadCell key={pad.index} pad={pad} bundle={bundle} engine={engine} />
      ))}
    </div>
  );
}
