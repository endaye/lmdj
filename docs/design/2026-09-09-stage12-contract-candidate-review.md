# Stage 12 R1/R2 — complete review proposal

Date: 2026-09-09. Status: **proposed; requires product/Contract confirmation**.
Relates to #467 and #471. Baseline: 72de97e359b7e49ebde3af777831665ff9cf9f21.
This document supplies the choices left open by the
[confirmed byte-boundary decision](../prd/decisions/2026-09-09-stage12-byte-boundary.md)
and [Issue decomposition](../plans/2026-09-09-stage12-decision-followups.md).
It records recommendations, not allocations or an approval inferred from “continue”.
It supersedes conflicting *proposals* in the older Candidate draft if approved.

## Review decisions

| ID | Recommendation | Alternative and consequence |
| --- | --- | --- |
| R1 | Adopt the complete Slice descriptor/profile/limits/error inventory below; first reference execution is test-only | Advertising linux/macos before platform evidence would conflate design portability with measured support |
| R2-A | Keep one SDK Candidate with one slice-points Artifact; Core expands recipes in Workspace | Plural SDK results add an unrelated breaking migration without helping this one-output consumer |
| R2-B | With onsets, partition the whole source at onsets; with no onsets, expose zero recipes | Dropping leading audio loses selectable material; returning the entire silent/no-onset input implies a detection result |
| R2-C | One running Attempt per Job; preserve old active set on failure/cancel, replace it only after durable successful publication | Concurrent retries need winner arbitration and allow late completion to change the selected result |
| R2-D | Allow the same candidate on distinct explicit Pads; reject repeated target; repeat adoption requires current revision and is a new command | A durable idempotency receipt would introduce another cross-store commit protocol |
| R2-E | Compare source Asset identity and full ArtifactRef; unrelated Project revisions do not invalidate candidates; no automatic expiry | Invalidating every edit needlessly discards usable analysis; wall-clock expiry requires retention/clock policy |
| R2-F | Extend existing Asset.lineage with one closed capability-adoption derivation; preview read-only; multi-Pad adoption atomic | Generic optional-field lineage and multiple truth carriers make incomplete provenance representable |

R1 approval enables K1 once its exact current file inventory is refreshed below.
R2 approval resolves the named product choices; it does not skip L1–L5 exact
implementation planning, version allocation or verification.

## R1: complete capability instance

Proposed path: `contracts/capability/sample.slice.v1.json`.
The JSON below contains every required field of the unchanged
[capability.v2 schema](../../contracts/capability/lmdj.capability.v2.schema.json).
The instance's `contract_version` identifies this consumer contract, not the
schema envelope's existing `2.0.0` version.

```json
{
  "contract": "lmdj.capability.v2",
  "capability_id": "sample.slice.v1",
  "contract_version": "1.0.0",
  "input_artifacts": [{
    "name": "source_audio",
    "media_types": ["audio/wav"],
    "schema_id": "lmdj.audio.pcm16-wav.v1",
    "schema_version": "1.0.0",
    "required": true,
    "max_count": 1
  }],
  "output_artifacts": [{
    "name": "slice_points",
    "media_types": ["application/json"],
    "schema_id": "lmdj.slice-points.v1",
    "schema_version": "1.0.0",
    "required": true,
    "max_count": 1
  }],
  "determinism": "deterministic",
  "progress_events": ["analyzing"],
  "errors": ["PROVIDER_FAILED", "UNSUPPORTED_AUDIO", "INVALID_ARGUMENT"],
  "resources": {"class": "cpu", "memory_mib": 64},
  "execution": {"timeout_ms": 1000, "max_attempts": 1},
  "policy": {
    "data_classifications": ["public", "private"],
    "regions": ["local"],
    "required_permissions": ["sample.slice.execute"]
  }
}
```

### C++ descriptor, permission and budget consumers

These values belong outside the closed JSON schema:

| Value | Exact proposal | Consumer / obligation |
| --- | --- | --- |
| `platforms` | `["test"]` for K3 reference registration in tests | SDK `CapabilityDescriptor.platforms`, checked by `validate_request` in attempt_store.cpp; no measured native platform support claimed |
| `max_output_bytes` | 262144 aggregate bytes | SDK descriptor/execution; exact-limit and +1 rejection |
| `maximum_input_bytes` | 16777216 aggregate bytes | Proposed K2 execution ingress; checked before owner reads/staging |
| `maximum_output_bytes` | 262144 | Proposed K2 ingress, intersected with descriptor ceiling |
| `staging_budget_bytes` | 67108864 reference ingress allowance | Proposed K2 shared lease budget: input copies, output staging and validator scratch together; lower Host allowance prevails |
| permission | request includes `sample.slice.execute`; Host explicitly grants the same token | Existing `ProviderPolicy.granted_permissions` plus descriptor policy, checked in attempt_store.cpp |
| classification / region | request chooses `public` or `private`, region `local`; Host allowlists also must allow it | Existing SDK policy checks; local is an execution policy token, not a filesystem permission |
| native platform promotion | K4 may advertise only individually measured and reviewed tokens | No unconditional linux/macos registration and no implicit permission grant |

