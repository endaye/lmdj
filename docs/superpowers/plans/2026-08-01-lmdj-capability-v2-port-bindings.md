# LMDJ Capability v2 Port Bindings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the active Provider path's ambiguous flat Artifact arrays with explicit, canonical port bindings across Capability Request, Artifact Sink, Candidate, Attempt evidence, Application Facade, CLI, and MCP.

**Architecture:** Keep `lmdj.capability.v1` immutable, add `lmdj.capability.v2`, and migrate the active Product Assembly to v2 without a v1 adapter. `ArtifactBinding {port, artifact}` is the only runtime carrier for Provider inputs and outputs. AttemptStore validates every named port independently before and after Provider execution, owns all minted Artifact bindings, and persists canonical binding evidence outside Project Truth.

**Tech Stack:** C++20, CMake 3.24+, CTest, nlohmann/json 3.12.0, Python 3.11+ standard library, JSON Schema Draft 2020-12, MCP `2025-11-25` over stdio.

## Global Constraints

- Work only on a short-lived `feat/capability-v2-port-bindings` branch in an isolated worktree; never edit or commit on `main`.
- Start from the latest protected `main` containing Product Build `1.0.7.0` and the approved decision in `docs/architecture/2026-08-01-provider-multi-port-contract-decision.md`.
- Do not modify `lmdj.capability.v1`; retain its Schema and its v1-specific conformance assertions unchanged.
- Do not build a v1-to-v2 request, Candidate, Provider, or terminal-Attempt adapter. Active code emits and accepts v2 only after Task 2.
- Existing `.lmdj-workspace/attempts/*.json` v1 files are not Project Truth. Preserve them on disk, reject them as an unsupported private format when inspected by v2 code, and never delete or silently rewrite them.
- Project Truth, Runtime Snapshot, Provider selection, Provider failure isolation, and Product Assembly ownership boundaries remain unchanged.
- `ArtifactBinding.port` is semantic identity. Array order, media type, Schema identity, and Descriptor order must never infer a port.
- The same Artifact Ref may appear in at most one binding in a Request, one mint set, or one Candidate. This is a global v2 uniqueness rule even when the port names differ.
- A Candidate-producing Descriptor must register at least one output port. All output ports may be optional, and a valid Candidate may then contain zero outputs.
- Every port independently enforces `required`, `max_count`, media type, and declared Schema identity. `max_count` must be at least one.
- Current `ArtifactRef` has no Schema provenance and AttemptStore has no input Artifact resolver. This plan validates the Descriptor Schema identity selected by the binding; it does not claim byte-level input Schema validation.
- Provider output bytes remain Attempt-scoped. Any unknown port, wrong media type, duplicate mint, Candidate/mint mismatch, count violation, exception, or invalid terminal result removes staged outputs and fails only that Attempt.
- Use TDD for each behavior: add the failing assertion, observe the intended failure, implement the minimum code, then observe the pass.
- Task 1 and Task 2 are separate reviewable Conventional Commits. Stage only the files declared by that Task.
- Do not push, open a Pull Request, merge, tag, release, publish, deploy, or promote a Channel unless separately authorized.

## Locked v2 Wire Shapes

The public Facade/MCP Request input is:

```json
{
  "port": "source",
  "artifact": {
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "media_type": "audio/wav",
    "byte_length": 48000
  }
}
```

The public success output uses the same binding shape:

```json
{
  "outputs": [
    {
      "port": "drums",
      "artifact": {
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "media_type": "audio/wav",
        "byte_length": 48000
      }
    }
  ]
}
```

The public C++ interfaces become:

```cpp
struct ArtifactBinding {
  std::string port;
  foundation::ArtifactRef artifact;

  auto operator<=>(const ArtifactBinding&) const = default;
};

void to_json(nlohmann::json& output, const ArtifactBinding& binding);
void from_json(const nlohmann::json& input, ArtifactBinding& binding);

struct CapabilityRequest {
  std::string capability;
  std::vector<ArtifactBinding> inputs;
  nlohmann::json parameters;
  std::string data_classification;
  std::string platform;
  std::string region;
  std::vector<std::string> required_permissions;
};

struct Candidate {
  foundation::CandidateId id;
  std::vector<ArtifactBinding> outputs;
  nlohmann::json provenance;
};

using ArtifactSink =
    std::function<foundation::Result<foundation::ArtifactRef>(
        std::string port,
        std::span<const std::byte> bytes,
        std::string media_type)>;
```

