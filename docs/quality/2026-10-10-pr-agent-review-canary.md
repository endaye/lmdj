# PR-Agent review pipeline canary (2026-10-10)

This file exists only as a dedicated canary Pull Request for the self-hosted
review pipeline's end-to-end fallback and publication acceptance (umbrella
#1149, T5). It documents no product fact and is merged only after the
canary evidence is retained; see
docs/quality/2026-09-10-pr-agent-netcup-operations.md for the receipts.

Fault-injection leg: with the review host's DeepSeek endpoint pointed at an
unroutable address (2026-10-10), this head's review must be carried by the
GLM fallback and still publish normally.
