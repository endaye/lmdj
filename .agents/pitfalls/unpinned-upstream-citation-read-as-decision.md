---
id: unpinned-upstream-citation-read-as-decision
area: docs-governance
status: open
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/issues/758
    observed_by: claude-code/opus-5
exit: none
---

# A version that entered retained research only as a documentation-URL citation was read a year later as that research's locked version decision, and the `master` link beside it could no longer show what had actually been read.

## Why

Two ESP32 research documents cited ESP-IDF `5.5.1` documentation pages for C++
support and the I2S driver. Neither document ever chose a version; the
2026-08-27 assessment §13 explicitly deferred it, requiring a future spike to
"lock the exact ESP-IDF version, toolchain and development board". `5.5.1` was
simply the current release on the day the pages were retrieved.

A year later (#758) those citations were read back as the research's version
decision and repeated as a recommendation to install `5.5.1`. By then `5.5.1`
was the oldest patch of a line already at `5.5.5`, that line had left its
Service period, and two newer majors existed. Nothing in either document was
false — and that is the point. A citation and a decision are written in the
same shape, so the reader cannot tell which one a version number is, and the
recency that made the citation unremarkable when written is exactly what decays.

The second half compounds it. §3 of the same document cited
`components/esp_libc/src/stdatomic.c` on the **`master` branch** to support a
claim about 64-bit atomic emulation. When that claim was rechecked it turned
out to be true but incomplete — the same file gates 32-bit atomics behind
`CONFIG_STDATOMIC_S32C1I_SPIRAM_WORKAROUND` — and there was no way to tell
whether the omission was an error at writing time or upstream drift since,
because the cited ref had moved. An unpinned citation cannot be audited against
itself; it documents a claim without preserving its evidence.

The cost here was one round of rework and a recommendation that was withdrawn
before any hardware was touched. The same shape applied to a Contract version,
a toolchain pin, or a supported-target list would have been acted on.

## How to apply

- **Pin every upstream citation to an immutable ref** — a tag, a release, or a
  commit SHA — in retained research, specs, plans, and pitfalls alike. Never
  cite `master`, `main`, `latest`, or `stable`. If only a moving page exists,
  quote the sentence you relied on and record the retrieval date next to it, so
  a later reader can see what was actually read.
- **Say which one a version number is.** When a version appears because it was
  the current release on the retrieval date, label it as a citation, not a
  choice: "documentation retrieved from vX.Y.Z on <date>; no version is chosen
  here". When it is a decision, say so and name what it is binding.
- **Before repeating a version out of a document, re-derive it.** Check the
  upstream release list and support policy against today's date rather than
  quoting the document. A version in prose is a claim about a moment; the query
  behind it is cheap to run again.
- **When re-derivation contradicts the document, amend the document, not just
  the answer.** Record both the original citation and the corrected finding.
  The pair is what tells the next reader the number was never a decision.

No mechanism exits this entry. "Is this version a citation or a decision" is a
judgment about authorial intent, and a link checker cannot see that a live URL
now describes something other than what was read, so neither half is
mechanically decidable under the admission criteria. If this recurs, the exit
is a section in the research-authoring guidance rather than a gate.
