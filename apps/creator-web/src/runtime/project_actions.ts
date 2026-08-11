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

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function integer(value: unknown, minimum = 0): value is number {
  return Number.isSafeInteger(value) && (value as number) >= minimum;
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
  if (project.contract !== "lmdj.project.v1" ||
      project.project_id !== summary.projectId ||
      !integer(project.revision) ||
      project.revision !== inspected.project_revision ||
      !integer(project.bpm, 40) || project.bpm > 240 ||
      !record(project.assets) || !Array.isArray(project.banks) ||
      project.banks.length !== 4) {
    throw protocolMismatch("Project inspection truth is invalid");
  }

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
