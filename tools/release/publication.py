"""Collect one immutable publication record from verified exact Release state.

This is an external read-only operation. It does not edit the ledger, publish a
Release, generate portal files, or assert that the portal is already deployed.
"""

from dataclasses import replace

from .batch_reference import thaw
from .changelog import ChangelogError, binding
from .changelog_site import project
from .model import Disposition, ReleaseLedger
from .transitions import verify_published_state


class PublicationError(ValueError):
    pass


def collect_publication(tag, release_id, plan_sha256, context):
    verified = verify_published_state(tag, release_id, plan_sha256, context)
    intent, release = verified.authority.intent, verified.release
    if intent.changelog is None:
        raise PublicationError("why: published intent has no frozen changelog; remedy: do not fabricate or retrofit historical notes")
    digests = binding(thaw(intent.changelog))
    record = {"tag": intent.tag, "target_revision": intent.target_revision,
              "release_id": release.id, "published_at": release.published_at,
              "plan_sha256": verified.result.plan_sha256,
              "changelog_sha256": digests["sha256"], "notes_sha256": digests["notes_sha256"]}
    # Apply exactly the publication consumer's schema. The ledger may still be
    # releasable just after publication; only the later reviewed evidence PR
    # changes it to published. This local projection edits no authority state.
    try:
        project(ReleaseLedger((replace(intent, disposition=Disposition.PUBLISHED),), ()),
                {"schema": "lmdj.release-changelog-publications.v1", "entries": [record]})
    except ChangelogError:
        raise PublicationError("why: verified Release lacks valid publication metadata; remedy: reconcile the numeric Release; never invent its publication date") from None
    return record
