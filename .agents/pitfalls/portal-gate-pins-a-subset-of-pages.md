---
id: portal-gate-pins-a-subset-of-pages
area: docs-governance
status: open
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/470
    observed_by: Claude Code (Opus 5)
exit: none
---

# The Portal gate pins content on a subset of pages, so every other page can go stale silently — and a Build snapshot then freezes whatever they say

## Why

`scripts/docs-site.sh check` passing is routinely read as "the current pages are
correct". It does not mean that. The gate asserts derived identities
mechanically — routes resolve, links resolve, the Build matches the manifests —
and it asserts *content* only where a test names a page. Today that is
`overview/index.mdx`, `core/overview.mdx`, `product/capability-map.mdx` and
`operations/testing-and-proof.mdx`, in `content-inventory.test.mjs` and
`repo-facts.test.mjs`. Every other page is unpinned prose.

Allocating Product Build `1.0.45.0` made that concrete. The Task updated the
four pinned pages, because those were the ones that turned the gate red. Nine
unpinned pages kept Build 44's version numbers in the present tense, and
`contracts/soundset.mdx` and `product/workflows.mdx` kept saying that
`soundset.audition` was served by three native Hosts only, that the Web bridge
and protocol had not registered it, that Creator had no audition control, and
that #900 still blocked browsing and installing. All four had been false since
`45756035`, `917decee` and `f1293997`.

The gate was green throughout, before and after. Nothing in it can tell a true
sentence from a false one.

The compounding half is that a Build snapshot **freezes whatever the pages say
at cut time**, and the snapshot is immutable by policy. So an unpinned page that
has quietly gone stale does not merely mislead until someone notices — it is
preserved, permanently, in the artefact that is supposed to describe that Build.
An external reviewer found this in `1.0.45.0`; the errata is in
`operations/version-and-release.mdx` under 不可变性.

This is not [`portal-snapshot-not-deferrable`](portal-snapshot-not-deferrable.md).
That entry is about *when* a snapshot must be cut. This one is about *what a
green check proves* about the pages going into it.

## How to apply

Before cutting a Build snapshot, do not rely on the gate to find stale prose.
Instead:

1. **Diff the narrative surface, not just the pinned pages.** For every version
   the Assembly moves, `grep` the current pages for the *old* value in present
   tense and confirm each hit is either corrected or genuinely historical. A
   page that says "Build 44 曾…" is correct; one that says "X 是 `3.1.0`" is not.
2. **Re-read every page that names a capability the Stage changed**, whether or
   not the gate mentions it. The question is "was this true when written, and is
   it true now" — the second half is what expires.
3. **Treat a green `docs-site.sh check` as evidence of mechanical consistency
   only**, and say so when reporting it. It is the same distinction as a test
   suite passing versus the behaviour being right.

What no mechanism here can decide: whether a sentence of prose is true. That is
why this exits to attention rather than to a gate — a check that could judge
narrative truth would be the thing it is checking. What *could* be mechanised,
and is not yet, is the narrower question in step 1: no current page may contain
a superseded version literal in the present tense. That is decidable, and it
would have caught nine of the eleven sites here.
