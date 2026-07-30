# LMDJ Headless Core Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first UI-free LMDJ proof that creates a 64-pad project, imports fixed audio, records a user-played pattern, cooks an immutable runtime snapshot, renders deterministic WAV audio, exposes identical state through CLI and MCP, switches a test Provider, and proves that a failed Attempt cannot mutate Project Truth.

**Architecture:** A single authoritative C++20 Authoring Domain is persisted by Project I/O and cooked into an immutable Runtime Snapshot consumed by a derived Audio Runtime. Every Host calls one Application Facade; the C ABI is only a narrow JSON boundary around that Facade. Provider execution is Capability-based and Attempt-scoped. Product-specific composition lives only in `products/lmdj/assembly.json`.

**Tech Stack:** C++20, CMake 3.24+, CTest, nlohmann/json 3.12.0, PicoSHA2 pinned to commit `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29`, Python 3.11+ standard library for fixtures/MCP/E2E, JSON Schema Draft 2020-12, MCP `2025-11-25` over stdio, GitHub Actions.

## Global Constraints

- Work only on a short-lived branch/worktree; never edit or commit on `main`.
- This is a clean break. New code must not import, wrap, translate, or emit `lmdj.patch.v1` or `lmdj.materials.v1`.
- Remove the stopped product implementation from the active source tree in Task 1. Git history remains the archive; `references/demos/` remains untouched.
- The first proof contains no Creator UI, Web runtime, live audio device, Stem/Slice model, Sound Set catalog, marketplace, or cloud deployment.
- The first proof uses terminal in-process Provider Attempts. Async Job lifecycle, cancellation, timeout, partial result, retry, and Event subscriptions belong to the later full Provider Conformance Lab.
- `foundation`, `authoring-domain`, `project-io`, `project-cooker`, `audio-runtime`, and `provider-sdk` are product-neutral.
- `core-cli`, `core-mcp`, tests, and future Hosts use only `application-facade`; they never parse `.lmdj` files.
- Pattern events reference `PadSlotId {bank, pad}`. They never reference an Asset directly.
- Every successful Project command carries `expected_revision`, is atomic, and increments revision exactly once.
- `RecordTake` captures `expected_revision` when recording begins. A changed revision returns `REVISION_CONFLICT`; there is no auto-rebase. The sealed Take remains recoverable and Project Truth remains unchanged.
- Provider failure mutates only an Attempt record in Workspace State; it never mutates Project Truth.
- Runtime Snapshot is immutable and derived. Runtime transport, voice, cache, buffer, and telemetry state is never persisted as Project Truth.
- Use Test-Driven Development: add a failing test, observe the expected failure, add the minimum implementation, then observe the pass.
- Each task is one reviewable commit. Stage only the paths listed for that task.
- No implementation step may add unfinished-work markers, empty handlers, fake success results, or skipped assertions.
- The separate Web realtime-audio Spike starts under its own plan; it is not part of this proof.

## Locked Proof Decisions

| Decision | Proof value |
| --- | --- |
| Project bundle form | A directory ending in `.lmdj`; ZIP packaging is deferred. |
| Project truth files | Atomic `manifest.json` head plus immutable `history/checkpoints/<revision>.json` and `history/transactions/<revision>-<command-id>.json`. |
| Recoverable recording files | `recovery/active/*.jsonl` while recording; `recovery/sealed/*.json` after interruption or conflict. |
| Workspace files | `.lmdj-workspace/attempts/*.json` and `.lmdj-workspace/host-settings.json`, outside the Project bundle. |
| Audio fixture support | Little-endian PCM WAV, mono or stereo, 16-bit, 48 kHz. |
| Runtime mix format | Stereo signed PCM16 output at 48 kHz, saturating integer mix. |
| Musical grid | 4/4, 16 steps per bar; proof BPM is an integer from 40 through 240. |
| Pattern length | 1, 2, 4, or 8 bars; the proof fixture uses 1 bar at 120 BPM. |
| Project revision | Unsigned 64-bit integer serialized as a JSON integer. |
| Command identity | UUID-shaped lowercase string supplied by the Host; duplicate command IDs are idempotent. |
| Provider selection | Workspace/Host setting, not Project Truth. |
| MCP transport | JSON-RPC 2.0 over stdio, one UTF-8 JSON message per line; stdout is protocol-only and logs go to stderr. |

## Public Error Codes

All Facade, CLI, C ABI, and MCP failures map to this stable proof set:

```text
INVALID_ARGUMENT
NOT_FOUND
REVISION_CONFLICT
DUPLICATE_ID
UNSUPPORTED_AUDIO
MISSING_ASSET
INVALID_PROJECT
COOK_FAILED
PROVIDER_NOT_FOUND
PROVIDER_FAILED
PERMISSION_DENIED
IO_ERROR
INTERNAL_ERROR
```

Every structured failure has:

```json
{
  "ok": false,
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "expected project revision 2, actual revision 3",
    "details": {
      "expected_revision": 2,
      "actual_revision": 3
    }
  }
}
```

---

### Task 1: Remove the stopped product from the active tree and establish the new build lab

**Files:**

- Delete: `apps/api/`
- Delete: `apps/web/`
- Delete: `packages/core-models/`
- Delete: `packages/patchify/`
- Delete: `workers/audio/`
- Delete: `workers/generation/`
- Delete: `workers/render/`
- Delete: `scripts/dev.sh`
- Delete: `scripts/deploy/`
- Delete: `scripts/release/`
- Delete: `scripts/tests/`
- Delete: `.dockerignore`
- Delete: `Dockerfile`
- Delete: `Caddyfile`
- Delete: `compose.yml`
- Delete: `compose.smoke.yml`
- Delete: `.env.example`
- Delete: `.github/workflows/deploy-server.yml`
- Create: `CMakeLists.txt`
- Create: `CMakePresets.json`
- Create: `cmake/LmdjDependencies.cmake`
- Create: `cmake/LmdjWarnings.cmake`
- Create: `packages/foundation/CMakeLists.txt`
- Create: `scripts/core.sh`
- Create: `tests/build/test_active_tree.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitignore`
- Rewrite: `apps/README.md`
- Rewrite: `packages/README.md`
- Rewrite: `workers/README.md`
- Rewrite: `README.md`
- Rewrite together: `AGENTS.md`, `CLAUDE.md`

**Interfaces:**

- Produces the root build/test entry point used by every later task.
- Produces one active-source rule: formal code exists only under the new module layout.
- Preserves `references/demos/` and all confirmed redesign documents.

- [ ] **Step 1: Write the active-tree guard before removing anything**

Create `tests/build/test_active_tree.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for retired_path in \
  apps/api \
  apps/web \
  packages/core-models \
  packages/patchify \
  workers/audio \
  scripts/tests \
  Dockerfile \
  compose.yml
do
  if [[ -e "$repo_root/$retired_path" ]]; then
    echo "retired active path still exists: $retired_path" >&2
    exit 1
  fi
done

rg -q 'New Headless Core' "$repo_root/README.md"
rg -q 'lmdj.patch.v1.*must not' "$repo_root/AGENTS.md"
cmp "$repo_root/AGENTS.md" "$repo_root/CLAUDE.md"
```

