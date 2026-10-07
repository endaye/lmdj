# Build 87 journal refusal diagnostics

Relates to #1864. The candidate remains
`5abc52106728f463768210eb4186777a0b44ad7f`; this Task changes only diagnostic
information in the trusted controller transport.

## Observed defect and scope

Runs 37645291372/1 and 37648466482/1 stopped before product execution. The
first reports malformed jobs pagination without identifying the writer/page;
the second reports an unavailable request without its endpoint class or HTTP
metadata. A separate complete read-only replay authenticated 895 events and
1,144 successful reads, but does not explain either Actions failure.

Retain bounded endpoint classes, validated writer/page numbers and numeric
HTTP status/rate-limit metadata at the refusal site. Never print exception
text, URLs, headers, response bodies, GraphQL variables or journal payloads.
Preserve every authentication assertion, GET retry rule and single-attempt
write. This repairs a confirmed diagnostic blind spot, not the unknown
transport failure; #1864 remains open until its full acceptance passes.

Declared files:

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `.agents/pitfalls/gate-failure-readability.md`
- this plan

## Verification

First demonstrate the missing evidence with failing transport fixtures. Then
run the transport, journal, runtime and incremental-entry suites. Fixtures
must prove numeric HTTP observations and malformed jobs writer/page survive,
secret-bearing text stays absent, no write is replayed and no rejected writer
is cached. Run scope ownership after staging the new plan, Task declaration
checks, current-head independent review and guarded squash merge.

Real recovery follows separately: authenticate current journal state before
any supported same-ID reconciliation, retain its actual result, obtain one
current-policy complete 16-suite source, review the evidence-only intent
update and pass exact-tag remote audit. No fabricated candidate pass, local
proof waiver expansion, publication or deployment is part of this diagnostic
commit.

## Version Management

Version impact: none — internal diagnostic details only; Product, Host,
Module, Provider, Contract and Assembly identities are unchanged.

Documentation impact: none
Reason: no Portal route, diagram, projected identity, product behavior or
operational authentication/recovery policy changes.