`test` is an existing testing token, not evidence that any native/Web Host
journey works. K4/K5 must allocate the actual supported platform inventory.
Timeout is observation in direct execution, not preemption. The lease budget
does not bound arbitrary Provider allocations or owner RSS. No network access
is part of this consumer contract.

### Binary profile and request parameters

Proposed profile document:
`contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md`, identity/version as above.
It is a binary profile, not JSON Schema over WAV bytes.
Accept RIFF/WAVE little-endian PCM format code 1, 16-bit mono/stereo, 44100 or
48000 Hz, one fmt and one data chunk, nonzero complete frames. Require matching
block alignment/byte rate, bounded declared RIFF size matching actual bytes,
complete chunk headers/data/padding, and data length divisible by block alignment.
Skip well-formed unknown chunks; reject duplicate fmt/data, RF64, extensible/
compressed/float formats, truncation and zero-frame audio. fmt payload length
is 16, or at least 18 with its uint16 cbSize exactly equal to payload length
minus 18; extension bytes do not change PCM sample interpretation. Odd-sized
chunks require their pad byte within the declared RIFF boundary.
This formalizes the first consumer's profile; existing general import behavior
is not narrowed by a retained proposal.

Parameters accept only optional integer `threshold_pcm16` in [1,32767]
(default 4096) and `refractory_frames` in [1,decoded frame_rate] (default 240).
Reject bool, fraction, unknown keys and path/permission parameters.
The reference detector uses maximum absolute channel amplitude, widened for
-32768; emit on a below-to-at/above-threshold transition if far enough from the
last emitted frame, with prior-to-frame-0 amplitude zero. No resampling.
Equivalent omitted/default parameters produce the same reference output bytes;
Attempt provenance retains the SDK's hash of the actual submitted parameters,
not a fabricated hash of normalized defaults.

### Output shape and contextual validation

Proposed schema path: `contracts/slice-points/lmdj.slice-points.v1.schema.json`,
ID `lmdj.slice-points.v1`, initial version `1.0.0`.
Required root keys: `contract` (that exact ID), `source_sha256`,
`frame_rate`, `points`; reject extra root/point keys.
Each point requires integer `frame`; optional `confidence` is finite [0,1],
optional `label` is nonempty valid UTF-8, at most 128 encoded bytes.
Integers are within [0,9007199254740991], rate positive. At most 4096 points;
frames strictly ascending, each less than decoded frame_count; source hash
equals input binding, rate equals decoded source rate. Empty points are valid.
EOF is never an onset. Reject duplicate JSON keys, NaN/Infinity, malformed UTF-8.

Reference bytes: UTF-8, object keys lexicographically ordered, compact JSON,
no BOM or terminal newline, integer frame/rate tokens. Reference emits no
confidence/label. Other implementations must demonstrate their own byte replay;
this proposal does not invent a universal floating-point canonicalization rule.

Schema conformance owns shape; a consumer validator owns byte syntax, UTF-8 byte
limits, ordering and input-context equality. Place reusable validators in the
new local-sample-slice package's validation.hpp/.cpp (K3), injected into Registry
and executed before terminal (K2 generic interface). K1 adds Python conformance
vectors, not an SDK dependency on the Slice package. Thus K2 can land with proof
validators and generic test validators before K3 supplies this consumer.

### Failure ownership

| Owner / defect | Code / reason | Required observation |
| --- | --- | --- |
| SDK: wrong port/count/media, duplicate hash, unauthorized source callback | INVALID_ARGUMENT / input_binding_invalid | No unauthorized owner read; active callback error latches failure |
| SDK: input unavailable | NOT_FOUND / input_artifact_unavailable | No Provider run |
| SDK: hash/length mismatch | IO_ERROR / input_artifact_mismatch | No Provider run |
| SDK: aggregate input limit/overflow | INVALID_ARGUMENT / input_artifact_too_large | Reject before staging allocation |
| Provider: invalid parameters | INVALID_ARGUMENT / slice_parameters_invalid | Only this declared parameter reason may propagate |
| Provider: unsupported WAV | UNSUPPORTED_AUDIO / source_audio_unsupported | Preserve declared domain failure |
| Provider: detector failure, including more than 4096 onsets | PROVIDER_FAILED / slice_analysis_failed | No truncation masquerading as complete output |
| SDK: output shape/binding/count/size or ignored sink error | PROVIDER_FAILED / output_contract_invalid | Empty terminal output lists; no visible candidates |
| consumer validator: invalid JSON/context | PROVIDER_FAILED / output_schema_invalid | No success publication |
| SDK: Provider exception or undeclared error/reason | PROVIDER_FAILED / output_contract_invalid | Preserve diagnostic evidence; no spoofed policy/owner error |
| SDK: selection/policy refusal | Existing PROVIDER_NOT_FOUND / PERMISSION_DENIED paths | No new Provider-owned permissions or error codes |
| durable store I/O | Outer IO_ERROR if terminal cannot be persisted | Do not fabricate a durable failure/success receipt |