- [ ] **Step 2: Run the guard and Observe the expected failure**

Run:

```bash
bash tests/build/test_active_tree.sh
```

Expected: exit `1` and `retired active path still exists: apps/api`.

- [ ] **Step 3: Remove the stopped product source and deployment surface**

Use `git rm` only on the listed tracked paths. Do not remove `references/demos/`, redesign specs, PRD decision records, or Git history.

Rewrite `README.md`, `AGENTS.md`, and `CLAUDE.md` around the new Core. The two agent guides must be byte-identical and state:

```text
New Headless Core is the only active product source.
lmdj.patch.v1 and lmdj.materials.v1 must not be used by new code.
Hosts use Application Facade; they must not parse Project bundles.
Provider failure belongs to Attempt state, never Project Truth.
```

Rewrite the three directory READMEs to match §13:

- `apps/README.md`: neutral Core Hosts now; `creator-web` later.
- `packages/README.md`: product-neutral Core modules only.
- `workers/README.md`: future out-of-process `provider-host`; no active Patch/Materials worker.

- [ ] **Step 4: Add the root CMake configuration with immutable dependencies**

Create `cmake/LmdjDependencies.cmake`:

```cmake
include(FetchContent)

FetchContent_Declare(
  nlohmann_json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
)

FetchContent_Declare(
  picosha2
  GIT_REPOSITORY https://github.com/okdshin/PicoSHA2.git
  GIT_TAG 161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29
  GIT_SHALLOW FALSE
)

FetchContent_MakeAvailable(nlohmann_json picosha2)

add_library(lmdj_picosha2 ALIAS picosha2)
```

Create root `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.24)
project(lmdj_core VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

include(CTest)
include(cmake/LmdjDependencies.cmake)
include(cmake/LmdjWarnings.cmake)

add_subdirectory(packages/foundation)
```

Create `packages/foundation/CMakeLists.txt` initially as an `INTERFACE` target so configure succeeds; Task 2 replaces it with the real library.

`CMakePresets.json` must define `dev`, `release`, `test`, and `asan` presets under `build/core/<preset>`. `asan` enables AddressSanitizer and UndefinedBehaviorSanitizer on Clang/GCC.

- [ ] **Step 5: Add one stable developer entry point**

`scripts/core.sh` accepts only:

```text
configure [dev|release|asan]
build [dev|release|asan]
test [dev|release|asan]
proof
clean
```

`clean` may remove only the explicit repository path `build/core`; reject an empty or root path before removal.

- [ ] **Step 6: Replace CI with the new build guard**

`.github/workflows/ci.yml` runs on Ubuntu and macOS:

```yaml
- run: bash tests/build/test_active_tree.sh
- run: scripts/core.sh configure release
- run: scripts/core.sh build release
- run: scripts/core.sh test release
```

There is no deploy job in this proof.

- [ ] **Step 7: Verify the clean build lab**

Run:

```bash
bash tests/build/test_active_tree.sh
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev
git diff --check
```

Expected:

```text
100% tests passed, 0 tests failed
```

- [ ] **Step 8: Commit the retired boundary and build lab**

```bash
git add -A -- \
  .github .dockerignore .gitignore AGENTS.md CLAUDE.md README.md \
  CMakeLists.txt CMakePresets.json cmake scripts tests/build \
  apps packages workers Dockerfile Caddyfile compose.yml compose.smoke.yml .env.example
git commit -m "chore(core): replace retired product with headless build lab"
```

---

### Task 2: Define versioned contracts and the product-neutral Foundation

**Files:**

- Create: `contracts/project/lmdj.project.v1.schema.json`
- Create: `contracts/capability/lmdj.capability.v1.schema.json`
- Create: `contracts/assembly/lmdj.assembly.v1.schema.json`
- Create: `contracts/error/lmdj.error.v1.schema.json`
- Create: `packages/foundation/module.json`
- Replace: `packages/foundation/CMakeLists.txt`
- Create: `packages/foundation/include/lmdj/foundation/error.hpp`
- Create: `packages/foundation/include/lmdj/foundation/ids.hpp`
- Create: `packages/foundation/include/lmdj/foundation/artifact.hpp`
- Create: `packages/foundation/include/lmdj/foundation/json.hpp`
- Create: `packages/foundation/src/artifact.cpp`
- Create: `packages/foundation/src/json.cpp`
- Create: `tests/core/support/test.hpp`
- Create: `tests/core/foundation/artifact_test.cpp`
- Create: `tests/conformance/schema_contract_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- `foundation` consumes no product module.
- Produces typed IDs, `ArtifactRef`, stable errors, canonical JSON, and SHA-256 helpers.
- Schemas are the versioned cross-language contract; C++ types must serialize into them.

- [ ] **Step 1: Add failing Foundation tests**

Use this public model:

```cpp
namespace lmdj::foundation {

enum class ErrorCode {
  invalid_argument,
  not_found,
  revision_conflict,
  duplicate_id,
  unsupported_audio,
  missing_asset,
  invalid_project,
  cook_failed,
  provider_not_found,
  provider_failed,
  permission_denied,
  io_error,
  internal_error,
};

struct Error {
  ErrorCode code;
  std::string message;
  nlohmann::json details = nlohmann::json::object();
};

template <typename T>
class Result {
 public:
  static Result success(T value);
  static Result failure(Error error);
  bool has_value() const noexcept;
  const T& value() const;
  T& value();
  const Error& error() const;

 private:
  std::variant<T, Error> storage_;
};

template <>
class Result<void> {
 public:
  static Result success();
  static Result failure(Error error);
  bool has_value() const noexcept;
  const Error& error() const;

 private:
  std::variant<std::monostate, Error> storage_;
};

struct ArtifactRef {
  std::string sha256;
  std::string media_type;
  std::uint64_t byte_length;
  auto operator<=>(const ArtifactRef&) const = default;
};

Result<ArtifactRef> describe_artifact(
    const std::filesystem::path& path,
    std::string media_type);

std::string canonical_json(const nlohmann::json& value);

}  // namespace lmdj::foundation
```

`artifact_test.cpp` must assert:

- SHA-256 is lowercase 64-character hex.
- Hashing `abc` yields `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.
- `byte_length` is `3`.
- Canonical JSON recursively sorts object keys and emits no insignificant whitespace.

- [ ] **Step 2: Observe the compile failure**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
```

Expected: compilation fails because Foundation headers and functions do not exist.

- [ ] **Step 3: Implement typed IDs, canonical JSON, and streamed hashing**

Use strong wrappers for `ProjectId`, `CommandId`, `AssetId`, `PatternId`, `TakeId`, `AttemptId`, and `CandidateId`; do not pass raw strings between modules.

`describe_artifact` must:

1. reject missing/non-regular files with `NOT_FOUND`;
2. stream in 64 KiB chunks;
3. calculate byte length without reading the whole file into memory;
4. return `IO_ERROR` on read failure.

- [ ] **Step 4: Add and validate all four schemas**

The top-level portion of `lmdj.project.v1.schema.json` must contain:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lmdj.dev/contracts/project/lmdj.project.v1.schema.json",
  "type": "object",
  "required": [
    "contract",
    "project_id",
    "revision",
    "bpm",
    "banks",
    "assets",
    "takes",
    "patterns"
  ],
  "additionalProperties": false
}
```

