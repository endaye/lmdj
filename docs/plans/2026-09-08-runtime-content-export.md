# B2 T2 — bounded runtime content and computer-side export

Status: implementation verified locally; current-head review and shipping are
tracked by the Task Pull Request. Scope was authorized by the user's confirmation
of the [first-slice decision](../prd/decisions/2026-09-08-runtime-content-first-slice.md).
Base: `cdeb4c3e7f417e1bf17b5266f98f26d86376052a` (includes T1).
One reviewable Task: an export and read-back of the same derived content boundary.
No T3 lifecycle, T4 device build, T5 Host/Assembly or flashing is included.

## Declared files

- this plan
- `docs/prd/decisions/2026-09-08-runtime-content-first-slice.md`
- `contracts/runtime-content/README.md`
- `contracts/runtime-content/lmdj.runtime-content.v1.schema.json`
- `tests/fixtures/contracts/runtime-content-valid.json`
- `tests/fixtures/contracts/runtime-content-invalid-slot.json`
- `tests/fixtures/contracts/runtime-content-v1.hex`
- `tests/conformance/runtime_content_contract_test.py`
- `tests/conformance/schema_contract_test.py`
- `tests/build/version_test.py`
- `packages/project-cooker/include/lmdj/cooker/runtime_content.hpp`
- `packages/project-cooker/src/runtime_content.cpp`
- `packages/project-cooker/CMakeLists.txt`
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/src/application.cpp`
- `packages/application-facade/CMakeLists.txt`
- `tests/core/cooker/runtime_content_test.cpp`
- `tests/core/facade/runtime_content_export_test.cpp`
- `CMakeLists.txt`
- `apps/docs-site/docs/contracts/runtime-snapshot.mdx`
- `apps/docs-site/docs/core/modules/project-cooker.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/diagrams/project-cooker.architecture.json`
- `apps/docs-site/static/diagrams/project-cooker.html` (generated)
- `apps/docs-site/static/diagrams/project-cooker.svg` (generated)
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html` (generated)
- `apps/docs-site/static/diagrams/application-facade.svg` (generated)

## Engineering boundary

Introduce `lmdj.runtime-content.v1` with Contract SemVer `1.0.0`. Its normative
binary layout and semantic-projection schema live together under
`contracts/runtime-content/`. The schema describes decoded metadata, **not** a
JSON transport or C++ memory image. The independent Python conformance reader
and C++ codec consume the same retained hex fixture. No new Module or third-party
dependency is needed: reuse the vendored picosha2 privately in Project Cooker.

The little-endian, uncompressed encoding has a fixed header, ordered Pad and
event tables, then length-and-SHA-256-bound sample bodies. Each sample body
includes rate, channels and frame count in its digest, so identical raw PCM
with different interpretations cannot alias. Full content identity is SHA-256
and byte length over the complete encoding, supplied separately to the reader;
there is no self-referential digest field or dependency URL/path.

Existing 48 kHz mono/stereo PCM16, resolved playback, gain/mute and all four
trigger modes are retained. Events name Pad Slots only. Canonical Pad order,
unique event keys/order, first-use sample order, deduplication and exact framing
make repeated encoding deterministic. Unknown versions/required capabilities,
nonzero reserved fields, trailing/truncated bytes, invalid identity, unclosed
references, invalid timing/playback, overflow and explicit budget violations
fail closed. No sample truncation, event dropping or automatic downsampling.

`RuntimeContentLimits` is an explicit caller-owned limit set for encoded bytes,
unique decoded PCM bytes, per-sample frames, Pad count and event count. Zero is
not unlimited. Checked lengths and counts precede allocation; all sample bodies
are validated before constructing the immutable decoded Snapshot. These are
codec limits, not the future complete Engine/FX/stack/DMA admission budget.

The full Facade adds a typed `export_runtime_content` entry point: absolute
Project path, expected Project ID/revision, one Pattern ID, explicit extra live
Pad Slots and codec limits. Core includes all event-referenced slots plus the
requested extra live slots. It filters a detached Project value before Cook,
never Project Truth, and includes no unrelated Pad material. A later Project
revision does not change an already loaded source value; exported provenance
names exactly that value. Artifact resolution retains existing byte/hash
validation. An absent/unassigned live slot is an error, never silently omitted.
Existing ProjectStore loading verifies every source Asset; a corrupt unselected
Asset therefore still rejects the source before export. Narrowing only avoids
unrelated PCM cooking/encoding, not source integrity validation. Codec budgets
apply after computer-side source loading/Cook, not to that earlier memory peak.

Host gets opaque bytes and complete identity; it does not inspect Project or
call Cooker. T2 does not add a CLI/UI operation or a device Host API. T3 will
wrap the Core decoder inside its Runtime Facade; returning a Core Snapshot to
Core callers here does not authorize a device Host to construct one.

