# Cardputer sender POSIX PTY boundary

Relates to #1104 and #1109. This task exercises the existing 1–6 transfer
contract at an operating-system PTY boundary; it does not add a wire opcode,
change the Contract schema, or claim physical USB enumeration.

## Declared files

- `tests/build/cardputer_transfer_test.py`
- This plan.

## Defect and correction

The sender's prior tests replaced `os.open`, `os.read`, `os.write`, `select`,
and termios calls with mocks. Those tests prove sender validation and parser
behavior, but not that a real POSIX serial descriptor can carry a complete
HELLO → BEGIN → DATA → COMMIT exchange. Add a PTY peer that uses the existing
bounded frame decoder, returns the exact existing acknowledgements, and checks
that the received content bytes and final digest match.

The peer runs in a bounded test thread and reports failures to the test owner.
It does not stand in for the ESP C++ endpoint, USB enumeration, DMA timing,
device power state, or the A1 physical journey. Those remain separate gates.

## Verification

Run `python3 tests/build/cardputer_transfer_test.py`; the PTY scenario must
exercise the actual sender file descriptor and complete with the exact final
length/SHA-256 acknowledgement. Existing negative ACK, nonce, CRC, noise,
length, and fragmentation cases remain unchanged.

## Version Management

Version impact: none — existing framing and response formats only.

## Documentation Impact

Documentation impact: none — this adds test evidence without changing a
capability, identity, portal route, or public workflow.