The schema enforces exactly four Banks, exactly sixteen Pad Slots in each Bank, Bank indices `0..3`, Pad indices `0..15`, and unique IDs. Pattern events require a slot object:

```json
{"bank": 0, "pad": 0}
```

They must not accept an `asset_id` field.

`tests/conformance/schema_contract_test.py` uses Python standard library JSON to inspect all four schemas and assert the required keys, exact cardinalities, ID patterns, `additionalProperties` rules, and Pad Slot event shape. C++ serialization round-trip tests validate positive and negative Project instances against the same locked invariants. Do not add an unpinned Python package.

- [ ] **Step 5: Run Foundation and schema tests**

Run:

```bash
scripts/core.sh build dev
scripts/core.sh test dev
python3 tests/conformance/schema_contract_test.py
```

Expected:

```text
foundation.artifact Passed
schema contract checks: 4 passed
```

- [ ] **Step 6: Commit contracts and Foundation**

```bash
git add contracts packages/foundation tests/core/support tests/core/foundation tests/conformance CMakeLists.txt
git commit -m "feat(core): add versioned contracts and foundation"
```

---

### Task 3: Implement the authoritative 64-pad Authoring Domain

**Files:**

- Create: `packages/authoring-domain/module.json`
- Create: `packages/authoring-domain/CMakeLists.txt`
- Create: `packages/authoring-domain/include/lmdj/domain/project.hpp`
- Create: `packages/authoring-domain/include/lmdj/domain/commands.hpp`
- Create: `packages/authoring-domain/include/lmdj/domain/command_handler.hpp`
- Create: `packages/authoring-domain/src/project.cpp`
- Create: `packages/authoring-domain/src/command_handler.cpp`
- Create: `tests/core/domain/project_test.cpp`
- Create: `tests/core/domain/command_handler_test.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `foundation`.
- Produces: immutable-value Project state, Commands, typed command outcomes.
- Does not perform file I/O, Provider calls, rendering, or Host parsing.

- [ ] **Step 1: Add failing tests for the 64-pad and slot-reference invariants**

The public state shape is:

```cpp
namespace lmdj::domain {

struct PadSlotId {
  std::uint8_t bank;
  std::uint8_t pad;
  auto operator<=>(const PadSlotId&) const = default;
};

struct PadSlot {
  PadSlotId id;
  std::optional<foundation::AssetId> asset_id;
};

struct Asset {
  foundation::AssetId id;
  foundation::ArtifactRef artifact;
};

struct PatternEvent {
  PadSlotId slot;
  std::uint32_t step;
  std::uint8_t velocity;
};

struct Pattern {
  foundation::PatternId id;
  std::uint8_t bars;
  std::vector<PatternEvent> events;
};

struct RawTakeEvent {
  PadSlotId slot;
  std::uint32_t frame_offset;
  std::uint8_t velocity;
};

struct RawTake {
  foundation::TakeId id;
  std::uint32_t sample_rate;
  std::vector<RawTakeEvent> events;
};

struct ProjectState {
  foundation::ProjectId id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::array<std::array<PadSlot, 16>, 4> banks;
  std::map<foundation::AssetId, Asset> assets;
  std::map<foundation::TakeId, RawTake> takes;
  std::map<foundation::PatternId, Pattern> patterns;
};

}  // namespace lmdj::domain
```

Tests assert:

- a new Project has exactly 64 addressable slots;
- valid slot indices are Bank `0..3`, Pad `0..15`;
- a Pattern event survives reassignment of its Pad and resolves the new Asset;
- velocity is `1..127`;
- bars are one of `1, 2, 4, 8`;
- an event step is `< bars * 16`.

- [ ] **Step 2: Add failing command atomicity and idempotency tests**

All mutations implement:

```cpp
struct CommandMeta {
  foundation::CommandId command_id;
  std::uint64_t expected_revision;
};

using Command = std::variant<
    ImportAsset,
    AssignPad,
    RecordTake,
    CreatePattern>;

struct AppliedCommand {
  ProjectState state;
  nlohmann::json event;
  bool replayed;
};

struct CommandReceipt {
  std::uint64_t committed_revision;
  nlohmann::json event;
};

foundation::Result<AppliedCommand> apply(
    const ProjectState& state,
    const Command& command,
    const std::map<foundation::CommandId, CommandReceipt>& receipts);
```

Tests assert:

- correct revision applies and increments exactly once;
- wrong revision returns `REVISION_CONFLICT` and byte-equivalent state;
- duplicate command ID returns the original successful outcome with `replayed=true`;
- invalid command changes no state;
- `RecordTake` adds Raw Take and user Pattern atomically;
- Take events are retained unquantized while Pattern events use explicit step positions.

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
```

Expected: missing Authoring Domain headers/targets.

- [ ] **Step 4: Implement the Project factory and pure Command Handler**

The new Project factory sets revision `0`, creates all 64 slots, and accepts BPM only from `40..240`.

For `RecordTake`:

```text
validate meta.expected_revision
validate every RawTakeEvent
validate every PatternEvent
reject duplicate TakeId or PatternId
copy ProjectState
insert RawTake and Pattern into the copy
increment copy.revision once
return the copy and one canonical command event
```

No code in this module may reference a filesystem path.

- [ ] **Step 5: Run Domain tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'domain\\.' --output-on-failure
```

Expected:

```text
100% tests passed, 0 tests failed
```

- [ ] **Step 6: Commit the Authoring Domain**

```bash
git add packages/authoring-domain tests/core/domain CMakeLists.txt
git commit -m "feat(domain): add transactional 64-pad authoring model"
```

---

### Task 4: Persist Project Truth and recover interrupted or conflicted recordings

**Files:**

- Create: `packages/project-io/module.json`
- Create: `packages/project-io/CMakeLists.txt`
- Create: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Create: `packages/project-io/include/lmdj/project_io/take_journal.hpp`
- Create: `packages/project-io/src/project_store.cpp`
- Create: `packages/project-io/src/take_journal.cpp`
- Create: `tests/core/project_io/project_store_test.cpp`
- Create: `tests/core/project_io/take_journal_test.cpp`
- Create: `tests/fixtures/projects/.gitkeep`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `foundation`, `authoring-domain`.
- Produces: atomic `.lmdj` save/load, deterministic replay, active Take Journal, sealed recovery Candidate.
- No Host may call this package directly; Application Facade will own it.

- [ ] **Step 1: Add failing round-trip and replay tests**

The Project bundle must be:

```text
beat-proof.lmdj/
  manifest.json
  assets/
    <sha256>.wav
  history/
    checkpoints/
      0.json
      <revision>.json
    transactions/
      <revision>-<command-id>.json
  recovery/
    active/
    sealed/
```

Use:

```cpp
class ProjectStore {
 public:
  struct ImportArtifactRequest {
    domain::CommandMeta meta;
    foundation::AssetId asset_id;
    std::filesystem::path source;
    std::string media_type;
  };

