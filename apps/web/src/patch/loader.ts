import Ajv2020 from "ajv/dist/2020";
import schema from "./schema/lmdj.patch.v1.schema.json";
import type { LmdjPatchV1 } from "./types";

export type Patch = LmdjPatchV1;
export type Pad = Patch["pads"][number];
export type PatchElement = Patch["elements"][number];
export type Pattern = Patch["patterns"][number];
export type Note = Pattern["notes"][number];

export interface PatchBundle<B = AudioBuffer> {
  patch: Patch;
  buffers: Map<string, B>;
  playableElementIds: Set<string>;
  missingElementIds: Set<string>;
  warnings: string[];
}

export class PatchValidationError extends Error {
  constructor(public readonly issues: string[]) {
    super(`patch.json failed lmdj.patch.v1 validation:\n${issues.join("\n")}`);
    this.name = "PatchValidationError";
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validate = ajv.compile(schema as object);

/** scene 契约读取路径的唯一实现：activeScene（v1 = scenes[0]）→ pattern_ids → patterns */
export function scenePatterns(patch: Patch): Pattern[] {
  const scene = patch.scenes[0];
  const byId = new Map(patch.patterns.map((p) => [p.pattern_id, p]));
  return scene.pattern_ids.map((id) => {
    const pattern = byId.get(id);
    if (!pattern) {
      throw new PatchValidationError([
        `scene ${scene.scene_id} references unknown pattern: ${id}`,
      ]);
    }
    return pattern;
  });
}

/** trigger 类 pad 的全组 element id；empty/reserved 返回 [] */
export function padElementIds(pad: Pad): string[] {
  if (pad.action !== "trigger_element" && pad.action !== "trigger_group") return [];
  const ids = (pad.behavior as { element_ids?: unknown }).element_ids;
  if (Array.isArray(ids)) return ids.filter((id): id is string => typeof id === "string");
  return pad.element_id ? [pad.element_id] : [];
}

export async function loadPatch<B>(
  files: Map<string, ArrayBuffer>,
  decodeAudio: (data: ArrayBuffer) => Promise<B>,
): Promise<PatchBundle<B>> {
  const raw = files.get("patch.json");
  if (!raw) throw new PatchValidationError(["patch.json not found in dropped directory"]);

  let data: unknown;
  try {
    data = JSON.parse(new TextDecoder().decode(raw));
  } catch (error) {
    throw new PatchValidationError([`patch.json is not valid JSON: ${String(error)}`]);
  }

  if (!validate(data)) {
    throw new PatchValidationError(
      (validate.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message ?? "invalid"}`),
    );
  }
  const patch = data as Patch;
  scenePatterns(patch); // scene→pattern 引用完整性在加载期 fail-fast

  const buffers = new Map<string, B>();
  const playableElementIds = new Set<string>();
  const missingElementIds = new Set<string>();
  const warnings: string[] = [];

  for (const element of patch.elements) {
    const bytes = files.get(element.source_path);
    if (!bytes) {
      missingElementIds.add(element.element_id);
      warnings.push(`missing sample file: ${element.source_path} (${element.element_id})`);
      continue;
    }
    try {
      buffers.set(element.element_id, await decodeAudio(bytes.slice(0)));
      playableElementIds.add(element.element_id);
    } catch {
      missingElementIds.add(element.element_id);
      warnings.push(`failed to decode: ${element.source_path} (${element.element_id})`);
    }
  }

  return { patch, buffers, playableElementIds, missingElementIds, warnings };
}
