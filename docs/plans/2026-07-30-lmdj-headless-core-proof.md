# LMDJ Headless Core Proof Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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
- For this Proof only, `RecordTake` captures `expected_revision` when recording begins. Any changed revision returns `REVISION_CONFLICT`; there is no auto-rebase. The sealed Take remains recoverable and Project Truth remains unchanged. Product-level selective conflict/rebase semantics remain a design-review question.
- Provider failure mutates only an Attempt record in Workspace State; it never mutates Project Truth.
- Runtime Snapshot is immutable and derived. Runtime transport, voice, cache, buffer, and telemetry state is never persisted as Project Truth.
- This Proof does not implement Quantize. A Host supplies explicit Pattern steps alongside unquantized Raw Take frame offsets; Domain validates both and never derives one from the other.
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
| Recording concurrency | Proof-scoped strict revision match with sealed recovery on conflict; it does not settle product-level irrelevant-Command or selective-rebase semantics. |
| Provider selection | Workspace/Host setting, not Project Truth. |
| MCP transport | JSON-RPC 2.0 over stdio, one UTF-8 JSON message per line; stdout is protocol-only and logs go to stderr. |

## Integration PR Boundaries

Do not accumulate all eleven Task commits into one final Pull Request. Use these six protected-main integration gates:

| PR | Included Tasks | Squash result | Product Build / Channel |
| --- | --- | --- | --- |
| PR 1 — Build and Contracts | Tasks 1–2 | Active-tree reset, reproducible build, Foundation, schemas | `1.0.1.0` / `dev` |
| PR 2 — Project Truth | Tasks 3–4 | Authoring Domain, atomic Project I/O, Take recovery | `1.0.2.0` / `dev` |
| PR 3 — Derived Runtime | Tasks 5–6 | Cooker, PCM fixtures, deterministic offline render | `1.0.3.0` / `dev` |
| PR 4 — Extensibility Boundary | Tasks 7–8 | Provider SDK, Attempt isolation, Facade, C ABI | `1.0.4.0` / `dev` |
| PR 5 — Headless Hosts | Tasks 9–10 | CLI and MCP over the same Facade | `1.0.5.0` / `dev` |
| PR 6 — Product Proof | Task 11 | Assembly, cross-Host E2E, CI acceptance | `1.0.6.0` / `dev` |

Within a PR, preserve one local commit per Task for review. After that PR passes CI and review, squash-merge it, delete its short-lived branch, synchronize `main`, and branch the next PR from the merged head. An implementation worker stops at its PR boundary and returns evidence to the Integration Owner; it does not open one eleven-Task mega-PR.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

### Version domains affected

| Domain | Start | M1 Proof target |
| --- | --- | --- |
| Plan stage | `lmdj-m1-plan.1` at `34236c062d5982d22701ad0482518a29bfaefa60` | immutable; later plan review uses `lmdj-m1-plan.2` |
| Product Build | no runnable M1 Build | `1.0.6.0` / `dev` |
| Core Modules | not created | each starts at `0.1.0` |
| Contracts | not created | six retained Contract IDs at `v1` / `1.0.0`; completed Assembly target is `lmdj.assembly.v2` / `2.0.0` |
| Proof Providers | not created | each starts at `0.1.0` |
| Proof model/rule identity | not created | immutable Artifact hash recorded by every Attempt |

`M1` means only the Headless Core Proof defined in redesign spec §22. It is not
SemVer Major 1 and does not imply a Stable user product.

### Product Build rules

- Product Builds use `MILESTONE.MINOR.BUILD.PATCH`.
- This plan owns Build numbers `1` through `6`; abandoned numbers are not reused.
- Branch candidates display the target Build plus `canary` and Git revision.
- After a PR Gate is squash-merged to `main`, full CI and version conformance
  pass, the Integration Owner creates the corresponding annotated
  `lmdj-v1.0.<BUILD>.0` tag on the full merge SHA.
- Product Build tags do not contain the Channel.
- M1 cannot be promoted above `dev`; Beta requires the later first-user-value
  milestone.
- Tag creation does not authorize tag push, GitHub Release, Channel promotion,
  publishing, deployment, or release verification.

### Module, Contract and Provider rules

- Every `module.json` declares its own SemVer and exact dependency versions.
- Contract ID Major and full Schema SemVer are independent from Product Build.
- Provider ID, Provider SemVer, Capability Contract and model/rule Artifact
  identity are all recorded separately.
- `products/lmdj/assembly.lock.json` locks the exact resolved versions and
  hashes used by a Product Build.
- Changing an internal module version does not mechanically change the Product
  Build until a new Assembly is integrated.

### Files and verification

This plan creates and verifies:

```text
contracts/version/lmdj.product-version.v1.schema.json
products/lmdj/version.json
products/lmdj/assembly.lock.json
scripts/version.py
tests/build/version_test.py
build/core/<preset>/build-manifest.json
```

Required gates:

```bash
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tests/build/version_test.py
version_tag="$(python3 scripts/version.py tag-name \
  --version-file products/lmdj/version.json)"
git rev-list -n 1 "$version_tag"
git cat-file -t "$version_tag"
```

Rollback reuses the original immutable Product Build tag and Artifact hashes.
It never moves the tag or creates a new version for identical bits.

## Accepted Proof Scaffolding and Recorded Debt (2026-07-30 architecture review)

These positions are deliberate. Implementers must not "fix" them inside this
proof, and later plans must not inherit them silently:

- **The integer renderer is scaffolding.** Byte-exact Golden Audio exists to
  prove determinism cheaply. Product DSP (filters, FX, time-stretch) will be
  floating-point, and the cross-platform gate then becomes the tolerance-based
  Golden comparison of redesign spec §21.2. Do not extend the integer mixer
  beyond this proof.
- **The Facade is the control plane, not the realtime data plane.**
  `take.begin/append/commit` over JSON proves transactional semantics only.
  Realtime Hosts must feed recording through the §11.4 lock-free Capture Ring;
  they must not reuse the per-event JSON path.
- **`project-io` writes `std::filesystem` directly.** The §9 Storage Provider
  abstraction is deferred on purpose; Web/OPFS has no fsync and different
  rename semantics, so porting to Web requires introducing that interface
  first. Recorded as debt, not an oversight.
- **`nlohmann::json` appears in public C++ headers** (`Error.details`, Facade
  request/response types). Accepted inside the monorepo because the C ABI
  isolates external consumers; it must never leak across the C ABI, the JSON
  Schemas, or any published SDK header.

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

The names above are the only public Proof error enum. The broader design’s §18 labels are diagnostic categories, not a second enum:

| Proof error | §18 diagnostic category |
| --- | --- |
| `UNSUPPORTED_AUDIO` | `DECODE_FAILED` |
| `INVALID_PROJECT`, `MISSING_ASSET`, `COOK_FAILED` | `SNAPSHOT_REJECTED`, preserving the Proof code as the cause |
| `PROVIDER_NOT_FOUND`, `PROVIDER_FAILED`, `PERMISSION_DENIED` | Provider selection/execution failure |
| `IO_ERROR` | Project or Artifact persistence failure |

The later full Provider Conformance Lab must extend this versioned error contract through design review instead of introducing parallel codes.

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
- Create: `products/lmdj/version.json`
- Create: `scripts/core.sh`
- Create: `scripts/version.py`
- Create: `scripts/verify-core-dependencies.sh`
- Create: `tests/build/test_active_tree.sh`
- Create: `tests/build/version_test.py`
- Preserve: `docs/governance/version-management.md`
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
- Produces Product Build `1.0.1.0` identity and the version verification API used by all later PR gates.
- Preserves `references/demos/` and all confirmed redesign documents.

- [ ] **Step 1: Encode and run the immutable-dependency preflight**

Create `scripts/verify-core-dependencies.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

json_sha="42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa"
pico_commit="161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29"
verify_root="$(mktemp -d)"
trap 'rm -rf "$verify_root"' EXIT

curl --proto '=https' --tlsv1.2 -fsSL \
  https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz \
  -o "$verify_root/json.tar.xz"

if command -v sha256sum >/dev/null 2>&1; then
  actual_json_sha="$(sha256sum "$verify_root/json.tar.xz" | awk '{print $1}')"
else
  actual_json_sha="$(shasum -a 256 "$verify_root/json.tar.xz" | awk '{print $1}')"
fi
test "$actual_json_sha" = "$json_sha"

mkdir "$verify_root/PicoSHA2"
git -C "$verify_root/PicoSHA2" init --quiet
git -C "$verify_root/PicoSHA2" fetch --quiet --depth 1 \
  https://github.com/okdshin/PicoSHA2.git "$pico_commit"
git -C "$verify_root/PicoSHA2" checkout --quiet FETCH_HEAD
test "$(git -C "$verify_root/PicoSHA2" rev-parse HEAD)" = "$pico_commit"
grep -Eq '^project\(picosha2\)' "$verify_root/PicoSHA2/CMakeLists.txt"
grep -Eq '^add_library\(\$\{PROJECT_NAME\} INTERFACE\)' \
  "$verify_root/PicoSHA2/CMakeLists.txt"
cmake -S "$verify_root/PicoSHA2" -B "$verify_root/pico-build" \
  -DPICOSHA2_TEST=OFF -DPICOSHA2_EXAMPLE=OFF

echo "core dependency verification: PASS"
```