The sink returns an `ArtifactRef`, while AttemptStore records the `port` passed to the sink as the authoritative minted binding. A Provider must bind that returned Artifact to the same port in its Candidate; terminal validation compares canonical binding sets and rejects any mismatch.

Canonical binding order is `port`, then `artifact.sha256`, `artifact.media_type`, and `artifact.byte_length`. The caller's input order and the Provider's Candidate order must not affect persisted Attempt bytes or returned semantic identity.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.7.0` | `1.0.8.0` | Active Assembly, Provider behavior, and public Host request/output shape change. |
| Capability Contract | `lmdj.capability.v1` `1.0.0` | add `lmdj.capability.v2` `2.0.0`; remove v1 from active Assembly | Breaking binding and Descriptor requirements; v1 Schema remains immutable. |
| `provider-sdk` | `0.1.0`, API 1 | `1.0.0`, API 2 | Public C++ Request, Candidate, Sink, and private persisted Attempt semantics are incompatible. |
| `application-facade` | `0.1.1`, API 1 | `1.0.0`, API 2 | `provider.run` and `attempt.inspect` JSON shapes change incompatibly. |
| `core-cli` | `0.1.1`, API 1 | `1.0.0`, API 2 | Exact Facade dependency and exposed Provider JSON change. |
| `core-mcp` | `0.1.1`, API 1 | `1.0.0`, API 2 | Exact Facade dependency and MCP tool Schema change. |
| Proof Providers | `0.1.0`, API 1 | `1.0.0`, API 2 | Provider SDK interface requirement changes. |
| Proof Capability | `proof.candidate.v1` `1.0.0` | `proof.candidate.v2` `2.0.0` | Request/output binding semantics are incompatible. |
| Model identity | `null` | `null` | Both Proof Providers remain pure code Providers. |

- Task 1 adds the reviewed Contract file but does not activate it or allocate a Product Build by itself.
- Task 2 atomically moves the runnable Assembly to `1.0.8.0`; update every exact dependency and regenerate `products/lmdj/assembly.lock.json` with `scripts/version.py lock`.
- `lmdj.capability.v1` remains in `contracts/` for immutable history and conformance, but the `1.0.8.0` Assembly lists only `lmdj.capability.v2`.
- No automatic migration exists for v1 Workspace terminal Attempts or v1 Host selections. Fresh v2 selection is explicit; old files remain recoverable from an old Build.
- Only after squash merge to `main`, full CI, integrated Proof, and version conformance pass may the Integration Owner create annotated tag `lmdj-v1.0.8.0` on the full merge SHA.
- This plan does not authorize tag creation or push, GitHub Release, deployment, publication, or Channel promotion.

## Integration Boundary

Use one Pull Request containing the two Task commits below. Do not open the Pull Request after Task 1 alone: the new Schema is intentionally inactive until the runtime migration is complete. The final PR Gate is the full `scripts/core.sh proof` on the complete branch plus CI on macOS and Linux.

---

### Task 1: Define `lmdj.capability.v2` and its Contract fixtures

**Files:**

- Create: `contracts/capability/lmdj.capability.v2.schema.json`
- Create: `tests/fixtures/contracts/capability-v2-valid.json`
- Create: `tests/fixtures/contracts/capability-v2-invalid.json`
- Modify: `tests/conformance/schema_contract_test.py`

**Interfaces:**

- Retain the v1 top-level Capability Descriptor fields.
- Change `contract` to `lmdj.capability.v2` and `x-lmdj-contract-version` to `2.0.0`.
- Require `max_count` with integer minimum `1` on every `artifact_port`.
- Require at least one `output_artifacts` entry.
- Add `$defs.artifact_ref`, `$defs.artifact_binding`, `$defs.capability_request`, and `$defs.candidate` matching the locked wire shapes.
- Set `artifact_binding.required` to exactly `port` and `artifact`, reject additional properties, and apply the existing port-name pattern.
- Use `uniqueItems: true` on binding arrays as a structural first gate; runtime conformance supplies the stronger same-hash-across-ports rule that JSON Schema cannot express.

- [ ] **Step 1: Add failing conformance assertions before the Schema exists**

Add `capability_v2` to `schema_paths`, expect version `2.0.0`, and assert:

```python
capability_v2 = schemas["capability_v2"]
assert capability_v2["properties"]["contract"]["const"] == (
    "lmdj.capability.v2"
)
assert capability_v2["properties"]["output_artifacts"]["minItems"] == 1
port_v2 = capability_v2["$defs"]["artifact_port"]
assert "max_count" in port_v2["required"]
assert port_v2["properties"]["max_count"] == {
    "type": "integer",
    "minimum": 1,
}
binding = capability_v2["$defs"]["artifact_binding"]
assert set(binding["required"]) == {"port", "artifact"}
assert binding["additionalProperties"] is False
assert binding["properties"]["artifact"]["$ref"] == "#/$defs/artifact_ref"
```

Run:

```bash
python3 tests/conformance/schema_contract_test.py
```

Expected: fail because `lmdj.capability.v2.schema.json` does not exist.

- [ ] **Step 2: Add the v2 Schema and exact positive/negative fixtures**

The valid fixture contains two output ports accepting the same media type and two bindings in reversed Descriptor order. The invalid fixture contains no output ports, `max_count: 0`, and a binding without `port`; it exists as permanent negative evidence, not as accepted runtime data.

Do not copy v2 assertions over v1: keep the v1 test proving that its original shape and identity remain unchanged.

- [ ] **Step 3: Prove the Contract test passes and the fixtures encode the intended boundary**

Run:

```bash
python3 tests/conformance/schema_contract_test.py
python3 -m json.tool contracts/capability/lmdj.capability.v2.schema.json >/dev/null
python3 -m json.tool tests/fixtures/contracts/capability-v2-valid.json >/dev/null
python3 -m json.tool tests/fixtures/contracts/capability-v2-invalid.json >/dev/null
```

Expected: all commands exit `0`; the conformance script prints `schema contracts: ok`.

- [ ] **Step 4: Commit only the Contract Task**

```bash
git add contracts/capability/lmdj.capability.v2.schema.json \
  tests/fixtures/contracts/capability-v2-valid.json \
  tests/fixtures/contracts/capability-v2-invalid.json \
  tests/conformance/schema_contract_test.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(contracts): define capability v2 port bindings"
