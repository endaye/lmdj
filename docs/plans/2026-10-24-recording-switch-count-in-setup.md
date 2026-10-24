# Restore the ordinary recording-switch journey after COUNT-IN re-land

Relates to #2112 and #2233. Base `8dd263239292c66ad12419ed4b9d683fdd5cd1e0`;
branch `fix/recording-switch-count-in-setup`, isolated worktree.

## Premises and remaining scope

C1–C3 and Creator C4 are already delivered; C4 #2377 actually merged as
`98c794d2bc774a9f1ee66adc8dac89ed05b7ed04`. Do not reimplement the producer or
ordinary consumer. COUNT-IN was restored by #2479, actual merge
`880535aee2cb238706e06bbc5628b16630240680`. Current Sequence SETUP has the
Count-in group and its Off/1/2 choices. The existing S3 preparation at line121
still asserts the group is absent. The current S3 spec and App are identical
to the preceding audit: both complete ordinary cases fail exactly there
(expected0/actual1, actual42.660s); no recording leg was reached. The old proof's
entire product tree equals this refreshed base, including #2481's live fix.

The first corrected preparation run reached recording: one complete case
passed and one failed on source onset (expected199/actual194 ticks), actual
61.825s. Preserve it. `control_runtime.cpp` samples the recording ingress frame
before reserving/enqueueing; `PatternTransportCoordinator::drive_inputs` retains
that original request frame. Native completion separately reports when audio
consumed the queue. The approved count-in design retains original frames and
explicitly distinguishes admission from later audible consumption. The existing
`eventFor` incorrectly uses the completion frame as the recording candidate
frame. The existing checksum-verified/lossless `readCountInJournal` is the
independent durable input oracle already used by the count-in journeys.

Still outstanding: use the real restored Count-in Off choice and prove its
pressed state before ordinary Record. Bind each retained candidate to its actual
Native sequence/correlation, kind, slot and session, retain its checked Journal
record and compute exact expected ticks from that original recording frame.
Do not overwrite the Native completion frame or change production timing.
Unretained cross-S releases still have no target candidate. Keep exact complete
Truth equality rather than introducing a tolerance. Keep the terminal proof of zero
count-in requests, the original request deadlines and every subsequent leg.
Uncertain/unverified: COUNT-IN-enabled switching, packaged fault combinations,
full candidate-host lanes and physical/audio acceptance. They remain separate
#2233/#2112 work; a green ordinary journey does not complete them. S5/I2c
product questions are not decided here.

## Declared files

1. This plan.
2. `tests/platform/web/creator/creator_web_recording_switch.spec.mjs`

No product/Facade/Host/SDK, deadline, workflow, release tool or portal source
change. Amend this declaration before expanding.

## Verification and far-side evidence

Run the entire two-case original recording-switch selection on the ordinary
production artifact and locked Chromium, workers1, with the original budgets:

1. Real SETUP choice is Count-in Off before Record; retain the final zero
   count-in-request assertion.
2. Source Press, actual queued/applied S and cross-S loop-Gate physical Release
   remain authoritative; a genuine refusal needs a new explicit gesture.
3. Target input, Perform return to A and optional terminal switch to B retain
   per-Pattern events and revisions.
4. Record-off checks the actual current A/B and complete committed Truth;
   Stop keeps that Truth; all Asset paths/lengths/digests remain equal.
5. Reload/reopen checks the entire expected Project and page-error absence.

Retain traces/JSON, exact test source and distribution/fixture hashes and the
observed audio endpoints. Preserve the prior negative result and any later
failure. This test-only Task may reuse the retained official clean #2481
production artifact because its complete source tree equals the refreshed
base; copy and verify all10 files and both official fixture hashes, and bind
the modified test bytes separately. It is not a new build or full Creator proof.
Run Node syntax, staged new-file ownership, whitespace, body lint and applicable
documentation declaration. Refresh main before commit and guarded merge;
independent current-head review and live protection still apply.

## Actual Task evidence

The initial restored-Off selection failed1/passed1 at the original exact Truth
assertion (61.825s); that failure remains retained. The corrected input oracle
then ran both entire original cases: 2 PASS, actual61.162s wrapper exit0.
All ten distribution hashes and two fixture hashes match the retained official
artifact; test-source bytes match the recorded inputs. Both actual complete
Truth snapshots reopen identically, both full Asset inventories match, and five
recorded Native/candidate pairs per case are retained with matching successful
attachments. Source, real cross-S release, target input, Perform return, optional
terminal B, Record-off, Stop and reopen all ran without reducing a deadline.
Both output endpoints report built-in MacBook Pro Speakers, no warnings.
The ten Native/ingress timestamp pairs happen to coincide in this successful
run; the literal probe below distinguishes the domains. The prior failed run
did not retain its raw candidate, so no sole-cause repair claim follows.

An external Node26 probe extracts the actual old/new `eventFor` functions:
for literal ingress1000/1250 versus consumption1028/1306 at origin0, independent
expected onset40/duration10 is met by the current calculator; the legacy one
returns41/11. This discriminates the two clock domains without claiming a
production mutation or rebuilding unchanged product code. Node syntax and
staged new-file ownership77 pass. Full Creator/candidate/COUNT-IN-enabled
switching, fault composition, devices and human listening remain unverified.

## Version Management

Version impact: none
Reason: existing browser preparation and its plan only; no shipped product API,
ABI, persistence, manifest, Product Build or snapshot change.

## Documentation Impact

Documentation impact: none
Reason: tests now follow the already documented restored Count-in Off behavior;
no current portal page or documented product fact changes.