Run:

```bash
bash scripts/verify-core-dependencies.sh
```

Expected: `core dependency verification: PASS`.

The pinned PicoSHA2 commit is known to define `project(picosha2)` and `add_library(${PROJECT_NAME} INTERFACE)`, so the imported target name is `picosha2`. The preflight and CMake configuration both fail closed if the fetched sources disagree. The nlohmann/json `URL_HASH` repeats the tarball integrity check during `FetchContent`.

- [ ] **Step 2: Write the active-tree guard before removing anything**

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

grep -Eq 'New Headless Core' "$repo_root/README.md"
grep -Eq 'lmdj.patch.v1.*must not' "$repo_root/AGENTS.md"
grep -Eq 'docs/governance/version-management.md' "$repo_root/AGENTS.md"
cmp "$repo_root/AGENTS.md" "$repo_root/CLAUDE.md"
```

- [ ] **Step 3: Observe the active-tree guard failure**

Run:

```bash
bash tests/build/test_active_tree.sh
```

Expected: exit `1` and `retired active path still exists: apps/api`.

- [ ] **Step 4: Remove the stopped product source and deployment surface**

Use `git rm` only on the listed tracked paths. Do not remove `references/demos/`, redesign specs, PRD decision records, or Git history.

Rewrite `README.md`, `AGENTS.md`, and `CLAUDE.md` around the new Core. The two agent guides must be byte-identical and state:

```text
New Headless Core is the only active product source.
lmdj.patch.v1 and lmdj.materials.v1 must not be used by new code.
Hosts use Application Facade; they must not parse Project bundles.
Provider failure belongs to Attempt state, never Project Truth.
docs/governance/version-management.md is the canonical version policy.
Every implementation plan contains a Version Management section.
```

Rewrite the three directory READMEs to match §13:

- `apps/README.md`: neutral Core Hosts now; `creator-web` later.
- `packages/README.md`: product-neutral Core modules only.
- `workers/README.md`: future out-of-process `provider-host`; no active Patch/Materials worker.

- [ ] **Step 5: Add the root CMake configuration with immutable dependencies**

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
project(lmdj_core LANGUAGES CXX)

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

Create `packages/foundation/CMakeLists.txt` initially as an `INTERFACE` target so configure succeeds; Task 2 replaces it with the real library. The root CMake Project intentionally has no Product version: `products/lmdj/version.json` owns Product Build identity, while each Module owns its own SemVer.

`CMakePresets.json` must define `dev`, `release`, `test`, and `asan` presets under `build/core/<preset>`. `asan` enables AddressSanitizer and UndefinedBehaviorSanitizer on Clang/GCC.

- [ ] **Step 6: Add failing Product Build version tests**

Create `products/lmdj/version.json`:

```json
{
  "contract": "lmdj.product-version.v1",
  "product": "lmdj",
  "milestone": 1,
  "minor": 0,
  "build": 1,
  "patch": 0
}
```

Create `tests/build/version_test.py` with these assertions:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.version import ProductVersion, load_version

version = load_version("products/lmdj/version.json")
assert version == ProductVersion(1, 0, 1, 0)
assert str(version) == "1.0.1.0"
assert version.product_tag() == "lmdj-v1.0.1.0"
assert version.display("dev", "a" * 40) == "1.0.1.0 · dev · gaaaaaaaa"

for invalid in (
    {"milestone": 0, "minor": 0, "build": 1, "patch": 0},
    {"milestone": 1, "minor": -1, "build": 1, "patch": 0},
    {"milestone": 1, "minor": 0, "build": 0, "patch": 1},
):
    try:
        ProductVersion(**invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f"accepted invalid product version: {invalid}")
```

- [ ] **Step 7: Observe the missing version module failure**

Run:

```bash
python3 tests/build/version_test.py
```

Expected: import failure because `scripts/version.py` does not exist.

- [ ] **Step 8: Implement Product Build parsing and verification**

Create `scripts/version.py` around this exact public API:

```python
from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import re
import subprocess


@dataclass(frozen=True, order=True)
class ProductVersion:
    milestone: int
    minor: int
    build: int
    patch: int

    def __post_init__(self) -> None:
        if self.milestone < 1:
            raise ValueError("milestone must be >= 1")
        if min(self.minor, self.build, self.patch) < 0:
            raise ValueError("minor, build, and patch must be >= 0")
        if self.build == 0 and self.patch != 0:
            raise ValueError("patch requires a non-zero build")

    def __str__(self) -> str:
        return (
            f"{self.milestone}.{self.minor}."
            f"{self.build}.{self.patch}"
        )

    def product_tag(self) -> str:
        return f"lmdj-v{self}"

    def display(self, channel: str, revision: str) -> str:
        if channel not in {"canary", "dev", "beta", "stable"}:
            raise ValueError(f"invalid channel: {channel}")
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("revision must be a full lowercase Git SHA")
        return f"{self} · {channel} · g{revision[:8]}"

def load_version(path: str | Path) -> ProductVersion:
    data = json.loads(Path(path).read_text())
    if data["contract"] != "lmdj.product-version.v1":
        raise ValueError("unsupported product version contract")
    if data["product"] != "lmdj":
        raise ValueError("unexpected product id")
    return ProductVersion(
        data["milestone"],
        data["minor"],
        data["build"],
        data["patch"],
    )
```

The CLI supports:

```text
current --version-file PATH --channel CHANNEL --revision FULL_SHA
verify --version-file PATH [--assembly PATH --lock PATH]
tag-name --version-file PATH
```

`verify` checks exact integer fields, Product/Contract IDs, Assembly version
equality when supplied, lock completeness when supplied, and validates the
full lowercase SHA returned by `git rev-parse HEAD`. It never creates or moves
a tag.

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json
```

Expected:

```text
product version tests: PASS
version verification: PASS (1.0.1.0)
```

- [ ] **Step 9: Add one stable developer entry point**

`scripts/core.sh` accepts only:

```text
configure [dev|release|asan]
build [dev|release|asan]
test [dev|release|asan]
proof
clean
```

`clean` may remove only the explicit repository path `build/core`; reject an empty or root path before removal.

- [ ] **Step 10: Replace CI with the new build guard**

`.github/workflows/ci.yml` runs on Ubuntu and macOS:

```yaml
- run: bash scripts/verify-core-dependencies.sh
- run: bash tests/build/test_active_tree.sh
- run: python3 tests/build/version_test.py
- run: python3 scripts/version.py verify --version-file products/lmdj/version.json
- run: scripts/core.sh configure release
- run: scripts/core.sh build release
- run: scripts/core.sh test release
```

There is no deploy job in this proof.

- [ ] **Step 11: Verify the clean build lab**

Run:

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev
git diff --check
```

Expected:

```text
100% tests passed, 0 tests failed
```

- [ ] **Step 12: Commit the retired boundary and build lab**

```bash
git add -A -- \
  .github .dockerignore .gitignore AGENTS.md CLAUDE.md README.md \
  CMakeLists.txt CMakePresets.json cmake scripts tests/build \
  apps packages products/lmdj/version.json workers \
  Dockerfile Caddyfile compose.yml compose.smoke.yml .env.example
git commit -m "chore(core): replace retired product with headless build lab"
```

---

### Task 2: Define versioned contracts and the product-neutral Foundation

**Files:**

- Create: `contracts/project/lmdj.project.v1.schema.json`
- Create: `contracts/capability/lmdj.capability.v1.schema.json`
- Create: `contracts/assembly/lmdj.assembly.v1.schema.json`
- Create: `contracts/error/lmdj.error.v1.schema.json`
- Create: `contracts/module/lmdj.module.v1.schema.json`
- Create: `contracts/version/lmdj.product-version.v1.schema.json`
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
- Produces Module SemVer `0.1.0` and Contract Schema versions `1.0.0`, independent from Product Build `1.0.1.0`.

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

- [ ] **Step 4: Add and validate all six schemas**

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

Every Schema declares metadata version `1.0.0`. `lmdj.module.v1` requires Module ID, SemVer, integer `api_version`, and exact dependency versions. `lmdj.product-version.v1` requires Product `lmdj`, `milestone >= 1`, and non-negative `minor/build/patch`.

Create `packages/foundation/module.json`:

```json
{
  "contract": "lmdj.module.v1",
  "module": "foundation",
  "version": "0.1.0",
  "api_version": 1,
  "dependencies": {}
}
```

`tests/conformance/schema_contract_test.py` uses Python standard library JSON to inspect all six schemas and assert the required keys, exact cardinalities, ID patterns, version metadata, `additionalProperties` rules, and Pad Slot event shape. C++ serialization round-trip tests validate positive and negative Project instances against the same locked invariants. Do not add an unpinned Python package.

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
schema contract checks: 6 passed
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
- Modify: `products/lmdj/version.json`
- Modify: `tests/build/version_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `foundation`.
- Produces: immutable-value Project state, Commands, typed command outcomes.
- Does not perform file I/O, Provider calls, rendering, or Host parsing.

- [ ] **Step 1: Advance the PR 2 Product Build and declare Module version**

Set `products/lmdj/version.json` to Build `2`, Patch `0`; update
`tests/build/version_test.py` to expect `1.0.2.0` and
`lmdj-v1.0.2.0`.

`packages/authoring-domain/module.json` declares version `0.1.0`,
`api_version: 1`, and exact dependency `foundation: 0.1.0`.

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
```