  foundation::Result<void> create(
      const std::filesystem::path& bundle,
      const domain::ProjectState& initial);
  foundation::Result<domain::ProjectState> load(
      const std::filesystem::path& bundle) const;
  foundation::Result<domain::AppliedCommand> execute(
      const std::filesystem::path& bundle,
      const domain::Command& command);
  foundation::Result<domain::AppliedCommand> import_artifact(
      const std::filesystem::path& bundle,
      const ImportArtifactRequest& request);
};
```

Tests assert:

- canonical checkpoint state survives save/load byte-for-byte;
- replaying committed transaction files from revision `0` yields the checkpoint named by the manifest head;
- imported assets are named by SHA-256 and duplicate import does not duplicate bytes;
- write failure leaves the previous valid Project loadable;
- a duplicate command after reopen remains idempotent.

- [ ] **Step 2: Add failing recording journal tests**

Use:

```cpp
class TakeJournal {
 public:
  foundation::Result<void> begin(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      std::uint64_t expected_revision,
      std::uint32_t sample_rate);
  foundation::Result<void> append(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      const domain::RawTakeEvent& event);
  foundation::Result<domain::RawTake> read_active(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id) const;
  foundation::Result<std::filesystem::path> seal(
      const std::filesystem::path& bundle,
      foundation::TakeId take_id,
      std::string reason);
  foundation::Result<std::vector<RecoveryCandidate>> list_recoverable(
      const std::filesystem::path& bundle) const;
};
```

Tests assert:

- `append` flushes each event before returning;
- process restart can read all acknowledged events;
- successful `RecordTake` deletes the active journal only after Project commit;
- revision conflict seals a Candidate with reason `revision_conflict`;
- conflict leaves manifest head, checkpoints, and committed transactions unchanged;
- sealed recovery files are never removed by ordinary Workspace cleanup.

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
scripts/core.sh build dev
```

Expected: missing Project I/O target and headers.

- [ ] **Step 4: Implement atomic persistence**

For every Project commit:

1. hold a per-bundle process mutex;
2. load and validate current state;
3. call the pure Command Handler;
4. write and fsync immutable transaction and checkpoint temp files;
5. rename both temp files to their final revision-scoped names;
6. write and fsync `manifest.json.tmp.<command_id>` pointing to those exact files;
7. atomically rename the manifest temp file to `manifest.json`;
8. fsync the parent directory where supported;
9. return the committed revision.

The manifest rename is the only commit point. Revision-scoped files beyond the manifest head are ignored after a crash and removed during verified recovery. Never report success before the new manifest head is durable.

`import_artifact` performs the same revision transaction: it hashes and stages the blob, constructs the Domain `ImportAsset` command, and publishes the blob plus new manifest head as one logical commit. A staged or unreferenced blob from a crash is outside the manifest head and is removed during verified recovery.

- [ ] **Step 5: Implement the locked recording concurrency rule**

`begin` stores the Project revision captured when recording starts. On completion:

```text
if current revision == captured expected_revision:
    execute one atomic RecordTake command
    remove active journal after durable commit
else:
    seal active journal as recovery Candidate
    return REVISION_CONFLICT
    do not alter Project Truth
```

The recovery Candidate contains Raw Take events and metadata, not a fabricated Pattern. Adoption is a later explicit command.

- [ ] **Step 6: Run persistence and recovery tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'project_io\\.' --output-on-failure
```

Expected: all round-trip, replay, atomicity, and recovery tests pass.

- [ ] **Step 7: Commit Project I/O**

```bash
git add packages/project-io tests/core/project_io tests/fixtures/projects CMakeLists.txt
git commit -m "feat(project-io): add atomic bundle and take recovery"
```

---

### Task 5: Cook validated immutable Runtime Snapshots

**Files:**

- Create: `packages/project-cooker/module.json`
- Create: `packages/project-cooker/CMakeLists.txt`
- Create: `packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp`
- Create: `packages/project-cooker/include/lmdj/cooker/wav_reader.hpp`
- Create: `packages/project-cooker/include/lmdj/cooker/project_cooker.hpp`
- Create: `packages/project-cooker/src/wav_reader.cpp`
- Create: `packages/project-cooker/src/project_cooker.cpp`
- Create: `tests/core/cooker/project_cooker_test.cpp`
- Create: `tests/fixtures/audio/make_fixtures.py`
- Generate and add: `tests/fixtures/audio/kick.wav`
- Generate and add: `tests/fixtures/audio/snare.wav`
- Create: `tests/fixtures/audio/hashes.json`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `foundation`, `authoring-domain`.
- Reads Artifact bytes through an injected resolver; it does not know Project bundle layout.
- Produces a fully validated immutable Snapshot with decoded PCM and resolved Pattern events.

- [ ] **Step 1: Generate independent deterministic audio fixtures**

`make_fixtures.py` uses only `math`, `struct`, `wave`, `hashlib`, and `json`. Generate:

- `kick.wav`: 48 kHz mono PCM16, 4,800 frames, decaying 60 Hz sine.
- `snare.wav`: 48 kHz mono PCM16, 2,400 frames, deterministic xorshift32 noise with decay.

The script writes `hashes.json` and exits non-zero if regenerating existing fixtures changes hashes unexpectedly.

- [ ] **Step 2: Add failing WAV and Cook tests**

Use:

```cpp
struct PcmSample {
  std::uint32_t sample_rate;
  std::uint16_t channels;
  std::vector<std::int16_t> interleaved;
};

struct ResolvedEvent {
  domain::PadSlotId slot;
  std::uint32_t step;
  std::uint8_t velocity;
  std::shared_ptr<const PcmSample> sample;
};

struct RuntimeSnapshot {
  foundation::ProjectId project_id;
  std::uint64_t project_revision;
  std::uint16_t bpm;
  std::uint8_t bars;
  std::vector<ResolvedEvent> events;
};

using ArtifactResolver = std::function<
    foundation::Result<std::vector<std::byte>>(
        const foundation::ArtifactRef&)>;

foundation::Result<std::shared_ptr<const RuntimeSnapshot>> cook(
    const domain::ProjectState& project,
    foundation::PatternId pattern_id,
    ArtifactResolver resolve);
```

Tests assert:

- mono/stereo PCM16 48 kHz fixtures decode correctly;
- unsupported sample rate or bit depth returns `UNSUPPORTED_AUDIO`;
- every event resolves through its current Pad Slot;
- unassigned event slots return `MISSING_ASSET`;
- missing Pattern returns `NOT_FOUND`;
- Snapshot retains Project revision and contains no mutable Project pointer;
- cooking the same state twice produces equal Snapshot values.

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
python3 tests/fixtures/audio/make_fixtures.py
scripts/core.sh build dev
```

Expected: fixture generation succeeds; compile fails before the Cooker exists.

- [ ] **Step 4: Implement strict WAV decode and Project Cook**

The decoder accepts only RIFF/WAVE with one `fmt ` and one `data` chunk, PCM format `1`, 16-bit, 48 kHz, one or two channels. Check all chunk bounds before reading.

The Cooker:

1. validates the Pattern and Project revision;
2. resolves each event’s Pad Slot at Cook time;
3. resolves Asset metadata to bytes through `ArtifactResolver`;
4. verifies bytes match the recorded SHA-256;
5. decodes each unique Artifact once;
6. creates a new immutable Snapshot;
7. returns no partial Snapshot on failure.

