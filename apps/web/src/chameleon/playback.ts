import type { Patch } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import type { ChameleonPlaybackRole } from "./model";

const SUPPORTED_ROLES = new Set([
  "drums",
  "bass",
  "harmony",
  "lead",
  "loop",
  "action",
]);

/**
 * Maps real active element IDs onto the public Pad role shown by the Chameleon.
 *
 * `lmdj.patch.v1` carries `role` on `elements[]`, not on `pads[]`, so a Pad's
 * role is resolved through the elements it actually triggers. Only public Patch
 * fields are read — never Material, stem, lane, or MIDI files.
 */
export function activePlaybackRole(
  patch: Patch,
  activeElementIds: ReadonlySet<string>,
): ChameleonPlaybackRole {
  const roleByElement = new Map(
    patch.elements.map((element) => [element.element_id, element.role]),
  );
  const roles = new Set<string>();
  for (const pad of patch.pads) {
    for (const elementId of padElementIds(pad)) {
      if (!activeElementIds.has(elementId)) continue;
      const role = roleByElement.get(elementId);
      if (typeof role === "string" && SUPPORTED_ROLES.has(role)) {
        roles.add(role);
      }
    }
  }
  if (roles.size === 0) return null;
  if (roles.size > 1) return "mixed";
  return [...roles][0] as Exclude<ChameleonPlaybackRole, null | "mixed">;
}
