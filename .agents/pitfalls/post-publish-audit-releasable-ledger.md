---
id: post-publish-audit-releasable-ledger
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/34017371873
    observed_by: grok-4.6
exit: gate:tests/build/release_transitions_test.py
---

# The in-workflow post-publish remote audit reads canonical `main`'s still-`releasable` ledger against a GitHub Release that `publish-draft` has already published, so `publish-release.yml` exits non-zero after a genuine publication.

## Why

`scripts/release.sh publish-draft` mutates only the GitHub Release. The intent
ledger stays `releasable` until a later docs Pull Request records
`disposition: published`. Canonical remote audit loads that ledger from
protected `main`, not from the just-published Release, and the closed check
`non-published intent identifies an already published GitHub Release` is
therefore the expected post-PATCH state.

`publish-release.yml` still runs `audit --remote` as its last step. A green
`release status: published` followed by a red job is a ledger-lag false
negative, not a publication failure. Retrying the workflow cannot help: the
Release is already `draft: false`, and a second dispatch cannot create.

This is the ledger-lag twin of
[[github-release-asset-url-rewrite]], which failed inside `publish-draft`
itself. `lmdj-v1.0.42.0` (run `34017371873`) is the first `web-hosts`
publication whose PATCH succeeded and then hit this audit.

The unit test
`test_nonpublished_intent_rejects_an_already_published_release` already
enforces the audit finding. It cannot make the workflow job green, because the
ledger on `main` is still the pre-publication row.

## How to apply

After `publish-draft` prints `release status: published`, read the live
Release by numeric ID before concluding the publication failed: `draft` must
be false, `prerelease` must match the Channel, the `html_url` must be the
exact tag URL, and the six-asset inventory must match the prepare plan. Do
not retry `publish-release.yml`. Record `disposition: published` and the
publication evidence in a docs Pull Request; only then will `audit --remote`
report the matching published intent. Deployment remains a separate
authorization and must not be inferred from either the failed job or the
successful PATCH.
