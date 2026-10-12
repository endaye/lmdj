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


def validate_verified_prefix(checkpoint):
    """The optional anchor-carried prefix: a locked writer authenticated the first
    `count` comments (writer liveness included) and got chain head `head`.

    Later processes still check every comment's metadata and the digest chain;
    only writer liveness re-proofs inside the prefix are skipped (#2025)."""
    verified = checkpoint.get("verified")
    require(verified is None
            or (isinstance(verified, dict) and set(verified) == {"head", "count"}
                and type(verified["count"]) is int and verified["count"] >= 0
                and (verified["head"] is None or type(verified["head"]) is str)
                and verified["head"] == checkpoint["head"]),
            "checkpoint verified prefix is malformed or disagrees with its head")
    return verified


class Transport(Protocol):
    def page(self, issue_id: int, cursor: str | None, authenticated_prefix: int = 0) -> dict:
        """Return {comments: [...], next: cursor|None}; fetch ALL pages.

        `authenticated_prefix` is honored only at transaction start (cursor
        None): the first N comments carry an anchor-recorded writer
        authentication, so their writer liveness re-proofs are skipped.
        Comment metadata and record checks still apply to every comment."""

    def last(self, issue_id: int) -> dict | None:
        """Newest comment row, or None on an empty journal.

        A cheap tail peek for the stranded-pending guard only. Writer
        provenance is NOT verified here; a matching peek never skips the
        complete authenticated replay, and a mismatch can only block."""

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
        return self.peek()

    def peek(self):
        """The authenticated checkpoint for a reader that holds no writer lock.

        Identical validation to `read`; it never writes, so a release-side
        observer can read committed state without joining the writer lock."""
        body = self.transport.read_body(self.issue_id)
        require(isinstance(body, dict) and set(body) == {"checkpoint", "provenance"},
                "checkpoint object is absent or malformed")
        require(self.authenticate(body, self.issue_id) is True, "checkpoint last editor or workflow is untrusted")
        checkpoint = body["checkpoint"]
        require(isinstance(checkpoint, dict)
                and set(checkpoint) in ({"head", "pending"}, {"head", "pending", "verified"}),
                "checkpoint schema is invalid")
        validate_verified_prefix(checkpoint)
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
        # Complete authenticated history verified by THIS process, if any:
        # {"head", "cursor", "count", "envelopes", "ids"}. Later reads verify
        # only what follows it and fall back to a complete replay whenever the
        # anchor head no longer matches, so no check is ever skipped.
        self._verified = None

    def _guard(self):
        require(self.lock_held() is True, "journal operation lacks the shared short writer lock")
        require(self.anchor is not None, "durable journal checkpoint is unavailable",
                "configure an authenticated checkpoint object; do not infer progress from comments alone")

    def _verify(self, comments, previous, ids, skip_authenticate=0):
        envelopes = []
        for index, comment in enumerate(comments):
            require(isinstance(comment, dict) and set(comment) == {"id", "edited", "envelope", "provenance"},
                    "invalid journal comment metadata")
            require(type(comment["id"]) is int and comment["id"] not in ids, "duplicate or invalid journal comment ID")
            ids.add(comment["id"])
            require(comment["edited"] is False, "journal comment was edited",
                    "stop admission and reconcile the original authenticated record")
            if index >= skip_authenticate:
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

    def _read_complete(self, authenticated_prefix=0):
        cursor, seen, envelopes, end = None, set(), [], None
        ids, head = set(), None
        remaining_prefix = authenticated_prefix
        while True:
            page = self.transport.page(self.issue_id, cursor,
                                       authenticated_prefix=authenticated_prefix if cursor is None else 0)
            require(isinstance(page, dict) and set(page) == {"comments", "next", "cursor"}
                    and isinstance(page["comments"], list), "invalid or incomplete journal page")
            # Consume this page while its transport writer proofs are current.
            # The next page refreshes mutable observations; collecting all rows
            # first would re-authenticate every earlier page over HTTP.
            verified, head = self._verify(page["comments"], head, ids,
                                          skip_authenticate=remaining_prefix)
            remaining_prefix = max(0, remaining_prefix - len(page["comments"]))
            envelopes.extend(verified)
            if page["cursor"] is not None:
                require(isinstance(page["cursor"], str) and bool(page["cursor"]), "invalid journal page cursor")
                end = page["cursor"]
            cursor = page["next"]
            if cursor is None:
                break
            require(isinstance(cursor, str) and cursor and cursor not in seen, "journal pagination loop")
            seen.add(cursor)
        self._verified = {"head": head, "cursor": end, "count": len(envelopes),
                          "envelopes": envelopes, "ids": ids}
        return envelopes, head

    def _read_delta(self, cache):
        """Authenticate only what follows the history this process verified.

        The chain still has to continue from the cached head, every new comment
        faces the same metadata/writer/digest checks, and the provider's total
        must equal the cached count plus the delta. Anything else blocks."""
        require(hasattr(self.transport, "page_after"), "transport cannot read a bounded delta")
        cursor, seen, comments, end, total = cache["cursor"], set(), [], None, None
        while True:
            page = self.transport.page_after(self.issue_id, cursor)
            require(isinstance(page, dict) and set(page) == {"comments", "next", "cursor", "total"}
                    and isinstance(page["comments"], list), "invalid or incomplete journal delta")
            require(type(page["total"]) is int and page["total"] >= 0, "journal delta total is invalid")
            require(total in (None, page["total"]), "journal inventory changed during the delta read")
            total = page["total"]
            comments.extend(page["comments"])
            if page["cursor"] is not None:
                require(isinstance(page["cursor"], str) and bool(page["cursor"]), "invalid journal delta cursor")
                end = page["cursor"]
            cursor = page["next"]
            if cursor is None:
                break
            require(isinstance(cursor, str) and bool(cursor) and cursor not in seen,
                    "journal delta pagination loop")
            seen.add(cursor)
        require(total == cache["count"] + len(comments), "journal inventory changed during the delta read",
                "stop admission; reconcile the exact authenticated history before trusting a delta")
        if not comments:
            return list(cache["envelopes"]), cache["head"]
        ids = set(cache["ids"])
        envelopes, head = self._verify(comments, cache["head"], ids)
        self._verified = {"head": head, "cursor": end or cache["cursor"],
                          "count": cache["count"] + len(envelopes),
                          "envelopes": [*cache["envelopes"], *envelopes], "ids": ids}
        return list(self._verified["envelopes"]), head

    def _read(self, anchor):
        """Complete authenticated history, reusing a verified prefix when one binds this head.

        The in-process prefix is reused only while the anchor still names
        exactly the head this process verified; any other head forces a
        complete replay. The anchor-persisted prefix ("verified") extends the
        same rule across processes: those comments still face metadata and
        digest-chain checks, only their writer liveness re-proofs are skipped."""
        expected_head = anchor["head"]
        cache = self._verified
        if cache is not None and cache["cursor"] is not None and cache["head"] == expected_head:
            return self._read_delta(cache)
        prefix = anchor.get("verified")
        if prefix is not None and prefix["head"] == expected_head:
            return self._read_complete(authenticated_prefix=prefix["count"])
        return self._read_complete()

    def _verified_payload(self, head):
        """The persistable prefix when this process's read covers `head`, else None."""
        cache = self._verified
        if cache is None or cache["head"] != head:
            return None
        return {"head": head, "count": cache["count"]}

    def _peek_pending(self, anchor):
        """Fail fast on a proven-absent stranded pending before any full replay.

        A blocked journal must not burn the writer's request budget on every
        health tick; that exhaustion is what strands appends in the first
        place. The peek can only block: a matching tail still faces the
        authenticated history read below, so no trust moves to it."""
        pending = anchor["pending"]
        require(isinstance(pending, dict), "anchor pending intent is malformed",
                "reconcile the exact pending event; do not issue a second POST")
        tail = self.transport.last(self.issue_id)
        require(isinstance(tail, dict) and tail.get("edited") is False
                and tail.get("envelope") == pending and pending.get("previous") == anchor["head"],
                "pending append is not yet visible or its outcome is uncertain",
                "reconcile the exact pending event; do not issue a second POST")

    def load(self):
        """Recover a known pending append; missing/ambiguous write remains blocked."""
        try:
            self._guard()
            anchor = self.anchor.read()
            require(isinstance(anchor, dict) and set(anchor) in ({"head", "pending"}, {"head", "pending", "verified"}),
                    "anchor is missing or malformed")
            if anchor["pending"] is not None:
                self._peek_pending(anchor)
            envelopes, head = self._read(anchor)
            if anchor["pending"] is not None:
                pending = anchor["pending"]
                require(envelopes and envelopes[-1] == pending and pending["previous"] == anchor["head"],
                        "pending append is not yet visible or its outcome is uncertain",
                        "reconcile the exact pending event; do not issue a second POST")
                replacement = {"head": head, "pending": None}
                verified = self._verified_payload(head)
                if verified is not None:
                    replacement["verified"] = verified
                self.anchor.replace(anchor, replacement)
                anchor = replacement
            require(head == anchor["head"], "journal suffix is missing or unanchored",
                    "stop admission; restore the independent anchor and journal or audit old runs before bootstrap")
            return [deepcopy(envelope["event"]) for envelope in envelopes]
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: journal state unavailable: {error}; remedy: reconcile storage; do not advance cursor") from error

    def persist_verified(self):
        """Record this process's authenticated prefix on the anchor for later processes.

        No-op unless this process has authenticated the current anchor head and
        the anchor does not already carry that exact prefix. One locked PATCH
        amortized against a complete writer re-authentication per later tick."""
        try:
            self._guard()
            anchor = self.anchor.read()
            require(isinstance(anchor, dict) and set(anchor) in ({"head", "pending"}, {"head", "pending", "verified"}),
                    "anchor is missing or malformed")
            desired = self._verified_payload(anchor["head"])
            require(desired is not None,
                    "this process has not authenticated the current head; remedy: load the journal before persisting a verified prefix")
            if anchor.get("verified") == desired:
                return False
            replacement = dict(anchor)
            replacement["verified"] = desired
            self.anchor.replace(anchor, replacement)
            return True
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: verified prefix persist unavailable: {error}; remedy: reconcile storage; do not advance cursor") from error

    def read_committed(self):
        """Read-only: the complete authenticated history up to the anchored head.

        Takes no writer lock and writes nothing. A persisted-but-unanchored
        pending append is excluded, never adopted: only a locked writer's
        `load()` may commit it. Every other check of the complete replay still
        applies, and any other suffix beyond the anchored head is refused."""
        try:
            require(self.anchor is not None, "durable journal checkpoint is unavailable",
                    "configure an authenticated checkpoint object; do not infer progress from comments alone")
            anchor = self.anchor.peek()
            envelopes, head = self._read(anchor)
            if head != anchor["head"]:
                pending = anchor["pending"]
                require(isinstance(pending, dict) and envelopes and envelopes[-1] == pending
                        and pending.get("previous") == anchor["head"],
                        "journal suffix is missing or unanchored",
                        "read only anchored history; reconcile the writer's pending append first")
                envelopes = envelopes[:-1]
            return [deepcopy(envelope["event"]) for envelope in envelopes]
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: journal state unavailable: {error}; remedy: reconcile storage; do not advance cursor") from error

    def reconcile_pending(self, expected_digest):
        """Clear a stranded pending intent after an exact operator audit.

        The only safe drain for a pending append whose POST never persisted:
        the operator names the exact audited digest, the complete authenticated
        replay proves the event absent from the journal, and the anchor returns
        to {head, None}. The dropped event is re-derived by the next ordinary
        reconcile from actual run state; no POST is ever replayed here."""
        try:
            self._guard()
            require(isinstance(expected_digest, str) and bool(expected_digest),
                    "pending reconcile needs the audited digest of the exact stranded intent")
            anchor = self.anchor.read()
            require(isinstance(anchor, dict) and set(anchor) in ({"head", "pending"}, {"head", "pending", "verified"}),
                    "anchor is missing or malformed")
            pending = anchor["pending"]
            require(isinstance(pending, dict),
                    "no stranded pending append to reconcile; remedy: ordinary load recovery, never a manual clear")
            require(pending.get("digest") == expected_digest,
                    "operator audit names a different intent; remedy: re-audit the exact stranded pending before clearing")
            require(pending.get("previous") == anchor["head"],
                    "stranded intent is not the chain successor; remedy: reconcile forked history first, never clear by hand")
            envelopes, head = self._read(anchor)
            require(all(envelope != pending for envelope in envelopes),
                    "pending append persisted; remedy: ordinary load recovery adopts it, never clear a committed event")
            require(head == anchor["head"], "journal suffix is missing or unanchored",
                    "stop admission; restore the independent anchor and journal or audit old runs before bootstrap")
            replacement = {"head": anchor["head"], "pending": None}
            verified = self._verified_payload(head)
            if verified is not None:
                replacement["verified"] = verified
            self.anchor.replace(anchor, replacement)
            return [deepcopy(envelope["event"]) for envelope in envelopes]
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: pending reconcile unavailable: {error}; remedy: reconcile storage; do not advance cursor") from error

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
            verified = self._verified_payload(anchor["head"])
            if verified is not None:
                prepared["verified"] = verified
            self.anchor.replace(anchor, prepared)
            self.transport.append(self.issue_id, envelope)
            return self.load()
        except Exception as error:
            if isinstance(error, JournalBlocked):
                raise
            raise JournalBlocked(f"why: append not committed: {error}; remedy: reconcile pending identity before another write") from error
