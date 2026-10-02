import {expect, test} from "vitest";

import {userMessage} from "../src/state/error_messages";

// The public typed error codes Creator receives from the Host and its own
// journeys (#1680).
const PUBLIC_CODES = [
  "INVALID_ARGUMENT", "NOT_FOUND", "REVISION_CONFLICT", "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO", "MISSING_ASSET", "INVALID_PROJECT", "COOK_FAILED",
  "BANK_QUOTA_EXHAUSTED", "PROJECT_QUOTA_EXHAUSTED", "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED", "PERMISSION_DENIED", "IO_ERROR", "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME", "PROJECT_BUSY", "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID", "HOST_TIMEOUT", "HOST_RESTART_REQUIRED",
  "HOST_PROTOCOL_MISMATCH", "LOCAL_PROJECT_UNREADABLE", "ABORTED",
] as const;

// A code, a snake_case token or the tooling why/remedy format in user text.
const TECHNICAL = /\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b[a-z]+_[a-z_]+\b|\bwhy:|\bremedy:/;

test.each(PUBLIC_CODES)("%s has a user-language message and a next step", (code) => {
  const {message, nextStep} = userMessage(code);
  expect(message.length).toBeGreaterThan(0);
  expect(nextStep.length).toBeGreaterThan(0);
  expect(`${message} ${nextStep}`).not.toMatch(TECHNICAL);
});

test("the general failure message is kept for a code Creator does not know", () => {
  const unknown = userMessage("SOMETHING_NEW");
  expect(unknown).toEqual(userMessage("INTERNAL_ERROR"));
  expect(`${unknown.message} ${unknown.nextStep}`).not.toContain("SOMETHING_NEW");
});

test("a full device is told how to free space", () => {
  expect(userMessage("IO_ERROR", {storage_condition: "quota_exceeded"})).toEqual({
    message: "This device has run out of storage space for Creator.",
    nextStep: "Free some space, for example by deleting Projects or sounds you no longer need, then try again.",
  });
});

test("a storage writer conflict reads as the busy Project", () => {
  expect(userMessage("IO_ERROR", {storage_condition: "project_busy"}))
    .toEqual(userMessage("PROJECT_BUSY"));
});

test.each(["io_failure", "invalid_state", "already_exists", undefined])(
  "other storage condition %s says saved work stays on this device",
  (condition) => {
    const {message, nextStep} = userMessage("IO_ERROR",
      condition === undefined ? {} : {storage_condition: condition});
    expect(message).toBe("Creator could not read or save data on this device.");
    expect(nextStep).toContain("saved work stays on this device");
  },
);

test.each(["HOST_RESTART_REQUIRED", "HOST_TIMEOUT"])(
  "%s says the Project is not affected and how to restart",
  (code) => {
    const {message, nextStep} = userMessage(code);
    expect(message).toContain("Your Project is saved and not affected.");
    expect(nextStep).toBe("Choose Retry runtime to restart it.");
  },
);

test("a resource limit never echoes its resource token or counts", () => {
  const {message, nextStep} = userMessage("WEB_RUNTIME_RESOURCE_LIMIT", {
    resource: "ingest_decoded_frames", observed: 43200001, limit: 43200000,
  });
  expect(`${message} ${nextStep}`).not.toMatch(/ingest|43200/);
});

test("an inherited object key is not a message", () => {
  expect(userMessage("toString")).toEqual(userMessage("INTERNAL_ERROR"));
  expect(userMessage("__proto__")).toEqual(userMessage("INTERNAL_ERROR"));
});
