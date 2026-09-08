---
id: draft-release-read-visibility
area: ci-release
status: open
recurrences:
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/issues/335
    observed_by: claude-code/fable-5
exit: none
---

# GitHub hides Draft Releases from read-scoped identities, so no read-only stage can verify a Draft

## Why

GitHub exposes Draft Releases only to identities with push (write) access; an
Actions installation token holding `contents: read` receives 403 on
`GET /releases/{id}` for a draft, and the list endpoint silently omits drafts.
The release pipeline design assigned Draft verification (`verify-draft`) to the
read-only `preflight` job of `publish-release.yml` — a stage that can never see
the object it must verify. The contradiction stayed hidden because preflight
had never passed its earlier credential failure
([[release-authority-fetch-credentials]]), so the first run to reach
`verify-draft` (lmdj-v1.0.36.0, run 32971112709) was the discovery. The
tooling's broad exception wrapping reported it as `GitHub Release projection
is unavailable`, which reads like an outage, not a permission boundary.

## How to apply

- Any check that must read a Draft Release belongs in a stage that holds
  `contents: write` — in this pipeline, only the `publish` job after the
  `release` Environment gate. Never assign draft-reading work to a read-only
  job; it fails 100% of the time, not intermittently.
- The read-only exact-tag remote audit is still valid in preflight: with
  drafts invisible it reports the releasable tag-without-Release state as ok
  and defers Release metadata/asset checks to the write-scoped stage.
- Spec amendment 2026-08-26 in
  `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`
  §8.4 records the boundary; the workflow contract test asserts preflight has
  no `verify-draft`.
- No gate exit yet: "which API objects are visible at which token scope" is a
  GitHub-side property that repo-static checks cannot prove; the workflow
  contract test pins this instance only.
