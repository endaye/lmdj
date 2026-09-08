# Stage 12 independent benchmark report and onset scorer plan

Date: 2026-09-08. Status: **reviewable implementation proposal** under the
[approved benchmark design](../design/2026-08-31-lmdj-stage12-provider-benchmark-design.md)
S12B-D1–D9. Relates to #466 and #472. New GitHub Tasks are local drafts only.
No new product-level decisions or production acceptance thresholds are made.

## Scope and independence

B1/B2 operate on explicit local JSON evidence and the existing smoke corpus;
neither calls Provider SDK nor imports a Provider. They do not create capability
instances, Artifact outputs, Project candidates, Asset Lineage, Host UI, Product
identity, or active Contracts. Internal tooling schema names below are local
file-format identifiers, not new active LMDJ cross-language Contract IDs.

B1 and B2 may each start once this tool plan is accepted and a Task is authorized;
neither waits for Stage 10/11 or C-Q1–C-Q5. B2 consumes B1 only to wrap scores into
a full report; its scoring library/CLI can ship first. Give one owner the common
README/CMake/CI routing edits when sequencing them. Different directories alone
do not prove simultaneous changes to those shared files are safe.

B1 -> optional report packaging by B2. SDK execution harness, resource enforcement,
real Provider output adapter and production comparison follow separately. A
validated fabricated fixture report is a **validator test**, not benchmark evidence.

## Task B1 — closed report format and fail-closed validator

Outcome: parse, structurally validate and semantically validate retained reports
without executing Provider code. Python 3.11 standard library; reuse the existing
repository JSON Schema validator only after checking supported keywords.

Declared files:

- Create `tools/provider-benchmark/report.schema.json`.
- Create `tools/provider-benchmark/validate_report.py`.
- Create `tools/provider-benchmark/tests/report_test.py`.
- Create `tools/provider-benchmark/README.md`.
- Create `tools/provider-benchmark/tests/fixtures/report-valid.json` and
  `report-invalid.json` (explicit `evidence_kind: validator_fixture`).
- Modify root `CMakeLists.txt` to register `provider.benchmark_report`, contract
  tier, Python command and provider/benchmark labels.
- Modify `scripts/ci/scope_policy.json` and
  `tests/build/ci_change_scope_test.py` only if the new test/schema paths are not
  already covered. No wildcard extension that admits unowned unrelated tooling.

Proposed local format `format: provider-benchmark-report`, `format_version: 1`:
all objects reject unknown fields, JSON rejects duplicate keys and non-finite
numbers. UTF-8, safe-integer counts, lowercase full SHA-256 / 40-character Git
revision syntax. Object order is irrelevant on input; retained canonical output
uses sorted keys, compact separators and one final newline.

| Required field | Shape and semantic validation |
| --- | --- |
| `evidence_kind` | `validator_fixture` or `measured`; fixture documents cannot pass CLI `--require-measured` |
| `environment` | OS, kernel, architecture, CPU description, positive memory_bytes, accelerator status (`none` or device/driver), toolchain list and dependency-lock digests; no absolute paths or cache paths |
| `identity` | bench_revision, harness_revision, capability {id, contract_version, document_sha256}, candidate {publisher, provider_id, version, source_revision, artifact_sha256, license_evidence}, model (`null` for model-free or immutable revision/hash/license evidence) |
| `measurement_config` | execution_zone enum, sampler identity/revision/cadence or explicit not-applicable, deadline_ms and kill_grace_ms or explicit not-applicable; applicable values positive except nonnegative grace |
| `gates` | Tool policy version plus an array of explicit resource gates `{metric, unit, maximum, required}`; metrics limited to elapsed, peak_process_tree_rss, gpu_peak_bytes; no implicit threshold or quality gate |
| `cases` | Nonempty rows with unique fixture_id, fixture manifest_sha256, input hash/length or explicit absent-input scenario, status (`accepted`, `rejected`, `observation_only`), measurements, checks and rejection reasons |
| `rejections` | Closed reason vocabulary: determinism_violation, schema_invalid, required_output_missing, input_not_refused, timeout, memory_limit, gpu_limit; references existing case IDs, no dangling or contradictory rows |
| `supplemental_provider_reported` | Optional bounded scalar records for elapsed/RSS/GPU/server completion; never used to calculate acceptance |

