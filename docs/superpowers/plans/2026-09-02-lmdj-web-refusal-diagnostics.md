# Web Proof Refusal Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.

**Issue:** #542
**Authority:** the #443 diagnosis of the `INVALID_PROJECT`-instead-of-
`REVISION_CONFLICT` failure, and the sanitization boundary in
`packages/web-runtime-platform/src/control_runtime.cpp`.

## Outcome

When the packaged Web Host normalizes a Facade refusal, the pre-sanitization
reason — source error code, source message, and a bounded scalar copy of the
source details — is emitted as one structured console line by the packaged runtime. The
Creator Playwright harness collects those lines per test and
attaches them to the test's results, so a failed refusal assertion in CI
carries the real reason inside the `test-results` artifact the lane already
uploads (`.github/actions/web-ci-proof/action.yml` "Retain proof output").

The wire payload is byte-identical to today. `safe_message`,
`sanitize_details`, and `sanitize_quota_details` are not touched.

## Design decisions

1. **Emission point.** `normalized_error(code, details, source_message)` at
   `control_runtime.cpp:491` is the single choke point through which every
   Facade-originating refusal is redacted (`normalized_facade_error` and the
   `Error` overload both route through it). Direct `host_error(...)` sites
   already carry exact Host-authored messages and are not the diagnostic gap.
   Emit the diagnostic there, once per normalized refusal, unconditionally —
   uniform emission is simpler to test than "only when information was lost".
2. **Channel.** One line to `stderr`. In the packaged Wasm build stderr
   reaches Emscripten `printErr`, which defaults to `console.error`
   (`packages/web-runtime-platform/src/web-runtime-pre.js` overrides neither
   `print` nor `printErr`), and Emscripten proxies runtime-worker stderr to
   the page, so the line reaches the page console whichever thread dispatched
   the refusal — the fail-closed proof in decision 5 pins this end to end. In
   the native `lmdj_web_control_runtime_tests` build it is ordinary process
   stderr. The
   browser console is a local developer diagnostic surface on the user's own
   machine; the sanitizer's contract protects the host protocol payload that
   application code consumes, and that payload does not change. No build
   flag, no runtime flag, no new host protocol surface, one packaged
   artifact.
3. **Line shape.** Fixed prefix `lmdj-refusal-diagnostic ` followed by one
   compact JSON object:
   `{"normalized": "<wire code>", "source_code": "<facade code>",
   "source_message": "<facade message>", "details": {…}}` where `details`
   copies only string/number/boolean scalar members of the source details.
   Hard-cap the full line at 2048 bytes; when the cap truncates the details
   copy, replace it with `{"truncated": true}` rather than emitting cut JSON.
4. **Collection.** A shared Playwright fixture module subscribes
   `page.on("console")`, filters the prefix, and attaches the collected lines
   as a `refusal-diagnostics.jsonl` attachment via `testInfo.attach`, so
   Playwright stores it with the failing test's other outputs under
   `tests/platform/web/test-results`, which CI already uploads on failure.
5. **Fail-closed collection proof.** The Creator sample-editor journey
   already manufactures a real `REVISION_CONFLICT`
   (`creator_web_sample_editor.spec.mjs:429`). After that assertion, the spec
   also asserts the collector observed a `lmdj-refusal-diagnostic` line with
   `"normalized": "REVISION_CONFLICT"`. If emission, Worker console
   forwarding, or collection ever silently regresses, the lane goes red
   instead of silently losing diagnostics again.

## File audit

Redaction paths inside `control_runtime.cpp` that currently discard the
source reason, all reached only through `normalized_error`:

| Site | Redaction |
| --- | --- |
| `safe_message` (`:373`) | replaces the message with one fixed string per code |
| `sanitize_details` (`:303`) | keeps only the approved revision fields |
| `sanitize_quota_details` (`:400`) | keeps only the approved quota fields |
| special-cased rewrites (`:503`–`:570`) | substitute fixed code/message pairs |

## Tasks

### Task 1: Emit the bounded refusal diagnostic from the Control Runtime

**Files:**
- Modify: `packages/web-runtime-platform/src/control_runtime.cpp`
- Modify: `packages/web-runtime-platform/test/control_runtime_test.cpp`

**Steps:**
- [ ] Write the tests first in `control_runtime_test.cpp`: drive an existing
  refusal path (a revision-conflicted `sample.update_pad` and an
  `INVALID_PROJECT` load) while capturing stderr; assert exactly one
  `lmdj-refusal-diagnostic ` line per refusal, that the JSON carries
  `normalized`, `source_code`, `source_message`, and scalar-only `details`,
  that a >2048-byte source detail set yields `{"truncated": true}` inside a
  line under the cap, and that the returned wire payloads are unchanged
  against the existing payload assertions (do not weaken any existing
  assertion).
