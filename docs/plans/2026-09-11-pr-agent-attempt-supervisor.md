# S1 bounded installed-attempt supervisor implementation

Date: 2026-09-11 (Asia/Shanghai)

Status: locally implemented and verified on the exact clean-base checkout;
shipping authority ends at one local Conventional Commit. This plan records
the source contract and the actual local evidence. It does not claim the
protected manifest is installed, Linux PID1/systemd acceptance, provider
health, runner capacity, T5 shadow, T6 cutover, or operational handoff.

## Baseline, ownership, and boundaries

The source baseline is `892029848ea313754ca4fac6f325812e49df8d18`, equal to
`origin/main` before this Task. The implementation is confined to exactly
these five declared files:

1. `scripts/ci/pr_agent_attempt_supervisor.py` — fixed root-triggered public
   entrypoint, closed schemas, durable state, single-slot launch, observation,
   recovery, closure, output authentication and terminal readback.
2. `tests/build/ci_pr_agent_attempt_supervisor_test.py` — real local Popen,
   pipe, descriptor, flock, filesystem and public-entrypoint journeys with
   low-level root/PID1/identity seams.
3. `docs/plans/2026-09-11-pr-agent-attempt-supervisor.md` — this selected
   contract and verification record.
4. `docs/quality/2026-09-10-pr-agent-netcup-operations.md` — source/local
   operations boundary and explicit not-installed state.
5. `apps/docs-site/docs/operations/testing-and-proof.mdx` — Portal source
   route and source/local versus installed/provider/T5/T6 separation.

No installer, bundle/inventory, workflow, producer, adapter, credential,
funding/ledger, dependency, required-check, host, provider, GitHub or cleanup
path is changed. S2 owns protected installation and removal of the old active
flock launcher; S3 owns the complete producer/input receipt; S4 owns trusted
Actions intake and runner isolation; later Tasks own paid/provider shadow and
formal cutover.

## Fixed public interface

`main(argv)` accepts exactly one of the following forms:

```text
submit REQUEST_UUID
observe ATTEMPT_UUID
cancel ATTEMPT_UUID
status
```

Selectors are canonical lower-case versioned UUIDs. Mutation refuses a
non-root caller and refuses every path, command, interpreter, environment,
provider, unit, expected digest or timeout option. Ambient environment is not
used for trust or command construction. The UUID is only a selector for a
root-published spool generation; the root creates the attempt UUID and derives
the only transient unit as
`lmdj-pr-agent-attempt-<UUID without hyphens>.service`.

The fixed paths are:

| Object | Path and contract |
| --- | --- |
| installation manifest | `/etc/lmdj/pr-agent/supervisor-installation.json`, root:root `0600` |
| durable operator state | `/var/lib/lmdj/pr-agent/operator-state/supervisor`, root:root `0700` |
| spool generations | `.../admissions/<request UUID>/`, root:root `0700` |
| durable attempt generations | `.../attempts/<attempt UUID>/`, root:root `0700` |
| metadata mutex | `.../metadata.lock`, root:root `0600` |
| protected checkpoint | `.../checkpoint.json`, root:root `0600` |
| volatile supervised root | `/run/lmdj-pr-agent/supervised`, root:runtime-group `0750` |
| execution slot | `/run/lmdj-pr-agent/slot.lock`, S2 root:root `0400`, empty regular file |

S1 refuses the current service-owned `0660` slot and old independent-flock
launcher as an installed S1 profile. S1 does not create or install these
prerequisites.

## Closed installation manifest

Schema: `lmdj.pr-agent-supervisor-installation.v1`. Top-level keys are exactly:

```text
schema, host, deployment_revision, source_identity, adapter_identity,
config_identity, bundle_identity, installation_record_identity,
runtime_identity, limits
```

`host` is exactly:

```text
release_root, engine_path, config_path, source_root, engine_cwd, ledger_path,
adapter_path, manager, slice, slot_path, old_launcher_disabled
```

