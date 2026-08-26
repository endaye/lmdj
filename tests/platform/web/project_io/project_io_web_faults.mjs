export const REPLACEMENT_FAULT_POINTS = Object.freeze([
  "before_write",
  "during_write",
  "before_close",
  "after_close",
  "before_cleanup",
]);

export function replacementReachedCommit(point) {
  if (!REPLACEMENT_FAULT_POINTS.includes(point)) {
    throw new TypeError(`unknown replacement fault point: ${point}`);
  }
  return point === "after_close" || point === "before_cleanup";
}

export const PUBLICATION_FAULT_POINTS = Object.freeze([
  "before_intent_write",
  "during_intent_write",
  "after_pending_intent",
  "during_directory_copy",
  "after_directory_copy",
  "during_directory_verify",
  "before_commit_close",
  "after_commit_close",
  "before_source_cleanup",
  "before_intent_cleanup",
]);

export const PUBLICATION_CLEANUP_FAULT = "destination_cleanup_failure";

export const STORAGE_CONDITION_FAULTS = Object.freeze([
  "QuotaExceededError",
  "InvalidStateError",
]);

// Mirrors the native Project I/O Sequence flush commit/recovery boundaries.
// Web conformance consumes this list so new boundaries cannot silently lose
// OPFS restart coverage.
export const SEQUENCE_FLUSH_FAULT_POINTS = Object.freeze([
  "journal_write",
  "transaction_write",
  "checkpoint_write",
  "manifest_publish",
  "receipt_reload",
  "journal_completion",
  "journal_deletion",
]);
