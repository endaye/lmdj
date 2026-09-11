# Cardputer STATUS length bounds

Relates to #1104. The endpoint allocated 14 payload bytes but wrote an eight-byte
length at offset 8: two stack bytes were overwritten and absent from the response.
Encode all 16 bytes in a shared, platform-independent function called by the
real endpoint. Keep existing field offsets and little-endian length semantics.

## Declared files

- apps/cardputer-host/main/usb_transfer_endpoint.cpp
- apps/cardputer-host/main/status_payload.hpp
- tests/platform/cardputer/status_payload_test.cpp
- tests/platform/cardputer/CMakeLists.txt
- docs/plans/2026-09-11-cardputer-status-bounds.md

## Verification

Lowest-tier test compares all 16 bytes of the production encoder, with distinct
high length bytes that small fixtures previously missed. Run with ASan/UBSan,
strict EIM v6.1 target compile, scope ownership and whitespace checks. Original
STATUS writing should reproduce a stack buffer overflow under ASan. Device
validation follows integration with the independent shared-I2C repair.
No threshold or full journey requirement changes.

## Version Management

Version impact: none — correct a truncated uint64 field and memory corruption;
no new wire field, public API or Product Build allocation. Diagnostic builds
are source validation; formal Product Build acceptance remains separate.

## Documentation Impact

Documentation impact: none — this restores the existing length representation;
no Portal interface or documented capability changes.

## Pitfall Impact

Product buffer defect, captured by the regression test; no ledger entry.
