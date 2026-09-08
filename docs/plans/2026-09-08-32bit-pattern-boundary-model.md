# Preserve Pattern timing constraints in the 32-bit design

## Scope

Translate the existing claim-boundary regression and origin/descriptor update
order into independent reduced experiments. These constrain a future protocol;
they do not implement it or certify Engine equivalence.

Declared files: this plan and `demos/32bit-pattern-mailbox/{boundary_test.py,README.md}`.

## Verification

Run `python3 demos/32bit-pattern-mailbox/boundary_test.py` and the existing
`model.py`. Detect callback-tail-only Transport and origin-after-clear variants
as wrong; keep original product source/test untouched. Run staged ownership and
whitespace checks. No new CI gate or modified test budgets.

## Version Management

Version impact: none
Reason: standalone timing examples; no public API, ABI or product manifest change.

## Documentation Impact

Documentation impact: none
Reason: experimental design evidence, not a current product support claim or
documentation-site page change.

## Remaining work

Full Q/A/slot reuse and authority model, cross-channel weak-memory reasoning,
target atomic code generation, and approved implementation/Engine regression
testing remain necessary before returning to ESP32 Step A. In particular the
valid-authority precondition in the prior cancel model is not a validation test.
