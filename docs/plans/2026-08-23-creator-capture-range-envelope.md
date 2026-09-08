# Creator Capture Range Envelope Implementation Plan

> Approved design: [Creator Capture Range Envelope and Selection Zoom](../design/2026-08-23-creator-capture-range-envelope-design.md)

**Goal:** Close #212 with a real selection-zoom caller, range-correct exact and
block envelope paths, and corrected Product Build `1.0.29.0` evidence.

**Architecture:** `CaptureBuffer` remains append-only and owns both raw chunks
and incremental 256-frame peak summaries plus append-chunk start indexes.
`CapturePanel` chooses the requested
view from reducer state: whole-buffer while recording and selection-window
while trimming or retrying a failed commit. No Core, Facade, Contract, Provider,
or Project Truth boundary changes.

**Technology:** TypeScript, React, Vitest/Testing Library, generated LMDJ
Product Assembly identity, Docusaurus Architecture Portal.

## Task 1: Record the approved design and version allocation

**Files:**

- Create: `docs/design/2026-08-23-creator-capture-range-envelope-design.md`
- Create: `docs/plans/2026-08-23-creator-capture-range-envelope.md`
- Modify: `docs/plans/2026-08-23-lmdj-stage9-sequence-recording.md`

- Record CR-D1 through CR-D5 and the exact acceptance boundary.
- Record the original allocation of `1.0.28.0` for #212, `1.0.29.0` for #213,
  and `1.0.30.0` for Stage 9. After independent review rejects the first #212
  candidate, preserve it and advance the corrected sequence to #212
  `1.0.29.0`, #213 `1.0.30.0`, and Stage 9 `1.0.31.0`.
- Run `git diff --check`, inspect the staged list, and commit only these files
  with `docs(creator): design capture selection zoom`.

## Task 2: Drive the range contract red with unit tests

**Files:**

- Modify: `apps/creator-web/test/capture_buffer.test.ts`

- Add exact-range tests spanning append chunks and combining stereo channels.
- Add range-keyed memoization and invalid-input tests.
- Add a long-window block-path fixture with high peaks immediately outside the
  requested window and at partial bin edges.
- Run
  `npm --prefix apps/creator-web test -- --run test/capture_buffer.test.ts` and
  record the expected RED failures before implementation.

## Task 3: Implement the bounded envelope and real panel caller

**Files:**

- Modify: `apps/creator-web/src/capture/capture_buffer.ts`
- Modify: `apps/creator-web/src/components/capture_panel.tsx`
- Modify: `apps/creator-web/test/capture_panel.test.tsx`

- Implement strict `(bins, startFrame, frameCount)` validation and a range-aware
  cache key.
- Traverse only the requested samples in the exact path.
- Use summaries only for completely covered blocks; scan partial edge samples
  exactly.
- Use exact integer quotient bin boundaries and monotonic chunk/range cursors;
  a late narrow range must not rescan every preceding append chunk per bin.
- Make recording paint the complete buffer and trimming/commit-error paint the
  current selection.
- Add selection values to paint dependencies and component-test both caller
  modes plus repaint after slider changes.
- Run the two focused test files, then the complete Creator Vitest suite.

## Task 4: Integrate Product and documentation identity

**Files:**

- Modify: `apps/creator-web/module.json`
- Modify: `apps/creator-web/package.json`
- Modify: `apps/creator-web/package-lock.json`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: generated Assembly/Runtime identity consumers
- Modify: `tests/build/version_test.py`
- Modify: `products/lmdj/README.md`
- Modify: current Portal pages that report Product/Creator/Web identities
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `docs/quality/2026-08-17-machine-task-todo.md`

- Retain the rejected `1.0.28.0` / Creator `1.3.5` snapshot as immutable
  branch-local evidence; do not overwrite or reuse it.
- Set Creator Web Host to `1.3.6` and corrected Product Build to `1.0.29.0`.
- Regenerate compiled Assembly, Assembly lock, and Web Runtime identity using
  the stable version tooling; do not hand-enter hashes.
- Mark E2 implemented by #212 and describe range/selection evidence on current
  Portal pages without claiming merge, release, deployment, or physical QA.
- Run:

```bash
python3 scripts/version.py verify --version-file products/lmdj/version.json
python3 tests/build/version_test.py
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
npm --prefix apps/creator-web test -- --run
scripts/architecture-portal.sh check
scripts/creator-web.sh proof
```

- Inspect the staged list and `git diff --cached --check`, then commit the
  complete implementation/version/current-docs Task with
  `feat(creator): zoom capture waveform to selection`.

## Task 5: Freeze corrected Product Build 1.0.29.0

**Files:** generated immutable Portal snapshot and provenance files only.

- Start from Task 4's committed clean head.
- Run `scripts/architecture-portal.sh version 1.0.29.0 canary`.
- Inspect generated identity, provenance, route inventory, source revision,
  Assembly lock digest, and immutable paths.
- Run `scripts/architecture-portal.sh check` and rerun version verification.
- Stage only generated snapshot/provenance files, inspect the diff and commit
  with `docs(portal): snapshot Product Build 1.0.29.0`.

## Task 6: Review and integrate through the queue

- Request an independent code review over the complete branch diff and resolve
  every actionable finding with targeted tests.
- Push only after local commits and verification are complete.
- Open a PR with `Closes #212`, full verification, version, documentation, and
  release-boundary declarations.
- Add `merge:queue`, verify exact-head full CI, squash merge, exact merge/main
  tree equality, and the post-merge main CI result independently.
- Close/update #212 and Project status only from live PR/Issue evidence.

## Version Management

- Product Build: `1.0.28.0 -> 1.0.29.0` because the first candidate was
  abandoned after review and allocated Build identities are not reused.
- Creator Web Host: `1.3.5 -> 1.3.6`, a compatible correctness/performance
  correction to the selection-zoom implementation.
- Contracts, Core Modules, Providers, and other Hosts: no version impact because
  their public behavior and identity do not change.
- Product Build `1.0.28.0` / Creator `1.3.5` remains an immutable, unmerged,
  unpublished rejected-candidate snapshot.
- Product Build `1.0.30.0` is reserved for #213; Stage 9 uses `1.0.31.0`.
- Snapshotting is documentation evidence only. No tag, Release, deployment,
  publication, or Channel promotion is in scope.

## Documentation Impact

Documentation impact: required.

Affected Portal pages:

- `/overview/`
- `/assembly/lmdj/`
- `/core/modules/web-runtime-platform/`
- `/hosts/overview/`
- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/platform/input/`
- `/platform/web-runtime/`
- `/product/capability-map/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Reason: selection-driven capture zoom and Product/Host identity are current
product facts. The Product Build allocation also requires an immutable Portal
snapshot from the clean committed integration source.
