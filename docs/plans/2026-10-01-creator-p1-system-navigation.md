# P1 T7: contextual tools and System subpage

Relates to #1665. Depends on the musical gesture, default streaming and Pad capture Tasks.

## Declared files

Creator `src/app.tsx`, `src/styles.css`, new `src/components/system_surface.tsx`,
workspace/audio lifecycle/System tests; `tests/platform/web/creator/fixtures/creator_navigation.mjs`,
Creator audio fixture and all changed accessibility, browser, Candidate, capture,
lifecycle, System and sample browser call sites; shared `tests/platform/web/candidate_journey.mjs`;
this plan and current Creator portal page.

## Behavior and verification

System is a bottom-right touch subpage over the retained creative page. Four
physical page keys remain. Native entry cancels unfinished Pad capture without
committing it; returning restores the entry focus and original creative page.
Opening System neither suspends nor commands the global Pattern transport.
Actual Suspend Audio, MIDI permission, report export and diagnostics move inside
System. Registered Provider capabilities and permission revocation live there;
Provider selection and analysis authorization stay beside the Slice action.
Project owns Sound Sets; Sample owns Slice. Contextual failure recovery remains
reachable on the page that owns the failed operation.

Lowest tests: System heading/return focus, mode retention, playing transport with
zero navigation commands, permission revocation preserving other grants and
refusal on failed refresh, existing activation/lifecycle and keyboard journeys.
Browser helpers use real System navigation for permission actions. Capture-modal
report instrumentation retains its explicit programmatic-click limitation.

## Version Management

Version impact: Creator UI changes settle with T8's coordinated Product/Host
allocation. No new Provider or Project Contract is introduced.

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: contextual content/tool navigation and actual System ownership.