Measurement record: `metric`, `execution_zone`, `measurement_source`, `unit`,
`status`, `value`. Status is `measured`, `not_enforceable`, `not_applicable` or
`missing`; only measured has a finite numeric value, other statuses require
null. Known metric/unit pairs include elapsed/seconds, real_time_factor/ratio,
peak_process_tree_rss/bytes, gpu_peak_bytes/bytes, precision/ratio,
recall/ratio, f1/ratio, tp/count, fp/count, fn/count. Unknown pairs fail closed.
Ratios stay in [0,1] only for precision/recall/F1, not RTF. Counts/bytes are
nonnegative safe integers. Source is harness, external_sampler, tool_scorer or
provider_reported; provider_reported belongs exclusively to the supplemental
section. Same row metric cannot appear twice. Zone must agree with parent.
`maximum` is finite/nonnegative with the corresponding metric's unit. Compare
measured values against the declared inclusive maximum; exact limit passes,
limit+1 rejects. An optional gate with unavailable measurement cannot be claimed
as passed. An explicitly required but unavailable gate precludes accepted.

Every case has closed `checks` entries for `determinism`, `output_schema`,
`required_outputs`, `failed_input_refusal`, each with `status` in
`pass|fail|not_applicable|not_run` and evidence digest references. Include expected
case kind (`success|input_failure`) and candidate determinism class. Applicable
checks cannot be omitted or not_run in an accepted case. A failed check requires
its corresponding rejection; no rejections means nothing if checks are missing.
Deterministic checks reference both output-set digests; seeded checks also
reference the same seed/parameters digest; equality is required for pass.
Nondeterministic candidates mark repeatability not_applicable explicitly.
Input_failure cases require failed_input_refusal=pass, with other checks scoped
as not_applicable when execution correctly never produced output. Evidence
references use supplied content digests; their external authenticity belongs to
the later harness audit, not to this JSON-only validator.

B2's undefined precision/recall/F1 are carried as status=not_applicable,
value=null with matching zero-denominator TP/FP/FN counts. They are not missing
observations or perfect scores. For defined ratios, cross-check reported values
against the integer counts within documented floating-point display tolerance.

Semantic rules derived from S12B-D3–D5:

- `in_process_reference`: elapsed/determinism/schema observations may be valid;
  hard timeout and per-Attempt RSS/GPU acceptance are `not_enforceable`. Overall
  qualification in this v1 tool format is observation_only when checks pass;
  it never encodes an overall accepted resource qualification for direct mode. Rejections for bad schema/determinism still
  apply. No in-process hard timeout/memory-limit verdict fabricated from elapsed.
- `subprocess_sandbox`: accepted requires actual harness deadline configuration,
  process-tree sampler identity/cadence and measurements for all declared hard
  gates. GPU requires attributable/exclusive measurement; otherwise GPU is
  not_applicable and a required GPU gate cannot pass. This validator checks
  evidence completeness; it cannot prove that a sampler actually ran.
- `remote`: deadline represents client request deadline/cancel; server killed
  is not a supported claim. Local Provider RSS/GPU are not_applicable. Client
  observations are explicitly distinguished from remote provider resource use.
- A missing required observation never becomes zero or accepted. Partial output,
  forbidden nondeterminism and failed-input acceptance reject a candidate before
  quality comparison. Do not encode quality threshold or production promotion.
- Contextual comparison identity must match fixture digest, metrics policy and
  execution zone; incomparable reports remain separate, not a zero-filled ranking.
- Inputs containing secret-like extension fields are rejected by the closed
  schema. Validate path-bearing fields as repository-relative POSIX paths without
  `..`, backslashes or absolute prefixes; license citations use pinned HTTPS
  evidence references without credentials/query secrets. This is structural
  hygiene, not a guarantee that arbitrary free text contains no secrets; author
  review is required before retaining measured reports.

CLI:

```text
python3 tools/provider-benchmark/validate_report.py REPORT.json [--require-measured]
```

Exit 0 valid, 1 invalid with a field path, why and remedy; parse/IO failure also
nonzero, never skip. Never fetch remote citations while validating; provenance
verification against actual external sources belongs to the measurement Task.
No report is written on failure. Limit input to a documented tool-only 8 MiB
and reject oversize before JSON parsing; this is a file-reader bound, not a
Provider memory budget or product Contract choice.

