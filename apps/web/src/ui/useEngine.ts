import { useEffect, useReducer } from "react";
import type { AudioEngine } from "../engine/AudioEngine";

/** engine emit 时强制重渲 */
export function useEngineTick(engine: AudioEngine): void {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => engine.subscribe(force), [engine]);
}

let singleton: { engine: AudioEngine; decode: (b: ArrayBuffer) => Promise<AudioBuffer> } | null =
  null;

/** 浏览器入口用的单例（测试不走这里，走依赖注入） */
export async function getAudio(): Promise<{
  engine: AudioEngine;
  decode: (b: ArrayBuffer) => Promise<AudioBuffer>;
}> {
  if (!singleton) {
    const { AudioEngine } = await import("../engine/AudioEngine");
    const ctx = new AudioContext();
    singleton = { engine: new AudioEngine(ctx), decode: (b) => ctx.decodeAudioData(b) };
  }
  return singleton;
}
