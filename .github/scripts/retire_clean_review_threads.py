#!/usr/bin/env python3
"""Resolve a review thread that carries nothing but a clean review.

`main` requires every review thread to be resolved before a merge, and
`Pre-heavy Gate` counts unresolved threads as an admission condition (#659).
Both rules assume a thread means "a reviewer found something a human must
answer". A reviewer that posts "No issues found" as a *thread* therefore
blocks the merge it just approved.

That happens for a mechanical reason rather than a judgement one: the vendored
`/pr-review` command is told to post a clean summary as a Pull Request issue
comment through `gh`, and `gh` is not installed on the self-hosted runners
these lanes use. Five such threads were resolved by hand on 2026-09-06 across
#677, #680, #685, #694 and #698. The command now names the REST fallback, but
a prompt is an instruction, not a guarantee, so this closes the same hole
deterministically after the fact.

What it will resolve, all four conditions together:

* the thread is unresolved;
* it holds exactly one comment, so no human has replied into it;
* that comment's first line is the signature of the backend that just ran, so
  a different reviewer's thread is never touched;
* the body has the *shape* of a clean review -- signature, heading, then the
  clean sentence -- rather than merely containing that sentence somewhere, and
  carries no finding marker.

Anything else is left alone. The failure mode this must never have is
resolving a real finding, so every condition narrows and none widens.

Never fails the job: a review that could not be tidied is a cosmetic problem,
and this runs beside a lane that is advisory by design.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/graphql"
API_VERSION = "2022-11-28"

# The clean review's opening, in order. The body is matched by *shape*, not by
# containment: a finding is free-form prose and may well quote the clean
# sentence -- reviewing this very change would -- and a `in body` test would
# then resolve the finding. So the sentence must be where the vendored command
# puts it, immediately under the heading, with nothing before it but the
# signature. Anything the reviewer appends after it (notes about what was
# checked) is still a clean review.
CLEAN_HEADING = "## Code review"
CLEAN_SENTENCE = "No issues found. Checked for bugs and CLAUDE.md compliance."

# A finding, however it is framed, uses one of these. Their presence vetoes the
# clean reading even when the clean sentence is also there.
FINDING_MARKERS = ("[critical]", "[important]", "[nit]", "**Bug:", "## Findings")

THREADS_QUERY = """
query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$cursor) {
        nodes {
          id
          isResolved
          comments(first:2) { totalCount nodes { body } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

RESOLVE_MUTATION = """
mutation($id:ID!) {
  resolveReviewThread(input:{threadId:$id}) { thread { isResolved } }
}
"""


def _graphql(token: str, query: str, variables: dict) -> dict:
    request = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "lmdj-retire-clean-review-threads",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL error: {payload['errors']}")
    return payload["data"]


def is_clean_review(body: str, marker: str) -> bool:
    """True when this comment is a clean review posted by `marker`'s backend.

    Shape, in order: the signature, the review heading, then the clean
    sentence. A finding that merely mentions the sentence fails at the
    heading or at the sentence's position, which is the point.
    """
    if not body.startswith(marker):
        return False
    rest = body[len(marker):].strip()
    if not rest.startswith(CLEAN_HEADING):
        return False
    rest = rest[len(CLEAN_HEADING):].strip()
    if not rest.startswith(CLEAN_SENTENCE):
        return False
    # Belt and braces, and it only ever refuses: a clean review whose notes
    # happen to contain a finding word is left for a human rather than tidied.
    return not any(finding in body for finding in FINDING_MARKERS)


def clean_threads(threads: list[dict], marker: str) -> list[str]:
    """Ids of the unresolved, unanswered, clean threads signed by `marker`."""
    selected = []
    for thread in threads:
        if thread.get("isResolved"):
            continue
        comments = thread.get("comments") or {}
        # A reply means a human is using the thread; leave it to them even if
        # the opening comment was clean.
        if comments.get("totalCount") != 1:
            continue
        nodes = comments.get("nodes") or []
        if not nodes:
            continue
        if is_clean_review(nodes[0].get("body") or "", marker):
            selected.append(thread["id"])
    return selected


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3:
        print(
            "usage: retire_clean_review_threads.py <owner/repo> <pr-number> <marker>",
            file=sys.stderr,
        )
        return 0
    repository, number, marker = argv
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("::notice::no GITHUB_TOKEN; leaving review threads alone")
        return 0
    owner, _, name = repository.partition("/")

    try:
        threads: list[dict] = []
        cursor = None
        while True:
            data = _graphql(
                token,
                THREADS_QUERY,
                {"owner": owner, "name": name, "number": int(number), "cursor": cursor},
            )
            page = data["repository"]["pullRequest"]["reviewThreads"]
            threads.extend(page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

        for thread_id in clean_threads(threads, marker):
            _graphql(token, RESOLVE_MUTATION, {"id": thread_id})
            print(f"::notice::resolved a clean review thread signed {marker}")
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as error:
        # Cosmetic work beside an advisory lane. Say what happened and leave
        # the job green; a thread left open costs one human click, and failing
        # here would cost a red check on a lane that cannot block a merge.
        print(f"::notice::could not tidy clean review threads: {error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
