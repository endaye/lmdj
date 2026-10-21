---
id: pr-base-snapshot-behind-main
area: ci-release
status: open
recurrences:
  - date: 2026-10-21
    occurrence: https://github.com/endaye/lmdj/actions/runs/39577546759
    observed_by: Codex (GPT-6)
exit: none
---

# A main-target PR can retain an older API base SHA after its dependencies merge, so review collection includes already integrated changes and refuses a small Task as oversized.

## Why

For #2388 head `00bf28725de1425f53d79ea523142eb725a420a1`, both the
live PR API and failed collector named base `3112ad8d`, although the main
branch ref was `d1096649`. The retained collection-failure artifact contains
57 paths, including the already merged Native/SDK tempo and release-doctor
changes; the actual current-main Task has17 paths. The model step was skipped.
This observation establishes inconsistent API reference snapshots, not a
product defect or the internal cause of GitHub's stale base snapshot.

Updating the PR's existing base to `main` again refreshed its API SHA to
`d1096649` and changed-file count to17. A fresh official main dispatch,
run39578187614, then published eligible review of the unchanged exact head
and independently repair-rechecked the original fixed finding. No source
history, input limit, workflow or branch protection changed.

## How to apply

Read the failed job and collection-failure artifact before rerunning an input
limit refusal. Compare the live PR's base SHA with the actual named branch
ref, and inspect the complete merge-base diff against that current branch.
Do not infer a stale snapshot from the file count alone or exclude real Task
paths to make the input fit.

When those receipts prove this mismatch, preserve the failed inventory and
refresh the PR's unchanged base branch through the supported PR update API.
Read back its base SHA, head SHA and complete changed paths. If they still
disagree, stop this remedy rather than retargeting to an unrelated branch.
Start a fresh `pr-review.yml` dispatch on main for the unchanged PR head;
include `recheck_comment_id` for a repaired finding that still needs its
independent verdict. Preserve live findings and conversation protection.

Authenticate the completed new run with the trusted current-head review
helper and inspect its actual findings/repair receipt before merging. The
old failed run remains failed. A genuinely oversized current-main diff still
requires the existing split or independent takeover procedure; this is not
an exception to the complete-input limits.

No automatic gate currently owns this external API snapshot behavior. This
first occurrence remains open pending an eligible shared procedure or gate;
product regression tests cannot reproduce GitHub's reference refresh.
