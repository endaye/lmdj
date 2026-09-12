# Cardputer observation wire codec draft

Relates to #1104, #1107 and #1111. This is a proposal-only serialization
seam. It does not register opcodes, modify the active Contract schema or
manifest/Assembly identities, and is not included in the ESP firmware target.

## Declared files

- `apps/cardputer-host/main/observation_wire.hpp`
- `tests/platform/cardputer/observation_wire_test.cpp`
- `tests/platform/cardputer/CMakeLists.txt`
- This plan.

## Scope and boundary

The pending observation plan defines a 146-byte complete-status prefix and a
338-byte stopped-diagnostics prefix, each followed by a bounded canonical
identity JSON object. This draft implements only a fixed-buffer writer for
those proposed layouts. It checks little-endian widths, boolean/enum ranges,
reserved fields, transfer progress bounds, non-zero boot/generation markers,
identity presence, exact JSON escaping and the distinction between unavailable
and measured diagnostics.

No endpoint dispatch, response nonce behavior, Host identity sourcing, profile
digest generation, Contract version, or Product Build is changed. The ESP
component deliberately does not compile this header until the independent
review of the opcode allocation and byte tables is recorded on the wire plan.

## Verification

The native proposal-only target runs five focused scenarios: valid status,
invalid status state, valid diagnostics, explicit unavailable diagnostics and
canonical escaped identity. It asserts field offsets and lengths, including
the mechanically derived maxima of 658 and 850 bytes when identity data uses
the full 512-byte bound. These tests are evidence for the draft codec only;
they do not establish USB, PTY receiver, device timing, or physical A1 gates.

## Version Management

Version impact: none — no active Contract, Module, Host, Assembly or Product
identity is allocated or modified.

## Documentation Impact

Documentation impact: none — this remains an unadvertised, unintegrated draft
and introduces no portal capability or source identity.
