# Provider benchmark tools

These Python 3.11 standard-library tools consume local evidence. They do not
execute Providers or depend on Stage 10/11, Provider SDK migration, or draft
Capability decisions. The smoke generator remains a separate existing tool.

## Report validator (B1)

```bash
python3 tools/provider-benchmark/validate_report.py REPORT.json
python3 tools/provider-benchmark/validate_report.py REPORT.json --require-measured
python3 tools/provider-benchmark/tests/report_test.py
```

Exit 0 means the report's structure and internal claims are consistent. Exit 1
means invalid evidence or a read/parse failure; stderr names a field path, why,
and remedy. CLI usage errors exit 2. The command only reads local files and
prints diagnostics. It never executes a Provider, fetches a citation, writes a
report, authenticates evidence, or chooses a production Provider.

`--require-measured` rejects `validator_fixture`. Changing the marker does not
prove a run happened: the later harness audit must authenticate all identities,
measurements and referenced evidence. Both committed fixtures are fabricated
validator tests, including their hashes, revisions and `example.invalid` license
citation. They are not candidate benchmark results.

Inputs are UTF-8 JSON, at most 8 MiB (read before parsing). Duplicate JSON keys,
nonfinite numbers (including exponent overflow), invalid Unicode surrogates,
unknown fields and unsupported enum values fail closed. Semantic nesting is
bounded at 128 levels. Counts and byte values are integers in [0, 2^53−1];
booleans are not numbers. SHA-256 digests are 64 lowercase hex characters and
Git revisions are 40. Strings are bounded to 512 non-control characters except
fixed digests. Canonically retained reports use sorted object keys, compact
separators, and one final newline; input object order does not matter.

[report.schema.json](report.schema.json) is the complete structural definition.
It uses only the explicitly supported subset of the repository's
`tests/conformance/json_schema.py`; the semantic validator enforces cross-field
rules. This is internal tool format version 1, not an active product Contract.

| Field | Required evidence |
| --- | --- |
| `format`, `format_version` | `provider-benchmark-report`, integer `1` |
| `evidence_kind` | `validator_fixture` or `measured` |
| `environment` | OS, kernel, architecture, CPU, positive memory bytes, accelerator (`none` or device/driver), nonempty toolchain name/version list and dependency lock path/digest list |
| `identity` | Bench/harness Git revisions; capability id/version/document digest; candidate publisher/id/version/source revision/artifact digest/license evidence/determinism; model null or id/revision/artifact digest/license evidence |
| `measurement_config` | Execution zone, sampler configuration or literal `not_applicable`, deadline milliseconds or `not_applicable`, kill grace milliseconds or `not_applicable` |
| `gates` | Explicit policy version and unique resource gates `{metric, unit, maximum, required}` |
| `cases` | Unique fixture id, manifest digest, input `{status: present, sha256, byte_length}` or `{status: absent}`, case kind, qualification, measurements, checks, rejection reasons |
| `rejections` | Exactly one fixture-id/reason row for each case rejection; no dangling or duplicate entries |
| `supplemental_provider_reported` | Optional, at most 256 unique case/metric scalar records; never acceptance evidence |

License evidence is `{url, sha256}`. URLs must use HTTPS, contain a host, and
have no credentials, query, fragment, explicit port, encoded whitespace or
backslash. The digest pins the cited content; this tool does not authenticate
it. Dependency lock paths must be repository-relative POSIX paths without empty,
`.`/`..`, drive/absolute prefixes, backslashes, or `.cache`/`__pycache__` segments.
No filesystem existence or symlink claim is made for these citation paths.
Closed fields reject secret-bearing extensions, but arbitrary free text still
requires author review before retaining measured evidence.

## Measurements and qualification

Each measurement contains `metric`, `execution_zone`, `measurement_source`,
`unit`, `status`, `value`. `measured` requires a finite nonnegative number;
`not_enforceable`, `not_applicable`, and `missing` require null. A case cannot
repeat a metric or mix execution zones.

| Metric | Unit | Authoritative source |
| --- | --- | --- |
| elapsed, real_time_factor | seconds, ratio | harness |
| peak_process_tree_rss, gpu_peak_bytes | bytes | external_sampler |
| tp, fp, fn | count | tool_scorer |
| precision, recall, f1 | ratio | tool_scorer |

Precision/recall/F1 lie in [0,1]. RTF can exceed one. Quality metrics must appear
as a complete set of three exact counts and three derived ratios. Precision is
TP/(TP+FP), recall TP/(TP+FN), F1 2TP/(2TP+FP+FN). Zero denominators require
`not_applicable`/null; defined ratios must match counts within absolute display
tolerance 1e-12. No quality threshold or perfect-score substitution exists.