- [ ] **Step 5: Run Cooker tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'cooker\\.' --output-on-failure
```

Expected: all WAV validation, slot resolution, hash, and determinism tests pass.

- [ ] **Step 6: Commit Cooker and fixed fixtures**

```bash
git add packages/project-cooker tests/core/cooker tests/fixtures/audio CMakeLists.txt
git commit -m "feat(cooker): add immutable runtime snapshot cooking"
```

---

### Task 6: Render deterministic offline WAV through the Audio Runtime

**Files:**

- Create: `packages/audio-runtime/module.json`
- Create: `packages/audio-runtime/CMakeLists.txt`
- Create: `packages/audio-runtime/include/lmdj/audio/offline_renderer.hpp`
- Create: `packages/audio-runtime/include/lmdj/audio/wav_writer.hpp`
- Create: `packages/audio-runtime/src/offline_renderer.cpp`
- Create: `packages/audio-runtime/src/wav_writer.cpp`
- Create: `tests/core/audio/offline_renderer_test.cpp`
- Create: `tests/fixtures/golden/reference_render.py`
- Generate and add: `tests/fixtures/golden/one_bar_120bpm.wav`
- Create: `tests/fixtures/golden/one_bar_120bpm.sha256`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes only `foundation` and immutable `RuntimeSnapshot`.
- Produces deterministic stereo PCM16 WAV.
- Does not read Project files and does not mutate Authoring state.

- [ ] **Step 1: Add an independent Golden Audio reference renderer**

The Python renderer uses the same documented integer rules, but no production C++ code:

```python
step_frame = (step * sample_rate * 60) // (bpm * 4)
scaled = (sample_value * velocity + 63) // 127
mixed = max(-32768, min(32767, current + scaled))
```

For stereo output, duplicate mono input; preserve left/right for stereo input. Render exactly:

```python
bar_frames = (4 * 60 * sample_rate) // bpm
```

The fixture Pattern triggers `kick.wav` on steps `0, 8` and `snare.wav` on steps `4, 12` at velocity `127`.

- [ ] **Step 2: Add failing C++ rendering tests**

Use:

```cpp
struct OfflineRenderRequest {
  std::shared_ptr<const cooker::RuntimeSnapshot> snapshot;
  std::filesystem::path output_path;
};

struct OfflineRenderResult {
  foundation::ArtifactRef artifact;
  std::uint64_t frame_count;
  std::uint32_t sample_rate;
  std::uint16_t channels;
};

foundation::Result<OfflineRenderResult> render_offline(
    const OfflineRenderRequest& request);
```

Tests assert:

- exact frame count for 1 bar at 120 BPM is `96,000`;
- step positions are `0`, `24,000`, `48,000`, `72,000`;
- output is 48 kHz stereo PCM16;
- velocities scale deterministically;
- saturating mix never wraps;
- input Snapshot is unchanged;
- output SHA-256 equals `one_bar_120bpm.sha256`.

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
python3 tests/fixtures/golden/reference_render.py
scripts/core.sh build dev
```

Expected: Golden fixture is generated; compile fails before Audio Runtime exists.

- [ ] **Step 4: Implement the deterministic renderer**

Use integer scheduling and mixing only. Do not use platform floating-point DSP, threads, devices, locks, network, logging, or allocation in the inner per-frame mix loop. Allocate the destination buffer before mixing.

Write the WAV header explicitly in little-endian order. Hash the final file through Foundation and return its `ArtifactRef`.

- [ ] **Step 5: Run the renderer and Golden Audio gate twice**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'audio\\.' --output-on-failure
ctest --test-dir build/core/dev -R 'audio\\.' --output-on-failure
```

Expected: both runs pass and produce the same SHA-256.

- [ ] **Step 6: Commit Audio Runtime and Golden Audio**

```bash
git add packages/audio-runtime tests/core/audio tests/fixtures/golden CMakeLists.txt
git commit -m "feat(audio): add deterministic offline wav renderer"
```

---

### Task 7: Add the Capability-based Provider SDK and isolated Attempt Store

**Files:**

- Create: `packages/provider-sdk/module.json`
- Create: `packages/provider-sdk/CMakeLists.txt`
- Create: `packages/provider-sdk/include/lmdj/provider/capability.hpp`
- Create: `packages/provider-sdk/include/lmdj/provider/provider.hpp`
- Create: `packages/provider-sdk/include/lmdj/provider/registry.hpp`
- Create: `packages/provider-sdk/include/lmdj/provider/attempt_store.hpp`
- Create: `packages/provider-sdk/src/registry.cpp`
- Create: `packages/provider-sdk/src/attempt_store.cpp`
- Create: `providers/local-proof-success/module.json`
- Create: `providers/local-proof-success/CMakeLists.txt`
- Create: `providers/local-proof-success/src/provider.cpp`
- Create: `providers/local-proof-failure/module.json`
- Create: `providers/local-proof-failure/CMakeLists.txt`
- Create: `providers/local-proof-failure/src/provider.cpp`
- Create: `tests/core/provider/conformance_test.cpp`
- Create: `tests/core/provider/attempt_isolation_test.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- `provider-sdk` consumes `foundation`, not LMDJ Product code or Project I/O.
- Provider implementations consume only `provider-sdk`.
- Produces Capability discovery, Provider selection, typed Attempt outcome, and Candidate metadata.

- [ ] **Step 1: Add failing Provider conformance tests**

Use:

```cpp
struct CapabilityRequest {
  std::string capability;
  std::vector<foundation::ArtifactRef> inputs;
  nlohmann::json parameters;
  std::string data_classification;
  std::string platform;
  std::string region;
  std::vector<std::string> required_permissions;
};

struct Candidate {
  foundation::CandidateId id;
  std::vector<foundation::ArtifactRef> outputs;
  nlohmann::json provenance;
};

struct AttemptResult {
  foundation::AttemptId attempt_id;
  std::optional<Candidate> candidate;
  std::optional<foundation::Error> error;
};

using ArtifactSink = std::function<foundation::Result<foundation::ArtifactRef>(
    std::span<const std::byte> bytes,
    std::string media_type)>;

class Provider {
 public:
  virtual ~Provider() = default;
  virtual std::string id() const = 0;
  virtual std::vector<std::string> capabilities() const = 0;
  virtual AttemptResult run(
      foundation::AttemptId attempt_id,
      const CapabilityRequest& request,
      ArtifactSink output) = 0;
};
```

Both proof Providers declare `proof.candidate.v1`.

Tests assert:

- registry lists both Providers and their Capability;
- selection rejects an unknown Provider with `PROVIDER_NOT_FOUND`;
- success returns one Candidate with Provider/version provenance;
- failure returns `PROVIDER_FAILED` and no Candidate;
- every terminal Attempt is persisted as a separate canonical JSON file;
- Project bundle path is not accepted by the Provider interface;
- invalid region/data classification fails closed before Provider execution.

- [ ] **Step 2: Add the mutation isolation test before implementation**

The test hashes every file under a prepared `.lmdj` bundle, runs the failing Provider, then asserts:

