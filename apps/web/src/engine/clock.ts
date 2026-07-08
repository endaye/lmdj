import type { Note } from "../patch/loader";

/** 16 分音符时长（秒） */
export function stepDuration(bpm: number): number {
  return 60 / bpm / 4;
}

export interface ScheduledNote {
  note: Note;
  time: number; // 自 transport 起点的秒
}

/** 半开窗口 [from, to) 内应发声的 note，跨 loop 回卷 */
export function notesInWindow(
  notes: readonly Note[],
  lengthSteps: number,
  stepDur: number,
  from: number,
  to: number,
): ScheduledNote[] {
  const loopDur = lengthSteps * stepDur;
  const out: ScheduledNote[] = [];
  const firstLoop = Math.floor(from / loopDur);
  const lastLoop = Math.floor(to / loopDur);
  for (let loop = firstLoop; loop <= lastLoop; loop += 1) {
    for (const note of notes) {
      const time = loop * loopDur + note.step * stepDur;
      if (time >= from && time < to) out.push({ note, time });
    }
  }
  return out.sort((a, b) => a.time - b.time);
}

/** 当前播放头所在 step（回卷到 [0, lengthSteps)） */
export function playheadStep(elapsed: number, lengthSteps: number, stepDur: number): number {
  const loopDur = lengthSteps * stepDur;
  const inLoop = ((elapsed % loopDur) + loopDur) % loopDur;
  return Math.floor(inLoop / stepDur) % lengthSteps;
}
