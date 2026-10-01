# Creator P0.3：删除 Pad 声音并保留 Pattern（#1661）

## Outcome and authority

Implement the Delete control for the selected Pad through Domain, Project I/O,
Facade, Web Host and Creator. Based on the 2026-09-29 workflow and the accepted
2026-09-30 Undo/Redo semantics. Baseline: `722ccb80` on an isolated
`feat/creator-pad-delete` worktree. The Task includes verified commit, push,
current-head review and squash merge; it does not release or clean worktrees.

## Behavior

- Clear the Pad binding and restore default playback; retain all Pattern events,
  Assets and bytes. Reassignment makes the existing rhythm use the new sound.
- Expose an explicit typed Domain deletion and Facade/Host `pad.delete`. Lower
  deletion to the existing canonical `AssignPad` with null Asset for durable
  storage and receipt identity; no new persisted transaction dialect is needed.
- Commit through the existing session history: one changed Pad is one action;
  Undo restores the complete binding/parameters, Redo reuses retained artifacts.
  A delete of an already empty/default Pad creates no history entry.
- Stop the selected voice and clear its preview, then publish the derived Runtime
  Bank after the successful authoring commit. Preserve recording, recovery,
  writer ownership, revision, command-replay and failed-publication guards.
- Cancellation is Pad-scoped. Refused commands and exact retries preserve newer
  Facade/Host import ownership; successful fresh commits return exact cancelled
  tokens. Staging cleanup is best effort after commit, without resurrecting token
  authority or misreporting a saved deletion. Cancel queued/in-flight byte imports and decoded
  long-source work for the target, clear its failed transient state, and prevent
  superseded results from publishing. Other Pads' operations remain owned by
  their producers. Cancellation itself is not an Undo action.
- Current file/capture import and long-source decode are the existing Pad-owned
  producers. Per-Pad default-Set network streaming (#1663) and background
  Chop/Stem target-Pad processing (#1670) are not implemented by this Task; their
  later producers must obey the same cancellation/publication boundary. Existing
  source-based Slice analysis has explicit adoption and revision guards, rather
  than owning a target Pad during analysis.
- Delete is a touch-screen action, with selected Pad identity and disabled reason;
  no deletion gesture is added to the performance Pad plane. Existing Undo means
  no additional delete confirmation is needed.

## Declared files

- Domain `commands.hpp`, `command_handler.cpp`, `command_handler_test.cpp`.
- Project I/O `project_store.hpp/.cpp`, `authoring_history_test.cpp`.
- Project Cooker `project_cooker.cpp`, `project_cooker_test.cpp`: empty Pad events
  remain in Truth and are omitted from the derived audible event list; assigned
  Asset corruption remains an error. This supersedes the original proof plan
  unassigned-event failure behavior to satisfy #1661.
- Facade `application.hpp/.cpp`, a dedicated `pad_delete_test.cpp`, its CMake
  registration and root coverage inventory; existing operation-inventory and typed failure-boundary tests
  only where the public operation is pinned.
- Web Platform `control_runtime.cpp`, `bridge.cpp`, `protocol.mjs`,
  `runtime_session.mjs`, `runtime_types.d.ts`, corresponding Host, protocol,
  Session and source-boundary tests.
- Creator `runtime_types.ts`, `sample_actions.ts`, `sample_state.ts`,
  `sample_surface.tsx`, `long_source_editor.tsx`, `styles.css`, app capability wiring, and their focused tests/fixtures.
- Packaged Creator browser deletion journey under `tests/platform/web/creator/`.
- `.agents/pitfalls/macos-fixture-transfer-adds-appledouble.md`: retain the
  cross-host fixture-transfer failure and its recovery procedure.
- Current Portal Authoring Domain, Project I/O, Facade, Project Cooker, Web Platform and Creator
  pages; this plan and a focused acceptance record if needed.

## Verification

Start with the existing Domain command and Project I/O history baseline. Add
lowest-tier facts for deletion, invalid/stale/refused commands, exact replay,
unchanged Pattern events/assets, history/no-op/failure/reopen, cancellation and
late-result isolation. Dedicated Facade tests avoid enlarging budget-bound
Sample surface shards. Web tests check stop/publication and the operation
inventory. Creator tests cover loaded, pending, failed and empty states.

The packaged journey exercises delete -> silence/empty -> Undo -> restored
binding/parameters -> Redo -> empty -> reassign -> existing events retained ->
reopen with persisted Truth and an empty history. Keep failures and platform
skips explicit. Physical listening, microphone and device lifecycle acceptance
are not inferred from browser automation.

Run relevant native and JS tests, Creator/Web proofs, `scripts/docs-site.sh check`,
new-file ownership, and every final classified batch-only lane before merge.
No timeout, coverage floor, owned lane or journey leg is relaxed. New assertions
catch specific behavior defects; no new repository-wide gate is introduced.

## Version Management

Version impact: additive Domain, Project I/O, Project Cooker, Facade, Web Platform and Creator
capabilities owe MINOR changes at the next coordinated version settlement.
This feature Task preserves manifests/Assembly identities, following the ongoing
Creator parity feature/cut split. Canonical null-AssignPad persistence keeps
existing readers compatible; no Contract schema or transaction format change.
Product allocation and immutable snapshots belong to that version settlement.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/authoring-domain/ /core/modules/project-io/ /core/modules/project-cooker/ /core/modules/application-facade/ /core/modules/web-runtime-platform/ /hosts/creator-web/
Document deletion, Pattern/Asset retention, session history, cancellation and
Runtime publication with derived identities. Preserve frozen snapshot contents.

The existing source diagrams retain the same Host → Facade → Store/Cooker flow;
this Task changes command behavior without changing that dependency topology.