Expected: both pass and report `1.0.2.0`.

- [ ] **Step 2: Add failing tests for the 64-pad and slot-reference invariants**

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

- [ ] **Step 3: Add failing command atomicity and idempotency tests**

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
- Domain never derives a Pattern step from `RawTakeEvent.frame_offset`; the Proof Host is responsible for supplying both representations.

- [ ] **Step 4: Observe the expected failures**

Run:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
```

Expected: missing Authoring Domain headers/targets.

- [ ] **Step 5: Implement the Project factory and pure Command Handler**

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

- [ ] **Step 6: Run Domain tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'domain\\.' --output-on-failure
```

Expected:

```text
100% tests passed, 0 tests failed
```

- [ ] **Step 7: Commit the Authoring Domain**

```bash
git add \
  packages/authoring-domain \
  products/lmdj/version.json \
  tests/build/version_test.py \
  tests/core/domain \
  CMakeLists.txt
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
- `packages/project-io/module.json` declares version `0.1.0`, `api_version: 1`, and exact dependencies `foundation: 0.1.0`, `authoring-domain: 0.1.0`.

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
- a duplicate command after reopen remains idempotent;
- while the test holds an exclusive advisory lock on `<bundle>/.lock` through
  an independent file descriptor, `execute` does not commit; after the lock is
  released it completes at the next revision — proving cross-process
  serialization without relying on an in-process mutex.

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

1. acquire an exclusive OS advisory file lock (`flock`/`fcntl`) on
   `<bundle>/.lock`, creating the file if missing — a process-local mutex is
   insufficient because the one-shot CLI and the long-lived MCP Host can
   commit to the same bundle concurrently;
2. load and validate current state;
3. call the pure Command Handler;
4. write and fsync immutable transaction and checkpoint temp files;
5. rename both temp files to their final revision-scoped names;
6. write and fsync `manifest.json.tmp.<command_id>` pointing to those exact files;
7. atomically rename the manifest temp file to `manifest.json`;
8. fsync the parent directory where supported;
9. return the committed revision.

The manifest rename is the only commit point. Revision-scoped files beyond the manifest head are ignored after a crash and removed during verified recovery. Never report success before the new manifest head is durable.

The advisory lock is held from before state load until after the manifest
rename and directory fsync. A concurrent Host therefore blocks, then loads the
new revision and fails its own `expected_revision` check honestly. Without the
lock, two processes could both validate against the same revision and the
later manifest rename would silently discard a commit already reported as
successful — a violation of the never-lie-about-success rule.

`import_artifact` performs the same revision transaction: it hashes and stages the blob, constructs the Domain `ImportAsset` command, and publishes the blob plus new manifest head as one logical commit. A staged or unreferenced blob from a crash is outside the manifest head and is removed during verified recovery.

- [ ] **Step 5: Implement the Proof-scoped strict recording rule**

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

This branch deliberately handles every changed revision the same way. It must not classify unrelated Commands or add selective rebase behavior inside the Proof.

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
- Generate and add: `tests/fixtures/audio/stereo.wav`
- Create: `tests/fixtures/audio/hashes.json`
- Modify: `products/lmdj/version.json`
- Modify: `tests/build/version_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `foundation`, `authoring-domain`.
- Reads Artifact bytes through an injected resolver; it does not know Project bundle layout.
- Produces a fully validated immutable Snapshot with decoded PCM and resolved Pattern events.

- [ ] **Step 1: Advance the PR 3 Product Build and declare Module version**

Set `products/lmdj/version.json` to Build `3`, Patch `0`; update the version
test to expect `1.0.3.0` and `lmdj-v1.0.3.0`.

`packages/project-cooker/module.json` declares version `0.1.0`,
`api_version: 1`, and exact dependencies `foundation: 0.1.0`,
`authoring-domain: 0.1.0`.

Run the version test and verifier; both must report `1.0.3.0`.

- [ ] **Step 2: Generate independent deterministic audio fixtures**

`make_fixtures.py` uses only `math`, `struct`, `wave`, `hashlib`, and `json`. Generate:

- `kick.wav`: 48 kHz mono PCM16, 4,800 frames, decaying 60 Hz sine.
- `snare.wav`: 48 kHz mono PCM16, 2,400 frames, deterministic xorshift32 noise with decay.
- `stereo.wav`: 48 kHz stereo PCM16 with four frames whose left samples are `[32767, -32768, 123, -456]` and right samples are `[-32768, 32767, -789, 1011]`.

The script writes `hashes.json` and exits non-zero if regenerating existing fixtures changes hashes unexpectedly.

- [ ] **Step 3: Add failing WAV and Cook tests**

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

- mono PCM16 fixtures decode correctly;
- `stereo.wav` decodes to exactly four frames and preserves the declared left/right interleave;
- unsupported sample rate or bit depth returns `UNSUPPORTED_AUDIO`;
- every event resolves through its current Pad Slot;
- unassigned event slots return `MISSING_ASSET`;
- missing Pattern returns `NOT_FOUND`;
- Snapshot retains Project revision and contains no mutable Project pointer;
- cooking the same state twice produces equal Snapshot values.

- [ ] **Step 4: Observe the expected failures**

Run:

```bash
python3 tests/fixtures/audio/make_fixtures.py
scripts/core.sh build dev
```

Expected: fixture generation succeeds; compile fails before the Cooker exists.

- [ ] **Step 5: Implement strict WAV decode and Project Cook**

The decoder accepts only RIFF/WAVE with one `fmt ` and one `data` chunk, PCM format `1`, 16-bit, 48 kHz, one or two channels. Check all chunk bounds before reading.

The Cooker:

1. validates the Pattern and Project revision;
2. resolves each event’s Pad Slot at Cook time;
3. resolves Asset metadata to bytes through `ArtifactResolver`;
4. verifies bytes match the recorded SHA-256;
5. decodes each unique Artifact once;
6. creates a new immutable Snapshot;
7. returns no partial Snapshot on failure.

- [ ] **Step 6: Run Cooker tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'cooker\\.' --output-on-failure
```

Expected: all WAV validation, slot resolution, hash, and determinism tests pass.

- [ ] **Step 7: Commit Cooker and fixed fixtures**

```bash
git add \
  packages/project-cooker \
  products/lmdj/version.json \
  tests/build/version_test.py \
  tests/core/cooker \
  tests/fixtures/audio \
  CMakeLists.txt
git commit -m "feat(cooker): add immutable runtime snapshot cooking"
```

---

### Task 6: Render deterministic offline WAV through the Audio Runtime

**Files:**

- Create: `packages/audio-runtime/module.json`
- Create: `packages/audio-runtime/CMakeLists.txt`
- Create: `packages/audio-runtime/include/lmdj/audio/mix_math.hpp`
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
- `packages/audio-runtime/module.json` declares version `0.1.0`, `api_version: 1`, and exact dependencies `foundation: 0.1.0`, `project-cooker: 0.1.0`.

- [ ] **Step 1: Add an independent Golden Audio reference renderer**

The Python renderer uses the same documented integer rules, but no production C++ code:

```python
def floor_div(numerator: int, denominator: int) -> int:
    return numerator // denominator

step_frame = (step * sample_rate * 60) // (bpm * 4)
scaled = floor_div(sample_value * velocity + 63, 127)
mixed = max(-32768, min(32767, current + scaled))
```

Velocity scaling uses mathematical floor division in every language. C++ must not use its default signed division directly because it truncates toward zero. `mix_math.hpp` defines:

```cpp
namespace lmdj::audio::detail {

constexpr std::int64_t floor_div(
    std::int64_t numerator,
    std::int64_t denominator) {
  const auto quotient = numerator / denominator;
  const auto remainder = numerator % denominator;
  return remainder != 0 && ((remainder < 0) != (denominator < 0))
      ? quotient - 1
      : quotient;
}

constexpr std::int32_t scale_velocity(
    std::int16_t sample,
    std::uint8_t velocity) {
  return static_cast<std::int32_t>(
      floor_div(
          static_cast<std::int64_t>(sample) * velocity + 63,
          127));
}

}  // namespace lmdj::audio::detail
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
- `floor_div(-64, 127) == -1`, `scale_velocity(-1, 127) == -1`, `scale_velocity(1, 127) == 1`, and `scale_velocity(-2, 64) == -1`;
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

