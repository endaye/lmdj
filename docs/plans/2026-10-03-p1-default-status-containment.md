# P1 default status containment

## Problem

The independent actual Native Chromium layout diagnosis on T6 found a stable
32-pixel console-centre displacement. Its root flex-column had the Pad
recording row and failed-default retry button as siblings of the device. Their
combined 64-pixel height shifted the device by half that height. Four reads
over 4.3 seconds retain the same defect and the original `centreDelta <= 2`
assertion fails. Default retry/status alone has the same root-placement cause;
waiting does not remove these siblings.

## Task and declared files

On `fix/p1-default-status-containment`, based on correction composition
`b227f81674e228b0e3a30999391821024ebdef3a`, move the existing default error,
retry and prepare controls into the existing `touchWorkspace` content. Preserve
their full handlers, visibility conditions, text and accessibility roles.
System navigation and the Capture status correction remain separate Tasks.

- `apps/creator-web/src/app.tsx`
- `docs/plans/2026-10-03-p1-default-status-containment.md`

No component, CSS, geometry threshold or instrumentation seam is added. Every
other file, including R20 request admission, receipt recovery, Native code,
default corpus, manifests, quota and recording guards, retains the parent's
exact mode and blob.

## Verification

Before commit run the full Creator unit suite serially with unchanged budgets,
TypeScript/Vite, Platform tests, staged ownership and whitespace checks. Retain
the independent original Native layout RED and its actual product identities.
After commit run the complete newly changed Creator lane on a clean candidate,
including the original hardware layout journey and its full strict dimensions,
centre bound, input and responsive legs. The full proof and current independent
review remain required; a unit/compile check is not called Native geometry
acceptance. Existing full Deploy evidence may be cited only with its actual
producer head and unchanged canonical input key. All original failed proofs
remain separate; none is attributed to this layout repair without evidence.

## Version Management

Version impact: none. This pending P1 correction restores the existing console
layout, changes no public Contract or version identity, and allocates no
Product Build. Coordinated P1 version settlement remains a separate Task.

Documentation impact: none. The relocation restores documented hardware-console
geometry and preserves existing controls and behavior; it introduces no new
portal route, architecture, identity projection or Source fact requiring a
portal page or diagram change.