```text
same Project file set
same Project bytes
same Project revision
one new Workspace Attempt file
```

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
scripts/core.sh build dev
```

Expected: missing Provider SDK and proof Provider targets.

- [ ] **Step 4: Implement Registry, policy gate, and Attempt persistence**

`AttemptStore` writes only under the injected Workspace root:

```text
.lmdj-workspace/
  attempts/
    <attempt-id>.json
  host-settings.json
```

Provider selection writes `host-settings.json`, not `.lmdj`. An Attempt records request metadata, Provider ID/version, start/end timestamps, terminal status, typed error, Candidate IDs, and Artifact hashes. It does not store secrets or reasoning.

- [ ] **Step 5: Implement two deterministic proof Providers**

- `local.proof.success.v1` writes zero bytes through the injected `ArtifactSink` and returns the resulting `application/x-lmdj-proof` Candidate Artifact with SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and deterministic provenance.
- `local.proof.failure.v1` returns `PROVIDER_FAILED` with message `intentional proof failure`.

The sink writes only inside the current Attempt workspace. Neither Provider receives a Project Store, Project bundle path, or mutable Project object.

- [ ] **Step 6: Run all Provider conformance and isolation tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'provider\\.' --output-on-failure
```

Expected: both Providers pass the shared conformance suite; isolation test passes.

- [ ] **Step 7: Commit Provider SDK**

```bash
git add packages/provider-sdk providers tests/core/provider CMakeLists.txt
git commit -m "feat(provider): add capability registry and isolated attempts"
```

---

### Task 8: Compose all mutations and queries behind one Application Facade and C ABI

**Files:**

- Create: `packages/application-facade/module.json`
- Create: `packages/application-facade/CMakeLists.txt`
- Create: `packages/application-facade/include/lmdj/facade/application.hpp`
- Create: `packages/application-facade/include/lmdj/facade/c_api.h`
- Create: `packages/application-facade/src/application.cpp`
- Create: `packages/application-facade/src/c_api.cpp`
- Create: `tests/core/facade/application_test.cpp`
- Create: `tests/core/facade/c_api_test.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: Domain, Project I/O, Cooker, Audio Runtime, Provider SDK.
- Produces the only supported Host API.
- C ABI owns opaque engine handles and caller-freed UTF-8 JSON responses.

- [ ] **Step 1: Add failing Facade behavior tests**

Use:

```cpp
struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
};

class Application {
 public:
  explicit Application(ApplicationConfig config);
  nlohmann::json command(const nlohmann::json& request);
  nlohmann::json query(const nlohmann::json& request) const;
};
```

Supported proof commands:

```text
project.create
asset.import
pad.assign
take.begin
take.append
take.commit
snapshot.cook
render.offline
provider.select
provider.run
```

Supported proof queries:

```text
project.inspect
take.recoverable.list
provider.list
provider.selected
attempt.inspect
```

Tests call only these methods and assert stable success/error envelopes, revision propagation, and no exception crossing the public boundary.

- [ ] **Step 2: Add failing C ABI tests**

The entire ABI is:

```c
#ifdef __cplusplus
extern "C" {
#endif

typedef struct lmdj_engine lmdj_engine;

int lmdj_engine_create(
    const char* config_json,
    lmdj_engine** out_engine,
    char** out_error_json);

int lmdj_engine_command(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json);

int lmdj_engine_query(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json);

void lmdj_string_free(char* value);
void lmdj_engine_free(lmdj_engine* engine);

#ifdef __cplusplus
}
#endif
```

Return `0` when the ABI call itself completed and placed a JSON envelope in `out_response_json`; return non-zero only for null pointers, malformed UTF-8/JSON, allocation failure, or invalid engine handle.

`packages/application-facade/CMakeLists.txt` builds product-neutral static target `lmdj_application` and shared C ABI target `lmdj_core_c`. The latter is emitted under `build/core/<preset>/lib/` with the platform extension supplied by CMake.

- [ ] **Step 3: Observe the expected failures**

Run:

```bash
scripts/core.sh build dev
```

Expected: missing Facade and C ABI targets.

- [ ] **Step 4: Implement one routing table, not separate Host logic**

Each command handler validates its request contract, invokes one module operation, and returns:

```json
{
  "ok": true,
  "result": {},
  "project_revision": 4
}
```

Queries never increment revision. `snapshot.cook` holds the Snapshot in an in-process handle registry keyed by opaque `snapshot_id`; the ID is Runtime state, not Project Truth. `render.offline` consumes that handle.

- [ ] **Step 5: Implement exception-safe C ABI ownership**

Catch all exceptions inside `c_api.cpp` and translate to `INTERNAL_ERROR`. Allocate returned strings with one allocator and free only through `lmdj_string_free`. Add tests for malformed JSON, repeated create/free, null pointers, and 1,000 command/query calls under ASan.

- [ ] **Step 6: Run Facade and sanitizer tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'facade\\.' --output-on-failure
scripts/core.sh configure asan
scripts/core.sh build asan
ctest --test-dir build/core/asan -R 'facade\\.c_api' --output-on-failure
```

Expected: tests pass with no sanitizer report.

- [ ] **Step 7: Commit Facade and C ABI**

```bash
git add packages/application-facade tests/core/facade CMakeLists.txt
git commit -m "feat(facade): expose unified application and c abi"
```

---

### Task 9: Add a JSON-first Headless CLI Host

**Files:**

- Create: `apps/core-cli/module.json`
- Create: `apps/core-cli/CMakeLists.txt`
- Create: `apps/core-cli/src/main.cpp`
- Create: `tests/host/cli_test.py`
- Modify: `CMakeLists.txt`
- Modify: `scripts/core.sh`

**Interfaces:**

- Consumes only `application-facade`.
- Outputs exactly one canonical JSON response to stdout.
- Human diagnostics go to stderr; no color when stdout is not a terminal.

- [ ] **Step 1: Add failing black-box CLI tests**

The CLI shape is:

```text
lmdj-core --workspace <dir> command --request '<json>'
lmdj-core --workspace <dir> query --request '<json>'
lmdj-core --workspace <dir> command --request-file <path>
lmdj-core --workspace <dir> query --request-file <path>
```

`cli_test.py` must run real subprocesses and assert:

- create → import → assign → begin/append/commit → inspect works across separate processes;
- stdout parses as exactly one JSON value;
- errors use the public error envelope and exit `2`;
- successful operations exit `0`;
- malformed CLI usage exits `64`;
- CLI has no import of Project I/O and contains no bundle parsing code.

- [ ] **Step 2: Observe the missing executable failure**

Run:

```bash
python3 tests/host/cli_test.py build/core/dev/bin/lmdj-core
```

Expected: `FileNotFoundError` for `lmdj-core`.

- [ ] **Step 3: Implement the thin Host**

`main.cpp`:

1. parses only Host flags;
2. constructs `Application` from workspace root and an injected Provider Registry;
3. parses request JSON;
4. calls `command` or `query`;
5. writes canonical JSON plus one newline;
6. maps envelope success/failure to the defined exit codes.

Task 9 tests core Project behavior with an empty Registry; Task 11 supplies the Product Assembly and proof Providers. The CLI does not inspect command names beyond selecting command versus query.

- [ ] **Step 4: Run CLI black-box tests**

Run:

```bash
scripts/core.sh build dev
python3 tests/host/cli_test.py build/core/dev/bin/lmdj-core
```