git show --stat --oneline --decorate HEAD
git status --short
```

Expected staged and committed files: exactly the four paths declared above. Expected final status: clean.

---

### Task 2: Migrate Provider runtime, Hosts, Proof, and Product Assembly to v2

**Files:**

- Modify: `packages/provider-sdk/include/lmdj/provider/capability.hpp`
- Modify: `packages/provider-sdk/include/lmdj/provider/provider.hpp`
- Modify: `packages/provider-sdk/include/lmdj/provider/attempt_store.hpp`
- Modify: `packages/provider-sdk/src/capability.cpp`
- Modify: `packages/provider-sdk/src/registry.cpp`
- Modify: `packages/provider-sdk/src/attempt_store.cpp`
- Modify: `packages/provider-sdk/module.json`
- Modify: `providers/local-proof-success/src/provider.cpp`
- Modify: `providers/local-proof-success/CMakeLists.txt`
- Modify: `providers/local-proof-success/module.json`
- Modify: `providers/local-proof-failure/src/provider.cpp`
- Modify: `providers/local-proof-failure/CMakeLists.txt`
- Modify: `providers/local-proof-failure/module.json`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/module.json`
- Modify: `apps/core-cli/module.json`
- Modify: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/server.py`
- Modify: `apps/core-mcp/pyproject.toml`
- Modify: `apps/core-mcp/module.json`
- Modify: `tests/core/provider/conformance_test.cpp`
- Modify: `tests/core/provider/spec_regression_test.cpp`
- Modify: `tests/core/provider/attempt_isolation_test.cpp`
- Modify: `tests/core/facade/application_test.cpp`
- Modify: `tests/core/facade/assembly_loader_test.cpp`
- Modify: `tests/e2e/headless_core_proof.py`
- Modify: `tests/e2e/requests/run-failing-provider.json`
- Modify: `tests/host/cli_test.py`
- Modify: `tests/host/mcp_facade_parity_test.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/version_lock_test.py`
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Modify: `products/lmdj/src/compiled_assembly.cpp`
- Modify: `products/lmdj/README.md`
- Regenerate: `products/lmdj/assembly.lock.json`

**Runtime behavior:**

- Registry rejects duplicate input names, duplicate output names, `max_count == 0`, and empty output port lists.
- Request validation resolves each binding by exact input port name, validates the Artifact Ref and that port's media types, counts each port independently, and rejects a duplicate Artifact hash before Provider invocation.
- Artifact Sink resolves the exact output port before writing, validates only that port's media types and the global output-byte limit, and records `{port, artifact}` in the mint set.
- Candidate validation resolves every output binding, applies per-port counts, accepts zero outputs only when all output ports are optional, requires exact canonical equality with the mint set, and rejects duplicate hashes across ports.
- Terminal Attempt JSON uses `"format":"terminal-attempt-v2"` and persists `request.inputs`, `minted_outputs`, and `candidate_outputs` as canonical binding arrays. The flattened `artifacts` evidence remains a de-duplicated list of input and minted Artifact Refs.
- `AttemptStore::inspect` accepts only `terminal-attempt-v2`; it returns `INVALID_ARGUMENT` for preserved v1 files and never rewrites or deletes them.
- Facade `provider.run`, Facade `attempt.inspect`, CLI JSON, and MCP tool schemas use the locked binding shape. No Host parses Workspace Attempt files directly.

- [ ] **Step 1: Add failing Provider conformance tests for all four approved decisions**

Add focused cases before changing implementation:

```text
same media type on two named ports remains distinguishable
missing second required input returns INVALID_ARGUMENT before Provider run
missing second required output becomes PROVIDER_FAILED
non-first port over max_count becomes PROVIDER_FAILED
unknown input port returns INVALID_ARGUMENT before Provider run
unknown sink port returns a failed sink Result
unknown Candidate port becomes PROVIDER_FAILED
same input Artifact hash on two ports returns INVALID_ARGUMENT
same minted Artifact hash on two ports is rejected
Candidate port differing from its sink port becomes PROVIDER_FAILED
all-optional outputs accept an empty Candidate
empty output Descriptor is rejected at Registry::add
input and Candidate reordering yield identical canonical Attempt evidence
invalid outcomes remove staged Artifact files
v1 terminal Attempt inspection fails without deleting the file
```

Use two input and two output ports that both accept `application/x-lmdj-proof`; this proves the result is not inferred from media type. Extend the existing test Provider classes instead of creating production-only test hooks.

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure -R '^provider_'
```

