---
id: github-release-asset-url-rewrite
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/actions/runs/33624132320
    observed_by: claude-fable-5-1
exit: gate:tests/build/release_transitions_test.py
---

# Publishing a Draft rewrites every asset `browser_download_url` from the untagged path to the exact tag path, so an asset snapshot that treats it as draft-invariant fails after GitHub has already published.

## Why

[[github-draft-html-url-rewrite]] settled this for the Release's own
`html_url`, and `_release_without_draft` correctly excludes it. The asset
snapshot kept `browser_download_url`, which GitHub rewrites the same way and
for the same reason: a draft's download path is
`/releases/download/untagged-<hash>/<name>` and becomes
`/releases/download/<exact-tag>/<name>` on publication.

The consequence is worse than a plain false negative. The comparison runs
*after* the publish PATCH is accepted, so `publish-release.yml` exits non-zero
on a Release that is already `draft: false` with every asset uploaded and the
exact tag `html_url`. The operator is told `GitHub Release assets changed
during publication` about a publication that fully succeeded, and the
in-workflow post-publication audit is skipped. Retrying cannot help, because
the state the comparison rejects is the correct published state.

The fake GitHub client hid it exactly as the `html_url` fake once did: it
rewrote `html_url` on publish but left asset download paths untouched, so it
certified the broken comparison. `lmdj-v1.0.41.0` (run `33624132320`) was the
first `web-hosts` publication and the discovery, the same
never-exercised-path class as [[github-draft-html-url-rewrite]],
[[draft-release-read-visibility]] and [[release-authority-fetch-credentials]].

## How to apply

Compare only genuinely draft-invariant asset fields across the publish
mutation: `id`, `name`, `label`, `content_type`, `state`, `size`, the
downloaded payload digest, `api_url` and `release_id`. Repository ownership of
`browser_download_url` is still validated in `github_api.py`; it is simply not
a pre/post invariant. When a fake models publication, rewrite the asset
download paths as GitHub does, or the fake will approve whatever the
production comparison gets wrong. If a publish workflow reports drift after the
PATCH, read the live Release state before concluding the publication failed.