Use integer scheduling and mixing only. All velocity scaling must call the shared `scale_velocity` helper so Golden Python floor division and C++ negative-sample behavior are identical. Do not use platform floating-point DSP, threads, devices, locks, network, logging, or allocation in the inner per-frame mix loop. Allocate the destination buffer before mixing.

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
- Modify: `products/lmdj/version.json`
- Modify: `tests/build/version_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- `provider-sdk` consumes `foundation`, not LMDJ Product code or Project I/O.
- Provider implementations consume only `provider-sdk`.
- Produces Capability discovery, Provider selection, typed Attempt outcome, and Candidate metadata.
- `provider-sdk` and both proof Provider implementations start at SemVer
  `0.1.0`; every dependency in their `module.json` is exact.
- Provider IDs are stable (`local.proof.success` and `local.proof.failure`);
  implementation SemVer is stored separately.
- Both Providers declare Capability `proof.candidate.v1` under
  `lmdj.capability.v1` Schema version `1.0.0`.

- [ ] **Step 1: Advance the PR 4 Product Build and declare Provider identities**

Set `products/lmdj/version.json` and `tests/build/version_test.py` to
`1.0.4.0`. Create the three `module.json` manifests with:

```text
provider-sdk                 0.1.0 -> foundation 0.1.0
local.proof.success          0.1.0 -> provider-sdk 0.1.0
local.proof.failure          0.1.0 -> provider-sdk 0.1.0
Capability proof.candidate.v1       -> Contract Schema 1.0.0
```

These code-only proof Providers record `model_identity: none`, exact Provider
SemVer, and the built Provider Artifact hash in every Attempt. A future
Provider that uses model weights or a rule asset must additionally record that
asset's immutable ID, version, and SHA-256.

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json
```

Expected: both report Product Build `1.0.4.0`.

- [ ] **Step 2: Add failing Provider conformance tests**

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

- [ ] **Step 3: Add the mutation isolation test before implementation**

The test hashes every file under a prepared `.lmdj` bundle, runs the failing Provider, then asserts:

```text
same Project file set
same Project bytes
same Project revision
one new Workspace Attempt file
```

- [ ] **Step 4: Observe the expected failures**

Run:

```bash
scripts/core.sh build dev
```

Expected: missing Provider SDK and proof Provider targets.

- [ ] **Step 5: Implement Registry, policy gate, and Attempt persistence**

`AttemptStore` writes only under the injected Workspace root:

```text
.lmdj-workspace/
  attempts/
    <attempt-id>.json
  host-settings.json
```

Provider selection writes `host-settings.json`, not `.lmdj`. An Attempt records request metadata, Provider ID/version, start/end timestamps, terminal status, typed error, Candidate IDs, and Artifact hashes. It does not store secrets or reasoning.

- [ ] **Step 6: Implement two deterministic proof Providers**

- `local.proof.success` version `0.1.0` writes zero bytes through the injected
  `ArtifactSink` and returns the resulting `application/x-lmdj-proof`
  Candidate Artifact with SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
  and deterministic provenance.
- `local.proof.failure` version `0.1.0` returns `PROVIDER_FAILED` with message
  `intentional proof failure`.

The sink writes only inside the current Attempt workspace. Neither Provider receives a Project Store, Project bundle path, or mutable Project object.

- [ ] **Step 7: Run all Provider conformance and isolation tests**

Run:

```bash
scripts/core.sh build dev
ctest --test-dir build/core/dev -R 'provider\\.' --output-on-failure
```

Expected: both Providers pass the shared conformance suite; isolation test passes.

- [ ] **Step 8: Commit Provider SDK**

```bash
git add \
  packages/provider-sdk \
  providers \
  tests/core/provider \
  products/lmdj/version.json \
  tests/build/version_test.py \
  CMakeLists.txt
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
- Create: `tests/core/facade/dynamic_load_test.cpp`
- Modify: `CMakeLists.txt`
- Modify: `packages/project-io/module.json`
- Modify: `packages/project-io/CMakeLists.txt`
- Modify: `packages/project-io/include/lmdj/project_io/project_store.hpp`
- Modify: `packages/project-io/src/project_store.cpp`
- Modify: `tests/core/project_io/project_store_test.cpp`
- Modify: `docs/plans/2026-07-30-lmdj-headless-core-proof.md`

**Interfaces:**

- Consumes: Domain, Project I/O, Cooker, Audio Runtime, Provider SDK.
- Produces the only supported Host API.
- C ABI owns opaque engine handles and caller-freed UTF-8 JSON responses.
- `application-facade` starts at SemVer `0.1.0` and locks exact `0.1.0`
  dependencies on `foundation`, `authoring-domain`, `project-cooker`,
  `audio-runtime`, and `provider-sdk`, plus exact `project-io 0.2.0`.
- Task 8 adds the bounded, symlink-safe, byte-length- and SHA-verifying
  `ProjectStore::read_artifact` API and advances `project-io` from `0.1.0` to
  `0.2.0`. Facade must use this API as Cooker's Artifact resolver and must not
  know the Project bundle's private Artifact layout.
- Task 8 remains inside PR 4, so it does not allocate another Product Build.

- [ ] **Step 1: Add failing Facade behavior tests**

Use:

```cpp
struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource timestamp_source;
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
render.offline
provider.select
provider.run
```

Supported proof queries:

```text
project.inspect
take.recoverable.list
snapshot.cook
provider.list
provider.selected
attempt.inspect
```

All request objects reject additional properties. The exact fields after
`operation` are:

| Operation | Exact fields after `operation` |
| --- | --- |
| `project.create` | `project_path`, `project_id`, `bpm` |
| `asset.import` | `project_path`, `command_id`, `expected_revision`, `asset_id`, `source_path`, `media_type` |
| `pad.assign` | `project_path`, `command_id`, `expected_revision`, `slot:{bank,pad}`, `asset_id` (UUID or null) |
| `take.begin` | `project_path`, `take_id`, `expected_revision`, `sample_rate` |
| `take.append` | `project_path`, `take_id`, `event:{slot:{bank,pad},frame_offset,velocity}` |
| `take.commit` | `project_path`, `command_id`, `expected_revision`, `take_id`, `pattern:{pattern_id,bars,events:[{slot,step,velocity}]}` |
| `render.offline` | `project_path`, `pattern_id`, `output_path` |
| `provider.select` | `capability`, `provider_id` |
| `provider.run` | `attempt_id`, `capability`, `inputs`, `parameters`, `data_classification`, `platform`, `region`, `required_permissions` |
| `project.inspect` | `project_path` |
| `take.recoverable.list` | `project_path` |
| `snapshot.cook` | `project_path`, `pattern_id` |
| `provider.list` | no additional fields |
| `provider.selected` | `capability` |
| `attempt.inspect` | `attempt_id` |

UUID-backed IDs use lowercase RFC 4122 version/variant-shaped strings.
Attempt IDs use Provider SDK's safe file-ID grammar. Integer fields reject
fractional, negative, string, and overflow values. Every success envelope has
exactly `ok`, `result`, and `project_revision`; Project-scoped operations
return the observed/current unsigned revision and Workspace-only Provider
operations return JSON `null`. Errors have exactly
`ok:false,error:{code,message,details}` and claim no Project revision.

Tests call only these methods and assert stable success/error envelopes, revision propagation, and no exception crossing the public boundary. `snapshot.cook` is a non-persisting diagnostic Query. `render.offline` is a self-contained Command with this request shape:

```json
{
  "operation": "render.offline",
  "project_path": "/absolute/path/proof-beat.lmdj",
  "pattern_id": "00000000-0000-4000-8000-000000000010",
  "output_path": "/absolute/path/beat.wav"
}
```

The Facade test must construct one `Application`, call `snapshot.cook`, destroy it, construct a fresh `Application`, and successfully call `render.offline` using only `project_path` and `pattern_id`. No public request or response contains `snapshot_id`.

`ApplicationConfig` injects Provider policy and time. Defaults are an empty
Registry, deny-all policy, and a non-locale Host clock. Product-neutral Facade
must not hard-code Proof region/classification/platform/permission policy.
`take.commit` reads Raw Take events from the Project-owned active journal; the
request supplies only Pattern data, which is fully validated before any
revision-conflict path.

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

The opaque engine implementation uses a synchronized live registry and
process-lifetime tombstone shells. Calls look up before dereference, retain
in-flight shared ownership, and serialize per engine. Null, unknown, freed,
double-freed, and ABA handles are safe. The Task 8 C config is exactly
`{"workspace_root":"/absolute/path"}` and composes an empty Registry with
deny-all policy. All static dependencies of the shared ABI are PIC, and a real
dynamic-load test resolves only the declared callable surface.

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

Queries never increment revision. `snapshot.cook` loads the requested Project revision, cooks a Snapshot, returns a diagnostic summary (`project_revision`, `pattern_id`, `event_count`, resolved Artifact hashes), and then releases it.

`render.offline` loads the Project and Pattern named in the same request, performs Cook and Render inside that one Facade call, and returns the output Artifact. There is no public Snapshot handle registry. A long-lived Host may later cache immutable Snapshots as a private optimization, but cache identity can never become required public input.

Render rejects an existing destination and every path inside a `.lmdj`
bundle. It writes a unique sibling temporary file, verifies the rendered
Artifact, then atomically publishes without overwrite. Every failure removes
the temporary and leaves Project Truth and any existing destination unchanged.

- [ ] **Step 5: Implement exception-safe C ABI ownership**

Catch all exceptions inside `c_api.cpp` and translate to `INTERNAL_ERROR`.
Allocate returned strings with one allocator and free only through
`lmdj_string_free`. Define ABI version/status macros, null required output
pointers before work, and make `lmdj_string_free(NULL)` a no-op. Add tests for
malformed JSON/UTF-8, null pointers, unknown/freed/double-free/ABA handles,
repeated create/free, racing free, and 1,000 command/query calls under ASan.

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
git add packages/application-facade packages/project-io tests/core/facade \
  tests/core/project_io/project_store_test.cpp CMakeLists.txt \
  docs/plans/2026-07-30-lmdj-headless-core-proof.md
git commit -m "feat(facade): expose unified application and c abi"
```