Resource gates cover only elapsed/seconds, process-tree RSS/bytes and GPU/bytes.
They carry explicit finite nonnegative maxima: equality passes, excess rejects.
Unavailable required evidence prevents acceptance; optional unavailable evidence
remains unavailable. Optional gate exceedance still rejects when measured.
An elapsed value exceeding the configured deadline also records timeout; for
remote reports this means client deadline exceeded, not server process killed.
Kill grace describes termination configuration, not extra execution allowance.

| Zone | Qualification and resource meaning |
| --- | --- |
| `in_process_reference` | Passing checks are `observation_only`, never `accepted`. Sampler, deadline and kill grace are `not_applicable`; RSS/GPU rows are `not_enforceable`/null. Elapsed observation cannot generate hard timeout or memory/GPU rejection. |
| `subprocess_sandbox` | Acceptance requires a positive configured deadline, nonnegative kill grace, process-tree sampler id/Git revision/positive cadence, measured harness elapsed and externally sampled process-tree RSS, plus every required gate measurement. |
| `remote` | Acceptance requires measured client elapsed and client deadline configuration. Kill grace is `not_applicable`; Provider RSS/GPU rows are `not_applicable`/null. An optional sampler is scoped to `client`, never server resources. |

Sampler records contain `id`, `revision`, `cadence_ms`, `scope`,
`gpu_attribution`, `gpu_evidence_sha256`. GPU attribution is `not_applicable`
with null evidence, or `exclusive`/`attributable` with a digest and a configured
sandbox accelerator. Only the latter can support measured GPU bytes. This
checks completeness, not whether process-tree sampling or termination occurred.

Every case declares `success` or `input_failure` and checks for determinism,
output schema, required outputs, and failed-input refusal. Every performed check
requires retained evidence digests. Success requires present input identity and
passing applicable output checks; input-failure requires passing refusal, with
output checks not applicable. A failed applicable check requires the matching
rejection. `not_run` can occur only on a rejected case with another evidenced
failure; it cannot support acceptance or passing observations.

Candidate determinism is `deterministic`, `seeded`, or `nondeterministic`.
Performed repeatability checks contain exactly two output-set digests, equal
for pass and different for fail. Seeded comparisons additionally contain two
identical seed digests and two identical parameter digests. Nondeterministic
candidates explicitly mark repeatability not applicable. Unperformed checks
carry no evidence or comparison digests.

Closed rejection reasons are `determinism_violation`, `schema_invalid`,
`required_output_missing`, `input_not_refused`, `timeout`, `memory_limit`,
`gpu_limit`. Case status is rejected exactly when the checks/gates establish
one or more reasons. Partial output or forbidden nondeterminism cannot be
hidden by a good quality score. Non-rejected cases outside direct mode may be
`observation_only` when hard-gate evidence is incomplete.

Supplemental rows contain fixture id, metric, `measurement_source:
provider_reported`, and a scalar value. Metrics are elapsed/RSS/GPU (numeric or
null) or `server_completed` (boolean or null). This last value is an explicitly
untrusted server report, never a local cancellation or kill verdict.

The importable `comparison_key(report)` validates its input and returns a
canonical contextual key including fixture ids/digests/input identities, full
resource policy, execution zone and capability identity. Different keys must
remain separate. Equal keys are necessary context, not proof that machines,
samplers or candidates are equivalent; no ranking, zero filling, or environment
normalization is performed.

## Verification and remaining scope

CTest `provider.benchmark_report` runs the Python boundary suite in the contract
tier with provider/benchmark labels. It detects reports that incorrectly qualify
missing, self-reported, contradictory or zone-inappropriate evidence. The suite
checks accepted and rejected cases, numerical boundaries, CLI exit diagnostics,
read-only behavior and comparison separation. It does not substitute fabricated
reports for real harness/Provider acceptance runs.

B2 onset scoring, SDK execution, deadline/process-group enforcement, real
process-tree/GPU sampling and measured candidate evaluation remain separate
Tasks under the [benchmark plan](../../docs/superpowers/plans/2026-09-08-lmdj-stage12-benchmark-tools.md).

Version impact: none. Internal tooling/test format only; no Product, Module,
Host, Provider, Contract, Assembly or Channel identity changes.
Documentation impact: none. This README documents local tooling; current
Architecture Portal pages and product availability are unchanged.
