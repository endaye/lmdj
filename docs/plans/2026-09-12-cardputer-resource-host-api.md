# Cardputer resource observation Host boundary

Relates to #1104 and #1111. This follow-up exposes the already implemented
resource sampler through the serialized Host control owner for a later,
reviewed diagnostics transport. It does not add a wire opcode, alter status
bytes, or publish a Contract.

## Declared scope

- `apps/cardputer-host/main/runtime_host.hpp`
- `apps/cardputer-host/main/runtime_host.cpp`
- `tests/platform/cardputer/resource_observation_test.cpp`
- `apps/docs-site/docs/hosts/cardputer-host.mdx`
- this plan

`RuntimeHost::read_resources` is available only on the ESP Host and writes a
caller-owned `ResourceObservation`. It can be called by the serialized control
owner, never by the render callback or an ISR. The underlying heap samples are
sequential and non-atomic; the fields must not be summed across overlapping
capability classes. This boundary does not impose a finished-audio barrier:
the caller must bind each sample to its session/phase when the reviewed
diagnostics transport is added.

## Verification

The component resource test compiles the exact public member signature against
the ESP stand-ins and retains all capability, mapping, absent-heap, stack,
interval and resample assertions. The pinned EIM firmware build verifies the
real Host definition. No wire or physical behavior is claimed.

## Version Management

Version impact: none — internal Host API only; no Contract, Assembly, Product
Build or distribution identity changes.

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/` documents the
control-owner API and its phase-binding limitation.

## Remaining acceptance

The future diagnostics transport must receive independent contract review,
bind identity/session/phase, and exercise every A1 resource-cycle leg. Real
allocator behavior, scheduler timing, reclamation, USB extraction, load,
latency, hearing and device acceptance remain pending.

The first review found that the signature-only component test linked the full
Facade library unnecessarily. The fix removes that link and adds only the
public Facade and project-cooker include directories; the assertion now cannot
mask link coupling or hide a runtime-library dependency.

The follow-up also routes the already-published ESP audio-task stack value
through the Host boundary. The base session method is optional so existing
alternate sessions remain source-compatible; `nullopt` is preserved when no
worker has completed.

After this extension, the resource and unchanged audio lifecycle component
tests pass 32/32 in both dev and ASan/UBSan (`/tmp/cardputer-resource-host-api-reviewfix3-dev-tests.log`,
`/tmp/cardputer-resource-host-api-reviewfix3-asan-tests.log`). The refreshed
EIM build exits 0 (`/tmp/cardputer-resource-host-api-reviewfix3-eim.log`), the
portal check remains 116/116 with 46 routes (`/tmp/cardputer-resource-host-api-reviewfix3-portal.log`),
and staged ownership remains 72/72 (`/tmp/cardputer-resource-host-api-reviewfix2-scope.log`).
