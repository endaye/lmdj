# Stage 8B Pad Capture Acceptance — 2026-08-16

## Current status

Stage 8B is allocated as Product Build `1.0.23.0 canary` by
`c34a353e`. The immutable Architecture Portal snapshot committed by
`00769017debdb4f260ada7782c1f7f3e187eab1e` authenticates that exact revision.
Only `creator-web` moved, from `1.2.0` to `1.3.0`; nothing depends on it and no
other Module, Provider, Contract or Host identity changed. `web-runtime-host`
stays `1.2.9`.

Capture is implemented entirely in the Creator. Core Modules, the Application
Facade surface, the transport protocol and every Contract are unchanged, and
the manifest `resource_limits` are untouched: a committed capture is encoded to
48 kHz PCM16 WAV in the Host and handed to the same `sample.import.*` session
the file picker uses.

This record claims automated acceptance at
`cd182361baf1` for the gates listed below. It does not claim physical or
manual acceptance: every row in the deferred ledger stays
`deferred / unverified`.

## Automated acceptance contract

| Evidence | Required result |
| --- | --- |
| Capture unit/component tests | Buffer bounds, deterministic float→PCM16 encoding, the full state-machine transition matrix, controller lifecycle and the panel's recording/trim/commit surface pass |
| Commit journey | A committed capture reaches Core through the unchanged import journey, carries a commit-time `expected_revision`, and a conflict retry re-encodes byte-identical WAV |
| Chromium fake device, granted | Record, trim and commit onto a Pad; the 5 s commit clamp; blur stops capture and keeps the buffer; no device identity or filesystem path leaks |
| Chromium fake device, denied | A refused microphone renders an explained, retryable error rather than a silent no-op |
| Packaged distribution | The Creator serves exactly its declared asset roles, including the same-origin capture worklet, each content-hashed and manifest-verified |
| Core no-regression | The Core tiers still pass with no Core source change |
| Identity and Portal | Product/Module identities verify, the conformance gates pass, and the immutable snapshot matches repository truth |

## Automated results

All results below ran locally on `cd182361baf1` on 2026-08-16, using the pinned
Emscripten 6.0.5 toolchain (`emsdk` revision
`dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`) and its bundled Node 22.16.0.

| Gate | Result |
| --- | --- |
| `npm --prefix apps/creator-web test -- run` | 287/287 pass across 16 files |
| `npx tsc --noEmit` (creator-web) | pass |
| `python3 apps/creator-web/test/package_test.py` | 9/9 pass |
| `python3 apps/creator-web/test/server_test.py` | 3/3 pass |
| `scripts/core.sh build dev` | pass |
| `scripts/core.sh test dev fast` | 26/26 pass |
| `python3 tests/build/version_test.py` | pass |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | `1.0.23.0` pass |
| `tests/conformance/*.py` | module graph, version lock, JSON schema, schema contract and project bundle contract all pass |
| `scripts/architecture-portal.sh check` | 48/48 tests, 37 pages, release-doc snapshot and 42 routes/internal links pass |
| `scripts/creator-web.sh proof` | Project/Sample fixture reproducibility, byte-identical distributions, Creator 287/287, package 9/9, server 3/3, Runtime Node 127/127, Sample Editor Chromium and both WebKit capability checks pass; **capture granted 4 pass / 1 declared skip and capture denied 1 pass / 4 declared skip**; the general Chromium group is **not green**, see below |

### Capture browser evidence

The two fake-device projects are the automated acceptance gate for capture
(S8B-D8). `creator-capture-chromium` streams a deterministic 2 s 440 Hz mono
48 kHz PCM16 fixture through `--use-file-for-fake-audio-capture`;
`creator-capture-denied-chromium` omits the fake UI so the headless prompt
auto-dismisses into a deterministic `NotAllowedError`. Each journey self-skips
outside its own project, which is why each run reports four declared skips.

Both projects passed on two consecutive full Proof runs at
`524864e4` and `cd182361baf1`.

### Coverage this record does not claim

- **The 60 s buffer cap has unit coverage only.** `capture_buffer.test.ts`
  proves the batch crossing 2,880,000 frames is truncated and capacity is
  reported; the end-to-end journeys assert the 5 s commit clamp instead of
  elapsing a real minute, so no browser journey reaches the cap.
- **No automated result speaks to how a capture sounds.** The fake device
  replays a synthetic tone; correct wiring is proven, audible correctness is
  not.

## Pre-existing intermittent failure, not introduced here