---

### Task 9: Add a JSON-first Headless CLI Host

**Files:**

- Create: `apps/core-cli/module.json`
- Create: `apps/core-cli/CMakeLists.txt`
- Create: `apps/core-cli/src/main.cpp`
- Create: `tests/host/cli_test.py`
- Modify: `products/lmdj/version.json`
- Modify: `tests/build/version_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes only `application-facade`.
- Uses exactly one of these position-sensitive five-token forms
  (`argc == 6`, including the executable):

  ```text
  lmdj-core --workspace WORKSPACE command --request JSON
  lmdj-core --workspace WORKSPACE query   --request JSON
  lmdj-core --workspace WORKSPACE command --request-file FILE
  lmdj-core --workspace WORKSPACE query   --request-file FILE
  ```

  Reordering, combined or duplicate flags, stdin, extra operands, and both
  request sources are not supported.
- A grammar-valid invocation writes exactly
  `canonical_json(response) + "\n"` to stdout and nothing to stderr. Success
  exits `0`; every structured Host or Facade failure exits `2`.
- A grammar-invalid invocation writes no stdout, one plain usage diagnostic to
  stderr, and exits `64`. Task 9 emits no ANSI color. A broken stdout exits
  `2`.
- `WORKSPACE` must be non-empty UTF-8, absolute, and lexically normalized. The
  Host neither resolves it nor requires it to exist. Invalid workspace values
  return `INVALID_ARGUMENT`.
- Inline and file requests are bounded at 16,777,216 bytes before parsing.
  On macOS/Linux, request files are opened once without blocking, validated as
  regular through that same file descriptor, and read in bounded chunks.
  `EINTR`, read failure, concurrent growth, and the 16 MiB + 1 sentinel are
  handled without a fixed 16 MiB allocation. A non-POSIX build must use an
  explicit unsupported-platform error path rather than a path-check/path-open
  fallback. Missing, non-regular, unopenable, or failed file reads return
  `IO_ERROR`; empty, oversized, invalid UTF-8, malformed JSON, and non-object
  requests return `INVALID_ARGUMENT`.
- Project, source, and output paths pass unchanged to Facade; the Host neither
  parses a Project bundle nor requires Project containment in the Workspace.
- Host exceptions never escape `main`. Unexpected construction, parsing,
  serialization, or dispatch failures become a fixed `INTERNAL_ERROR`
  envelope without exception text, with a predeclared ASCII fallback for the
  final catch-all.
- Dispatch depends only on the argv `command`/`query` token. The Host never
  reads the request's `operation`.
- `core-cli` starts at Module SemVer `0.1.0` with exact dependency
  `application-facade 0.1.0`.
- It constructs an explicitly empty Provider Registry and does not link either
  Proof Provider.
- Version impact: Product Build advances from `1.0.4.0` to `1.0.5.0`;
  `core-cli` is introduced at `0.1.0`; no existing Module, Provider, or
  Contract version changes.

- [ ] **Step 1: Advance the PR 5 Product Build**

First update `tests/build/version_test.py` to require Product Build `1.0.5.0`
and the real `apps/core-cli/module.json` to be exactly:

```json
{
  "contract": "lmdj.module.v1",
  "module": "core-cli",
  "version": "0.1.0",
  "api_version": 1,
  "dependencies": {
    "application-facade": "0.1.0"
  }
}
```

Run the test and observe failure against Product Build `1.0.4.0` and the
missing real Host manifest. Then set `products/lmdj/version.json` to
`1.0.5.0` and create the manifest.

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json
```

Expected: both report Product Build `1.0.5.0`.

- [ ] **Step 2: Add failing black-box CLI tests**

`cli_test.py` derives the repository root from `__file__`, resolves the
supplied executable, uses only absolute fixture/workspace/Project/output
paths, and invokes subprocesses with argv arrays and `shell=False`. Every
grammar-valid helper additionally asserts one complete canonical JSON value
plus LF on stdout and empty stderr. Every child process has an explicit
timeout; timeout cleanup kills and reaps it. The registered `host.cli` CTest
has an overall 60-second timeout.

Implement exactly nine fixtures:

1. `usage_contract`: missing, unknown, reordered, duplicate, extra, and both
   request-source forms return `64`, empty stdout, plain non-ANSI stderr.
2. `workspace_contract`: relative/non-normalized Workspace returns canonical
   `INVALID_ARGUMENT`/`2`; normalized absolute Workspace is accepted.
3. `request_source_parity`: inline and file `provider.list` responses are
   byte-identical and contain an empty Provider list.
4. `request_validation`: empty, malformed, invalid UTF-8, non-object, and
   16 MiB + 1 requests return `INVALID_ARGUMENT`/`2`; missing, directory, and
   FIFO request files return `IO_ERROR`/`2` without blocking; a symlink that
   resolves to a regular request file remains valid.
5. `facade_routing_and_exit_mapping`: success returns `0`; unknown operation
   and command/query mismatch preserve Facade `INVALID_ARGUMENT`/`2`.
6. `separate_process_authoring`: create, import, assign, begin, each append,
   commit, and inspect use separate processes; revisions are `0..5`; inspect
   shows 64 Pads, two Assets, one Take, one Pattern, and four events; the
   active Take journal is absent after commit.
7. `fresh_process_replay`: replay after journal cleanup returns
   `replayed:true`, original `committed_revision:5`, no active Take journal,
   and no Project mutation.
8. `fresh_process_snapshot_render_golden`: a new render process receives only
   Project path, Pattern ID, and output path; no `snapshot_id`; output bytes
   and SHA-256 equal committed Golden and manifest bytes do not change.
9. `host_boundary_and_identity`: Product Build is `1.0.5.0`; CLI manifest is
   exact; CLI links only `lmdj::application`; among `lmdj/...` headers
   `main.cpp` includes only `lmdj/facade/application.hpp`; source contains no
   `project_io`, managed bundle layout/recovery literals, or request-side
   access to `operation`; CMake configure/generate emits read-only
   `LINK_LIBRARIES` metadata reporting only the direct Application dependency;
   CTest JSON reports the real executable and 60-second timeout. Do not pin
   implementation spelling such as the argc
   comparison or request-limit literal.

Compare committed Golden files without regenerating them. The harness is
path-portable, but Task 9 acceptance covers macOS/Linux CI only.

- [ ] **Step 3: Observe the missing executable failure**

Run:

```bash
python3 tests/host/cli_test.py build/core/dev/bin/lmdj-core
```

Expected: `FileNotFoundError` for `lmdj-core`.

- [ ] **Step 4: Implement the thin Host**

`main.cpp`:

1. parses only Host flags;
2. constructs `Application` from workspace root and an injected Provider Registry;
3. parses request JSON;
4. calls `command` or `query`;
5. writes canonical JSON plus one newline;
6. maps envelope success/failure to the defined exit codes.

Task 9 tests core Project behavior with an empty Registry; Task 11 supplies the Product Assembly and proof Providers. The CLI does not inspect command names beyond selecting command versus query.

Add `add_subdirectory(apps/core-cli)` after Application Facade. The target is
`lmdj_core_cli`, has `OUTPUT_NAME lmdj-core`, links only
`PRIVATE lmdj::application`, and uses repository warnings/sanitizers. Register
`host.cli` in CTest with `${Python3_EXECUTABLE}` and
`$<TARGET_FILE:lmdj_core_cli>`.

Do not modify `scripts/core.sh`: its existing build/test commands already
cover root targets and registered CTest tests.

- [ ] **Step 5: Run CLI black-box tests**

Run:

```bash
scripts/core.sh build dev
python3 tests/host/cli_test.py build/core/dev/bin/lmdj-core
```

Expected:

```text
cli behavior fixtures: 9 passed
```

- [ ] **Step 6: Commit the CLI Host**

```bash
git add \
  apps/core-cli \
  tests/host/cli_test.py \
  products/lmdj/version.json \
  tests/build/version_test.py \
  CMakeLists.txt \
  docs/plans/2026-07-30-lmdj-headless-core-proof.md
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
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes the C ABI shared library through `ctypes`.
- Implements MCP `2025-11-25` lifecycle and Tools over stdio.
- Emits no non-protocol bytes on stdout.
- `core-mcp` starts at Module SemVer `0.1.0`, locks
  `application-facade 0.1.0`, and declares C ABI compatibility
  `lmdj_core_c@1` in package metadata. Its schema-conforming Module manifest
  has exactly the `application-facade 0.1.0` dependency.
- Task 10 remains inside PR 5, so it does not allocate another Product Build.
- Python code is standard-library-only. It dynamically loads the explicit
  current-target C ABI library path and never imports or parses a Project
  bundle.
- Workspace is Host configuration supplied by required `--workspace`; it is
  never a Tool argument. The invocation is:

```bash
python3 -m lmdj_core_mcp \
  --library /absolute/path/to/liblmdj_core_c.dylib \
  --workspace /absolute/lexically/normalized/workspace
