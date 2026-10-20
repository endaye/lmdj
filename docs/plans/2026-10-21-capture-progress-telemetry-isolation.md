# Isolate optional capture telemetry failures

## Premises before implementation

Main/worktree base32b3ce0c3a82bd748c04819b148fbd7f60875840 is the actual
squash of feature #2440, source0a6df18e. Its complete tree is equal to the
independently reviewed source. #2135 A0 explicitly makes telemetry optional:
missing/bad metadata must make the read unavailable without refusing otherwise
valid capture. The original source, #2440 review/result, #2135/#2112 approved
scope and current seven governing files were read; the rules are unchanged.

- Outstanding: SDK start reads the optional raw receipt's generation outside
  its error boundary, after the provider actually started. A throwing accessor
  rejects public capture admission. The same isolated generation-getter capture
  case passes on before-feature9ff12bc7 and fails on exact feature/main source.
- Outstanding: the public getter looks up optional captureProgress and coerces
  identity.generation before entering its try. A throwing accessor or malformed
  primitive/object can escape instead of returning unavailable. Two actual
  current-source external probes fail the promised admission/read assertions.
- Already correct: actual provider start/stop errors and mandatory capture
  ownership retain their original failure paths. Default real Worklet counting,
  ACK/binding, final partial, loss, identity and stopped snapshot semantics passed
  all601 Node tests,170 Perform callers and the current27 packaged journeys in
  #2440; retain that evidence without pretending it covered these missing cases.
- Scope: guard optional property reads only. Never move required start/stop into
  a catch, retain a raw receipt/sink/queue for deferred reads, invent a numeric
  fallback, change packet/handle keys, add a timer/RPC/I/O or another owner.

One writer in the new isolated fix/capture-progress-telemetry-isolation worktree,
based on the actual main squash. Ten tracked links are actual symlinks. Original
published stack, root main and other WIPs remain untouched. This is a compatible
correction within approved A0, not a new product/concurrency decision.

## Declared files

- packages/web-runtime-platform/web/runtime_session.mjs
- packages/web-runtime-platform/test/runtime_session.test.mjs
- docs/plans/2026-10-21-capture-progress-telemetry-isolation.md

One atomic Conventional Commit. Default capture's required errors, old exact
capture {stop}, configuration and all current tests stay intact.

## Implementation and verification

1. Add persistent regressions before the fix: generation accessor failure must
   preserve admission/delivery/stop; progress accessor failure returns explicit
   unavailable without stopping capture; invalid Symbol/coercion-object generation
   must not escape or invoke valueOf. Assert delivered sink callbacks in the injected-provider case and the
   exact old handle, not only a diagnostic return value.
2. Observe their actual semantic RED against unmodified main, retaining existing
   positive tests. Guard optional generation lookup at start, using the existing
   unsupported sentinel only for unavailable metadata. Put progress lookup and
   strict integer validation inside the read boundary, with no coercion.
3. Run the full owning Runtime Session and complete Platform Node suites, Creator
   types and existing Perform caller cases, dependency/source boundaries and
   standalone Runtime Lab. Genuine provider start/stop failures must still reject.
4. Build the official clean-head pinned Creator package, read all assets/hashes
   and run the full original added capture journey (two captures, actual port/
   WAV identities, final partial, owner replacement, terminal cleanup and cold
   reopen). The unchanged default success path's parent27-case result stays
   labeled parent evidence; this fix must not claim it was rerun on a new head.
5. Inspect declared/staged/committed files, ownership and final scope; authenticate
   current-head review, all findings/conversations, conflicts and live protection
   before expected-head squash and authorized safe cleanup. No published rewrite.

The two pre-fix probes are product defects directly represented by regression
coverage, not a new process-ledger rule. No source Frame/Worklet/Native changes.
Full candidate/device/hearing/Host consumer acceptance remains outstanding.

## Version Management

Version impact: compatible Web Runtime Platform JS PATCH correction under #2237,
deduplicated beneath the higher API MINOR debt from #2440. No new API/key/type,
Native ABI, persisted Contract, dependencies, manifests, Product/Assembly/Build,
Channel or snapshot allocation.

## Documentation Impact

Documentation impact: none
Reason: restore the already documented optional-telemetry/noninterference and
unavailable-read contract; no new behavior or portal identity/route/diagram.

## Delivery boundary

Ordinary protected main integration, PR/review and safe postmerge cleanup are
authorized. Keep old published refs/worktrees still needed downstream. Release
workflow/tools/evidence/releases paths remain frozen; fixed candidate8c361623f
is unchanged. No auto-merge, tag, Release, Runtime deployment or Channel.
#2112/#2135/#2228 remain open until their whole consumer/candidate/device scope.

## Source results before clean checkpoint

Own fresh main baseline601/601 PASS1.886s. Before any production edit, all4 new
owning cases fail on main (416 existing tests pass,420 total): generation lookup
rejects otherwise valid capture; progress accessor and Symbol/coercion values
escape the read boundary. The isolated admission case also passes on the exact
before-feature9ff12bc7 Runtime Session. External and persistent RED records stay
retained separately; none is a fixture/setup failure.

The correction guards only optional property access and validates generation
without numeric coercion. Keep a primitive invalid marker privately, never a
provider object or raw receipt in the compact identity. Missing/throwing metadata
uses the existing unsupported read; malformed metadata is protocol-error.
Mandatory start/stop behavior and normal packets/handles remain unchanged.
Complete Platform605/605 PASS1.975s, no skips; original601 and four new cases all
remain. In the injected-provider cases actual sink callbacks continue and only
the explicit caller stop changes the stop count. These are Node fault-injection
facts, not physical audio capture. Creator types/Perform170, dependency/source
boundaries and Lab42/server/active-tree pass before this checkpoint.

Clean-head production asset verification, the unchanged complete added capture
journey, committed ownership/scope and independent current-head review remain
shipping boundaries. Parent #2440's full27-case/Portal evidence stays labeled
parent evidence; this correction does not claim a new complete candidate run.