Expected: compilation or Provider assertions fail because `ArtifactBinding` and port-aware Sink behavior do not exist yet.

- [ ] **Step 2: Implement `ArtifactBinding` JSON and canonical ordering**

Add the locked C++ type and JSON conversion functions. `from_json` must reject extra or missing keys through the caller's exact-shape validation; it must not accept a flat Artifact as shorthand.

Use one comparison helper everywhere:

```cpp
bool binding_less(
    const ArtifactBinding& left,
    const ArtifactBinding& right) {
  return std::tie(
             left.port,
             left.artifact.sha256,
             left.artifact.media_type,
             left.artifact.byte_length) <
         std::tie(
             right.port,
             right.artifact.sha256,
             right.artifact.media_type,
             right.artifact.byte_length);
}
```

Do not canonicalize by mutating the Provider's returned order. Copy and sort only for comparison and persisted evidence.

- [ ] **Step 3: Implement registration and Request validation per port**

Build a name-to-Descriptor lookup separately for input and output ports. For each declared port, compute its binding count and enforce:

```cpp
const auto minimum = port.required ? std::size_t{1} : std::size_t{0};
if (count < minimum || count > port.max_count) {
  return invalid_argument("capability request input count is invalid");
}
```

Reject an unknown port and a duplicate Artifact hash before invoking the Provider. A zero-input Capability remains legal when no input port is required. Do not add filesystem or Project access to Provider SDK.

- [ ] **Step 4: Implement the port-aware Sink and terminal Candidate validation**

Change all Provider implementations and test Providers to call:

```cpp
const auto artifact = output(
    "candidate",
    {},
    "application/x-lmdj-proof");
```

The success Provider returns:

```cpp
provider::Candidate{
    foundation::CandidateId{attempt_id.value()},
    {{"candidate", artifact.value()}},
    nlohmann::json::object(),
}
```

For terminal validation, count Candidate bindings per output port, validate exact port/media matches, reject duplicate hashes, and compare the sorted Candidate bindings with sorted minted bindings. If a Provider minted bytes and then returns an error or invalid Candidate, clean staging before persistence and persist no successful Candidate.

- [ ] **Step 5: Persist and inspect complete v2 binding evidence**

Change typed Workspace evidence to:

