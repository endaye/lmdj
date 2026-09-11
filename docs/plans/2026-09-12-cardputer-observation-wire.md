# Cardputer complete status and stopped diagnostics transport

Relates to #1104, #1107, #1109 and #1111. This plan addresses missing development
before the user's joint device testing. It does not allocate a Product Build,
publish a Contract, or authorize device/release operations.

## Current source evidence and required outcome

At `3424bc209cca3b7be8d478ee3519b7c5c8a3724e`, `status_payload.hpp`
serializes exactly 16 bytes: result, phase/error/armed/mute/volume/Pad count and
content length. It omits the full digest, Pad mapping, profile limits, transfer
progress and generated identities described in D1. The current Python sender
and C++ parser accept only opcodes 1–6. STATUS also bypasses TransferSession's
nonce/request admission. These are source gaps, not evidence that the complete
D1 status journey works. The fixed-format status regression proves only that
16-byte layout and cannot discharge the larger requirement.

Audio service instrumentation now provides a stopped-session snapshot, but
there is no wire reader for it and it is not bound to the identity of the
content measured. The Host can unload or replace content after stopping;
therefore copying current Host identity into an old diagnostic response would
misattribute the measurements. An immutable observation must capture identity
at the measured start, not at the later query.

The required end state is a computer-readable complete status and an immutable,
identity-bound stopped audio observation, usable without starting/stopping or
replacing content over USB. Existing transfer behavior and local playback
authority remain intact. No old narrow STATUS result may be accepted as this
complete status by the new observation client.

## Proposed compatibility boundary

Keep existing opcodes and the current STATUS bytes unchanged for existing
clients. Propose an additive Contract Minor with `STATUS_EXTENDED` and
`AUDIO_DIAGNOSTICS` operations, retaining wire major 1 and the 1024-byte payload
bound. Older peers reject the unsupported opcode; the new client reports
unsupported, never falls back to interpreting the narrow legacy status as a
complete observation. The exact opcode allocation and byte tables must be
reviewed and recorded before modifying active schema/manifest identities.

The new read-only operations must validate the current nonce and request
identity without consuming or advancing the content-transaction sequence. Use
a separately defined observation request domain in the new Contract; do not
invent Facade epochs on the wire, reuse a mutating session admission helper,
or silently consume the sender's next DATA/COMMIT ID. Define this domain
explicitly in the reviewed byte table and test interleaved status reads during
an active receive. Wrong nonce, malformed request and unknown format must not
cancel a valid receive, clear a diagnostic snapshot or change local playback.

One bounded response must contain a complete observation; no multi-page
mutable read may mix two content identities or runs. If a response cannot fit,
reduce redundant encoding, not required fields or identity precision. No
unsolicited serial logging, remote Pad/start/stop operation or unbounded queue
is added. Retain zero-timeout USB writes; a dropped/partial response is a
transport failure which the read-only client may retry with a fresh correlated
request, not permission to restart a content transfer.

## Required complete status fields

### Proposed byte tables for review

The following allocations are proposals only: request opcodes 7 and 8,
responses 0x87 and 0x88. Both requests have exactly one payload byte, format=1.
The header nonce must equal the current non-zero HELLO nonce. Their non-zero
request ID is correlation-only in the observation domain: it does not advance
the content session's exact-next ID and does not share its retry cache.
Only one request is in flight on the serial link; the client correlates both
opcode and request ID and never reuses an observation ID within a session.
Retries use a fresh observation ID. These are fresh reads, not idempotent
replays of a cached status; the immutable observation generation identifies
whether two successful diagnostics reads describe the same measurement.

No observation operation performs HELLO implicitly. A caller joining a live
transfer must use that transfer's existing session; a new HELLO has its existing
transaction-cancellation semantics and is not a harmless status probe.
Bad nonce returns stale-session=3; wrong payload shape/format returns
invalid-transfer=6, with no content/session/observation mutation. Error replies
contain only the u16 result and echo the request nonce/ID, never the current
nonce. This avoids accidentally issuing the live nonce to a stale requester.

All offsets below are within successful response payload, including result.
Integer fields are unsigned little-endian; every reserved byte must be zero.
The decoder requires exact final length, valid enums, boolean 0/1 and no extra
bytes. Complete status has a fixed 146-byte prefix followed by identity data:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 2 | result=0 |
| 2 | 1 | observation format=1 |
| 3 | 1 | flags: bit0 content present, bit1 receiving; other bits zero |
| 4 | 16 | non-zero boot nonce, fixed until device reset, distinct from session nonce |
| 20 | 1 each | phase, error, armed, muted, volume, Pad count |
| 26 | 8 | four bank/Pad pairs; unused pairs 255/255 |
| 34 | 2 | reserved |
| 36 | 8 each | maximum encoded bytes, maximum PCM bytes |
| 52 | 4 each | maximum frames, maximum Pads, maximum events |
| 64 | 8 | current content byte length |
| 72 | 32 | raw current content SHA-256 |
| 104 | 16 | active transfer ID |
| 120 | 8 each | actual received bytes, expected bytes |
| 136 | 8 | latest admitted observation generation, 0 before any attempt |
| 144 | 2 | identity JSON UTF-8 length, at most 512 |
| 146 | length | canonical identity object described below |

The prefix is field-encoded rather than copied from a compiler layout. Absence flags require the
corresponding content/transfer fields to be all zero. Expected receive length
must be non-zero while receiving and received must not exceed expected. The
identity object contains exactly product_build, host_version, revision,
assembly_lock_sha256 and profile_sha256, as in D1. Strings are validated against
the generated active identities; no null product identity is accepted by a
formal-candidate client. Maximum successful status payload is 658 bytes.

