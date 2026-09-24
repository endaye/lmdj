# WebKit navigation protocol evidence for #1570

## Problem and boundary

The Linux x64 `web_toolchain` lane sometimes waits 600 seconds in a WebKit
`page.goto`. The retained Playwright trace ends before document commit and the
`/proc` snapshot shows sleeping processes, but neither says whether the
browser received the navigation command. A second complete local run on the
same Linux x64 host reproduced the 600-second hang. Its shared `DEBUG_FILE`
was rewritten by later Playwright workers, so the remaining protocol packets
cannot be bound to the failed case. This is the evidence gap the sidecar
addresses. The earlier OPFS visibility finding
and page-pooling hypothesis have been handled separately. A 120-page r2361
open/navigate/close probe and the first complete Project I/O WebKit run on
the affected netcup host passed on 2026-09-24, confirming that a green run
does not establish that the intermittent signature is gone.

## Task: retain a bounded protocol timeline when the Project I/O WebKit proof fails

Declared files:

- `scripts/web-toolchain-conformance.sh`
- `tests/platform/web/project_io/webkit_protocol_timeline.mjs`
- `tests/platform/web/project_io/webkit_protocol_timeline_test.mjs`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/webkit-page-cycle-wedge-hangs-later-navigations.md`
- this plan

Run Playwright's locked `pw:protocol` logger only for the existing Project I/O
WebKit proof. Stream it through a sidecar that retains navigation sends, their
replies, page/target lifecycle, document requests, and frame navigation in a
small JSONL timeline capped at the latest 32768 events, with an explicit marker
if older events were dropped. If concurrent browser connections reuse an outer
command ID, label the reply ambiguous rather than attributing it to a page.
The sidecar must preserve the original Playwright
exit status. On success, discard the timeline; on failure, put it in that proof
slot's existing failure artifact directory beside the trace and `/proc`
snapshot. Keep the existing tests, timeouts, selected lane, browser builds,
and page-close semantics unchanged. This is diagnostic evidence, not a new
required gate or a claim that the intermittent browser defect is repaired.

Lowest-tier verification: `node --test
tests/platform/web/project_io/webkit_protocol_timeline_test.mjs` checks that
the real nested WebKit protocol shape yields the navigation sequence, excludes
unrelated payloads, retains evidence on a failing command, and returns its
status. `bash -n scripts/web-toolchain-conformance.sh` checks the shell edit.
Run the complete Project I/O WebKit spec with the pinned client and OPFS
browser to check the sidecar against the actual browser exchange. The
additional diagnostic catches missing send/reply/target evidence on the next
runner recurrence; it deliberately does not turn an intermittent hang into a
pass or change the release-candidate verdict.

## Version Management

Version impact: none. This Task changes test diagnostics and documentation,
not Product, Module, Host, Provider, or Contract behavior or identity.

## Documentation Impact

Documentation impact: required. Update `/operations/testing-and-proof/` to
describe the failure-only protocol timeline and its evidence limit. Run
`scripts/docs-site.sh check` before commit because the Task changes proof
tooling and the documented evidence path.
