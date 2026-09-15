import type {
  CreatorRuntimeSession,
  LocalProjectSummary,
  ProjectPadView,
  ProjectView,
  TransferProgress,
} from "./runtime_types";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PROJECTION_READ_ATTEMPTS = 4;

export interface ProjectActionToken {
  readonly generation: number;
  readonly session: CreatorRuntimeSession;
}

export interface ProjectActionLane {
  claim(session: CreatorRuntimeSession): ProjectActionToken | null;
  owns(
    token: ProjectActionToken,
    session: CreatorRuntimeSession,
  ): boolean;
  finish(token: ProjectActionToken): void;
  invalidate(): void;
  readonly busy: boolean;
}

export function createProjectActionLane(): ProjectActionLane {
  let generation = 0;
  let active: ProjectActionToken | null = null;
  return Object.freeze({
    claim(session: CreatorRuntimeSession) {
      if (active !== null) return null;
      active = Object.freeze({generation: ++generation, session});
      return active;
    },
    owns(token: ProjectActionToken, session: CreatorRuntimeSession) {
      return active === token &&
        token.generation === generation &&
        token.session === session;
    },
    finish(token: ProjectActionToken) {
      if (active === token && token.generation === generation) {
        active = null;
      }
    },
    invalidate() {
      generation += 1;
      active = null;
    },
    get busy() {
      return active !== null;
    },
  });
}

function protocolMismatch(message: string): Error & {code: string} {
  return Object.assign(new Error(message), {code: "HOST_PROTOCOL_MISMATCH"});
}

// The Project Contract levels this acceptance path can interpret, grouped by
// the shape family each is read with. These are the Creator-side copy of the
// level enumeration (#915): never retype them at a call site, because a level
// move must turn a test red before it ships. project_actions_contract.test.ts
// binds both families to the Bundle Contract's declared levels and to the
// level this Build's writer produces.
export const PATTERN_FREE_PROJECT_CONTRACTS: readonly string[] =
  Object.freeze(["lmdj.project.v3"]);
export const PATTERN_SLOT_PROJECT_CONTRACTS: readonly string[] =
  Object.freeze(["lmdj.project.v4", "lmdj.project.v5"]);

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function integer(value: unknown, minimum = 0): value is number {
  return Number.isSafeInteger(value) && (value as number) >= minimum;
}

function patternSlotsFor(
  project: Record<string, unknown>,
): readonly (string | null)[] {
  if (PATTERN_FREE_PROJECT_CONTRACTS.includes(project.contract as string)) {
    if ("pattern_slots" in project || "performances" in project) {
      throw protocolMismatch("Project v3 contains v4 fields");
    }
    return Object.freeze(Array<string | null>(16).fill(null));
  }
  const patterns = project.patterns;
  if (!PATTERN_SLOT_PROJECT_CONTRACTS.includes(project.contract as string) ||
      !Array.isArray(project.pattern_slots) ||
      project.pattern_slots.length !== 16 ||
      !record(patterns)) {
    throw protocolMismatch("Project Pattern slots are invalid");
  }
  const occupied = new Set<string>();
  const slots = Array.from(project.pattern_slots, (value) => {
    if (value === null) return null;
    if (typeof value !== "string" || !UUID_PATTERN.test(value) ||
        occupied.has(value) || !Object.hasOwn(patterns, value)) {
      throw protocolMismatch("Project Pattern slot reference is invalid");
    }
    occupied.add(value);
    return value;
  });
  return Object.freeze(slots);
}

