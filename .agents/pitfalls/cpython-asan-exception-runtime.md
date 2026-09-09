---
id: cpython-asan-exception-runtime
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-10
    occurrence: https://github.com/endaye/lmdj/issues/1042
    observed_by: Codex GPT-6
exit: gate:tests/host/provider_owner_test.py
---

# Preloading libasan alone into CPython can leave its C++ exception interceptor uninitialized.

## Why

The GNU/Linux MCP sanitizer harness starts uninstrumented CPython and loads the
instrumented C ABI later through ctypes. With a CPython executable that does not
already load libstdc++, ASAN initializes before `__cxa_throw` is available.
Successful requests work, but a real binding-refusal request terminates with
`real___cxa_throw != 0` inside the sanitizer interceptor.

## How to apply

Keep the compiler-resolved ASAN and C++ runtimes in the MCP subprocess preload
list, in that order, as configured in root CMakeLists.txt. Initialize this shared
environment before registering Host tests. Run `host.provider_owner` under ASAN:
its real MCP binding-refusal case exercises the exception boundary. Preserve
native leak checks and sanitizer interceptor checks; do not remove the refusal
case or treat the successful-request prefix as coverage of the complete Host.