```

The shared library and Workspace arguments must be absolute. Workspace is
lexically normalized without resolving symlinks and is passed only to
`lmdj_engine_create`.

**Locked lifecycle:**

```text
NEW
  initialize request -> response -> AWAIT_INITIALIZED

AWAIT_INITIALIZED
  notifications/initialized -> no response -> READY

READY
  tools/list and tools/call available
```

- `ping` is valid in all states and returns `{}`.
- Before `READY`, valid `tools/list` and `tools/call` requests return
  `-32002`, message `Server not initialized`.
- Known Tool methods validate their request shape before the lifecycle gate:
  malformed params return `-32602` even before `READY`; only a structurally
  valid Tool request reaches the `-32002` state response.
- `initialize` is a request with required object params. An initialize
  notification has no response and does not advance state.
- Premature `notifications/initialized` has no response and does not advance
  state.
- Duplicate `initialize` after the first accepted request returns `-32600`
  without resetting state.
- The only server protocol version is `2025-11-25`. A different client version
  receives server-selected `2025-11-25` and leaves the server in
  `AWAIT_INITIALIZED`.
- Initialization returns exact server identity
  `{"name":"lmdj-core-mcp","version":"0.1.0"}` and advertises exactly
  `{"tools":{"listChanged":false}}`.
- Standard MCP request `_meta` objects are accepted for `initialize`, `ping`,
  `tools/list`, `tools/call`, and `notifications/initialized`, but are never
  forwarded into Facade arguments. `clientInfo` requires `name` and `version`
  and accepts the standard optional `title`, `description`, `websiteUrl`, and
  `icons` Implementation metadata.

**Locked JSON-RPC and transport contract:**

- Read bounded binary stdin, one newline-delimited message at a time. The
  maximum line/request is 16 MiB. Drain an oversized line through its
  delimiter, return deterministic `-32600`, and never call C for it.
- Strict UTF-8 decode and malformed JSON return `-32700`. Non-standard Python
  JSON constants (`NaN`/`Infinity`) are rejected, and excessive nesting is
  contained without terminating the Host. Requests containing escaped lone
  UTF-16 surrogates are not Unicode scalar data and return `-32600` without
  terminating the Host; notifications with the same invalid data remain
  silent. Arrays/batches and other non-object JSON return one `-32600` with no
  partial dispatch.
- Missing/wrong `jsonrpc`, missing/non-string `method`, non-object `params`,
  or `id` equal to null, Boolean, float, object, or array return `-32600`.
  Valid IDs are strings or integers, including integer `0`.
- Valid unknown requests return `-32601`; known methods with malformed params
  return `-32602`; both echo the valid ID.
- Unknown or malformed notifications never receive a response.
- Empty EOF exits `0` with no extra output. A final unterminated nonempty line
  is rejected deterministically and then the process exits.
- Every response is one compact UTF-8 JSON line, flushed immediately. stdout
  contains protocol only; diagnostics and injected logging use stderr only.
  Broken stdout is contained without a traceback or non-protocol stdout.

**Locked Tool boundary:**

Publish exactly this immutable table:

| MCP Tool | Injected Facade operation | Surface |
| --- | --- | --- |
| `lmdj.project.create` | `project.create` | command |
| `lmdj.project.inspect` | `project.inspect` | query |
| `lmdj.asset.import` | `asset.import` | command |
| `lmdj.pad.assign` | `pad.assign` | command |
| `lmdj.take.begin` | `take.begin` | command |
| `lmdj.take.append` | `take.append` | command |
| `lmdj.take.commit` | `take.commit` | command |
| `lmdj.snapshot.cook` | `snapshot.cook` | query |
| `lmdj.render.offline` | `render.offline` | command |
| `lmdj.provider.list` | `provider.list` | query |
| `lmdj.provider.select` | `provider.select` | command |
| `lmdj.provider.run` | `provider.run` | command |
| `lmdj.attempt.inspect` | `attempt.inspect` | query |

Each row owns `tool_name`, injected operation, command/query kind,
`inputSchema`, and the shared `outputSchema`. `operation` is neither published
nor accepted. The Host validates arguments and constructs a new Facade request:

```text
{"operation": <table operation>, ...validated arguments}
```

Every `inputSchema` is a Draft 2020-12-compatible root object with the exact
Task 8 fields after `operation`, exact required fields, and
`additionalProperties:false`. `lmdj.provider.list` uses an empty object schema.
Omitted `arguments` normalizes to `{}` only for that tool. Use a small
deterministic validator for the required schema subset; do not add MCP or JSON
Schema dependencies. Unknown Tools and invalid arguments return `-32602`.

The shared `outputSchema` is itself a JSON Schema object with root
`type:"object"` and describes exactly `structuredContent`, using one schema
for these closed Facade envelopes:

```text
success: {ok:true, result:object, project_revision:(unsigned integer|null)}
error:   {ok:false, error:{code:string,message:string,details:object}}
```

Both variants reject additional properties. `content` contains one text item
whose text is the compact JSON serialization of exactly `structuredContent`.
`isError` is false for success and true for a Facade error. A Facade error is
still a successful JSON-RPC `tools/call` result. Protocol/schema failures use
JSON-RPC errors.

**Locked ctypes ownership and failure translation:**

- `ctypes.CDLL` receives the explicit absolute library path. Bind `argtypes`
  and `restype` for all five C ABI functions at startup; missing symbols fail
  closed.
- Engine and returned strings are `c_void_p`. Copy returned bytes with
  `ctypes.string_at`; free every non-null returned string in `finally`.
- Free the engine exactly once in an outer `finally`, including EOF and
  `BrokenPipeError`.
- Engine creation requires status `0`, non-null engine, and no contradictory
  error string. Create/load failure is startup failure: diagnostic on stderr,
  nonzero exit, empty stdout.
- Command/query requires status `0` plus a non-null, strict UTF-8 JSON object
  Facade envelope whose strings contain only Unicode scalar data. A
  null/status mismatch, malformed response, escaped lone surrogate, or
  Python/C exception returns JSON-RPC `-32603`; do not invent a Facade
  envelope.
- Preflight compact encoded Facade requests against the C ABI 16 MiB maximum.
- Windows `.dll` remains outside this Proof. CTest supplies the real `.dylib`
  on macOS and `.so` on Linux through `$<TARGET_FILE:lmdj_core_c>`.

- [ ] **Step 1: Add failing MCP lifecycle tests**

`tests/host/mcp_stdio_test.py` is Python stdlib-only and receives the explicit
shared-library path. It spawns:

```bash
python3 -m lmdj_core_mcp --library <shared-library> --workspace <dir>
```

Implement ten fixture groups:

1. `startup_and_platform`: explicit library only; missing/wrong library fails
   with empty stdout; normalized absolute Workspace; exact Module/package
   identity; Product Build remains `1.0.5.0`.
2. `lifecycle`: `ping` in all states; initialize and alternate-version
   selection; Tool requests blocked before `READY`; initialized notification
   silence; premature notification; duplicate initialize; initialize
   notification; clean EOF.
3. `request_shape`: string/integer/zero IDs and every invalid ID/request shape.
4. `parse_and_batch`: malformed UTF-8/JSON, escaped lone surrogate, non-object,
   batch with no dispatch, and post-error liveness.
5. `method_and_notification`: unknown request, malformed known params, and
   silence for unknown/malformed notifications.
6. `tools_list`: exact capabilities, server identity, 13 Tool names, exact
   schemas, no `operation`, shared output schema.
7. `tools_call_validation`: all 13 static routes plus omitted, extra, wrong,
   and unknown Tool arguments; no request operation/name passthrough.
8. `result_contract`: one real success, one Facade error, one contained C
   internal error; exact text/structured equality and `isError`.
9. `bounded_transport`: exact 16 MiB boundary, oversized drain/no C dispatch,
   final unterminated line, immediate flush.
10. `stdout_purity_and_shutdown`: byte-level compact newline responses,
    stderr-only diagnostics/logging, clean EOF, and contained broken stdout.

- [ ] **Step 2: Add failing tool parity tests**

`tests/host/mcp_facade_parity_test.py` receives both explicit target paths and
proves both directions across fresh processes:

1. CLI authors Project revision 5 and exits. MCP inspects, cooks, and renders
   it; result/revision match CLI and WAV bytes/SHA-256 equal committed Golden.
2. MCP creates and authors a second Project through revision 5 and exits. A
   fresh CLI process inspects, cooks, and renders it; result/revision match MCP
   and WAV bytes/SHA-256 equal committed Golden.

No public request contains `snapshot_id`. Both flows assert no Project mutation
from inspect/cook/render and no active Take journal after commit.

- [ ] **Step 3: Observe the expected module failure**

Run:

```bash
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_stdio_test.py \
  /absolute/path/to/current/liblmdj_core_c
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

- [ ] **Step 5: Register the canonical CTest gate**

Root CMake registers:

```text
host.mcp_stdio
host.mcp_facade_parity
```

Pass `$<TARGET_FILE:lmdj_core_c>` and
`$<TARGET_FILE:lmdj_core_cli>` directly. Set `PYTHONPATH` to
`apps/core-mcp`, set a 60-second timeout for stdio and 120-second timeout for
cross-host parity, and make both tests depend on the real CLI/library targets.
Existing `scripts/core.sh test <preset>` needs no modification.

