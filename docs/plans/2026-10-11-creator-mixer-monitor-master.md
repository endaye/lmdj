# Creator D04 MASTER monitor consumer

## Task and approved result

This is the independent MASTER consumer Task within
[Desktop Final follow-up I5](2026-10-09-creator-desktop-final-followup.md).
The owner-approved [D04 decision](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)
makes MASTER and ENC4 two controls for the same device monitoring level,
0–100%. The existing device preference survives reopening. This level includes
metronome clicks, never changes Project Truth or Undo history, and is after
the recorded, resampled and exported PCM path.

MASTER is the rightmost fourth vertical fader in Perform's live controls.
It reads and writes the existing App monitor level; moving either control
updates the other's displayed value. It is independent of FX gestures,
Performance event recording, FX / MORE and HOLD. The existing range and
44-design-unit input target remain. It has the same unavailable/restoring
boundary as ENC4; a refused Session update must not change the readback or
the stored preference.

## Refreshed source premises

Inspected source: fresh `origin/main`
`4a2b26f03a1e628882e907c92a9b9411b48e110d` on 2026-10-11. The original
`edd3d24e5e377ad6197b253a10f2f9b381f49e42` plan/test drafts were backed up
with their SHA-256 identities before fast-forwarding this worktree. The protected
main worktree is retained at its own revision; source reads use the fetched
revision and this Task's isolated worktree.

- `MonitorOutputSession` declares the synchronous monitor level and setter.
  `runtime_session.mjs` applies the level to the existing monitor gain after
  the capture tap; Creator's metronome uses that monitor destination.
- App owns one `monitorVolume` state/ref, preference restoration with
  current-Session readiness, the ENC4 setter and the IndexedDB write. The
  setter is the authoritative positive control for this consumer Task.
- `PerformSurface`'s actual props and `FxSliderBank` mount pass only FX
  gestures and values. The live bank renders Filter, Delay and Reverb;
  there is no MASTER binding. Existing CSS fixes that bank to three columns.
- `OverviewDisplay` already displays ENC4 Output and its percentage. It
  needs no new monitor state or additional overview consumer.
- #1989 is merged as `ea657b3e6f6346fcafe0c4fbeb7667518f073244`; its unified
  current Pad reducer and Bank/navigation behavior are retained. #1991 is
  merged as `083ac62812564266721c664dd49915d636b94123`; its owned inspections
  and browser fixtures do not add another monitoring or D04 producer.

The existing producer premise is valid. The missing D04 MASTER premise is a
consumer gap, not a missing Core operation. This Task adds no volume state,
AudioNode, Core API, Contract or preference key. It does not implement or
decide independent filter parameters, Mute/Solo lifecycle or output metering.
The D04 defaults/ranges, live Mute/Solo lifecycle/recording-start state and
meter display questions are now approved in #1999, merged as the inspected
revision. Their independent source implementation and acceptance remain pending;
this MASTER consumer does not implement those capabilities.

## Ownership and integration

Use short-lived `feat/mixer-monitor-master` in
`/Users/endaye/Projects/lmdj-wt-mixer-monitor-master`, created from the inspected
source with `--no-track` and command-local `core.symlinks=true`. It has no
upstream to protected main. Retain all other worktrees and processes.

#1992 at final head `8b48bec8e52f9fc4367a822d5dd5d382f673e07d` was merged as
`a98ae01c4f033c78221fc961f6207c7fe5cabfd7`. Its App, PerformSurface and
Creator Portal changes for Pattern transport/Launch are in this worktree.
Its mbp-m4-pro worktree and Codex terminal were observed earlier, and a single
section-coordination question was enqueued as `msg_cc0ef960558d`. Enqueue is
not owner consent or proof of a new turn; no reply was observed or inferred.
After its actual merge, the Goal owner authorized this independent consumer
Task to resume. Preserve all merged S2 observation, selection and
Launch wiring, existing browser specs and the active frozen proof inputs.
The refreshed base also contains #1998's `transportLaunchOpen` idle/stopped
Performance-phase gate; this Task retains it. The Goal owner's separate App
history-refresh work owns that section, not this monitor setter/prop wiring.

The Numeric Task owns its Sample parameter paragraph in the same Portal
file. MASTER's Portal scope is a separate Perform MASTER paragraph next to
the existing Output Volume description, with the existing V4 omission
wording made explicitly historical. Do not edit the Numeric paragraph or
the shared parent follow-up plan. Coordinate actual same-file sections;
worktree isolation alone does not resolve ownership.

All heavy Portal, Creator browser and Core lanes are serialized with the
Goal owner's active proof. No concurrent heavy lane is authorized here.

## Declared files

One reviewable Task, exactly seven declared files:

1. `apps/creator-web/src/app.tsx`
2. `apps/creator-web/src/components/perform_surface.tsx`
3. `apps/creator-web/src/components/fx_slider_bank.tsx`
4. `apps/creator-web/src/styles.css`
5. `apps/creator-web/test/monitor_output_controls.test.tsx`
6. `apps/docs-site/docs/hosts/creator-web.mdx`
7. `docs/plans/2026-10-11-creator-mixer-monitor-master.md`

Extract the existing App update into one callback used by ENC4's relative
turn and MASTER's absolute range value. Preserve its same-Session restore
guard and publish readbacks/preference only after the Session accepts the
value. Pass this controlled binding through PerformSurface to FxSliderBank;
the fourth fader never calls engage/move/release FX handlers.

## Lowest-tier verification and acceptance

The new isolated component spec mounts the actual App and Perform consumer
with a typed controllable Session fixture. Each test fixes a distinct fact:

- A remembered 0% restores and enables both controls; unresolved or retired
  preference reads do not enable the current Session's control.