```cpp
struct AttemptRequestMetadata {
  std::string capability;
  std::vector<ArtifactBinding> inputs;
  std::string parameters_sha256;
  std::string data_classification;
  std::string platform;
  std::string region;
  std::vector<std::string> required_permissions;
};

struct TerminalAttempt {
  // existing identity, timestamps, status, provider, capability, and error
  AttemptRequestMetadata request;
  std::vector<foundation::CandidateId> candidate_ids;
  std::vector<ArtifactBinding> minted_outputs;
  std::vector<ArtifactBinding> candidate_outputs;
  std::vector<foundation::ArtifactRef> artifacts;
};
```

Persist the Contract identity as `lmdj.capability.v2`. Require canonical byte equality on load as today. A successful empty Candidate has empty `minted_outputs`, empty `candidate_outputs`, one Candidate ID, and no error.

- [ ] **Step 6: Migrate Facade, CLI, MCP, and Host tests without compatibility shorthands**

Facade parsing must require each input object to have exactly `port` and `artifact`; the nested Artifact must have exactly `sha256`, `media_type`, and `byte_length`. Facade response and Attempt inspection emit the same nesting.

MCP's `lmdj.provider.run` tool Schema must define the nested binding object with both fields required and `additionalProperties: false`. Update CLI, MCP stdio, and parity fixtures to prove both Hosts return identical binding JSON.

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure \
  -R '^(provider_|facade_|host_)'
python3 tests/host/cli_test.py
python3 tests/host/mcp_stdio_test.py
python3 tests/host/mcp_facade_parity_test.py
```

Expected: all selected CTest and Host tests pass.

- [ ] **Step 7: Apply the version migration and regenerate Assembly lock**

Set the exact versions from the Version Management table, replace active `lmdj.capability.v1` with `lmdj.capability.v2`, replace `proof.candidate.v1` with `proof.candidate.v2`, and update all compiled/test expectations.

Generate rather than hand-edit the lock:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
```

Expected: all commands exit `0`; Product identity is `1.0.8.0`, active Contract is `lmdj.capability.v2` `2.0.0`, and source-package hashes match both `1.0.0` Proof Providers.

- [ ] **Step 8: Prove the complete Product and scan for accidental v1 runtime use**

Run:

```bash
scripts/core.sh proof
rg -n 'lmdj\.capability\.v1|proof\.candidate\.v1' \
  packages providers apps products tests/e2e tests/host tests/build \
  tests/core/facade
rg -n 'lmdj\.capability\.v1|proof\.candidate\.v1' \
  tests/core/provider tests/conformance/schema_contract_test.py
git diff --check
```

Expected:

- `scripts/core.sh proof` passes all selected non-stress tests, CLI/MCP parity, E2E Provider success/failure isolation, dependency verification, and version locks.
- The first `rg` command returns no active runtime, Assembly, Provider, Host, or E2E v1 reference. The second returns only immutable Schema assertions and the explicit v1-rejection regression fixture.
- `git diff --check` exits `0`.

- [ ] **Step 9: Commit the complete migration atomically**

Before staging, inspect `git status --short` and compare it to the Task 2 file list. Stage each declared path explicitly; do not use `git add .` or `git add -A`.

```bash
git diff --name-only HEAD
git diff --check
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(core): bind provider artifacts to capability ports"
git show --name-status --format=fuller HEAD
git status --short --branch
```

Expected: the commit contains only Task 2 paths, the integrated Proof evidence is from the same tree, and final worktree status is clean.

## Final Review Checklist

- [ ] Every approved decision has both a positive path and a negative regression.
- [ ] Two same-media-type ports are distinguished only by explicit name.
- [ ] Second and later ports receive the same required/count/media validation as the first.
- [ ] Candidate output sets and mint sets match by port plus Artifact identity, independent of order.
- [ ] All invalid Provider outcomes clean staged bytes and leave Project Truth unchanged.
- [ ] Empty optional-output success is represented as a real Candidate, not fake failure or omitted result.
- [ ] v1 Schema remains byte-for-byte unchanged and is absent from the active Assembly.
- [ ] Old private Attempt files are preserved and rejected, not migrated or deleted.
- [ ] No code or documentation claims byte-level input Schema validation.
- [ ] No placeholder, TODO, disabled assertion, skipped test, or fake success path was added.
- [ ] Product, Module, Provider, Capability, compiled Assembly, README, tests, and lock identities all agree.
- [ ] `scripts/core.sh proof`, version verification, staged diff check, committed file inspection, and final clean status all pass.
