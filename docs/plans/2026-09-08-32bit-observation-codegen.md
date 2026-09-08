# ESP32-S3 primitive code-generation evidence

## Scope

Compile the standalone observation publisher and selected atomic32 primitives
with the existing EIM-managed ESP32-S3 GCC 15.2.0 toolchain. Preserve assembly,
undefined-symbol inventory and an atomic64 positive control in a temporary
directory. Do not alter the old Step A build/cache or failure evidence.

Declared files: this plan and `demos/32bit-observation/{codegen.cpp,
codegen_control.cpp,codegen.sh,README.md}`.

This is object compilation, not a linked IDF project, firmware, target execution,
Core implementation, or completion of Step A. It does not import product code.

## Verification

- Verify installed EIM version and source SHA, compiler version and ESP32-S3 alias.
- Compile with gnu++20, -Wall -Wextra -Wpedantic -Werror at -O2 and -Os.
- Assert 32-bit ABI and lock-free atomic32; require emitted publisher/functions.
- Inspect disassembly and undefined symbols, with atomic64 helper positive control.
- Re-run existing host normal/TSan tests; staged ownership and whitespace checks.

## Version Management

Version impact: none
Reason: standalone compiler experiment, no product version or ABI changes.

## Documentation Impact

Documentation impact: none
Reason: experimental code-generation evidence, no current product support claim
or documentation-site change.
