---
id: playwright-success-body-attachment-not-persisted
area: creator
status: open
recurrences:
  - date: 2026-10-18
    occurrence: https://github.com/endaye/lmdj/issues/2231
    observed_by: Codex primary
exit: none
---

# A passing Playwright test's body-only attachment is not a retained file when its reporters and trace policy do not persist it.

## Why

The #2231 consumer checkpoint `c10a118d` passed both complete real-audio
journeys, but a post-run audit found only the six directly written PNGs. No
success trace or JSON remained for a far-side frame/PCM review. The locked
Playwright runner uses the line reporter and `trace: retain-on-failure`.
Its `normalizeAndSaveAttachment` returns body bytes in memory, whereas a path
attachment copies the file into the test's attachments directory. A passing
assertion proves its observed fact; it does not prove a diagnostic body was
retained for a later reader. The failed trace extraction is retained separately.

## How to apply

When success evidence must survive the run, write it beneath
`test.info().outputPath(...)` and attach that exact file by path. Keep a unique
results slot per invocation. After the actual full selection exits, inventory
and read back the files, their source head/identity and their meaningful data;
do not infer retention from calling `attach`, an existing directory or a PASS.
Preserve failure artifacts and original predicates/deadlines. Do not enable
global tracing or replace CI/reporters merely to retain one Task's evidence.

`exit: none`: whether a diagnostic must survive a successful run needs review
judgment. The meter spec's local file writer repairs that proof but does not
enforce the judgment for every future test; no generic gate is claimed.