All host paths are absolute protected installation paths, `manager` is
`system`, `slice` is `lmdj-pr-review.slice`, `slot_path` is the fixed slot,
and `old_launcher_disabled` is literal `true`. Each of the five member
identity objects has exactly `sha256`, `byte_length`, and `member`; the member
is a safe relative regular-file name and is read back below the protected
release root. Source, adapter, config, bundle and installation-record bytes
must independently match the manifest. The installation record is canonical
`lmdj.pr-agent-installation-record.v1` with exactly
`schema`, `deployment_revision`, `source_sha256`, `adapter_sha256`,
`config_sha256`, and `bundle_sha256`, each bound to the manifest.

`runtime_identity` is exactly `user`, `group`, `uid`, `gid`, `python` and must
be the fixed `lmdj-pr-agent` / Python 3.12 identity. `limits` is exactly
`cpu`, `memory_bytes`, `cpu_weight`, `tasks_max`,
`engine_deadline_seconds`, `launch_observation_seconds`,
`term_grace_seconds`, `kill_grace_seconds`, and `final_closure_seconds`.
The accepted fixed values are 1 CPU, 2 GiB, CPUWeight 1, TasksMax 128, launch
10 seconds, TERM 5 seconds, KILL 5 seconds, closure 10 seconds, and engine
deadline in `[1, 600]`. These are source-approved limits, not CLI knobs.

## Closed admission and attempt records

Admission schema: `lmdj.pr-agent-supervisor-admission.v1`. Its exact top-level
keys are:

```text
schema, request_id, identity, job_id, intake_evidence, complete_input,
producer_witness, installation_identity
```

`identity` is the exact existing seven-field T2 identity:
`repository`, `pr_number`, `base_sha`, `head_sha`, `control_sha`, `run_id`,
`run_attempt`. `job_id` is a positive non-boolean integer. `intake_evidence`
is exactly `kind`, `sha256`, `byte_length`, `member`; only `root-operator` is
accepted in S1. `github-actions` is explicitly refused until S4. The root
operator record authorizes the protected spool only; it is not GitHub proof.

`complete_input` is exactly `member`, `sha256`, `byte_length`,
`t2_input_sha256`; the member bytes are read from the same spool generation,
bounded by 8 MiB, and must match both digest and length. `producer_witness` is
exactly `schema`, `sha256`, `byte_length`, `member`, `status`, with literal
`successful`; it binds the separately produced complete-input collection
receipt. `installation_identity` is exactly `deployment_revision`,
`source_sha256`, `adapter_sha256`, `config_sha256`, `bundle_sha256`, and must
equal the independently authenticated manifest binding.

Attempt schema: `lmdj.pr-agent-attempt.v1`. Every immutable transition has
exactly:

```text
schema, sequence, previous_record_sha256, attempt_id, request_id, phase,
identity, installation_identity, input_identity, observation, outcome, evidence
```

The allowed phases are `admitted`, `published`, `launch_pending`, `running`,
`closing`, `terminal`, and `uncertain`. `observation` is exactly `unit`,
`invocation_id`, `main_pid`, `proc_start_ticks`, `boot_id`, `cgroup`,
`manager_job`, `unit_result`, `slot`; invocation remains literal null until
PID1 independently assigns it. Once invocation exists, PID, start, boot,
cgroup, unit result and slot device/inode are all required. `outcome` is
exactly `process`, `business`, `provider`, `exit_code`, `launcher_wait`,
`closure`; `unknown` is retained and nonterminal. `evidence` is exactly
`stdout`, `stderr`, `artifacts`, `diagnostics` and records full drained-byte
digests/counts with only a 2 MiB prefix retained.

Records use sorted UTF-8 JSON, comma/colon separators, no NaN/Infinity, one
trailing LF, duplicate/unknown-key rejection, bounded depth and finite sizes.
The protected checkpoint schema is
`lmdj.pr-agent-supervisor-checkpoint.v1`, exactly `schema` and `tips`; each
tip is independently `sequence`, `sha256`, `byte_length`. A rewritten chain
cannot supply its own expected tip. Every transition and containing directory
is fsynced before checkpoint publication/readback.

## Complete normal and recovery journey

The real source journey is intentionally not a reducer:

1. Validate root, protected manifest/release bytes, runtime identity, fixed
   ancestry and all outstanding attempt fences under the metadata mutex.
2. Authenticate the spool and exact input bytes, acquire the sole read-only
   slot descriptor nonblocking, then durably publish the `admitted` record.
