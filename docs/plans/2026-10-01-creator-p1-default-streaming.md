# P1 T5: independently playable default Bank A

Relates to #1663. Depends on T1, T2 and T3; this stacked branch retains their
commits until their integration heads can replace those ancestors.

## Declared files

- `products/lmdj/creator-defaults.mjs`
- Creator `src/app.tsx`, `src/main.tsx`, `src/state/default_seed.ts`,
  `src/runtime/{default_seed_controller,input_controller}.ts`,
  `src/components/pad_surface.tsx`
- Creator `test/default_seed.test.ts`, `test/default_seed_controller.test.ts`,
  input controller and Pad/workspace tests
- `tests/platform/web/creator/creator_web_default_streaming.spec.mjs`, accessibility journey and Creator proxy upstream configuration
- Current Creator portal page and this plan

## Behavior and verification

Product Assembly derives the exact default Set identity from its original corpus
Catalog; Host consumes only that identity and Facade DTOs. First auto-create claims
a per-device initialization journal under a browser lock before seeding. Manual
create, duplicate and import never claim it. Invalid or unavailable journal storage
refuses automatic seeding rather than overwriting content.

Four workers acquire independent slots outside Project authoring serialization.
Only installation and verified Runtime publication hold the short Project lane.
Persist command identity before install for exact receipt replay after a crash.
Ready follows durable receipt and same-Project Runtime publication; a failed
publication remains saved/unavailable. Persist terminal ownership, never refill a
ready/deleted/undone slot, and retry conflicts only while the original owned target
is still empty. Loading/Processing/Failed Pads cannot trigger or open an empty-Pad
capture/file-picker action. Other Pads remain usable.

Lowest tests: first claim and manual-project refusal, malformed journal refusal,
progressive readiness before other downloads, acquisition concurrency ceiling,
partial failure/retry, committed receipt resume, revision conflict ownership,
delete/reload/Undo non-refill and blocked Pad input. Browser proof must observe real
Facade installs and native VoiceStarted while other assets remain blocked. The
actual Worker origin is bound only after T3's live GET/hash verification.

## Version Management

Version impact: additive Product Assembly default selection and Creator behavior;
coordinated P1 Product Build/Host settlement is required in T8. No Contract ID is
changed and no release or Channel promotion is initiated here.

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: first-project initialization, per-Pad readiness and persistent non-refill ownership.
