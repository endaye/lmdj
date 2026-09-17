# Cardputer sender acknowledgement correlation

Relates to #1104 and #1109. This fixes existing 1–6 opcode handling without
introducing the proposed observation operations or changing wire formats.

## Declared files

- `scripts/cardputer-transfer.py`
- `tests/build/cardputer_transfer_test.py`
- This plan.

## Defect and verification

The sender accepted successful replies without checking request ID, nonce,
acknowledged transfer/offset or complete COMMIT identity. A valid CRC only
proves frame integrity, not that a reply describes this transfer.

Check opcode/request ID at exchange; HELLO must issue a non-zero nonce, and
later replies must match it. Require the exact existing success payload:
HELLO maximum payload, BEGIN transfer ID and zero offset, DATA transfer ID and
next offset, COMMIT full content length and SHA-256. Reject missing/trailing
or altered fields. Failure must not send the next mutation or claim completion.

The real send_serial path is exercised over mocked POSIX serial calls. The
complete positive transaction checks final identity; adversarial valid-CRC
replies with wrong ID/nonce or altered payload fail before the next mutation.
The original code fails six negative subcases (exit 1, preserved at
`/tmp/cardputer-transfer-ack-red.log`). Mocks do not establish physical USB,
PTY scheduling, dropped-response recovery or full D1 transport acceptance.
Run Python sender and Contract conformance tests plus staged ownership.

## Version Management

Version impact: none — enforce the existing response contract; no schema,
public wire operation, Assembly or Product Build identity change.

## Documentation Impact

Documentation impact: none — existing sender confirmation semantics are
enforced without changing public workflow or portal identity. This plan
records the source defect and narrowly scoped regression evidence.
