---
id: documentation-impact-means-portal-pages
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/594
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/595
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/600
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/603
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/608
    observed_by: claude-code/opus-5
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/611
    observed_by: claude-code/opus-5
  - date: 2026-09-04
    occurrence: https://github.com/endaye/lmdj/pull/624
    observed_by: claude-code/opus-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# `Documentation impact` means Architecture Portal pages, not any file under `docs/`, and the declaration has one exact spelling.

## Why

`check-doc-impact.mjs` reads three lines out of the Pull Request body and
compares them against the tree:

- `Documentation impact:` must be exactly `required` or `none` on its own line;
- a `Reason:` line must be present and non-empty, on its own line — prose on
  the impact line does not satisfy it;
- when `required`, an `Affected portal pages:` line must list routes each
  beginning with `/`, **and** a page under `apps/architecture-portal/docs/`
  must actually have changed.

Everything in that sentence is about the Architecture Portal. `docs/quality/`,
`docs/governance/`, `docs/prd/` and `docs/superpowers/` are ordinary
repository documentation: editing them is not portal impact, and declaring
`required` for them fails because no portal page changed.

Seven Pull Requests in two days declared `Documentation impact: required` for
edits to `docs/quality/core-test-policy.md`, and named the file on a `Routes:`
line the gate does not read. Both errors were wrong in the same way every time,
and the reason is not that the word "documentation" was read as ordinary
English. **Each declaration contained its own refutation.** Six of the seven
read, in full:

```
Documentation impact: required
Routes: `docs/quality/core-test-policy.md` <what it documents>. No Architecture
Portal route, manifest or diagram source changes; `scripts/architecture-portal.sh
check` passes.
```

The sentence asserting portal impact is immediately followed by a sentence
stating that no portal route, manifest or diagram source changed. The condition
the field exists to assert is denied one line below the assertion, in the same
block, by the same author.

That shape survived six repetitions because it was never re-read. It was
composed once, and thereafter copied forward from the previous Pull Request as
a filled-in template. A block that already looks reasoned -- it cites a file, it
names a command, it reports that the command passes -- does not invite the
re-reading that would expose the contradiction inside it.

The template's origin is the umbrella Issue #591, whose own declaration reads
`Required.` for the same `docs/quality/core-test-policy.md`, and defers the
portal routes to "each step's own plan". Every step inherited a `required` that
the umbrella had never justified and each step then failed to supply.

What let a self-contradicting block run for two days is the second half. The
gate runs only inside the `portal` lane, so a Pull Request that does not select
that lane never evaluates the declaration, and six of the seven were merged by
hand while the lane was queued or red. **A gate that is bypassed teaches
nothing.** The error was invisible to its author for two days while being
caught correctly every single time it ran.

`scripts/local-ci.sh --pr-body <file>` runs that same gate against a body file
and existed throughout. Nothing in `issue-done` said to use it, so the one tool
that would have closed the loop before the Pull Request opened was never
reached for.

It is not a milliseconds-only check, and describing it as one sets up the next
disappointment: the declaration verdict prints before any lane output, but
`--pr-body` has no declaration-only mode and goes on to execute every selected
lane, with a failed declaration changing only the exit code. Read the verdict
and interrupt if that is all you need.

## How to apply

- Declare `Documentation impact: required` when this change edits a page under
  `apps/architecture-portal/docs/`, **or** when it changes Product Build or
  Assembly identity — `products/lmdj/version.json`, `assembly(.lock).json`,
  `CMakeLists.txt` or `src/` — which cannot declare `none` at all;
  `check-doc-impact.mjs` forces `required` there regardless of the diff, and
  `CLAUDE.md` states it unconditionally. Editing any other documentation is
  `Documentation impact: none` with a reason, and the reason may perfectly well
  be "this change edits repository documentation, not a portal page".
- **Before settling on `none`, grep the portal's `source_paths` for the files
  you changed.** Each page declares the repository files it describes:

  ```bash
  grep -rl "<changed path>" apps/architecture-portal/docs --include='*.mdx'
  ```

  If a page names your file and your change makes that page's text wrong, the
  page must be updated in the same Task — and updating it is what makes the
  declaration `required`. This obligation has no gate behind it:
  `validate-docs.mjs` checks only that each `source_paths` entry *exists*, and
  `check-doc-impact.mjs` only cross-checks the declaration against which portal
  files the diff touched. A stale page therefore passes every mechanical check,
  so `none` can be simultaneously accepted by CI and wrong.

  Observed on #624, which edited `docs/quality/core-test-policy.md` and
  `.github/workflows/core-nightly.yml` — both named in the `source_paths` of
  `apps/architecture-portal/docs/operations/testing-and-proof.mdx` — and left
  that page grounding scheduled TSan in a historical observation the same Pull
  Request had just replaced with same-revision evidence. The declaration was
  `none`, the gate was green, and the page was wrong. An advisory review caught
  it; nothing else would have.
- Read the declaration block you just wrote as a whole, against itself, before
  the rest of the body. If one line says `required` and another says no portal
  route or diagram source changed, the block has already answered itself and the
  answer is `none`. This is the specific check the seven occurrences needed, and
  it takes one re-read.
- Never carry a declaration block forward from a previous Pull Request as a
  template. It is four lines to write from the actual diff, and copying is how
  a single unexamined judgement reproduced itself six times.
- When declaring `required`, the routes go on a line reading exactly
  `Affected portal pages:` and each entry starts with `/`. `Routes:` is not
  read by the gate.
- Check the body before opening the Pull Request, not after:
  `bash scripts/local-ci.sh --pr-body body.md`. `issue-done` §4 now writes the
  body to a file, gates it, and only then calls `gh pr create --body-file`,
  which is this entry's exit. An earlier revision of that step claimed to run
  "before opening" while sitting *after* `gh pr create`, and read the body back
  with `gh pr view` — a command that cannot run until the Pull Request exists.
  A step whose title and position disagree teaches the opposite of its title.
- After correcting a body, the gate needs a fresh `pull_request` event. A rerun
  replays the stale payload and fails again on the text you already fixed;
  close and reopen, or push.
- Do not merge past this gate by hand. A red declaration check is thirty
  seconds of editing, and merging around it removes the only signal that the
  declaration was wrong.
