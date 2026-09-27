# WebKit early provisional-load abort for #1570

## Problem and boundary

The protocol timeline added in #1607 captured the intermittent Linux x64
Project I/O WebKit `page.goto` hang on its first recurrence (batch run
36320748849, target `6ab797dc`). For a fresh page's COOP navigation, WebKit
r2361 created the provisional new-process target, emitted
`Playwright.provisionalLoadFailed` ("Load request cancelled") for the
navigation's loader, and destroyed that target. Only 2 ms later did the old
process report the document `Network.requestWillBeSent`. After that, nothing
arrived for the 598 seconds up to the test timeout. The trace records the
document request without a response.

The locked Playwright 1.62.1 client passes that failure to
`frameAbortedNavigation`. That function returns early when the main frame has
no pending document, and the pending document is set only by the later request
event. The abort is therefore lost, and `goto` waits for a commit the engine
has already cancelled. Upstream `main` has the same code. The engine-side
cancellation is outside this repository. The lost abort is a client defect that
converts an immediate navigation error into a timeout of any length.

## Task: surface the engine's cancellation and repeat only an uncommitted first load

Declared files:

- `tests/platform/web/package.json`
- `tests/platform/web/toolchain/playwright_webkit_abort_patch.mjs`
- `tests/platform/web/toolchain/playwright_webkit_abort_patch_test.mjs`
- `tests/platform/web/toolchain/fake_webkit_pipe_browser.mjs`
- `tests/platform/web/project_io/webkit_cancelled_navigation.mjs`
- `tests/platform/web/project_io/webkit_cancelled_navigation_test.mjs`
- `tests/platform/web/project_io/project_io_web_conformance.spec.mjs`
- `scripts/web-toolchain-conformance.sh`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/webkit-page-cycle-wedge-hangs-later-navigations.md`
- this plan

`npm ci` in `tests/platform/web` runs a postinstall edit of the locked client's
WebKit page:

- A provisional-load failure whose loader is not the main frame's pending
  document is remembered.
- It is replayed through `frameAbortedNavigation` when that loader's main-frame
  document request starts.

The edit accepts only Playwright 1.62.1 with exactly one site per change and
fails closed with `why`/`remedy` otherwise. The proof checks that the patch is
applied before running any browser.

Every Project I/O spec navigation goes through one helper. It repeats the
navigation once only when all of these hold:

- the project is WebKit;
- the page is open and still `about:blank`, so no document ever committed and
  no page script ran;
- the error is the engine's `Load request cancelled; maybe frame was detached?`.

The retry is recorded as a `webkit-engine-cancelled-first-load` annotation and
a log line. Every other error, a page that already holds a document, and a
second cancellation still fail. Test timeouts, browser builds, lane selection
and page-close semantics are unchanged.

Lowest-tier verification:

- `node --test tests/platform/web/toolchain/playwright_webkit_abort_patch_test.mjs`
  replays the recorded exchange through a fake WebKit inspector-pipe browser
  against scratch copies of the locked client. The unpatched copy times out.
  The patched copy rejects at once with the engine's error, keeps the
  existing rejection when the document request arrives first, and is
  idempotent, reversible and fail-closed.
- `node --test tests/platform/web/project_io/webkit_cancelled_navigation_test.mjs`
  checks that the retry condition fires once and never otherwise.
- The complete Project I/O spec runs on the OPFS WebKit and Chromium to check
  that the patched client and helper leave passing journeys unchanged.

The new gate catches a Playwright upgrade or reinstall that silently removes
the replay, which would bring back the unbounded hang.

## Version Management

Version impact: none. This Task changes the test client, test helpers and
documentation, not Product, Module, Host, Provider or Contract behavior or
identity.

## Documentation Impact

Documentation impact: required. Update `/operations/testing-and-proof/` with
the diagnosed cause, the bound client patch and the exact retry condition. Run
`scripts/docs-site.sh check` before commit.
