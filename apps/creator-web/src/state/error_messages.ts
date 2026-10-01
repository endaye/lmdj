// The user-language catalogue for Creator errors (#1680). Each public error
// code maps to what happened, in the user's terms, and what to do next.
// Codes, storage conditions and resource tokens never appear here; they go
// to Developer diagnostics, which is where support and automation read them.

export interface UserMessage {
  readonly message: string;
  readonly nextStep: string;
}

type Details = Readonly<Record<string, unknown>>;

const PROJECT_BUSY: UserMessage = Object.freeze({
  message: "The local Project is busy in another tab or process.",
  nextStep: "Choose Continue here to move it to this tab, or close it there and choose Retry project.",
});

const STORAGE_FULL: UserMessage = Object.freeze({
  message: "This device has run out of storage space for Creator.",
  nextStep: "Free some space, for example by deleting Projects or sounds you no longer need, then try again.",
});

const UNKNOWN: UserMessage = Object.freeze({
  message: "Something went wrong in Creator.",
  nextStep: "Try again. Details are in Developer diagnostics.",
});

const MESSAGES: Readonly<Record<string, UserMessage>> = Object.freeze({
  INVALID_PROJECT: {
    message: "This file is not a Project Creator can open.",
    nextStep: "Choose a .lmdj file exported from Creator.",
  },
  LOCAL_PROJECT_UNREADABLE: {
    message: "The local copy of this Project on this device could not be read. The imported file is not at fault.",
    nextStep: "Open another Project, or import this Project's file again.",
  },
  DUPLICATE_ID: {
    message: "The import was refused because the local copy of this Project has newer changes. Nothing was lost.",
    nextStep: "Open the local Project to keep working on it.",
  },
  PROJECT_BUSY,
  WEB_RUNTIME_RESOURCE_LIMIT: {
    message: "This is more audio than Creator can handle at once on this device.",
    nextStep: "Use a shorter sound or fewer Pads, then try again.",
  },
  HOST_PROTOCOL_MISMATCH: {
    message: "This copy of Creator is out of date.",
    nextStep: "Reload the page to load the current version.",
  },
  INTERNAL_ERROR: UNKNOWN,
  HOST_RESTART_REQUIRED: {
    message: "The audio engine stopped. Your Project is saved and not affected.",
    nextStep: "Choose Retry runtime to restart it.",
  },
  HOST_TIMEOUT: {
    message: "The audio engine stopped responding. Your Project is saved and not affected.",
    nextStep: "Choose Retry runtime to restart it.",
  },
  UNSUPPORTED_WEB_RUNTIME: {
    message: "This browser cannot run Creator.",
    nextStep: "Open Creator in a current version of another browser.",
  },
  NOT_FOUND: {
    message: "That item is no longer in this Project.",
    nextStep: "Refresh the view, then try again.",
  },
  REVISION_CONFLICT: {
    message: "The Project changed while this was in progress.",
    nextStep: "Review the change, then try again.",
  },
  INVALID_ARGUMENT: {
    message: "Creator could not apply that request.",
    nextStep: "Try again. Details are in Developer diagnostics.",
  },
  HOST_STATE_INVALID: {
    message: "That can't be done right now.",
    nextStep: "Stop playback and finish any recording or import, then try again.",
  },
  UNSUPPORTED_AUDIO: {
    message: "This audio file's format is not supported.",
    nextStep: "Choose a different audio file.",
  },
  MISSING_ASSET: {
    message: "A sound this Project needs is missing.",
    nextStep: "Assign the sound again, or import the Project again.",
  },
  COOK_FAILED: {
    message: "A sound could not be prepared for playback. Your changes are saved.",
    nextStep: "Try preparing the audio again.",
  },
  BANK_QUOTA_EXHAUSTED: {
    message: "This Bank has no room for more sound.",
    nextStep: "Free a Pad in this Bank, or use another Bank.",
  },
  PROJECT_QUOTA_EXHAUSTED: {
    message: "This Project has no room for more sound.",
    nextStep: "Shorten or remove sounds you no longer need.",
  },
  PROVIDER_NOT_FOUND: {
    message: "The tool needed for this is not available.",
    nextStep: "Try again later.",
  },
  PROVIDER_FAILED: {
    message: "The tool could not finish this.",
    nextStep: "Try again.",
  },
  PERMISSION_DENIED: {
    message: "Creator does not have permission to do this.",
    nextStep: "Grant the permission, then try again.",
  },
  ABORTED: {
    message: "The action was cancelled.",
    nextStep: "Start it again when you are ready.",
  },
});

function storageMessage(details: Details): UserMessage {
  switch (details.storage_condition) {
    case "quota_exceeded":
      return STORAGE_FULL;
    case "project_busy":
      return PROJECT_BUSY;
    default:
      return Object.freeze({
        message: "Creator could not read or save data on this device.",
        nextStep: "Try again. If it keeps happening, reload Creator; saved work stays on this device.",
      });
  }
}

export function userMessage(code: string, details: Details = {}): UserMessage {
  if (code === "IO_ERROR") return storageMessage(details);
  return Object.hasOwn(MESSAGES, code) ? MESSAGES[code]! : UNKNOWN;
}
