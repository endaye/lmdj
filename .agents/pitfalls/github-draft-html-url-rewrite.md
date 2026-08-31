---
id: github-draft-html-url-rewrite
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/issues/337
    observed_by: grok-4.6
exit: gate:tests/build/release_transitions_test.py
---

# Publishing a Draft Release rewrites html_url from untagged-* to the exact tag URL

## Why

GitHub Draft Release `html_url` values use
`/releases/tag/untagged-<hash>`. Publication rewrites that field to
`/releases/tag/<exact-tag>` on every genuine publish. A pre/post snapshot that
treats `html_url` as draft-invariant therefore fails on 100% of real
publications and skips the in-workflow post-publication audit, while a fake
GitHub client that keeps a tag-shaped draft URL certifies the broken
comparison. This stayed hidden until the pipeline's first end-to-end
publication (`lmdj-v1.0.36.0`, run 32982586705), the same never-exercised-path
class as [[draft-release-read-visibility]] and
[[release-authority-fetch-credentials]].

## How to apply

Compare only draft-invariant Release fields across the publish mutation
(`id`, `tag_name`, `target_commitish`, `name`, `body`, `prerelease`,
`make_latest`, `upload_url`, assets). Assert the expected transformations
explicitly: `draft` is false, and `html_url` equals
`https://github.com/<repository>/releases/tag/<tag>`. Fake GitHub clients
must create drafts with an `untagged-*` URL and rewrite it on publish. The
enforcing gate is `tests/build/release_transitions_test.py`.