function projectView(
  summary: LocalProjectSummary,
  inspected: unknown,
): ProjectView {
  if (!record(inspected) || !integer(inspected.project_revision) ||
      !record(inspected.project)) {
    throw protocolMismatch("Project inspection response is invalid");
  }
  const project = inspected.project;
  if (project.project_id !== summary.projectId ||
      !integer(project.revision) ||
      project.revision !== inspected.project_revision ||
      !integer(project.bpm, 40) || project.bpm > 240 ||
      !record(project.assets) || !record(project.patterns) ||
      !record(project.sequence_settings) ||
      typeof project.sequence_settings.quantize_enabled !== "boolean" ||
      !integer(project.sequence_settings.swing_percent, 50) ||
      project.sequence_settings.swing_percent > 75 ||
      !Array.isArray(project.banks) ||
      project.banks.length !== 4) {
    throw protocolMismatch("Project inspection truth is invalid");
  }
  const patternSlots = patternSlotsFor(project);

  const pads: ProjectPadView[] = [];
  for (let bankIndex = 0; bankIndex < 4; ++bankIndex) {
    const bank = project.banks[bankIndex];
    if (!record(bank) || bank.bank !== bankIndex ||
        !Array.isArray(bank.pads) || bank.pads.length !== 16) {
      throw protocolMismatch("Project Bank inspection is invalid");
    }
    for (let padIndex = 0; padIndex < 16; ++padIndex) {
      const pad = bank.pads[padIndex];
      if (!record(pad) || pad.pad !== padIndex ||
          !(pad.asset_id === null ||
            (typeof pad.asset_id === "string" &&
             UUID_PATTERN.test(pad.asset_id)))) {
        throw protocolMismatch("Project Pad inspection is invalid");
      }
      pads.push({
        slot: bankIndex * 16 + padIndex,
        assetId: pad.asset_id,
      });
    }
  }
  const assignedPadCount = pads.filter(({assetId}) => assetId !== null).length;
  const patterns = Object.entries(project.patterns).map(([patternId, value]) => {
    if (!UUID_PATTERN.test(patternId) || !record(value) ||
        ![1, 2, 4, 8].includes(value.bars as number)) {
      throw protocolMismatch("Project Pattern inspection is invalid");
    }
    return Object.freeze({
      patternId,
      bars: value.bars as 1 | 2 | 4 | 8,
    });
  }).sort((left, right) => left.patternId.localeCompare(right.patternId));
  if (!patterns.some(({patternId}) => patternId === summary.patternId)) {
    throw protocolMismatch("Selected Project Pattern is unavailable");
  }
  const assetCount = Object.keys(project.assets).length;
  if (assignedPadCount !== summary.assignedPadCount ||
      assetCount !== summary.assetCount) {
    throw protocolMismatch("Project summary does not match Project Truth");
  }
  return Object.freeze({
    ...summary,
    revision: project.revision,
    bpm: project.bpm,
    assetCount,
    assignedPadCount,
    key: "—",
    pads: Object.freeze(pads),
    patterns: Object.freeze(patterns),
    patternSlots,
    sequenceSettings: Object.freeze({
      quantizeEnabled: project.sequence_settings.quantize_enabled,
      swingPercent: project.sequence_settings.swing_percent,
    }),
  });
}

export async function listLocalProjectsJourney(
  session: CreatorRuntimeSession,
): Promise<LocalProjectSummary[]> {
  const projects = [...await session.listLocalProjects()];
  projects.sort((left, right) =>
    left.projectId < right.projectId ? -1 : left.projectId > right.projectId ? 1 : 0,
  );
  return projects;
}

export async function openProjectJourney(
  session: CreatorRuntimeSession,
  summary: LocalProjectSummary,
): Promise<ProjectView> {
  await session.openProject(summary.projectId, summary.patternId);
  const inspected = await session.inspectProject();
  await session.reloadSnapshot(summary.patternId);
  return projectView(summary, inspected);
}

export async function refreshProjectProjectionJourney(
  session: CreatorRuntimeSession,
  identity: Readonly<Pick<LocalProjectSummary, "projectId" | "patternId">>,
): Promise<ProjectView | null> {
  for (let attempt = 0; attempt < PROJECTION_READ_ATTEMPTS; ++attempt) {
    const inspected = await session.inspectProject();
    const projects = await listLocalProjectsJourney(session);
    const summary = projects.find(({projectId, patternId}) =>
      projectId === identity.projectId && patternId === identity.patternId,
    );
    if (summary === undefined) {
      throw Object.assign(new Error("Current Project is not listed"), {
        code: "NOT_FOUND",
      });
    }
    if (!record(inspected) || !integer(inspected.project_revision)) {
      throw protocolMismatch("Project projection inspection revision is invalid");
    }
    if (summary.revision !== inspected.project_revision) continue;
    return projectView(summary, inspected);
  }
  return null;
}

export async function importProjectJourney(
  session: CreatorRuntimeSession,
  file: File,
  signal: AbortSignal,
  progress: (value: TransferProgress) => void,
): Promise<ProjectView> {
  const summary = await session.importProject(file, {
    signal,
    onProgress: progress,
  });
  return openProjectJourney(session, summary);
}
