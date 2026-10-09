# Creator 四区交互联动文档

## Task premises

- Source audit base and task worktree base: `50d79fa894f3483d6593d50fafcfd3e1bff28ce0`
  (`origin/main`, fetched 2026-10-10).
- Outstanding: the existing Creator Host page describes features, but does not
  provide the requested four-region, page-by-page control/state/effect matrix.
  Inventory comes from the mounted components in `apps/creator-web/src/app.tsx`,
  their handlers, reducers, input controller, and existing component tests.
- Delivered already: four-region shell, six modes, System, global transport,
  Sample editing, Sequence layers, Perform, Sound Sets, Slice, recovery and
  diagnostics. Document their actual wiring; do not implement or change them.
- Uncertain: deployed-build parity and physical-device acceptance. This Task
  audits current source and automated UI evidence, and explicitly labels that
  boundary rather than asserting device acceptance.

## Declared files

- `apps/docs-site/docs/hosts/creator-interactions.mdx`: the complete Chinese
  interaction matrix, state restrictions, all sixteen Pad addresses, transient
  pages, cross-region examples, and source/test inventory.
- `apps/docs-site/docs/hosts/creator-web.mdx`: link to the matrix.
- `apps/docs-site/sidebars.ts`: include the new current manual page.
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`: move the independent
  current-page inventory pin from 51 to 52 for the newly added manual page;
  retain the existing snapshot completeness assertion.
- `docs/plans/2026-10-10-creator-interaction-map.md`: scope and verification.

## Verification

- Trace every mounted interactive component and each distinct gesture family
  back to the owning handler; distinguish local view state, audio state,
  Workspace preferences, authoring commits and recoverable recordings.
- Run existing Creator hardware-console, workspace-shell, Pad keyboard/input,
  Sample controls, Sequence surface/grid, Perform, Capture, Sound Set, Slice
  and encoder tests. These corroborate the described branches; they do not
  provide physical-device or deployed-build acceptance.
- `scripts/docs-site.sh check`: metadata, sources, links, routes, types,
  production rendering and existing portal checks.
- After staging new files, `python3 tests/build/ci_change_scope_test.py`:
  ownership/admission check for the new tracked paths.
- Render the new page in a browser and inspect readable tables and navigation.
- Before commit and final premerge, refresh `origin/main` and reconsider any
  intervening Creator behavior or governance changes.

## Version Management

Version impact: none
Reason: source-derived documentation only; no runtime, Contract, Assembly or
Product Build changes or allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-interactions/ /hosts/creator-web/
Reason: add the requested current interaction manual and its entry points.

## Pitfall Impact

Pitfall impact: none — reason: this Task records product behavior derivable from
source. Read the portal-content and acceptance-journey pitfalls; a green portal
build verifies rendering and metadata, not every sentence or physical behavior.

## Results

- Existing Creator verification: 12 files, 417 tests passed on the refreshed base. Command:
  `npm test --prefix apps/creator-web -- --run test/hardware_console.test.tsx test/workspace_shell.test.tsx test/pad_surface_keyboard.test.tsx test/input_controller.test.ts test/sample_controls.test.tsx test/sequence_surface.test.tsx test/sequence_grid_edit.test.tsx test/perform_surface.test.tsx test/capture_panel.test.tsx test/soundset_surface.test.tsx test/candidate_surface.test.tsx test/encoder_input.test.ts`.
- Browser reading check passed at 1440×1000: seven-column effects tables are
  readable, section anchors navigate, search filters rows and Clear restores
  the complete inventory. Exported HTML retains every table and data row.
- Staged ownership and exact-head lane evidence are recorded in the shipping
  Pull Request after execution.
- Initial portal check correctly refused the new page with `52 !== 51` in
  the independent completeness pin. Update the inventory constant alongside
  the page addition; do not derive it from the directory or weaken the test.
- Before commit, refresh found `origin/main` at
  `864c0f061033a7f0c3488f1908a8817516cd3b62`. Rebased this owned, uncommitted
  documentation Task onto that revision. The relevant merged change #1913
  changes Pad display traversal and Tab order, including the Set mapping
  preview; slot identity and handlers remain stable. The manual now includes
  the current bottom-left-first matrix. #1928 changes touch sizing, with no
  changed mounted controls or callbacks. #1910 adds capture-independent
  monitoring inside the Runtime without introducing a new Creator control.
  The selected Creator suites passed (12 files, 417 tests) and the complete
  portal check passed with 50 routes and internal links valid on this refreshed
  base. The manual contains 21 tables and 241 data rows.
