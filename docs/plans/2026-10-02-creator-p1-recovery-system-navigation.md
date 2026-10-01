# P1 recovery destinations from System

The current main recording-recovery prompt remains reachable in System, but
its direct mode setter leaves System open and its target editor hidden. The
independent actual App review and two regressions reproduce this on 2666ec03.

## Declared files and verification

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `docs/plans/2026-10-02-creator-p1-recovery-system-navigation.md`

Use the existing workspace navigation function for recovery destinations. It
closes System, clears pressed input and retains the established Perform-leave
and transport ownership boundaries. Add two actual App regressions: More
options opens its visible Sequence editor without mutation; Open Sequence after
a refused Keep opens the visible recovery list with the take retained. Require
both to fail before the source fix and pass afterwards, then all Creator unit
tests, TypeScript and staged scope. Existing System transport/focus assertions
remain strict. Final packaged lanes run on the settled candidate.

## Version Management

Version impact: deferred to the coordinated P1 candidate Creator PATCH.

Documentation impact: none
Reason: restore the already documented recovery destination and reuse existing
navigation without changing portal facts, public Contracts or identities.
