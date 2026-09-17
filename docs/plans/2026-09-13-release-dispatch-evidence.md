# Authenticate exact-run release dispatch receipts

Status: delivery integration of original `4edba6d0` onto producer `68e9ac88`
(merged as `0639209b`, identical trees), with the consumer's live-clock correction from `10f6d852`
included now rather than shipping its known constructor-time expiry defect.
Historical original-stack evidence below is not current delivery verification.

## Scope

The R4 workflow producer now retains original exact inputs, but a caller-supplied
receipt cannot establish which authenticated GitHub run received a request.
Implement its read-only consumer and closed GitHub transport. The caller
provides trusted repository/workflow numeric IDs, minimum reviewed producer
revision, original actor, exact control SHA and frozen inputs, not facts
learned from an arbitrary archive. No discovery or dispatch write is added.

Declared files:

- `tools/release/dispatch_evidence.py`
- `tools/release/github_api.py`
- `tests/build/release_dispatch_evidence_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-dispatch-evidence.md`

Verify live and attempt-1 API run identities, original actor and repository,
fixed workflow/main/control revision, complete paginated jobs/artifacts,
successful receipt-generation/upload steps, unique retained artifact, actual
download digest, bounded safe ZIP and complete canonical producer JSON.
Reconstruct the expected receipt through the real producer schema. Source
proof binds minimum reviewed producer -> workflow control -> checked-out
tooling -> observed protected main through real Git ancestry, without executing
target code or lazy-fetching missing objects. Trusted configuration must come
from the release controller's reviewed source, not from receipt claims. This
ancestry policy trusts reviewed main evolution; it is not an exact file-content
allowlist or a proof of effective protection history. Re-read run identities
and artifact inventory after download/source verification.

A failed or still-running publish/deploy run may have an authentic dispatch
receipt. Return only correlation bindings, never success/approval/absence or
permission to retry. Downstream effect verifiers retain their full obligations.
Missing, ambiguous, expired, changing or unreadable evidence refuses. The
consumer cannot prove absence of a second dispatch and does not implement
unknown-POST discovery, durable dispatch control, or end-to-end recovery.

## Verification

Real temporary Git history + shipped producer schema + actual closed HTTP
client with deterministic API/ZIP fixtures. Baseline binds even when later
effect failed; one-fact failures cover run/request/actor/ref/attempt mismatch,
failed upload, artifact origin/digest/retention/ambiguity/truncation, unsafe
archive, duplicate JSON, mid-read changes, and unmerged tooling. Exercise a
second artifact page and forbidden routes without I/O. Register and execute
the new CTest contract, plus producer and existing Portal API consumer tests,
staged ownership and Portal check. No actual dispatch, provider or deployment.

## Version Management

Version impact: none

Reason: internal correlation consumer only; no Product or Assembly changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish authenticated receipt reading from dispatch recovery and
successful release/deployment.

## Current delivery verification

The two new live-clock regressions first failed against the imported consumer
(2 tests, exit 1): reusing a reader at actual expiry and expiry during download
both returned evidence. The reader now uses the current clock unless an
explicit fixture clock is supplied and rechecks expiry before returning.

Independent review then reproduced a ZIP decoder resource overrun despite the
declared member-size check. The permanent real-producer/API/Git regression
changes ZIP metadata while wrapping the real DEFLATE decoder: before the fix,
the requested output bound was 1,073,741,824 and actual output 16,777,822 bytes.
The companion test also showed BZIP2 and LZMA were accepted. These two tests
failed with three failures (exit 1, 0.785s); the raw tool transcript retains the
red iteration. Like the existing Portal evidence consumer, this reader now
allows only STORED/DEFLATED and reads at most `LIMIT + 1` bytes. The causal
regression checks the real decoder request and output, not a mocked payload.
It proves resource bounds, not full compressed-tail validation: a valid
canonical receipt prefix may still be accepted.

After correction, consumer 24/24 (4.535s), producer 12/12 (0.332s), existing
Portal consumer 22/22 (10.904s) and GitHub API 39/39 (0.013s) passed, exit 0.
The three registered CTest contracts passed in 14.93s with unchanged timeouts.
Independent amendment review reran consumer 24/24 (4.542s) and found no other
actionable finding in the complete six-file scope. No standalone pitfall
entry: the clock and decoder defects are fully expressed by their regressions.

Staged ownership/admission passed 74/74 (12.639s). With Node 22.22.2,
`scripts/docs-site.sh check` exited 0: 144/144 tests, 47 metadata pages,
10 diagram sources / 20 outputs, snapshot validation, typecheck, changelog
validation and optimized build passed. Full output is retained at
`/tmp/lmdj-dispatch-evidence-delivery.RWGCsx/docs-v2.log`; the earlier process's
terminal result could not be recovered, so it is not counted as a second pass.

These are local fixture/source checks, not a live GitHub dispatch observation,
release, deployment, full self-test or end-to-end controller acceptance.

## Historical original-stack verification record

The first fixture iteration omitted the ZIP Content-Type. The real shared
HTTP reader correctly rejected the fixture before the downstream assertions;
`/tmp/lmdj-dispatch-evidence-tests-v2.log` retains that failed iteration. Add
the actual ZIP response type to the fixture, not an exception in the reader.

Independent review identified a missing protocol prohibition in the Git reader.
The first real partial-clone test passed on installed Git because it honors
`GIT_NO_LAZY_FETCH`; the retained `lazy-red.log` filename does not indicate a
failure. The compatibility test then removes that one environment variable
at the subprocess boundary to model older Git while keeping real partial-clone
and HTTP behavior: the original reader attempted a request to the loopback
observer and failed the no-network assertion. After adding
`GIT_ALLOW_PROTOCOL=''`, the same case refuses without an observer request and
the object remains missing. This is compatibility simulation, not a claim
that an old Git binary was installed or an external host was contacted.
Raw causal failure: `/tmp/lmdj-dispatch-evidence-legacy-red.log`.

The final behavior population includes all three workflows, 20 consumer tests;
the existing producer has 12 and Portal consumer 16 tests. GitHub API regression
39/39 passed. Configure exited 0 and the three selected CTest contracts executed
successfully. Portal check exited 0 with 139 tests and 47 routes/internal links.
Logs are `/tmp/lmdj-dispatch-evidence-{tests-v5,site,api,configure,ctest-v2,scope,docs}.log`;
later final-head reruns are retained separately. No live GitHub dispatch receipt
has been read; fixture success does not prove deployed producer compatibility.
Pitfall disposition: no separate entry; the real partial-clone regression fully
captures the protocol boundary without introducing a new general required gate.

Final staged verification: all three selected CTest contracts passed in
`/tmp/lmdj-dispatch-evidence-ctest-v3.log`; ownership 74/74 passed in
`/tmp/lmdj-dispatch-evidence-scope-v2.log`; whitespace check passed. The
independent reviewer re-ran the 20-case consumer suite and confirmed the
protocol finding fixed with no new actionable finding. No push, provider call,
dispatch, release, deployment or merge acceptance is represented by this Task.