Implementation steps:

1. Write fixtures and failing tests for every zone and semantic rule.
2. Implement strict parsing, Schema validation and semantic pass with stable
   diagnostic paths. Keep side effects to reads and stdout/stderr.
3. Test wrong/absent identities, duplicate cases/metrics, NaN, wrong units,
   measured-null/unmeasured-number, provider self-report acceptance, missing
   gate evidence, cross-zone comparison, absolute paths, credentialed citations,
   oversized input and rejected required-output case incorrectly marked accepted.
4. Verify command exit status and diagnostics, not just imported helpers.
5. Register CTest and ownership, document format/zone limitations in README.

```bash
python3 tools/provider-benchmark/tests/report_test.py
python3 tools/provider-benchmark/validate_report.py tools/provider-benchmark/tests/fixtures/report-valid.json
# Expected nonzero (assert this in tests):
python3 tools/provider-benchmark/validate_report.py tools/provider-benchmark/tests/fixtures/report-invalid.json
scripts/core.sh configure dev
ctest --preset dev -N -R '^provider.benchmark_report$'
ctest --preset dev -R '^provider.benchmark_report$' --output-on-failure
python3 tests/build/ci_change_scope_test.py
```

The negative CLI command must fail for the intended reason; a missing file or
unavailable interpreter is not the expected failure. No C++ build is needed
for this Python-only CTest if configure can complete; disclose toolchain absence.

Version impact: none. Internal tools/test format only, no Product/Module/Host/
Provider/Contract/Assembly/Channel identity. Documentation impact: none. Reason:
README and retained benchmark format do not change current product availability,
Provider facts or Portal pages. Update this declaration if scope changes.

## Task B2 — deterministic onset precision / recall / F1 scorer

Outcome: produce reproducible scores from integer frame predictions, without
requiring draft `lmdj.slice-points.v1` or SDK v2.

Declared files:

- Create `tools/provider-benchmark/score_slice.py`.
- Create `tools/provider-benchmark/tests/score_slice_test.py`.
- Create `tools/provider-benchmark/tests/fixtures/predictions-basic.json`.
- Modify `tools/provider-benchmark/README.md` (B1 owner coordinates, or B2 creates
  it first with a section reserved for B1).
- Modify root `CMakeLists.txt` to register `provider.benchmark_slice_score`,
  contract tier and provider/benchmark labels; routing ownership files only if
  needed as in B1.
- Read-only: existing smoke generator, LICENSE, manifest and five WAV files.

CLI:

```text
python3 tools/provider-benchmark/score_slice.py --manifest MANIFEST.json --predictions PREDICTIONS.json
```

Tool input is a closed JSON object with `format: slice-frame-predictions`,
`format_version: 1`, `manifest_sha256`, `cases`. Each case contains exactly
`fixture_id`, `source_sha256`, `frames`. Frames are zero-based integers, strictly
increasing, unique, within the manifest's generated frame_count. Reject booleans,
negative/fractional/out-of-range numbers, duplicate JSON keys and extra fields.
Require exactly one case for each success scenario; missing/extra/duplicate
cases fail. Input_failure scenarios are excluded from quality scoring and remain
separate fail-closed conformance cases, not zero-quality examples.

Use the existing manifest verbatim: basic tolerance=480 frames, close-overlap
=240, silence=480 at 48 kHz. These are observed fixture values, not constants to
hardcode in the scorer. Read `expected.onset_frames`, `expected.tolerance_frames`
and `generation.frame_count`, validate sorted/in-range truth and nonnegative
integer tolerance. Verify manifest digest, each selected source hash and length
against actual WAV bytes; reject missing/corrupt fixtures. Repository-relative
paths resolve from a repository root, never relative to an arbitrary CWD;
reject symlink/absolute/traversal escapes. Do not modify or regenerate fixtures
in the scoring command. A future native Provider output adapter is separate
and must validate its own schema, source hash and frame rate before conversion.

### Matching policy (tool metric definition)