## Tests and evidence

Baseline: configure dev, build/run `cooker.project`, `facade.application`,
`facade.performance_runtime_consumer` and `facade.c_api` before product edits.

Lowest-tier new tests:

- `cooker.runtime_content` (unit): fixed portable bytes, round trip including
  stereo/extreme PCM/gain/trim/mute/modes, canonical closure and sharing, empty
  content, malformed fields, digest/length, every budget exact/+1 and overflow.
  Its compile negative control rejects leaked Project IO/Provider roots.
- `facade.runtime_content_export` (component): real Facade-created Project and
  imported WAV, exact Project/revision binding, event plus extra live Pad
  closure, repeated identity, corruption/error preservation and unchanged
  persisted Truth. No Host-level Project parsing or runtime publication.
- `conformance.runtime_content` (contract): independently parse and validate
  fixed bytes and C++-emitted bytes, compare semantic projection with the schema,
  and reject malformed framing, references, capabilities and identities.

Register both native executables in coverage inventory and the Python reader
in CTest. Prove the new test registrations execute with deliberate red controls,
then rebuild green (not a stale binary). No new workflow or threshold.

Final verification: new tests plus all Cooker/Facade registrations and existing
native/Web control consumers; `scripts/core.sh coverage check`; ASan on the
new native codec/export tests for malformed bytes; schema/version/active-tree
and dependency checks; staged-index ownership suite; generated diagrams and
`scripts/docs-site.sh check`; exact committed inventory and independent review.
Hardware, browser UI, deadline and physical sound remain unexercised.

### Pre-commit verification record (2026-09-09)

- Baseline four tests: PASS before product edits.
- Fresh dev build; all Cooker/Facade/schema/content selected regressions:
  32/32 PASS. Native/Web control, realtime and Performance consumers: 6/6 PASS.
- New ASan native codec/export tests: 2/2 PASS, including malformed bytes and
  allocation-failure recovery. Final added request/fault/schema cases also PASS.
- `scripts/core.sh coverage check`: 137/137 tests, all floors PASS. Overall
  line/branch 83.75%/70.37%; Cooker 93.09%/85.93%; Facade 86.82%/72.72%.
- Version/source inventory, active tree and vendored dependency checks: PASS.
  Staged-index path ownership: 66/66 PASS, including every tracked path.
- Generated both diagrams; `scripts/docs-site.sh check`: 86 tests and 42 rendered
  routes/internal links PASS. npm reported existing dependency advisories; no
  dependency versions or gate thresholds were changed.
- Red controls: absent C++ implementation symbols rejected both new native
  consumers; a deliberate Python assertion failed registered CTest and returned
  green after removing only that fault. Large-allocation tests exposed SHA
  whole-range buffering, now fixed with bounded chunks and retained regressions.
- Facade journey: create/import/assign → export/decode → repeat/reopen → bad
  request or corrupted Asset rejection → unchanged source inventory → restore
  fixture and retry exact identity. Existing all-Asset source validation remains
  intact; unselected corruption is not a recovery bypass.

These are local source checks, not a full remote lane run, device readiness or
physical sound acceptance. The PR retains exact commands and current-head review.

## Version Management

Version impact: new Contract `lmdj.runtime-content.v1` / `1.0.0` with schema,
fixtures and conformance. No existing selected Contract is modified.

Prospective compatible Module MINOR changes are Project Cooker `1.1.0` → `1.2.0`
and Application Facade `3.1.0` → `3.2.0`; api_version remains unchanged. Allocation
belongs to the later reviewed B2 Assembly integration, not a new independently
shipped Package in this source-only Task (same staged allocation model as
Stage 11). Active Module manifests, selected Assembly and lock remain unchanged;
the new Contract is not represented as already selected by the desktop Assembly.
Before any B2 Package/Build distribution, pay those MINORs against live manifests,
lock all consumers and the new Contract, allocate a fresh Product BUILD (not a
PATCH), update generated identities and freeze its immutable Portal snapshot.

No Product Build, Channel, tag or Release is allocated here. No migration of
Project Truth or retired Contract is permitted. Rollback is the Task commit,
not mutation of any previously allocated identity. Release remains unauthorized.

## Documentation Impact

Documentation impact: required
Affected portal pages: /contracts/runtime-snapshot/ /core/modules/project-cooker/ /core/modules/application-facade/
Reason: current source gains a derived-content boundary, computer export and
validation evidence; update both affected Module source diagrams. Distinguish
source implementation from an Assembly-selected Contract or device product.
No Build snapshot is introduced by this Task.

## Pitfall Impact

Pitfall impact: none — apply positive-control, staged ownership, CTest/coverage
registration, fixed budget and complete-identity guidance. Product regression
tests own codec defects; no new process failure is claimed.
