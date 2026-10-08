import type {
  PadCategory,
  PadColour,
  ProjectPadView,
  ProjectView,
} from "../runtime/runtime_types";

// The five Pad colours of the 2026-10-07 decision, in the Contract's stable
// palette index order (lmdj.project.v5 5.3.0). The hex values live once, in
// styles.css, keyed by `data-pad-colour`; this table names them.
export const PAD_PALETTE: readonly Readonly<{
  index: PadColour;
  category: PadCategory;
  label: string;
}>[] = Object.freeze([
  Object.freeze({index: 0, category: "drums", label: "DRUMS"}),
  Object.freeze({index: 1, category: "bass", label: "BASS"}),
  Object.freeze({index: 2, category: "melodic", label: "MELODIC"}),
  Object.freeze({index: 3, category: "vocal", label: "VOCAL"}),
  Object.freeze({index: 4, category: "texture", label: "TEXTURE"}),
] as const);

// The colour every surface draws for one Pad: exactly the effective index the
// Project inspection carries. Core resolves override → category → neutral;
// the Creator never recomputes that rule, so a missing Pad is neutral.
export function padColourOf(
  project: Pick<ProjectView, "pads"> | null | undefined,
  slot: number,
): PadColour | null {
  const pad: ProjectPadView | undefined = project?.pads[slot]?.slot === slot
    ? project.pads[slot]
    : project?.pads.find((candidate) => candidate.slot === slot);
  return pad?.colour ?? null;
}

// The `data-pad-colour` value the stylesheet keys on: a palette index, or
// "neutral" for the D02 EMPTY grey outline.
export function padColourAttribute(colour: PadColour | null): string {
  return colour === null ? "neutral" : String(colour);
}

export function padCategoryLabel(category: PadCategory | null): string | null {
  return PAD_PALETTE.find((entry) => entry.category === category)?.label ?? null;
}