One-to-one maximum-cardinality matching within inclusive tolerance. With sorted
truth T and prediction P, two pointers suffice: if `P[j] < T[i]-tol`, count FP
and advance prediction; if `P[j] > T[i]+tol`, count FN and advance truth;
otherwise match this pair, count TP, advance both. Remaining predictions are FP,
remaining truths FN. This earliest-feasible rule is deterministic and maximizes
cardinality for sorted points with a uniform per-scenario tolerance. It is not
nearest-neighbor matching; a closer point must not steal a match and lower TP.
Retain matched frame pairs so scores are inspectable. No onset matched twice.

Per case: precision=TP/(TP+FP), recall=TP/(TP+FN),
F1=2TP/(2TP+FP+FN). For empty denominators use **null**, not an invented perfect
score. Thus silence with no predictions has all three null and a separate
`silence_correct: true`; silence with false predictions has precision=0,
recall=null, F1=0. Truth with no predictions has precision=null, recall=0, F1=0.
Report micro metrics computed from summed TP/FP/FN across all success cases;
false positives on silence count in the sum. Do not average nullable case ratios.
Use exact counts as authoritative values; float ratios are display derivatives.
Output tool-policy version, manifest hash, selected source identities, tolerance,
per-case pairs/counts/ratios and micro counts/ratios in canonical JSON to stdout.
No arbitrary minimum acceptable F1, no provider eligibility or promotion verdict.

### Tests and verification

Hand-computed tests: exact hits; tolerance exactly ±tol; ±(tol+1); duplicate
prediction rejection; closest-match trap (T=[0,10], P=[6,14], tol=6 => TP=2);
extra predictions; missing predictions; one prediction inside two truth windows;
empty silence; nonempty silence; all-empty micro metrics; corrupt hash/length;
wrong manifest hash; missing success case; failure case supplied as quality input;
unknown field, bool/fraction frame, invalid tolerance and path escape.
Exhaustively enumerate small sorted frame sets and compare the two-pointer TP
count to an independent brute-force bipartite matching oracle. This checks the
metric's correctness rather than mirroring its implementation. Verify output
bytes repeat and output contains no absolute host paths.

```bash
python3 tools/provider-benchmark/tests/score_slice_test.py
python3 tests/core/provider/stage12_fixture_corpus_test.py
scripts/core.sh configure dev
ctest --preset dev -N -R '^provider.benchmark_slice_score$'
ctest --preset dev -R '^provider.benchmark_slice_score$' --output-on-failure
python3 tests/build/ci_change_scope_test.py
```

After B1, test an adapter that wraps these counts with real caller-supplied
measurement identity. Do not invent SDK/Provider/checkpoint identities to make a
report validate. Scorer unit fixture output remains tool evidence.

Version impact: none. Test/scoring tooling only. Documentation impact: none.
Reason: local metric protocol and README do not alter current Portal/product
facts. No schema or Capability identity is created by these local format tags.

## Later Tasks outside B1/B2

1. Production execute harness after #467, explicitly choosing execution zone.
2. Subprocess process-group deadline/TERM/KILL and process-tree RSS measurement;
   fault injection for timeout/resource exhaustion, no in-process strong claims.
3. Remote deadline/cancel adapter and attributable GPU evidence when applicable.
4. Seeded synthetic evaluation corpora beyond smoke, Stem/Pattern fixtures and
   lawfully sourced restricted-data manifests.
5. Blind-listening package, randomized labels and separately held answer key.
6. Exact-candidate measured reports, pinned checkpoint/license/source evidence,
   resume/comparison policy and explicit production selection review.

These are remaining #466 acceptance work, not delivered by B1/B2 or #586.

## Version Management

Version impact: none. This plan and B1/B2 change retained docs or internal
benchmark tools/test data only. No module.json, Product Build, active Contract,
Assembly lock, model identity, tag, Channel or snapshot is allocated. Future
harness/Provider integration owns its separate version review. No tagging,
push, Issue mutation, release, deployment or promotion is authorized by this
plan. Revert faulty tooling through a normal corrective Task; immutable Product
identities remain unaffected.

## Documentation Impact

Documentation impact: none. Reason: retained tool plans and future tool README
are not current Architecture Portal claims. No current routes or source diagrams
change. This planning commit still runs portal check for the associated source
fact audit; B1/B2 implementation should assess actual final scope rather than
inherit an unrelated universal portal requirement.
