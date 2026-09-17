# R2: durable release request journal

Status: locally verified storage primitive; driver remains pending. Depends on R1 `74d20f59` and generated-output repair
PR #1266. No production release or installation is performed by this Task.

## Scope

Implement the durable state primitive for the full single-command release
sequence, including both changelog destinations. A canonical request binds
scope, actor reference, policy, control and base revisions. New request IDs may
not duplicate an unfinished repository release; an existing ID cannot change
scope. Each transition writes a durable intent before the driver may act and
requires an exact operation-bound verification receipt before advancing.

The journal is not external truth or authorization. The future run/resume driver
must independently authenticate the authorization reference and revalidate every
receipt against Git/GitHub/Host state. This Task does not implement that driver,
candidate allocation, API dispatch, signing, deployment or changelog rendering.

Declared files:

- `tools/release/orchestration.py`
- `tests/build/release_orchestration_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-orchestration-r2.md`

The private local POSIX directory is single-writer for the entire driver's
execution. Ownership, modes, hardlinks, symlinks, inode replacement and canonical
content are checked. Atomic replacement plus file/directory fsync protects
intent/receipt durability. Corrupt state is not silently recreated. Digests
detect corruption; they do not authenticate a malicious process running as the
same trusted account. Multi-host distributed storage is outside this primitive.

## Verification

`python3 tests/build/release_orchestration_test.py` exercises a real subprocess
that records intent, performs a far-side file effect and exits before receipt;
reopen must retain pending intent and refuse another begin, leaving the effect
unchanged. Other tests cover ordered completion across reopens, duplicate IDs,
concurrent writers, root/lock/file substitution and fsync faults before and after
replacement. A successful journal test is not successful real release acceptance.

The test is registered as `build.release_orchestration` in root CMake and is
also selected by the existing deployment CI `release_*_test.py` discovery. Run
the staged scope suite, Python compilation and Portal check. No gate or timeout
is loosened. Independent review must inspect fault paths before commit.

Verified on 2026-09-13: journal tests 19/19, staged path ownership 74/74,
Python compilation and Portal check (46 routes and internal links), all exit 0.
Independent review identified repository case aliasing and inherited fork-lock
cleanup; both were fixed and re-reviewed with no remaining actionable findings.
The fork regression checks both that child cleanup preserves the parent's lock
and that a live child does not retain it after the parent closes its context.
No new pitfall entry: these storage defects are fully expressed by regression
tests. No GitHub mutation, signing, deployment or remote acceptance was exercised.

### Delivery verification after R1 merge

R1 PR #1267 merged as `2dd0be8a0349de9cb02763b5d9534054194dd79b` after
authenticated exact-head DeepSeek review with no findings and guarded squash.
This R2 Task was replayed from `bd7d523d` onto that main without conflicts in
`feat/release-journal-delivery`; the original local stack remains intact.

Independent review found a write/read capacity mismatch not covered by the
original 19 tests: an oversized valid-character repository request could be
written successfully but was then unreadable under the 1 MiB limit. The write
path now encodes once and rejects oversized bytes before any temporary file or
record is created. The reader's limit was not increased. The original `_save`
from `bd7d523d` was substituted in memory for the two new regressions; both
failed as expected (JournalError not raised), exit 1. Retained red log:
`/tmp/lmdj-journal-delivery-size-regression-red.log`.

- Final direct journal suite: 21/21 in 0.168s, exit 0;
  `/tmp/lmdj-journal-delivery-tests-v2.log`.
- Registered CTest: build.release_orchestration passed in 0.33s, exit 0;
  `/tmp/lmdj-journal-delivery-ctest-v2.log`.
- Staged ownership: 74/74 in 7.160s, exit 0;
  `/tmp/lmdj-journal-delivery-ownership.log`. Python compilation passed.
- Full Node 22 Portal: 116/116 tests, production build and 46 routes/internal
  links, exit 0; `/tmp/lmdj-journal-delivery-portal.log`. Actual built operations
  HTML includes the storage layer and the not-yet-connected service boundary.
- Independent final five-file review found no remaining actionable finding;
  reviewer independently ran 21/21, exit 0. The size invariant is fully captured
  by code and regression tests, so no process pitfall entry is added.

No production driver, authorization service, signing, deployment or complete
release acceptance is inferred. The earlier 19-test results remain historical,
not retroactively presented as having covered the size defect.

## Version Management

Version impact: none

Reason: repository-internal orchestration storage only; Product, Assembly,
Module, Host, Provider and public Contract identities remain unchanged.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish implemented durable storage from pending end-to-end driver
and live acceptance; document unresolved-intent recovery rather than retrying.