Expected:

```text
cli behavior fixtures: 8 passed
```

- [ ] **Step 5: Commit the CLI Host**

```bash
git add apps/core-cli tests/host/cli_test.py CMakeLists.txt scripts/core.sh
git commit -m "feat(cli): add headless json host"
```

---

### Task 10: Add the MCP stdio Host over the same C ABI

**Files:**

- Create: `apps/core-mcp/module.json`
- Create: `apps/core-mcp/lmdj_core_mcp/__init__.py`
- Create: `apps/core-mcp/lmdj_core_mcp/__main__.py`
- Create: `apps/core-mcp/lmdj_core_mcp/c_api.py`
- Create: `apps/core-mcp/lmdj_core_mcp/server.py`
- Create: `apps/core-mcp/pyproject.toml`
- Create: `tests/host/mcp_stdio_test.py`
- Create: `tests/host/mcp_facade_parity_test.py`
- Modify: `scripts/core.sh`

**Interfaces:**

- Consumes the C ABI shared library through `ctypes`.
- Implements MCP `2025-11-25` lifecycle and Tools over stdio.
- Emits no non-protocol bytes on stdout.

- [ ] **Step 1: Add failing MCP lifecycle tests**

The test spawns:

```bash
python3 -m lmdj_core_mcp --library <shared-library> --workspace <dir>
```

It sends newline-delimited JSON-RPC and asserts:

1. `initialize` returns protocol version `2025-11-25`, server info, and `tools` capability;
2. `notifications/initialized` receives no response;
3. `tools/list` returns all proof tools with `inputSchema` and the shared success/error `outputSchema`;
4. unknown method returns JSON-RPC `-32601`;
5. malformed JSON returns `-32700`;
6. stderr logging never appears on stdout.

- [ ] **Step 2: Add failing tool parity tests**

Expose:

```text
lmdj.project.create
lmdj.project.inspect
lmdj.asset.import
lmdj.pad.assign
lmdj.take.begin
lmdj.take.append
lmdj.take.commit
lmdj.snapshot.cook
lmdj.render.offline
lmdj.provider.list
lmdj.provider.select
lmdj.provider.run
lmdj.attempt.inspect
```

Each tool forwards one Facade request. A success returns both:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"ok\":true,\"result\":{\"revision\":4},\"project_revision\":4}"
    }
  ],
  "structuredContent": {
    "ok": true,
    "result": {"revision": 4},
    "project_revision": 4
  },
  "isError": false
}
```

A Facade error remains a successful JSON-RPC response but sets `isError: true` in the MCP tool result.

The parity test creates one Project via CLI, queries it via MCP, and compares canonical `result` and `project_revision`.

- [ ] **Step 3: Observe the expected module failure**

Run:

```bash
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_stdio_test.py
```

Expected: import or startup failure because the MCP Host does not exist.

- [ ] **Step 4: Implement a strict stdio server**

`server.py` must:

- read one UTF-8 JSON object per stdin line;
- reject batches for this proof;
- require `initialize` before Tools;
- negotiate only `2025-11-25`;
- send every response as one compact JSON line;
- flush stdout after each response;
- route logs to stderr;
- terminate cleanly on EOF;
- call the C ABI wrapper for every tool.

Do not add a third-party MCP framework in this proof.

- [ ] **Step 5: Run lifecycle, error, and parity tests**

Run:

```bash
scripts/core.sh build dev
core_library="$(find build/core/dev/lib -maxdepth 1 -type f \
  \( -name 'liblmdj_core_c.so' -o -name 'liblmdj_core_c.dylib' -o -name 'lmdj_core_c.dll' \) \
  -print -quit)"
test -n "$core_library"
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_stdio_test.py
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_facade_parity_test.py \
  build/core/dev/bin/lmdj-core \
  "$core_library"
```

Expected:

```text
mcp stdio fixtures: 10 passed
cli/mcp facade parity: passed
```

- [ ] **Step 6: Commit the MCP Host**

```bash
git add apps/core-mcp tests/host/mcp_stdio_test.py tests/host/mcp_facade_parity_test.py scripts/core.sh
git commit -m "feat(mcp): expose core tools over stdio"
```

---

### Task 11: Assemble the LMDJ product and prove the complete vertical slice

**Files:**

- Create: `products/lmdj/assembly.json`
- Create: `products/lmdj/README.md`
- Create: `packages/application-facade/include/lmdj/facade/assembly_loader.hpp`
- Create: `packages/application-facade/src/assembly_loader.cpp`
- Create: `tests/core/facade/assembly_loader_test.cpp`
- Create: `tests/conformance/module_graph_test.py`
- Create: `tests/e2e/headless_core_proof.py`
- Create: `tests/e2e/requests/create-project.json`
- Create: `tests/e2e/requests/import-kick.json`
- Create: `tests/e2e/requests/import-snare.json`
- Create: `tests/e2e/requests/assign-kick.json`
- Create: `tests/e2e/requests/assign-snare.json`
- Create: `tests/e2e/requests/record-pattern.json`
- Create: `tests/e2e/requests/run-failing-provider.json`
- Modify: `scripts/core.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/core-mcp/lmdj_core_mcp/__main__.py`
- Modify: `README.md`
- Modify: `docs/prd/decision-log.md`
- Modify: `docs/prd/open-questions.md`

**Interfaces:**

- Product Assembly names exact modules, contracts, and Provider implementations.
- E2E uses public CLI and MCP surfaces only.
- CI proves the same Assembly on macOS and Ubuntu.

- [ ] **Step 1: Add the Assembly manifest and failing graph test**

`products/lmdj/assembly.json`:

```json
{
  "contract": "lmdj.assembly.v1",
  "product": {
    "id": "lmdj",
    "version": "0.1.0-proof"
  },
  "modules": [
    "foundation",
    "authoring-domain",
    "project-io",
    "project-cooker",
    "audio-runtime",
    "provider-sdk",
    "application-facade"
  ],
  "hosts": [
    "core-cli",
    "core-mcp"
  ],
  "providers": [
    {
      "id": "local.proof.success.v1",
      "capabilities": ["proof.candidate.v1"]
    },
    {
      "id": "local.proof.failure.v1",
      "capabilities": ["proof.candidate.v1"]
    }
  ],
  "contracts": [
    "lmdj.project.v1",
    "lmdj.capability.v1",
    "lmdj.error.v1"
  ]
}
```

`module_graph_test.py` validates all module manifests and rejects:

- unknown modules;
- dependency cycles;
- Host dependencies on Project I/O;
- Provider dependencies on Authoring Domain or Product Assembly;
- product-specific strings in neutral package manifests.

- [ ] **Step 2: Add the complete failing E2E proof**

`headless_core_proof.py` performs:

1. create temporary Workspace and `proof-beat.lmdj`;
2. create Project at 120 BPM;
3. import fixed kick and snare fixtures;
4. assign Bank A Pad 1 and Pad 2;
5. begin Take at current revision;
6. append user event timing plus velocities;
7. atomically commit Raw Take and one-bar Pattern;
8. inspect Project and assert 64 Pads;
9. cook Snapshot;
10. render WAV;
11. compare output hash with Golden Audio;
12. query the same Project through CLI and MCP and compare canonical state;
13. list Providers, select success Provider, and run one successful Attempt;
14. select failure Provider;
15. hash the complete Project bundle and record its revision;
16. run the intentional failed Attempt;
17. assert `PROVIDER_FAILED`;
18. assert Project revision, file set, and file bytes are unchanged;
19. assert one terminal failed Attempt exists outside `.lmdj`;
20. start a Take, mutate the Project with another valid Command, attempt Take commit, assert `REVISION_CONFLICT`, and assert a recoverable sealed Take exists.

- [ ] **Step 3: Observe the proof failure**

Run:

```bash
scripts/core.sh proof
```

Expected: failure because Assembly validation and proof wiring are not complete.

- [ ] **Step 4: Wire Assembly loading without introducing a second implementation path**

The product-neutral Assembly loader validates a manifest and filters the compiled module/Provider registry by declared IDs. CLI and MCP accept `--assembly <path>` and use that loader; neither contains an `lmdj` product branch. Both still construct and call the same `Application` implementation.

Validate the Assembly against `lmdj.assembly.v1.schema.json` before starting a Host. Fail closed on missing/unknown Provider or contract.

- [ ] **Step 5: Close the recording concurrency decision**

Add a dated entry to `docs/prd/decision-log.md`:

```text
RecordTake captures expected_revision at recording start. If Project revision
changes before commit, the command returns REVISION_CONFLICT without rebase or
Project mutation, and the Take is sealed as a recoverable Candidate.
```

Remove the corresponding row from `docs/prd/open-questions.md`. Leave the Web latency and Take audio-Bounce questions open.

- [ ] **Step 6: Make `scripts/core.sh proof` the single acceptance command**

It runs, in order:

```text
active tree guard
configure release
build release
CTest unit/integration suite
schema conformance
module graph conformance
CLI behavior fixtures
MCP lifecycle fixtures
CLI/MCP parity
Headless Core E2E
git diff --check
```

It preserves failed proof artifacts under `build/core/proof-failures/<run-id>` and removes successful temporary projects.

- [ ] **Step 7: Run the proof twice from a clean build**

Run:

```bash
scripts/core.sh clean
scripts/core.sh proof
first_hash="$(shasum -a 256 build/core/release/proof-output/beat.wav | awk '{print $1}')"
scripts/core.sh clean
scripts/core.sh proof
second_hash="$(shasum -a 256 build/core/release/proof-output/beat.wav | awk '{print $1}')"
test "$first_hash" = "$second_hash"
git diff --check
```

Expected:

```text
Headless Core Proof: PASS
Project pads: 64
Golden audio: MATCH
CLI/MCP state parity: MATCH
Failed attempt project mutation: NONE
Conflicted take recovery: SEALED
```

- [ ] **Step 8: Confirm the proof on both supported CI build hosts**

Update CI to run `scripts/core.sh proof` on:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest]
```

