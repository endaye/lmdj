# Bound batch artifact decompression

## Scope

Declared files:

- `tools/release/batch_evidence.py`
- `tests/build/release_batch_evidence_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-batch-bounded-zip.md`

Build on live-clock Task `434caf20`. The existing complete batch verifier checks
ZIP metadata sizes but uses unbounded archive.read. Forged smaller metadata can
still cause excessive decompressor output before Python truncates the result.
Permit only stored/deflated entries and use bounded member reads, preserving all
closed inventory, semantic digest, expiry and full sixteen-suite checks. Do not
claim rejection of every forged compressed tail: the invariant is a bounded
decoder, while authenticated parsed content remains separately verified.

## Verification

Use the actual full candidate fixture, baseline success and a real ZIP with one
origin member whose metadata claims the original valid JSON length while the
compressed stream expands beyond the evidence budget. Observe the actual
decompressor without substituting its output and assert a positive max_length
and bounded decoded bytes. Separately refuse BZIP2/LZMA, whose ZIP wrappers do
not offer the required bound. Run red before source repair, the full batch suite,
related evidence contracts, staged ownership, Portal and independent review.
Do not add a generic CI gate, change timeouts/retention or invoke external APIs.

## Version Management

Version impact: none

Reason: internal evidence decoding only; no Product or Assembly changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document the bounded decoder and remaining production limitations.

Git local-only isolation is a separate parallel Task; this ZIP repair does not
claim to implement it. Full service/signing/release acceptance remains incomplete.

## Verification results

The unchanged-source two-test reduction failed with three assertions (6.546s,
exit 1): DEFLATE requested max_length 1073741824 and emitted 8001290 bytes;
BZIP2/LZMA were accepted. After repair, the two tests passed in 4.779s. Full
batch suite 75/75 passed in 65.301s, exit 0; output retained at
`/tmp/lmdj-batch-zip-tests-v1.log`. Independent complete four-file review found
no actionable finding, rerunning both new cases and bad-ZIP refusal 3/3 (4.801s).
It did not repeat the full suite. Related dispatch evidence 34/34 (7.434s) and
Site evidence 22/22 (9.893s) passed, as did staged ownership 74/74 (10.766s).
Locked npm ci and Portal check under Node 22.22.2 exited 0, with 144 tests and
47 routes/internal links. Logs: `/tmp/lmdj-batch-zip-scope-v1.log` and
`/tmp/lmdj-batch-zip-docs-v1.log`. No private data or external service was involved.
Pitfall disposition: decoder-bound regression, not new process knowledge.
