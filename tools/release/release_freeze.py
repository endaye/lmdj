"""The release freeze: one repository variable the active release request holds.

While `scripts/release.sh run`/`resume` drive a request, `LMDJ_RELEASE_FREEZE`
names it; the PR Contract's Release freeze check fails Pull Requests that
change CI or release-tool control-plane paths while it is set, and agents do
not merge them. The variable is held before the request is created and
released when the request completes or is retired. Exactly one request may
hold it: a second request refuses rather than taking over (#2422 item 10,
#2404 item 1). Nothing here grants release authority.
"""

from __future__ import annotations

import re

from .orchestration import JournalError

VARIABLE = "LMDJ_RELEASE_FREEZE"
_REQUEST_ID = re.compile(r"release-[0-9a-f]{16}\Z")


def _fail(reason):
    raise JournalError(f"why: release freeze {reason}; remedy: finish or retire the request that "
                       "holds it (scripts/release.sh status), or clear a stale freeze as the doctor "
                       "directs; never merge frozen control-plane changes around it")


def _request_id(value):
    if not isinstance(value, str) or _REQUEST_ID.fullmatch(value) is None:
        _fail("names no release request id")
    return value


class ReleaseFreeze:
    def __init__(self, github, repository):
        if not isinstance(repository, str) or "/" not in repository:
            _fail("has no repository to live in")
        self.github, self.repository = github, repository

    def read(self):
        """The request id that holds the freeze, or None."""
        return self.github.get_repository_variable(self.repository, VARIABLE)

    def hold(self, request_id):
        """Hold the freeze for this request; refuse while another request holds it."""
        request_id = _request_id(request_id)
        holder = self.read()
        if holder is None:
            self.github.create_repository_variable(self.repository, VARIABLE, request_id)
        elif holder != request_id:
            _fail(f"another release request holds the freeze ({holder})")

    def release(self, request_id):
        """Release this request's freeze; a freeze another request holds is left alone, loudly."""
        request_id = _request_id(request_id)
        holder = self.read()
        if holder is None:
            return
        if holder != request_id:
            _fail(f"names another request ({holder}); it is not this request's to release")
        self.github.delete_repository_variable(self.repository, VARIABLE)