Golden WAV must match exactly because the renderer uses documented integer rules. A platform mismatch is a failing gate, not an allowed rebaseline.

- [ ] **Step 9: Update proof status documentation**

`README.md` and `products/lmdj/README.md` must distinguish:

```text
Designed: full new product/core architecture.
Implemented by this plan: Headless Core Proof only.
Not implemented: realtime audio, Web/PWA, Creator UI, Sample intelligence,
Sequence editing, Perform, Sound Sets, production Providers, cloud deployment.
```

- [ ] **Step 10: Commit the assembled proof**

```bash
git add \
  products/lmdj \
  packages/application-facade/include/lmdj/facade/assembly_loader.hpp \
  packages/application-facade/src/assembly_loader.cpp \
  packages/application-facade/CMakeLists.txt \
  apps/core-cli/src/main.cpp \
  apps/core-mcp/lmdj_core_mcp/__main__.py \
  tests/core/facade/assembly_loader_test.cpp \
  tests/conformance/module_graph_test.py \
  tests/e2e \
  scripts/core.sh \
  .github/workflows/ci.yml \
  README.md \
  docs/prd/decision-log.md \
  docs/prd/open-questions.md
git commit -m "feat(core): prove headless beat project end to end"
```

---

## Final Acceptance Checklist

- [ ] Active source tree contains no stopped `patch.v1`/`materials.v1` product implementation.
- [ ] All neutral packages have `module.json`, independent CMake targets, and direct tests.
- [ ] Four Banks × sixteen Pads are enforced.
- [ ] Pattern events contain Pad Slot references and no Asset references.
- [ ] Raw Take and user Pattern commit atomically.
- [ ] Recording revision conflict seals a recoverable Take and changes no Project Truth.
- [ ] Project save/load and command replay are deterministic.
- [ ] Runtime Snapshot is immutable, complete, and derived from one Project revision.
- [ ] Offline WAV matches independent Golden Audio on macOS and Ubuntu.
- [ ] CLI and MCP query the same Facade state.
- [ ] MCP conforms to the locked `2025-11-25` stdio lifecycle and Tools behavior.
- [ ] Provider selection stays outside the Project bundle.
- [ ] Failed Attempt changes no Project file or Project revision.
- [ ] Full proof passes twice from clean builds.
- [ ] `git diff --check` passes.
- [ ] Each task commit contains only its declared paths.
- [ ] Web realtime-audio latency remains explicitly outside this proof.

## Spec Traceability

| Redesign spec requirement | Plan coverage |
| --- | --- |
| §6.1 User performance is truth | Tasks 3, 4, 11 |
| §6.5 Raw Take persistence and recovery | Tasks 3, 4, 11 |
| §6.6 Pattern references Pad Slot | Tasks 2, 3, 5 |
| §9 Storage boundary | Tasks 4, 7, 8 |
| §10 Headless Engine / Host separation | Tasks 8, 9, 10 |
| §11 Authoring → Cook → Runtime | Tasks 3, 5, 6 |
| §12 proof subset: Command / Query / terminal Attempt | Tasks 3, 7, 8; async Job/Event lifecycle is deferred |
| §13 product-neutral modules and dependency direction | Tasks 1, 2, 7, 11 |
| §14 permanent Monorepo and Contract First | All tasks |
| §15 Capability / Provider / Attempt / Candidate | Task 7 |
| §18 transactional failure and recovery | Tasks 4, 7, 11 |
| §19 data/secret boundary | Tasks 4, 7 |
| §20 C++20 runtime and narrow C ABI | Tasks 1, 6, 8 |
| §21 proof-relevant deterministic, revision, round-trip, Golden, Host, and Assembly gates | Tasks 2 through 11; realtime and full Provider conformance remain deferred |
| §22 first Headless Core Proof | Task 11 |
| §23 Step 0 repository guide rewrite | Task 1 |
| §23 Web realtime-audio Spike | Deliberately separate implementation plan |

## Reference Baselines

- Redesign source of truth: `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
- MCP stdio transport: `https://modelcontextprotocol.io/specification/2025-11-25/basic/transports`
- MCP lifecycle: `https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle`
- MCP Tools: `https://modelcontextprotocol.io/specification/2025-11-25/server/tools`
- nlohmann/json 3.12.0 release: `https://github.com/nlohmann/json/releases/tag/v3.12.0`
- PicoSHA2 pinned source commit: `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29`