- MASTER changes the same Session level, ENC4 and its upper readback;
  ENC4 changes MASTER, with both endpoints staying within 0–100.
- A terminal setter failure keeps the last accepted readback/preference.
  Unavailable monitoring disables MASTER rather than pretending to apply.
- Reopening restores the last accepted value. Perform navigation, FX / MORE
  and HOLD do not reset it; monitor input emits no Performance FX/event or
  authoring call and creates no Undo entry.

Run this focused Vitest spec, existing monitor preference tests and the
existing ENC4 restoration/ownership regressions at their original bounds,
then Creator TypeScript checking. Stage new files before the Task ownership
suite. Inspect non-main branch, exact staged file list and cached diff check;
after the Conventional Commit, inspect committed files and clean worktree.

Portal source-fact checking must run before commit when the Goal's
heavy-resource slot is free; do not commit until that check completes.
Every selected batch-only lane then runs on this Task's committed head,
also serialized with the Goal's heavy-resource slot.
Current-head review, live protection/conversation checks and guarded squash
remain shipping requirements. Component fixtures do not establish hearing,
physical input, browser layout, Figma fidelity, release or deployment proof.

## Version Management

Version impact: additive Creator MINOR debt, coordinated by the parent
follow-up's V1 settlement after actual delivered scope is known. Inspected
Creator manifest/package version is `6.0.0`; no version number is allocated
here. This Task changes no active manifest, Product Build/Assembly, SDK or
Contract identity, and initiates no release or deployment.

## Documentation Impact

Documentation impact: required — update current Portal route
`/hosts/creator-web/` in this Task to describe the shared Perform MASTER and
ENC4 controls, same preference/readiness, and monitoring-only scope. The
implementation source facts require `scripts/docs-site.sh check` before
commit, serialized with the Goal's heavy work.

## Pitfall Impact

Pitfall impact: none at planning time. The `area:creator` open ledger entries
were read; keep real browser/physical evidence distinct and diagnose failures
from their retained artifacts. Existing shared-host capacity and task-upstream
rules are observed without starting duplicate heavy lanes or tracking main.
Record a qualifying recurrence only if this Task actually encounters one.

## Progress

The two prepared drafts are preserved outside the worktree with their original
hashes; tracked files were clean, the Task branch had no upstream, and the
worktree fast-forwarded to the inspected main revision. All seven declared files
are drafted; the App owns the single accepted update and preference, and the
fourth Perform range only consumes that binding. The unchanged vertical range
keeps its 44-design-unit target; four-column hardware layout retains that width.
The MASTER bank reserves the minimum width for four targets, three 4-unit gaps
and two 4-unit section insets within the existing fixed touch screen. This
source geometry does not replace actual browser/physical layout acceptance.

Lowest-tier evidence on the uncommitted source draft:

- A first baseline run exposed a test-fixture timing error: the monitor read
  finished while the real retained-Project boot journey was still opening.
  Awaiting the existing ready Perform key corrected that fixture; the failure
  is retained and is not counted as a product RED.
- Corrected baseline at the inspected main failed because the real Perform
  surface had no slider named MASTER. With the consumer wiring, all six new
  App tests pass, including shared readbacks, zero, rejected updates, current
  Session restoration, reopening, groups/HOLD and no FX/authoring call.
- `npm --prefix apps/creator-web test -- --run test/monitor_output_controls.test.tsx
  test/monitor_volume_preference.test.ts test/perform_surface.test.tsx`:
  84 tests passed across three files, including the existing S2/Launch gates.
- `npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx
  -t 'output-volume restore|ENC4 restores device volume'`: the three selected
  existing restoration tests passed; the other 132 workspace tests were not
  selected. This is not a full workspace/browser proof.
- `apps/creator-web/node_modules/.bin/tsc --noEmit` from `apps/creator-web` passed.
  React best-practices review found no new duplicate state, effects or global
  listeners; the existing Session guard and controlled native range are retained.

Portal changes are confined to the historical V4 MASTER omission sentence and
a new Perform MASTER paragraph after the Output Volume scope. The Numeric
Sample parameter paragraph is untouched.

The Goal owner granted an exclusive heavy-resource window for the required
Portal precommit check. This worktree had no Portal dependencies, so the stable
`scripts/docs-site.sh install` first installed the locked dependencies and
returned zero. The complete `scripts/docs-site.sh check` then returned zero
at 2026-10-10 17:48:41 UTC (2026-10-11 local date): all 176 Portal tests,
52 page validations, 10 source diagrams and 20 outputs, generated facts,
existing release documentation, TypeScript, optimized production build, and
the far-side 50 rendered routes and internal links passed. No Rspack stall
or cache recovery occurred. The actual terminal session was `46156`, npm
PID `37589`, from 17:47:40 to 17:48:41 UTC. The retained full log has SHA-256
`79e9d320de6c3b01ce67f2479e02610573589cd8e37b8068c1e99d671a35ec33`.

Before and after that check, HEAD remained the inspected main revision,
all seven declared source hashes and the staged inventory were identical,
the index tree remained `7eae07ed6412ee4a47f7730a4bdb7976078960eb`, all ten
tracked links remained real symlinks, and there were no unstaged tracked
changes. External evidence is retained under
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-11-master-consumer/`;
the before, command and after receipts bind the log, source hashes and actual
exit status. Dependency caches and the two original draft backups are retained.
The heavy-resource window was returned immediately after completion; no
Creator browser or Core suite was started in it.

Before commit, a fresh origin fetch confirmed main was still
`4a2b26f03a1e628882e907c92a9b9411b48e110d`, with no intervening source or
governance change. This verification-record update changes only this plan;
the already verified product and Portal source facts are unchanged. Commit,
current-head review, committed-head batch-only lanes, merge and applicable
browser/physical acceptance remain separate pending boundaries.