For the three Provider domain codes, only the exact three corresponding reasons
above propagate. SDK failures retain SDK authority. Existing C-Q4 late callback
rules remain: closed source/sink returns INVALID_ARGUMENT with its binding/
output-contract reason and cannot rewrite terminal. Existing C-Q5 terminal
visibility and retained interrupted reservation rules remain unchanged.

## R2: Candidate recipes and lifecycle

### Result identity and recipe rule

Keep SDK `AttemptResult.candidate` singular. Its outputs contain the one
validated slice-points Artifact. A Workspace CandidateSet is a consumer view,
not extra SDK terminal candidates. Persist the mapping from Job/Attempt/output
identity to CandidateSet and recipe IDs in Workspace owner state. Allocate IDs
once and persist them; replay reuses them. SDK candidate IDs and Core recipe
candidate IDs must be represented as distinct fields, never substituted in
terminal evidence.

Given source frame_count N and validated onset set P:
- P empty: zero candidates; a successful empty set is still a completed result.
- Otherwise boundaries are sorted unique `{0} union P union {N}`.
- Each adjacent pair yields a nonempty half-open `[start,end)` interval.
- Order by start frame. A leading pre-onset interval is selectable like any
  other; the final interval ends at N. Up to 4097 recipes from 4096 onsets.

Examples: N=1000, P=[100,400] yields [0,100), [100,400), [400,1000);
P=[0] yields [0,1000); P=[] yields no candidates. Provider points stay unchanged.
First adoption materializes the selected interval into an independent PCM16 WAV
Artifact using Core's bounded sample pipeline; source bytes and source Asset
are retained. Preview can read the source interval without materialization.
No-onset is a visible “no slices detected” result, not automatic whole-file import.

### Job serialization and durable visibility

Workspace owner (Facade-owned state; SDK holds only immutable Attempt evidence)
owns JobRecord, CandidateIndex and recipe expansion. Do not add public Job API
to SDK merely to store this consumer state. Admit one active Attempt per Job;
a concurrent start is refused with INVALID_ARGUMENT / job_busy. Different Jobs
may execute independently; mutations for one Workspace are serialized, including
publication, cancel, discard and adoption eligibility checks. Cross-process
writers must acquire the same Workspace mutation ownership or be refused.

Persist Job intent and allocated Attempt ID before execute. Terminal success
alone is insufficient for a visible CandidateSet: validate terminal and bytes,
build recipes, then atomically persist one owner-state transition containing
new active set, stable recipe IDs, ordered Job history and old-set supersession.
Use one durable publication boundary, not separate active-pointer/tombstone writes.
Terminal files are never rewritten.

A failed/cancelled retry leaves the preceding active set available. Successful
publication, including an empty set, supersedes the previous set. Starting a
retry alone does not supersede it. Cancellation durable before publication
prevents that Attempt becoming active even if direct Provider execution later
returns success; cancellation after committed publication returns an explicit
already-completed refusal. It cannot pretend publication was rolled back.

Restart inspects recorded Attempt IDs, never scans blobs: completed valid
terminal plus pending owner intent may publish exactly once; absent terminal
remains interrupted/unavailable and is not silently re-executed. An interrupted
Job may explicitly retry with a new Attempt ID after recovery; old evidence is
retained. L1 must prove this minimal recovery before lifecycle extensions in L4.

### Adoption, source freshness and repeated requests

AdoptCandidates requires current `expected_revision`, one active CandidateSet
and a nonempty explicit list of candidate/Bank/Pad pairs. Reject missing targets,
duplicate targets, cross-set selections and unknown IDs. Repeating a candidate
on different Pads is allowed; every target gets its own Derived Asset identity.
Sort by Bank/Pad before deterministic ID allocation and mutation.

Bind source by original project identity, Asset ID and complete ArtifactRef
(hash, length, media type). Missing source -> NOT_FOUND / source_asset_missing;
changed binding -> REVISION_CONFLICT / candidate_source_changed.
An unrelated Project edit is allowed if the caller supplies current revision and
the source binding still matches. Lineage retains the original analysis source
revision, not adoption revision. Identity mismatch of Project or stale
expected_revision fails before materialization.

