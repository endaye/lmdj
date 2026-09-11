# Cardputer bounded response resynchronization

Relates to #1104 and #1109. No new wire operation or schema change.

## Declared files

- `scripts/cardputer-transfer.py`
- `tests/build/cardputer_transfer_test.py`
- This plan.

## Defect and correction

The serial reader discarded only one noise byte before waiting for another
read, even when a complete valid reply was already buffered. An unchecked
u16 length could also hold a valid following reply behind a 65535-byte claim.
The reader must drain invalid magic/header/CRC candidates before another wait,
preserve split magic, and validate the payload bound before waiting for bytes.
The existing request/opcode/nonce/full acknowledgement checks still run after
framing; a valid but unrelated response is rejected, not silently skipped.

Before a read, the parser retains fewer than MAX_FRAME bytes; a read appends
at most two frames, bounding this sender's live input below three frames.
The original deadline is unchanged and noise never extends it. An incomplete
otherwise legal frame may still time out: no guessing frame boundaries inside
an unverified payload or automatic transaction restart is added.

## Verification

Exercise real send_serial with mocked serial reads for boot noise/split magic,
bad CRC followed by a valid frame, and an over-wide header followed by a valid
frame. Assert the sender completes without waiting for nonexistent extra data.
Retain the initial failures at `/tmp/cardputer-response-framing-red.log`.
Add maximum partial-frame/noise storage assertions and retain all existing
acknowledgement rejection tests. Run sender and conformance tests plus staged
ownership. This is not physical USB/PTY timing or recovery acceptance.

## Version Management

Version impact: none — enforce existing bounded framing, no Contract/Assembly
or Build identity changes.

## Documentation Impact

Documentation impact: none — restore existing noise-resynchronization behavior;
no portal capability, identity or public workflow changes.