For sanitizer presets, an unsanitized Python executable must load the current
compiler's ASan runtime before `ctypes` opens the sanitized C ABI. CMake locates
that runtime exactly once and passes its absolute path to the test harness in a
stable environment variable. The harness adds `DYLD_INSERT_LIBRARIES` on
macOS or `LD_PRELOAD` on Linux only when it spawns the MCP Python child. On
Apple, use the verified embedding option `ASAN_OPTIONS=verify_interceptors=0`;
the default interceptor verification rejects this otherwise valid embedded
runtime even when dyld loads it before the Python framework.

- [ ] **Step 6: Run lifecycle, error, parity, and full tests**

Run:

```bash
scripts/core.sh build dev
core_library="$(python3 - <<'PY'
from pathlib import Path
candidates = [
    *Path("build/core/dev/lib").glob("liblmdj_core_c.dylib"),
    *Path("build/core/dev/lib").glob("liblmdj_core_c.so"),
]
if len(candidates) != 1:
    raise SystemExit(f"expected exactly one Core C library, got {candidates}")
print(candidates[0].resolve())
PY
)"
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_stdio_test.py \
  "$core_library"
PYTHONPATH=apps/core-mcp python3 tests/host/mcp_facade_parity_test.py \
  build/core/dev/bin/lmdj-core \
  "$core_library"
ctest --test-dir build/core/dev \
  -R '^host\.mcp_(stdio|facade_parity)$' --output-on-failure
```

Expected:

```text
mcp stdio fixtures: 10 passed
cli/mcp facade parity: passed
100% tests passed, 0 tests failed out of 2
```

Then run the complete Dev, Release, and ASan/UBSan matrices. Both registered
tests must run through all three canonical `scripts/core.sh test` invocations.

- [ ] **Step 7: Commit the MCP Host**

```bash
git add \
  apps/core-mcp \
  tests/host/mcp_stdio_test.py \
  tests/host/mcp_facade_parity_test.py \
  CMakeLists.txt \
  docs/plans/2026-07-30-lmdj-headless-core-proof.md
git commit -m "feat(mcp): expose core tools over stdio"
```

---

### Task 11: Assemble the LMDJ product and prove the complete vertical slice

**Files:**

- Create: `products/lmdj/assembly.json`
- Create: `products/lmdj/assembly.lock.json` (generated)
- Create: `products/lmdj/CMakeLists.txt`
- Create: `products/lmdj/README.md`
- Create: `products/lmdj/src/compiled_assembly.cpp`
- Create: `contracts/assembly/lmdj.assembly.v2.schema.json`
- Create: `packages/application-facade/include/lmdj/facade/assembly_loader.hpp`
- Create: `packages/application-facade/src/assembly_loader.cpp`
- Create: `tests/build/proof_failure_artifacts_test.py`
- Create: `tests/core/facade/assembly_loader_test.cpp`
- Create: `tests/conformance/module_graph_test.py`
- Create: `tests/conformance/version_lock_test.py`
- Create: `tests/e2e/headless_core_proof.py`
- Create: `tests/e2e/proof_path_safety_test.py`
- Create: `tests/e2e/requests/create-project.json`
- Create: `tests/e2e/requests/import-kick.json`
- Create: `tests/e2e/requests/import-snare.json`
- Create: `tests/e2e/requests/assign-kick.json`
- Create: `tests/e2e/requests/assign-snare.json`
- Create: `tests/e2e/requests/record-pattern.json`
- Create: `tests/e2e/requests/run-failing-provider.json`
- Modify: `products/lmdj/version.json`
- Modify: `CMakeLists.txt`
- Modify: `scripts/version.py`
- Modify: `tests/build/version_test.py`
- Modify: `tests/conformance/schema_contract_test.py`
- Modify: `tests/core/facade/c_api_test.cpp`
- Modify: `scripts/core.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/governance/version-management.md`
- Modify: `docs/plans/2026-07-30-lmdj-headless-core-proof.md`
- Modify: `packages/application-facade/CMakeLists.txt`
- Modify: `packages/application-facade/src/application.cpp`
- Modify: `packages/application-facade/src/c_api.cpp`
- Modify: `packages/application-facade/include/lmdj/facade/c_api.h`
- Modify: `packages/provider-sdk/include/lmdj/provider/attempt_store.hpp`
- Modify: `packages/provider-sdk/include/lmdj/provider/registry.hpp`
- Modify: `packages/provider-sdk/src/attempt_store.cpp`
- Modify: `packages/provider-sdk/src/registry.cpp`
- Modify: `apps/core-cli/src/main.cpp`
- Modify: `apps/core-mcp/lmdj_core_mcp/__main__.py`
- Modify: `apps/core-mcp/lmdj_core_mcp/c_api.py`
- Modify: `tests/host/cli_test.py`
- Modify: `tests/host/mcp_stdio_test.py`
- Modify: `tests/core/provider/conformance_test.cpp`
- Modify: `README.md`

**Interfaces:**

- Product Assembly names exact Module, Host, Contract, and Provider versions.
- The generated Assembly lock binds their manifest/schema/source hashes without
  embedding a self-referential Git revision.
- The generated Build Manifest binds the lock hash to Product Build `1.0.6.0`,
  Channel, full Git revision, platform, and built Artifact hashes.
- The completed Assembly Contract is `lmdj.assembly.v2` Contract SemVer
  `2.0.0`: PR 6 adds the required Provider Selection region,
  data-classification, and permission policy that the redesign already assigns
  to `products/lmdj/assembly.*`. This required field is a breaking Contract
  completion, so it is not mislabeled as `1.0.0`.
- The lock binds each Provider's deterministic source-package identity and the
  versioned Product Assembly wiring source, not only their `module.json` files.
- E2E uses public CLI and MCP surfaces only.
- CI proves the same Assembly on macOS and Ubuntu.
- Task 11 explicitly extends the Task 8 C ABI configuration/composition so MCP
  and CLI resolve the same Assembly Providers and Provider policy. This is
  completion of the still-unreleased `application-facade 0.1.0` Proof surface;
  if `0.1.0` has been published before Task 11, advance the Module SemVer
  instead of silently changing it.
- The still-unreleased Provider SDK `0.1.0` Proof surface carries structured
  model identity (`id`, `version`, `artifact_sha256`) through registration,
  selection, Candidate provenance, and terminal Attempt inspection. Assembly,
  compiled catalog, and registration must match all three fields.

- [ ] **Step 1: Advance the PR 6 Product Build**