- [ ] Implement `emit_refusal_diagnostic` in the anonymous namespace beside
  `normalized_error` and call it from the end of
  `normalized_error(code, details, source_message)` with both the source
  inputs and the normalized code. Write with a single unbuffered `fputs` to
  `stderr` so one complete console message is forwarded per refusal.
- [ ] Run the Task-specific tier below and keep every existing control
  runtime test green unmodified.

### Task 2: Collect the diagnostics in the Creator Playwright harness

**Files:**
- Create: `tests/platform/web/creator/fixtures/refusal_diagnostics.mjs`
- Modify: `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_browser.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_capture.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- Modify: `tests/platform/web/creator/creator_web_sequence.spec.mjs`

**Steps:**
- [ ] Implement the fixture module: export `test` as
  `base.test.extend({ refusalDiagnostics: [auto fixture] })` where the
  fixture subscribes `page.on("console")` before use, exposes the parsed
  line objects as an array, and on teardown attaches the raw lines as
  `refusal-diagnostics.jsonl` via `testInfo.attach` whenever at least one
  line was seen. Re-export `expect`.
- [ ] Switch each Creator spec's `import {expect, test} from
  "@playwright/test"` to the fixture module. No other spec logic changes in
  this step.
- [ ] In the sample-editor v1-to-v2 journey, after the existing
  `REVISION_CONFLICT` expectation (`creator_web_sample_editor.spec.mjs:429`),
  assert `refusalDiagnostics` contains an entry with
  `normalized === "REVISION_CONFLICT"` whose `details` carry the same
  `expected_revision`/`actual_revision` pair the wire payload promised.
- [ ] `node --check` every changed `.mjs` file, then run the packaged Creator
  proof.

### Task 3: Documentation

**Files:**
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Steps:**
- [ ] Add one passage to the Creator lane description: refusal assertions
  carry a `refusal-diagnostics.jsonl` attachment holding the pre-sanitization
  Facade reason; the browser wire payload remains sanitized and unchanged.
- [ ] `scripts/architecture-portal.sh check`.

## Version Management

Version impact: Module `web-runtime-platform` requires a SemVer **patch**
(2.0.1 → 2.0.2): additive local diagnostic emission with no module API,
Contract, or wire-payload change. Publication follows the Stage 9/10
precedent (#420): the next Product Build integration Task takes the bump
together with `products/lmdj/assembly.json`, the `tests/build/version_test.py`
pins, and the regenerated assembly lock (`python3 scripts/version.py lock`).
This Task changes no version file. Contracts: none — `lmdj.error.v1` and the
host protocol payload are untouched.

## Documentation Impact

Documentation impact: required. Route:
`apps/architecture-portal/docs/operations/testing-and-proof.mdx` (Creator
lane artifact description), updated in Task 3 of this plan. No identity is
hand-entered; the passage describes lane behavior only.

## Verification

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev -R host.web_control_runtime --output-on-failure
node --check tests/platform/web/creator/fixtures/refusal_diagnostics.mjs
for spec in tests/platform/web/creator/creator_web_*.spec.mjs; do node --check "$spec"; done
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
python3 tests/build/version_test.py
```

Expected: every command exits 0; the packaged proof's sample-editor journey
proves end-to-end diagnostic collection; no existing wire-payload assertion
was modified.

## Constraints

- Work only on `fix/web-refusal-diagnostics` in an isolated worktree from
  `origin/main`; never modify or commit on `main`.
- One Conventional Commit:
  `fix(web): retain the Facade refusal reason in Web proof artifacts (fixes #542)`.
- Declared files: this plan plus the files listed in Tasks 1–3. Stage
  nothing else; inspect the staged list and `git diff --cached --check`
  before committing.
- Hard boundary: no change to `safe_message`, `sanitize_details`,
  `sanitize_quota_details`, the host protocol payload, or any Contract; no
  compile-time or runtime diagnostic flag; a single packaged artifact.
- At implementation start, search open `.agents/pitfalls/` entries by
  `area:web-host` and `area:creator` per
  `docs/governance/pitfall-ledger.md`; before shipping, follow `issue-done`
  to record or bump any qualifying pitfall.
- A local commit does not authorize push, Pull Request creation, merge,
  release, publication, deployment, or Channel promotion; ship through
  `.agents/skills/issue-done/SKILL.md`.