3. Create one root-generated volatile generation and immutable read-only
   `input.json`; publish and fsync the `published` record.
4. Persist `launch_pending` with null invocation, then invoke one fixed
   `/usr/bin/systemd-run --pipe --wait --service-type=exec` command. FD0 is the
   original shared slot OFD; engine input is a separate read-only path.
5. Independently observe the exact transient unit, manager job, InvocationID,
   MainPID, proc start ticks, boot, cgroup and slot device/inode before
   persisting `running`.
6. Observe business completion, cancellation or the fixed engine deadline.
   Cancel revalidates the exact InvocationID/cgroup and uses only bounded TERM
   then KILL. It never targets an arbitrary unit or signal.
7. Drain stdout/stderr concurrently, wait for the actual launcher, enumerate
   the exact cgroup/process descendants, and require complete closure. MainPID
   zero, unit disappearance or a zero launcher return is not closure proof.
8. Read result/coverage through no-follow descriptors with pre/open/post
   identity, enforce exact bounded inventory and cross-bind input/T2 identity,
   copy to root-owned immutable evidence, fsync and read back.
9. Append `closing` then `terminal` only after evidence and closure; close the
   shared slot descriptor last. A terminal duplicate revalidates the complete
   journal/evidence and returns the same result without launch.

Recovery takes the metadata mutex first and observes the same authenticated
unfinished attempt. It never relaunches. A pending launch without invocation,
changed boot, mismatched PID/start/cgroup, unknown launcher wait, leaked
descendant, changed output, corrupt checkpoint or missing evidence stays
`uncertain`/fenced. Recovery never infers no-spend, refunds, retries providers,
resets failed units, reboots, cleans generations or repairs a corrupted chain.

## Test design and actual results

`tests/build/ci_pr_agent_attempt_supervisor_test.py` invokes `main` for every
public journey. The temporary child is an installed executable selected only
by the low-level test launch boundary; it reads the separately published
input path and never receives JSON or Python source via fd0. Real local effects
include Popen, pipe draining, `pass_fds`, fstat identity, flock contention,
immutable link publication, fsync/readback and symlink/no-follow rejection.
The low-level seam supplies root/PID1/host identity and exact observation only;
admission, transition, output and terminal validators run unchanged.

The verified invocation was:

```text
python3 tests/build/ci_pr_agent_attempt_supervisor_test.py -v
```

Result: 13 tests, 13 passed, 0 failed, 0 skipped, exit 0. The population
covers:

| Journey | Far-side assertion |
| --- | --- |
| normal submit | six durable transitions, one launch, shared slot busy while child inherits fd, immutable evidence bytes |
| terminal duplicate | same attempt/result, full evidence readback, no second launch |
| competing request | unfinished generation returns busy and cannot launch |
| pre-observation crash | launch_pending persists, same child is observed/recovered, launch count remains one |
| cancel | exact invocation revalidation, fixed cancel boundary, one launch and not-reviewed business result |
| closure leak | uncertain durable fence and later duplicate busy result |
| schema/type/launcher refusals | duplicate JSON, bool job ID, Actions intake, old launcher and spool mutation all fail before launch |
| publication fault | checkpoint fsync failure retains prelaunch generation and no launch |
| output/authentication fault | symlink output is not reviewed; corrupt terminal evidence is fenced after restart |

Darwin cannot prove PID1/systemd `--pipe`, Linux OFD transfer through PID1,
real cgroup closure, service-account ownership, actual protected installation,
provider credentials or paid model behavior. Those remain explicit S2/T4/T5
acceptance populations, not skipped S1 legs. The local child and OS effects
are retained as source/local evidence only.

## Version Management

Version impact: none for Product Build, Core Module, Provider, public Contract,
tag or release. S1 adds only internal operator schemas and receipt identities;
S2 must bind their source/adapter bytes into a new immutable installed
supervisor revision. No Product Build or release allocation is made.

## Documentation Impact

Documentation impact: required. Affected portal page:
`/operations/testing-and-proof/`. The operations and Portal pages now describe
the source/local supervisor contract, exact local result, and explicit
not-installed status. They do not promote source or seam evidence into Linux,
provider, runner, T5 or T6 acceptance.
