# P1 slot acquisition inventory proof

Independent review reproduced a stale Host fixture: it requires the Facade's
Sound Set inventory to contain only the five Native instrument operations.
P1 adds catalog description, slot acquisition and slot installation to the
Facade/Bridge surface. Pin its complete eight-operation inventory separately,
while retaining the Native inventory's exact five operations and every existing
Performance CLI assertion. Product code and public operations do not change.

## Declared files and verification

- `tests/host/performance_cli_test.py`
- `docs/plans/2026-10-01-creator-p1-slot-inventory-proof.md`

Retain the original assertion failure. Before committing, check the complete
Facade and Native Sound Set and Performance registration inventories, then run
the full `host.performance_cli` fixture against this worktree's rebuilt CLI and
Native Host. Run the scope check for the newly declared plan. Selected batch
lanes and current-head independent review follow on the committed head.
No inventory subset, operation count, timeout or journey assertion is relaxed.

## Version Management

Version impact: none. Only a verification fixture changes; product source and
module identities remain unchanged.

Documentation impact: none
Reason: current portal source facts and product behavior are unchanged.