Adoption does not consume a CandidateSet. Repeating with the old revision
returns REVISION_CONFLICT; a newly confirmed request with current revision is
a new explicit adoption. This first version promises no idempotent command replay.
Clients receiving an unknown commit response inspect Project before retrying.
No automatic TTL: active, superseded and discarded are the availability states;
discard is durable tombstone only, never GC. Missing/corrupt bytes makes a read
unavailable; it does not erase lineage or rewrite terminal.

Hold owner mutation eligibility across the Project commit boundary, or use an
equivalent checked generation under the same serialized owner. A discard/retry
publication before that boundary causes candidate_unavailable; if adoption wins,
it completes atomically before later lifecycle changes. Candidate state has no
“adopted” write, avoiding a Project/Index dual-write transaction.

### Lineage field authority

Reuse `Asset.lineage.source` = existing asset_artifact variant with
`artifact_sha256` and `project_revision`. Add one closed
`capability_adoption` derivation for this Slice journey:

| Required derivation field | Authority |
| --- | --- |
| capability {id, contract, version} | Validated terminal capability identity |
| provider {id, version, artifact_sha256} | Validated terminal provider identity; hash is the registered source-package identity, not a claimed binary digest |
| model_identity | Exact terminal {id, version, artifact_sha256} or explicit null for reference detector |
| parameters_sha256 | Terminal request metadata, never reconstructed from UI defaults |
| attempt_id | Validated immutable terminal |
| source_asset_id | Workspace job source binding checked against Project at adoption |
| output_artifact {sha256, media_type, byte_length} | Terminal slice_points binding |
| recipe {kind: slice_interval_v1, start_frame, end_frame, frame_rate} | Core rule above plus validated source metadata |

The source variant carries source hash/revision once. Derived Asset.artifact is
the result identity. No duplicated timestamps or optional bag of unrelated
trim/copy fields; resample and soundset_install retain their exact existing
fields and load/save behavior. Future stems/other recipes need a separate
closed variant review. Job/recipe IDs stay Workspace references, not additional
authoritative lineage fields; Attempt + output + interval provides derivation
evidence even without the candidate index.

### Preview, quota and far-side acceptance

Preview may allocate transient Runtime resources but changes no Project, Pad,
Asset lineage or revision. Explicit stop and Host restart release/rebuild transient
playback; they must not publish Project state.
For adoption, simulate all final Pad bindings before commit, including existing
playback/preparation rules. Per-Pad prepared PCM is charged separately even for
identical bytes, replacing each target's old charge. Reuse per-Bank and total
generation limits, and keep resident publication backpressure distinct from
Project quota errors. Materialization/save failure leaves all Project state
unchanged; unpublished blobs are not visible adopted Assets.

| Transition or failure | Far-side assertion required in L tests |
| --- | --- |
| Request -> failed Provider | No new CandidateSet; Project and prior active set unchanged |
| Valid terminal -> crash before owner publication -> restart | Same recorded Attempt publishes once; stable set/recipe IDs, no blob discovery |
| Owner-state publication -> crash -> restart | New active pointer and old supersession agree; terminal bytes unchanged |
| Cancel -> late successful terminal -> restart | Cancelled output never becomes active; old set remains |
| Preview -> stop -> reload | Project/Pad/Asset/revision unchanged, no continued preview |
| Discard/supersede -> adopt | candidate_unavailable; no Project changes |
| Stale revision/source mismatch/missing bytes -> adopt | Typed refusal and complete Project equality |
| Multi-Pad quota/preparation failure -> inspect/reopen | All targets unchanged, no partial Derived Assets or revision |
| Multi-Pad success -> save/reopen | Exactly one revision, all target bindings and full lineage/artifact identities retained |
| Same candidate to two Pads -> inspect | Independent Asset IDs and two prepared charges |
| Duplicate target / repeated old-revision command | Refusal with no second revision |
| Lifecycle/adoption race, both orders | Exactly the serialized winner's result; no half-applied Pad list |

These are planned obligations, not evidence that implementation already passes.

## Version Management

Version impact: none for this retained proposal. Candidate recipe expansion
requires no plural SDK result ABI. K2 still has its independently approved MAJOR
direction for byte access. L1 initially belongs to the Facade's Workspace owner;
its exact API changes determine Facade SemVer. L3 extends a closed Project union,
so allocate a successor Contract and affected domain/project-io versions against
current manifests, preserving old-contract read/migration coverage. No numeric
Module, Product Build or Contract successor is reserved here.

## Documentation Impact

Documentation impact: none for this Task: retained proposals only, no Portal
availability or manifest change. Implementation routes include
/contracts/capability/, /contracts/artifact-audio/, /contracts/slice-points/,
/contracts/project/, /core/modules/provider-sdk/, /core/modules/application-facade/
and affected domain, project-io, Provider and Host pages. Confirm actual route
files in each implementation Task; current root is apps/docs-site.
