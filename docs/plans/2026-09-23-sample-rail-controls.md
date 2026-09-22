# Sample rail controls (#1517)

Remove the Sample touch workspace Bank row and Pad grid. Keep one rail Bank
selection and Pad matrix. Move the old grid's editing selection, empty-slot
file picker and drag/drop replacement entry to that matrix, retaining the common
input controller for pointer/keyboard press, release and cancellation. Capture
continues to own its selected slot while armed. Remove duplicate-only styles and
keyboard mapping, retaining the shared mapping.

Sound Set installation keeps a distinct target picker, explicitly labelled
Install target Bank, with no write to the playing Bank. The initial target is the
active Bank on mounting the Sound Set surface; subsequent rail navigation does
not silently retarget an installation. BankSelector remains shared UI code.

Declared files: `apps/creator-web/src/app.tsx`, components
`sample_surface.tsx`, `pad_surface.tsx`, `soundset_surface.tsx`,
`bank_selector.tsx`, `apps/creator-web/src/styles.css`,
`apps/creator-web/test/workspace_shell.test.tsx`,
`apps/creator-web/test/soundset_surface.test.tsx`,
`apps/creator-web/test/audio_lifecycle.test.tsx`,
`apps/docs-site/docs/hosts/creator-web.mdx`, this plan, and any packaged Creator
spec selectors that name the removed duplicate Pad controls.

Verification: revise the Sample shape assertion to prove metadata → waveform →
controls in touch, exactly one rail Bank control per Bank, and 16 rail Pads.
Assert rail Bank → visible Pads → selected Sample slot; preserve existing
empty-slot import, drag/drop, pointer/keyboard/cancel and focus-return tests on
the surviving matrix. Assert Sound Set target changes preview input without
changing the playing Bank. Full Creator Vitest and TypeScript, portal check, and
staged path ownership. Unit tests do not claim physical audio/touch acceptance.

## Version Management

Version impact: none — Creator UI integration repair, no public Host API,
Contract, Module, Provider or manifest identity changes. No Product Build or
independently published Host package is allocated here.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Describe the single Bank/Pad control surface and separate install target.

## Pitfall Impact

Pitfall impact: none — product presentation/control wiring, covered by regression
tests. Do not reinterpret unrelated physical acceptance as passed.
