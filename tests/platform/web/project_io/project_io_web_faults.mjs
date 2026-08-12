export const REPLACEMENT_FAULT_POINTS = Object.freeze([
  "before_write",
  "during_write",
  "before_close",
  "after_close",
  "before_cleanup",
]);

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