`creator_web_lifecycle.spec.mjs:402` and `:438` fail intermittently in the
general Chromium group. They passed at `524864e4` and both failed at
`cd182361baf1` with the same source and machine, so the behaviour is
intermittent rather than a deterministic break. At failure the page snapshot
retains only `Audio inactive` — the shell is gone — which points at a Runtime
generation replacement race in the suspend/restart path.

This family predates Stage 8B: the Stage 8 acceptance record documented the
same three journeys (then at `:346`, `:383`, `:421`) as reproducible failures,
and a `creator` lane dispatched on `40e7e7d1` — a branch state containing no
wired capture code — failed `:438` in CI. Stage 8B changes no lifecycle,
Runtime generation or audio-activation code.

It is recorded here as a known defect against `main` and tracked separately. It
is not waived: a Stage 8B Pull Request that fails this group has not passed CI,
and this record does not authorise merging over it.

Traces for both failures are retained under
`tests/platform/web/test-results/chromium/`, which is possible because two
evidence gaps were closed while investigating: CI now uploads Playwright
output on failure, and each of the Proof's six sequential Playwright
invocations writes to its own results slot instead of clearing the previous
one's.

## Defects this stage's own evidence caught

Three defects were found by gates rather than by review, each invisible to the
layer below it:

1. **The capture worklet could not load in the packaged Creator.** The
   distribution CSP is `script-src 'self' 'wasm-unsafe-eval'`, AudioWorklet
   module loading is governed by `script-src`, and the controller built its
   module from a `blob:` URL. `blob:`, `data:` and an
   `application/javascript` blob were all measured as rejected against the
   served distribution. Unit tests stub the module-URL seam and could not see
   it; the fake-device journeys caught it on their first real run. Resolved by
   S8B-D12: the worklet ships as a same-origin content-hashed asset.
2. **The wasm Runtime refused the new Host identity.**
   `products/lmdj/CMakeLists.txt` derives the Product Build from
   `version.json` but hard-codes `LMDJ_WEB_CREATOR_HOST_VERSION`, which is
   compiled into the Runtime as the manifest gate's allowlist. Allocating
   `1.0.23.0` therefore produced a distribution the Runtime rejected at boot
   with `HOST_PROTOCOL_MISMATCH`, breaking every packaged browser journey
   rather than only capture. The conformance gate now derives that constant
   from the Host manifests.
3. **Derived identity was stale after allocation.** The generated Web Runtime
   identity still carried `1.0.22.0`, which the Creator package gate rejected
   as "generated Runtime identity is stale for Product Build".

## Prohibited-boundary audit

| Boundary | Result |
| --- | --- |
| Core Module, Facade surface, transport protocol or Contract change | none; the diff against `main` touches `apps/creator-web/`, `products/`, `tools/web-runtime/`, tests and docs only |
| `resource_limits` change | none; `decoded_frames_per_pad` stays 240,000 and `imported_wav_bytes` stays 1,048,576 |
| Second limit authority in the Host | none; `COMMIT_MAX_FRAMES` is pinned to the generated manifest by a unit test |
| Input monitoring or capture routed to output | none; the source connects only to the worklet node (S8B-D4), asserted by a controller test |
| Retired `lmdj.patch.v1` / `lmdj.materials.v1` in active product source | none |
| Device identity or filesystem path in the Creator surface | none; asserted by the packaged privacy journey |

## Manual and physical acceptance rows

| Platform | Browser / device | Journey | Status |
| --- | --- | --- | --- |
| macOS | Chrome | Real microphone capture, commit and playback hearing | `deferred / unverified` |
| macOS | Chrome | External audio interface input | `deferred / unverified` |
| macOS | Safari | `getUserMedia` and AudioWorklet capture behaviour | `deferred / unverified` |
| iPadOS | Safari | Capture behaviour | `deferred / unverified` |

S8B-D8 makes these deferred by design and counted only once actually
performed. The Chromium fake device proves the pipeline, never the sound. Every
physical row inherited from Stage 6 and Stage 8 also remains
`deferred / unverified`; automation converts none of them, and they block any
physical-pass claim and promotion to Beta or Stable.

## External state

| Transition | Status |
| --- | --- |
| Push | not performed at the time of writing |
| Pull Request | not created at the time of writing |
| Merge | not authorised / not performed |
| Product tag or GitHub Release | not authorised / not created; `lmdj-v1.0.23.0` is `allocated` only |
| Deployment or publication | not authorised / not performed |
| Channel promotion | not authorised / not performed |
