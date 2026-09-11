# `lmdj.cardputer-transfer.v1`

Contract version `1.0.0` defines bounded USB Serial/JTAG framing for the
Cardputer runtime content sender/receiver. It is a transport envelope, not a
replacement for `lmdj.runtime-content.v1` and not USB audio.

All integers are unsigned little-endian. A frame is `LMCP`, version, opcode,
payload length (0–1024), request ID, 16-byte session nonce, payload, and
CRC-32/ISO-HDLC over every preceding byte. The maximum frame is 1056 bytes.
Requests use opcodes 1–6 (`HELLO`, `STATUS`, `BEGIN`, `DATA`, `COMMIT`,
`ABORT`); responses OR the opcode with `0x80`.

The Python reference is `scripts/cardputer-transfer.py`; the product C++
reader is the bounded `apps/cardputer-host/main/transfer.*` seam. Both reject
bad version/length/opcode/request ID and CRC before a handler can observe the
payload. A framing parser may discard one byte on bad magic to resynchronise;
it must not allocate based on an unverified length.

The implementation supplies framing plus a bounded ordered content transaction:
BEGIN reserves the exact byte length and a non-zero transfer ID, DATA accepts
only the next offset (exact repeats are idempotent), and COMMIT verifies
SHA-256/length before publishing to the sink. ABORT, disconnect, conflicting
duplicates, incomplete input and sink failure discard staging and expose no
partial content. The protocol-facing receiver also expires a stalled transfer
after five seconds of no new bytes; duplicate chunks do not extend that clock.
The reference sender puts the same 16-byte transfer ID in BEGIN, every DATA
chunk, and COMMIT; DATA chunks carry the transfer ID before their little-endian
offset, so a stale transaction cannot mutate a newer one.
Session/nonce authorization, exact request replay caching, and real USB/PTY
integration remain deployment/acceptance work and must preserve these D1 rules.
