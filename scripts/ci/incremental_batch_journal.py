#!/usr/bin/env python3
"""Issue journal protocol prototype, NOT a configured production backend.

An independently read checkpoint object is REQUIRED: IssueBodyAnchor uses the
fixed Issue body, separate from its comments but in the SAME failure domain.
Updates use the shared writer lock, not Issue PATCH/ETag CAS. No network client
is supplied; T4/O1 must validate the actual metadata and visibility behavior.
Trust is repository-controlled automation, not resistance to compromised write
tokens or malicious administrators. Hashes detect corruption; they do not sign.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from incremental_batch import BatchError, digest, require


class JournalBlocked(BatchError):
    pass


class Transport(Protocol):
    def page(self, issue_id: int, cursor: str | None) -> dict:
        """Return {comments: [...], next: cursor|None}; fetch ALL pages."""

    def append(self, issue_id: int, envelope: dict) -> None:
        """One POST only. A thrown error may mean the POST persisted."""


class Anchor(Protocol):
    def read(self) -> dict:
        """Durable {head: digest|None, pending: envelope|None}."""

    def replace(self, previous: dict, replacement: dict) -> None:
        """Replace under shared lock; verify reads. This is NOT a CAS API."""


class IssueBodyAnchor:
    """Checkpoint adapter over fixed Issue body, not an independent service.

Transport.read_body returns {checkpoint, provenance}; write_body accepts a
checkpoint. Authenticate MUST verify the last editor (body is intentionally
updated), fixed issue/repository, and trusted writer run/workflow. A human edit
must fail even when they recompute every digest. A missing body never creates
an empty checkpoint automatically. Controlled initialization is separate.
"""
    def __init__(self, issue_id, transport, authenticate, lock_held):
        self.issue_id, self.transport = issue_id, transport
        self.authenticate, self.lock_held = authenticate, lock_held

    def read(self):
        require(self.lock_held() is True, "checkpoint read lacks shared writer lock")
        body = self.transport.read_body(self.issue_id)
        require(isinstance(body, dict) and set(body) == {"checkpoint", "provenance"},
                "checkpoint object is absent or malformed")
        require(self.authenticate(body, self.issue_id) is True, "checkpoint last editor or workflow is untrusted")
        checkpoint = body["checkpoint"]
        require(isinstance(checkpoint, dict) and set(checkpoint) == {"head", "pending"},
                "checkpoint schema is invalid")
        return deepcopy(checkpoint)

    def replace(self, previous, replacement):
        require(self.read() == previous, "checkpoint changed or read visibility is uncertain")
        self.transport.write_body(self.issue_id, deepcopy(replacement))
        require(self.read() == replacement, "checkpoint update is not yet visible",
                "stop admission and reconcile the existing write; do not assume it failed")


class Journal:
    def __init__(self, issue_id, transport, anchor, authenticate, lock_held):
        require(type(issue_id) is int and issue_id > 0, "journal needs a fixed issue ID")
        self.issue_id, self.transport, self.anchor = issue_id, transport, anchor
        self.authenticate, self.lock_held = authenticate, lock_held

    def _guard(self):
        require(self.lock_held() is True, "journal operation lacks the shared short writer lock")
        require(self.anchor is not None, "durable journal checkpoint is unavailable",
                "configure an authenticated checkpoint object; do not infer progress from comments alone")

    def _read(self):
        cursor, seen, comments = None, set(), []
        while True:
            page = self.transport.page(self.issue_id, cursor)
            require(isinstance(page, dict) and set(page) == {"comments", "next"}
                    and isinstance(page["comments"], list), "invalid or incomplete journal page")
            comments.extend(page["comments"])
            cursor = page["next"]
            if cursor is None:
                break
            require(isinstance(cursor, str) and cursor and cursor not in seen, "journal pagination loop")
            seen.add(cursor)
        previous, envelopes, ids = None, [], set()
        for comment in comments:
            require(isinstance(comment, dict) and set(comment) == {"id", "edited", "envelope", "provenance"},
                    "invalid journal comment metadata")
            require(type(comment["id"]) is int and comment["id"] not in ids, "duplicate or invalid journal comment ID")
            ids.add(comment["id"])
            require(comment["edited"] is False, "journal comment was edited",
                    "stop admission and reconcile the original authenticated record")
            require(self.authenticate(comment, self.issue_id) is True, "untrusted journal writer or workflow")
            envelope = comment["envelope"]
            require(isinstance(envelope, dict) and set(envelope) == {"previous", "event", "digest"},
                    "invalid journal envelope")
            require(envelope["previous"] == previous, "journal history is missing or forked")
            require(envelope["digest"] == digest({"previous": previous, "event": envelope["event"]}),
                    "journal content digest mismatch")
            previous = envelope["digest"]
            envelopes.append(envelope)
        return envelopes, previous

    def load(self):
        """Recover a known pending append; missing/ambiguous write remains blocked."""
        try:
            self._guard()
            anchor = self.anchor.read()
            require(isinstance(anchor, dict) and set(anchor) == {"head", "pending"}, "anchor is missing or malformed")
            envelopes, head = self._read()
            if anchor["pending"] is not None:
                pending = anchor["pending"]
                require(envelopes and envelopes[-1] == pending and pending["previous"] == anchor["head"],
                        "pending append is not yet visible or its outcome is uncertain",
                        "reconcile the exact pending event; do not issue a second POST")
                replacement = {"head": head, "pending": None}
                self.anchor.replace(anchor, replacement)
                anchor = replacement
            require(head == anchor["head"], "journal suffix is missing or unanchored",
                    "stop admission; restore the independent anchor and journal or audit old runs before bootstrap")
            return [deepcopy(envelope["event"]) for envelope in envelopes]
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: journal state unavailable: {error}; remedy: reconcile storage; do not advance cursor") from error

    def append(self, event):
        """Intent in independent anchor precedes POST; state commits only at load.

If the POST or anchor update response is lost, load reconciles once visibility
returns. A pending-but-absent append blocks instead of unsafe blind retry.
"""
        try:
            events = self.load()
            require(isinstance(event, dict) and isinstance(event.get("id"), str)
                    and bool(event["id"]), "journal event needs a stable identity")
            for existing in events:
                if existing.get("id") == event["id"]:
                    require(existing == event, "journal event ID reused with different content")
                    return events
            anchor = self.anchor.read()
            require(anchor["pending"] is None, "unresolved append already exists")
            envelope = {"previous": anchor["head"], "event": deepcopy(event)}
            envelope["digest"] = digest(envelope)
            prepared = {"head": anchor["head"], "pending": envelope}
            self.anchor.replace(anchor, prepared)
            self.transport.append(self.issue_id, envelope)
            return self.load()
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: append not committed: {error}; remedy: reconcile pending identity before another write") from error