Set `products/lmdj/version.json` and `tests/build/version_test.py` to
`1.0.6.0`.

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json
```

Expected: both report Product Build `1.0.6.0`.

- [ ] **Step 2: Add the Assembly manifest and failing graph/lock tests**

`products/lmdj/assembly.json`:

```json
{
  "contract": "lmdj.assembly.v2",
  "product": {
    "id": "lmdj",
    "version": "1.0.6.0"
  },
  "provider_policy": {
    "allowed_regions": ["local"],
    "allowed_data_classifications": ["public"],
    "granted_permissions": ["proof.execute"]
  },
  "modules": [
    {"id": "foundation", "version": "0.1.0"},
    {"id": "authoring-domain", "version": "0.1.0"},
    {"id": "project-io", "version": "0.2.0"},
    {"id": "project-cooker", "version": "0.1.0"},
    {"id": "audio-runtime", "version": "0.1.0"},
    {"id": "provider-sdk", "version": "0.1.0"},
    {"id": "application-facade", "version": "0.1.0"}
  ],
  "hosts": [
    {"id": "core-cli", "version": "0.1.0"},
    {"id": "core-mcp", "version": "0.1.0"}
  ],
  "providers": [
    {
      "id": "local.proof.success",
      "version": "0.1.0",
      "capabilities": [
        {"id": "proof.candidate.v1", "version": "1.0.0"}
      ],
      "model_identity": null
    },
    {
      "id": "local.proof.failure",
      "version": "0.1.0",
      "capabilities": [
        {"id": "proof.candidate.v1", "version": "1.0.0"}
      ],
      "model_identity": null
    }
  ],
  "contracts": [
    {"id": "lmdj.project.v1", "version": "1.0.0"},
    {"id": "lmdj.capability.v1", "version": "1.0.0"},
    {"id": "lmdj.assembly.v2", "version": "2.0.0"},
    {"id": "lmdj.error.v1", "version": "1.0.0"},
    {"id": "lmdj.module.v1", "version": "1.0.0"},
    {"id": "lmdj.product-version.v1", "version": "1.0.0"}
  ]
}
```

`module_graph_test.py` validates all module manifests and rejects:

- unknown modules;
- dependency cycles;
- Host dependencies on Project I/O;
- Provider dependencies on Authoring Domain or Product Assembly;
- a `packages/*/module.json` containing `product` or `product_id` keys;
- a neutral package dependency outside the allow-listed neutral package IDs;
- an include/source path under `packages/` that references `products/lmdj/` or `apps/creator-web/`.

The graph test explicitly permits the `lmdj::` C++ namespace, `lmdj.*` Contract IDs, and neutral LMDJ platform/module names. It enforces dependency direction and Product Assembly ownership, not a raw substring ban on `lmdj`.

`version_lock_test.py` must fail until `scripts/version.py lock` generates
`products/lmdj/assembly.lock.json`. The generated canonical JSON contains the
Product Build, Assembly SHA-256, and exact versions plus SHA-256 values for
every Module/Host manifest, Contract Schema, and Provider source manifest. It
must not contain a Git revision, Channel, build time, or platform.

- [ ] **Step 3: Add the complete failing E2E proof**

`headless_core_proof.py` performs:

1. create temporary Workspace and `proof-beat.lmdj`;
2. create Project at 120 BPM;
3. import fixed kick and snare fixtures;
4. assign Bank A Pad 1 and Pad 2;
5. begin Take at current revision;
6. append user event timing plus velocities;
7. atomically commit Raw Take and one-bar Pattern;
8. inspect Project and assert 64 Pads;
9. use one CLI process to query `snapshot.cook`, assert its diagnostic summary, and let that process exit;
10. use a new CLI process to call `render.offline` with Project path plus Pattern ID and render WAV;
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

- [ ] **Step 4: Observe the proof failure**

Run:

```bash
scripts/core.sh proof
```

Expected: failure because Assembly validation and proof wiring are not complete.

- [ ] **Step 5: Wire Assembly loading without introducing a second implementation path**

The product-neutral Assembly loader validates a manifest, reads its effective
Provider policy, and filters the compiled module/Provider registry by declared
IDs. CLI and MCP accept `--assembly <path>` and use that loader; neither
contains an `lmdj` product branch. Both still construct and call the same
`Application` implementation.

Validate the Assembly against `lmdj.assembly.v2.schema.json` before starting a Host. Fail closed on missing/unknown Provider or contract.

- [ ] **Step 6: Document the Proof-scoped recording concurrency rule**

Add this explicit scope note to `products/lmdj/README.md`:

```text
The Headless Core Proof intentionally treats every revision change during a
recording as REVISION_CONFLICT and seals the Take for recovery. This is a
Proof-only safety rule. It does not decide which product Commands are irrelevant
to a Take or whether the user-facing product may selectively rebase.
```

Do not add this rule to `docs/prd/decision-log.md` and do not close the product-level question in `docs/prd/open-questions.md`. Any product-level conflict classification or selective rebase requires the design review required by redesign spec §25.

- [ ] **Step 7: Generate the Assembly lock and make `scripts/core.sh proof` the single acceptance command**

Extend `scripts/version.py` with:

```text
lock --version-file PATH --assembly PATH --output PATH
manifest --version-file PATH --assembly PATH --lock PATH
         --channel CHANNEL --artifacts-root PATH --output PATH
```

`lock` writes canonical deterministic JSON and hashes source manifests and
Schemas only. `manifest` runs after checkout/build and records full
`git rev-parse HEAD`, Channel, platform, build time, lock hash, and built
Artifact hashes. This separation avoids a lock file that recursively contains
the SHA of the commit containing that same lock.

Run:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tests/conformance/version_lock_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
```

Expected:

```text
version lock conformance: PASS
version verification: PASS (1.0.6.0)
```

It runs, in order:

```text
active tree guard
Product Build and Assembly lock conformance
configure release
build release
CTest unit/integration suite
schema conformance
module graph conformance
CLI behavior fixtures
MCP lifecycle fixtures
CLI/MCP parity
Headless Core E2E
canary Build Manifest generation
git diff --check
```

It preserves failed proof artifacts under `build/core/proof-failures/<run-id>` and removes successful temporary projects.

- [ ] **Step 8: Run the proof twice from a clean build**

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
Product Build: 1.0.6.0
Channel: canary
Assembly lock: MATCH
Project pads: 64
Golden audio: MATCH
CLI/MCP state parity: MATCH
Failed attempt project mutation: NONE
Conflicted take recovery: SEALED
```

- [ ] **Step 9: Confirm the proof on both supported CI build hosts**

Update CI to run `scripts/core.sh proof` on:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest]
```

Golden WAV must match exactly because the renderer uses documented integer rules. A platform mismatch is a failing gate, not an allowed rebaseline.

- [ ] **Step 10: Update proof status documentation**

`README.md` and `products/lmdj/README.md` must distinguish:

```text
Designed: full new product/core architecture.
Implemented by this plan: Headless Core Proof only.
Not implemented: realtime audio, Web/PWA, Creator UI, Sample intelligence,
Sequence editing, Perform, Sound Sets, production Providers, cloud deployment.
```

- [ ] **Step 11: Commit the assembled proof**

```bash
git add \
  CMakeLists.txt \
  contracts/assembly/lmdj.assembly.v2.schema.json \
  docs/governance/version-management.md \
  docs/plans/2026-07-30-lmdj-headless-core-proof.md \
  products/lmdj \
  packages/application-facade/include/lmdj/facade/assembly_loader.hpp \
  packages/application-facade/include/lmdj/facade/c_api.h \
  packages/application-facade/src/application.cpp \
  packages/application-facade/src/assembly_loader.cpp \
  packages/application-facade/src/c_api.cpp \
  packages/application-facade/CMakeLists.txt \
  packages/provider-sdk/include/lmdj/provider/attempt_store.hpp \
  packages/provider-sdk/include/lmdj/provider/registry.hpp \
  packages/provider-sdk/src/attempt_store.cpp \
  packages/provider-sdk/src/registry.cpp \
  apps/core-cli/src/main.cpp \
  apps/core-mcp/lmdj_core_mcp/__main__.py \
  apps/core-mcp/lmdj_core_mcp/c_api.py \
  tests/core/facade/assembly_loader_test.cpp \
  tests/core/facade/c_api_test.cpp \
  tests/core/provider/conformance_test.cpp \
  tests/build/proof_failure_artifacts_test.py \
  tests/conformance/module_graph_test.py \
  tests/conformance/schema_contract_test.py \
  tests/conformance/version_lock_test.py \
  tests/e2e \
  tests/build/version_test.py \
  tests/host/cli_test.py \
  tests/host/mcp_stdio_test.py \
  scripts/version.py \
  scripts/core.sh \
  .github/workflows/ci.yml \
  README.md
git commit -m "feat(core): prove headless beat project end to end"
```

- [ ] **Step 12: Complete the PR 6 integration and create the immutable Product tag**

After PR 6 is squash-merged and required macOS/Ubuntu CI is green, the
Integration Owner synchronizes `main`, verifies the full merge SHA, regenerates
the Build Manifest with Channel `dev`, and creates a signed annotated tag:

```bash
merge_sha="$(git rev-parse HEAD)"
test "$(git branch --show-current)" = "main"
test "$(printf '%s' "$merge_sha" | wc -c | tr -d ' ')" = "40"
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 scripts/version.py manifest \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json \
  --channel dev \
  --artifacts-root build/core/release \
  --output build/core/release/build-manifest.json
tag_name="$(python3 scripts/version.py tag-name \
  --version-file products/lmdj/version.json)"
git tag -s "$tag_name" "$merge_sha" \
  -m "LMDJ M1 Headless Core Proof build 1.0.6.0"
git tag -v "$tag_name"
test "$(git rev-list -n 1 "$tag_name")" = "$merge_sha"
```

If signing is unavailable, stop and report the gate rather than silently
creating an unsigned Product tag. This step does not push the tag, create a
GitHub Release, promote beyond `dev`, publish, or deploy.

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
- [ ] A CLI process can exit after `snapshot.cook`; a fresh CLI process can render from Project path plus Pattern ID with no `snapshot_id`.
- [ ] Offline WAV matches independent Golden Audio on macOS and Ubuntu.
- [ ] CLI and MCP query the same Facade state.
- [ ] MCP conforms to the locked `2025-11-25` stdio lifecycle and Tools behavior.
- [ ] Provider selection stays outside the Project bundle.
- [ ] Failed Attempt changes no Project file or Project revision.
- [ ] Full proof passes twice from clean builds.
- [ ] `git diff --check` passes.
- [ ] Each task commit contains only its declared paths.
- [ ] Concurrent commits from two Host processes serialize through the bundle advisory lock; no reported-successful commit is lost.
- [ ] Strict recording conflict is documented as Proof-only and the product-level concurrency question remains open.
- [ ] Web realtime-audio latency remains explicitly outside this proof.
- [ ] Product Build is `1.0.6.0`; every Module/Host/Provider is independently
  locked at `0.1.0`; the six retained v1 Contract Schemas are locked at
  `1.0.0`, and the completed Assembly Contract is independently locked as
  `lmdj.assembly.v2` / `2.0.0`.
- [ ] Assembly lock contains no self-referential revision; generated Build
  Manifest binds its hash to the full Git revision and Channel.

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

- Redesign source of truth: `docs/design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
- MCP stdio transport: `https://modelcontextprotocol.io/specification/2025-11-25/basic/transports`
- MCP lifecycle: `https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle`
- MCP Tools: `https://modelcontextprotocol.io/specification/2025-11-25/server/tools`
- nlohmann/json 3.12.0 release: `https://github.com/nlohmann/json/releases/tag/v3.12.0`
- PicoSHA2 pinned source commit: `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29`