Successful diagnostics has a fixed 336-byte measurement prefix, then the same
length-prefixed identity JSON (2+at most 512 bytes), maximum 850 bytes:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 2 | result=0 |
| 2 | 1 | observation format=1 |
| 3 | 1 | flags: start succeeded, quiescent, silent, diagnostics available in bits 0..3 |
| 4 | 16 | boot nonce |
| 20 | 8 | non-zero measured generation |
| 28 | 8 | measured content byte length |
| 36 | 32 | raw measured content SHA-256 |
| 68 | 4 | timing flags=7: bit0 elapsed microseconds, bit1 delivered EOF, bit2 prewarm/drain excluded |
| 72 | 8 each | attempts, submitted, stopped, wait failed, convert failed, write failed |
| 120 | 32 each | six duration records in wait/wakeup/render/convert/submit/service order |
| 312 | 8 each | recording samples, maximum microseconds, invalid samples |
| 336 | 2 | identity JSON length |
| 338 | length | identity object |

Each 32-byte duration record is valid samples u64, invalid samples u64,
maximum_us u64, p999_us u32, percentile_available u8 and three zero bytes.
Unavailable percentile requires p999_us=0, but availability=0 is not a measured
zero. Unavailable diagnostics require all duration/count fields zero while
preserving the identity and start/join outcome. Before any observation or while
audio owns it, return wrong-state=1 with no successful payload. Physical
underrun/latency/voice/resource measurements are deliberately absent from this
format; absent values must never be interpreted as measured zero.

Before implementation, add independent golden byte vectors at all listed
offsets and verify the maximum-length arithmetic mechanically. Freeze the
timing-bit numeric allocation and canonical identity encoding in the reviewed
Contract change, not by whichever language's encoder is implemented first.

- Explicit response format version, result and availability flags.
- Host phase/error, local armed state, mute/volume and canonical four Pad Slots.
- Exact configured encoded/PCM/frame/Pad/event limits, not inferred capacity.
- Current full content SHA-256 and byte length, or explicit absence.
- Current receive identity and actual progress/expected bytes, or absence.
- Manifest-derived Product Build, Host version, full source revision,
  Assembly lock digest and profile digest. No hand-entered or guessed values.

## Required stopped observation fields

- Explicit unavailable state while the audio task owns mutable observations.
- A Host-owned observation generation independent of RuntimeEpoch. It must
  distinguish reset/start attempts and never silently wrap or reuse identity.
- Identity of the content and generated firmware/profile at the measured start,
  retained after stop/unload until the next admitted measurement replaces it.
- Admitted start/final outcome and all attempt/success/partial-failure counts.
- Six duration records: valid count, invalid count, maximum, exact p99.9 and
  explicit percentile availability. Preserve retention exhaustion at 512000
  samples and the distinction between zero and unavailable.
- Recording-overhead count/max/invalid and precise timing-domain flags:
  microsecond elapsed intervals, not isolated CPU time; prewarm/drain excluded;
  delivered EOF is not masked-IRQ/physical-underrun observability.
- Physical underrun/latency/voice/resource values remain unavailable unless
  backed by their actual instruments. Do not populate them with zero or infer
  voice counts from accepted Pad commands.

## Implementation Tasks and verification

1. Freeze reviewed byte tables and paired positive/negative vectors. Declared
   files: this plan, `contracts/cardputer-transfer/README.md`, its schema,
   and the applicable version/Contract inventories and conformance tests.
   Any active Assembly identity change includes the governed version and
   immutable snapshot work; do not make a half-updated manifest pass by removing
   the consistency checks. Until that integrated boundary is ready, keep this
   proposal separate from active Contract metadata.
2. Implement the Host-owned immutable observation and canonical serialization.
   Declared source seams: `runtime_host.*`, `audio_diagnostics.hpp`,
   `status_payload.hpp`, `usb_transfer_endpoint.*`, `transfer.*`, their focused
   platform tests and the relevant portal pages. Lowest-tier tests must verify
   start A → stop → unload → load B still reports A for the old observation;
   start B replaces it; running/read failure never reveals partial or stale
   data. Test failed start and reset identity separately.
3. Implement the Python decoder/query command in `scripts/cardputer-transfer.py`
   and its conformance tests. Independent expected bytes must check every field,
   integer width, reserved bit, exact length, nonce, response correlation and
   unknown-version refusal; C++ and Python merely agreeing is insufficient.
   Test old-peer unsupported behavior and partial/dropped response retry.
4. Exercise the real endpoint over fake serial plus real Host lifecycle:
   observation reads between BEGIN/DATA/COMMIT leave next transaction ID,
   progress and published identity unchanged; stale/malformed reads have no
   far-side effects; retained A observation cannot be relabeled B. Add PTY
   reader tests without claiming physical USB enumeration or DMA acceptance.

Every Task runs its focused native/Python tests, ASan where applicable, EIM
compile/link, staged ownership, Contract/version consistency and affected
portal checks. New checks name the concrete misattribution, malformed-frame or
state-mutation defect; no full-CI gate or timeout/coverage reduction is added.

## Version Management

Version impact: none for this planning-only Task. An additive Contract Minor
is proposed, not allocated. The implementation must update all active version
inventories and the integrated candidate's Assembly/Build/snapshot together
under the canonical policy. Existing frozen Build identities remain unchanged.

## Documentation Impact

Documentation impact: none for this planning-only Task; no active capability or
portal identity is changed. Implementation requires `/hosts/cardputer-host/`
and `/contracts/cardputer-transfer/` updates with exact supported formats and
remaining physical acceptance limits.
