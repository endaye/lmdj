# LMDJ Workspace Evidence Durability Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Attempt terminal records and minted artifacts with native file+directory `fsync` before success returns, while leaving `host-settings.json` on flush-and-rename.

**Architecture:** Extract POSIX durable helpers into an internal `lmdj::provider::detail` translation unit that is not a public include. `write_new_atomic` and the Attempt output sink call those helpers; `write_bytes` / `write_replace_atomic` stay `ofstream`+`rename` for Host settings. Then pay the `provider-sdk` PATCH cascade and Product Build `1.0.25.0`.

**Tech Stack:** C++20, POSIX `open`/`write`/`fsync`/`close`, existing `LMDJ_CHECK` native tests, `scripts/version.py lock`, Architecture Portal freeze.

## Global Constraints

- Spec: `docs/design/2026-08-22-workspace-evidence-durability-design.md` (Issue #203 / G2).
- Start implementation on `fix/issue-203-workspace-evidence-durability` created from this docs branch; never edit `main`.
- One implementation Conventional Commit at the end of Task 6. Do not commit intermediate TDD steps.
- Do not export a new public C++ API under `packages/provider-sdk/include/`.
- Do not depend on `project-io` or move POSIX helpers into `foundation`.
- Do not change Attempt JSON, Artifact identity, Host settings schema, or public error codes.
- Do not implement G3 lock recovery.
- Do not `#ifdef` a second Emscripten write path; call the same POSIX sequence (`fsync` is a successful no-op there).
- Do not close Issue #203, push, open a PR, merge, tag, release, deploy, or promote a Channel.
- `assembly.lock.json` only via `python3 scripts/version.py lock`; never hand-edit.
- Portal snapshot channel is `canary`.
- Tests use `LMDJ_CHECK`, not GoogleTest.

---

## File Structure

- Create `packages/provider-sdk/src/durable_file.hpp` — internal `detail` declarations (`sync_descriptor`, `sync_directory`, `write_bytes_durable`, `publish_new_link`, `publish_replace`).
- Create `packages/provider-sdk/src/durable_file.cpp` — POSIX exclusive create, write, file `fsync`, publish, directory `fsync`, fail-closed cleanup.
- Modify `packages/provider-sdk/CMakeLists.txt` — compile `durable_file.cpp` into `lmdj_provider_sdk`.
- Modify `packages/provider-sdk/src/attempt_store.cpp` — `write_new_atomic` and the output sink call durable helpers; `write_bytes` / `write_replace_atomic` unchanged.
- Create `tests/core/provider/durable_file_test.cpp` — unit coverage for sync failure mapping, durable write, publish, fail-closed cleanup.
- Modify `tests/core/provider/CMakeLists.txt` — register `provider.durable_file` as `unit`.
- Modify `tests/core/provider/spec_regression_test.cpp` — source pins that settings stay volatile and evidence uses durable helpers; persist/mint files remain inspectable.
- Modify provider-sdk / facade / host / provider manifests, Product Build identity, compiled assembly, generated lock and Runtime identity, current Portal pages, and the `1.0.25.0` canary snapshot.
- Leave `write_bytes` as the only Host-settings writer.

## Version Management

Version impact: required.

| Identity | From | To |
| --- | --- | --- |
| `provider-sdk` | 1.1.2 | 1.1.3 |
| `application-facade` | 1.4.1 | 1.4.2 |
| `core-cli` | 1.0.13 | 1.0.14 |
| `core-mcp` | 1.1.10 | 1.1.11 |
| `native-test-host` | 1.0.11 | 1.0.12 |
| `web-runtime-platform` | 0.3.1 | 0.3.2 |
| `web-runtime-host` | 1.2.10 | 1.2.11 |
| `creator-web` | 1.3.1 | 1.3.2 |
| `local.proof.success` | 1.0.3 | 1.0.4 |
| `local.proof.failure` | 1.0.3 | 1.0.4 |
| Product Build | 1.0.24.0 | 1.0.25.0 |

Contract versions: none. Public ABI/capability additions: none. PATCH because persistence reliability changes without a new public API.

## Documentation Impact

Documentation impact: required

Affected portal pages: `/core/modules/provider-sdk/` `/providers/overview/` `/product/capability-map/` `/operations/version-and-release/` `/assembly/lmdj/`

Reason: native Attempt/artifact durability is a Provider SDK lifecycle fact, and Product Build plus Assembly identities change.

---

### Task 1: Internal durable file helpers

**Files:**
- Create: `packages/provider-sdk/src/durable_file.hpp`
- Create: `packages/provider-sdk/src/durable_file.cpp`
- Modify: `packages/provider-sdk/CMakeLists.txt`
- Create: `tests/core/provider/durable_file_test.cpp`
- Modify: `tests/core/provider/CMakeLists.txt`

**Interfaces:**
- Consumes: POSIX fds, `foundation::Result<void>`, `foundation::ErrorCode::io_error` / `duplicate_id` via caller-supplied existing code.
- Produces:

```cpp
namespace lmdj::provider::detail {
foundation::Result<void> sync_descriptor(
    int descriptor, const std::filesystem::path& path);
foundation::Result<void> sync_directory(
    const std::filesystem::path& path);
foundation::Result<void> write_bytes_durable(
    const std::filesystem::path& path, std::string_view bytes);
foundation::Result<void> publish_new_link(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path,
    foundation::ErrorCode existing_code);
foundation::Result<void> publish_replace(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path);
}
```

- [ ] **Step 1: Write the failing unit tests**

Create `tests/core/provider/durable_file_test.cpp`:

```cpp
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>

#include <lmdj/foundation/error.hpp>

#include "packages/provider-sdk/src/durable_file.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ErrorCode;
using lmdj::provider::detail::publish_new_link;
using lmdj::provider::detail::publish_replace;
using lmdj::provider::detail::sync_descriptor;
using lmdj::provider::detail::sync_directory;
using lmdj::provider::detail::write_bytes_durable;

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-durable-file-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }
  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

void test_sync_descriptor_rejects_invalid_fd() {
  const auto result =
      sync_descriptor(-1, "packages/provider-sdk/src/durable_file.cpp");
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      result.error().details.at("path") ==
      "packages/provider-sdk/src/durable_file.cpp");
}

void test_sync_directory_rejects_missing_path() {
  TempDirectory temp;
  const auto missing = temp.path() / "missing";
  const auto result = sync_directory(missing);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == ErrorCode::io_error);
}

void test_write_bytes_durable_round_trips_and_rejects_existing() {
  TempDirectory temp;
  const auto path = temp.path() / "evidence.bin";
  const auto first = write_bytes_durable(path, "attempt-bytes");
  LMDJ_CHECK(first.has_value());
  LMDJ_CHECK(read_bytes(path) == "attempt-bytes");
  const auto second = write_bytes_durable(path, "other");
  LMDJ_CHECK(!second.has_value());
  LMDJ_CHECK(second.error().code == ErrorCode::io_error);
  LMDJ_CHECK(read_bytes(path) == "attempt-bytes");
}

void test_publish_new_link_syncs_then_removes_temp() {
  TempDirectory temp;
  const auto staged = temp.path() / ".record.json.tmp";
  const auto final_path = temp.path() / "record.json";
  LMDJ_CHECK(write_bytes_durable(staged, "{\"ok\":true}\n").has_value());
  LMDJ_CHECK(
      publish_new_link(
          staged, final_path, ErrorCode::duplicate_id)
          .has_value());
  LMDJ_CHECK(read_bytes(final_path) == "{\"ok\":true}\n");
  LMDJ_CHECK(!std::filesystem::exists(staged));
}

void test_publish_new_link_conflict_uses_existing_code() {
  TempDirectory temp;
  const auto staged = temp.path() / ".record.json.tmp";
  const auto final_path = temp.path() / "record.json";
  LMDJ_CHECK(write_bytes_durable(staged, "left\n").has_value());
  LMDJ_CHECK(write_bytes_durable(final_path, "right\n").has_value());
  const auto published = publish_new_link(
      staged, final_path, ErrorCode::duplicate_id);
  LMDJ_CHECK(!published.has_value());
  LMDJ_CHECK(published.error().code == ErrorCode::duplicate_id);
  LMDJ_CHECK(!std::filesystem::exists(staged));
  LMDJ_CHECK(read_bytes(final_path) == "right\n");
}

void test_publish_replace_replaces_and_removes_temp() {
  TempDirectory temp;
  const auto staged = temp.path() / ".artifact.tmp";
  const auto final_path = temp.path() / "deadbeef";
  LMDJ_CHECK(write_bytes_durable(final_path, "old").has_value());
  LMDJ_CHECK(write_bytes_durable(staged, "new-bytes").has_value());
  LMDJ_CHECK(publish_replace(staged, final_path).has_value());
  LMDJ_CHECK(read_bytes(final_path) == "new-bytes");
  LMDJ_CHECK(!std::filesystem::exists(staged));
}

}  // namespace

int main() {
  try {
    test_sync_descriptor_rejects_invalid_fd();
    test_sync_directory_rejects_missing_path();
    test_write_bytes_durable_round_trips_and_rejects_existing();
    test_publish_new_link_syncs_then_removes_temp();
    test_publish_new_link_conflict_uses_existing_code();
    test_publish_replace_replaces_and_removes_temp();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "provider durable file tests: PASS\n";
  return 0;
}
```

Register in `tests/core/provider/CMakeLists.txt` immediately after the `Threads REQUIRED` block:

```cmake
  add_executable(
    lmdj_provider_durable_file_tests
    durable_file_test.cpp
  )
  target_include_directories(
    lmdj_provider_durable_file_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_durable_file_tests
    PRIVATE
      lmdj::provider_sdk
  )
  lmdj_target_warnings(lmdj_provider_durable_file_tests)
  lmdj_target_sanitizers(lmdj_provider_durable_file_tests)
  lmdj_add_test(
    NAME provider.durable_file
    TIER unit
    COMMAND lmdj_provider_durable_file_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider persistence
  )
```

- [ ] **Step 2: Confirm the tests fail to compile or link**

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
```

Expected: build fails because `packages/provider-sdk/src/durable_file.hpp` does not exist.

- [ ] **Step 3: Implement the internal helpers**

`packages/provider-sdk/src/durable_file.hpp`:

```cpp
#pragma once

#include <filesystem>
#include <string_view>

#include <lmdj/foundation/error.hpp>

namespace lmdj::provider::detail {

foundation::Result<void> sync_descriptor(
    int descriptor,
    const std::filesystem::path& path);

foundation::Result<void> sync_directory(
    const std::filesystem::path& path);

foundation::Result<void> write_bytes_durable(
    const std::filesystem::path& path,
    std::string_view bytes);

foundation::Result<void> publish_new_link(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path,
    foundation::ErrorCode existing_code);

foundation::Result<void> publish_replace(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path);

}  // namespace lmdj::provider::detail
```

`packages/provider-sdk/src/durable_file.cpp` (complete):

```cpp
#include "durable_file.hpp"

#include <cerrno>
#include <cstddef>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>
#include <system_error>
#include <utility>

#include <nlohmann/json.hpp>

namespace lmdj::provider::detail {
namespace {

using foundation::Error;
using foundation::ErrorCode;

Error io_error(
    std::string message,
    const std::filesystem::path& path,
    const std::error_code& system_error = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (system_error) {
    details["system_error"] = system_error.message();
  }
  return Error{
      ErrorCode::io_error,
      std::move(message),
      std::move(details),
  };
}

std::error_code last_system_error() {
  return {errno, std::system_category()};
}

class UniqueFd {
 public:
  explicit UniqueFd(int descriptor) : descriptor_(descriptor) {}
  UniqueFd(const UniqueFd&) = delete;
  UniqueFd& operator=(const UniqueFd&) = delete;
  UniqueFd(UniqueFd&& other) noexcept : descriptor_(other.descriptor_) {
    other.descriptor_ = -1;
  }
  UniqueFd& operator=(UniqueFd&& other) noexcept {
    if (this != &other) {
      close();
      descriptor_ = other.descriptor_;
      other.descriptor_ = -1;
    }
    return *this;
  }
  ~UniqueFd() { close(); }

  int get() const { return descriptor_; }

 private:
  void close() {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }
  int descriptor_ = -1;
};

void remove_quietly(const std::filesystem::path& path) {
  std::error_code error;
  std::filesystem::remove(path, error);
}

}  // namespace

foundation::Result<void> sync_descriptor(
    int descriptor,
    const std::filesystem::path& path) {
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        io_error("storage bytes could not be flushed", path, last_system_error()));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> sync_directory(
    const std::filesystem::path& path) {
  UniqueFd directory{::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC)};
  if (directory.get() < 0) {
    return foundation::Result<void>::failure(
        io_error(
            "storage directory could not be opened",
            path,
            last_system_error()));
  }
  return sync_descriptor(directory.get(), path);
}

foundation::Result<void> write_bytes_durable(
    const std::filesystem::path& path,
    std::string_view bytes) {
  UniqueFd file{::open(
      path.c_str(),
      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH)};
  if (file.get() < 0) {
    return foundation::Result<void>::failure(
        io_error("temporary file could not be opened", path, last_system_error()));
  }
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto written = ::write(
        file.get(), bytes.data() + offset, bytes.size() - offset);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      const auto error = last_system_error();
      remove_quietly(path);
      return foundation::Result<void>::failure(
          io_error("temporary file could not be written", path, error));
    }
    if (written == 0) {
      remove_quietly(path);
      return foundation::Result<void>::failure(
          io_error("temporary file could not be written", path));
    }
    offset += static_cast<std::size_t>(written);
  }
  const auto synced = sync_descriptor(file.get(), path);
  if (!synced.has_value()) {
    remove_quietly(path);
    return synced;
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> publish_new_link(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path,
    foundation::ErrorCode existing_code) {
  std::error_code publish_error;
  std::filesystem::create_hard_link(temp_path, final_path, publish_error);
  if (publish_error) {
    remove_quietly(temp_path);
    std::error_code final_status_error;
    const auto final_status =
        std::filesystem::symlink_status(final_path, final_status_error);
    if (!final_status_error &&
        final_status.type() != std::filesystem::file_type::not_found) {
      return foundation::Result<void>::failure(
          Error{
              existing_code,
              "destination already exists",
              {{"path", final_path.generic_string()}},
          });
    }
    return foundation::Result<void>::failure(
        io_error(
            "temporary file could not be published",
            final_path,
            publish_error));
  }
  const auto synced = sync_directory(final_path.parent_path());
  if (!synced.has_value()) {
    remove_quietly(final_path);
    remove_quietly(temp_path);
    return synced;
  }
  remove_quietly(temp_path);
  return foundation::Result<void>::success();
}

foundation::Result<void> publish_replace(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path) {
  std::error_code rename_error;
  std::filesystem::rename(temp_path, final_path, rename_error);
  if (rename_error) {
    remove_quietly(temp_path);
    return foundation::Result<void>::failure(
        io_error(
            "output artifact could not be published",
            final_path,
            rename_error));
  }
  const auto synced = sync_directory(final_path.parent_path());
  if (!synced.has_value()) {
    remove_quietly(final_path);
    return synced;
  }
  return foundation::Result<void>::success();
}

}  // namespace lmdj::provider::detail
```

Add `src/durable_file.cpp` to `add_library(lmdj_provider_sdk ...)` in `packages/provider-sdk/CMakeLists.txt`.

- [ ] **Step 4: Run the unit tests**

```bash
scripts/core.sh build dev
ctest --preset dev -R '^provider\.durable_file$' --output-on-failure
```

Expected: `provider.durable_file` PASS and `provider durable file tests: PASS`.

---

### Task 2: Durable Attempt records and artifact minting

**Files:**
- Modify: `packages/provider-sdk/src/attempt_store.cpp`
- Modify: `tests/core/provider/spec_regression_test.cpp`

**Interfaces:**
- Consumes: `write_bytes_durable`, `publish_new_link`, `publish_replace` from Task 1.
- Produces: `write_new_atomic` and the Attempt output sink on the durable path; `write_bytes` / `write_replace_atomic` unchanged.

- [ ] **Step 1: Add the failing source-pin tests first**

In `tests/core/provider/spec_regression_test.cpp`, add `#include <lmdj/foundation/artifact.hpp>` is already present. Add:

```cpp
void test_evidence_writes_are_durable_and_host_settings_are_not() {
  const auto store_source =
      read_bytes("packages/provider-sdk/src/attempt_store.cpp");
  const auto durable_source =
      read_bytes("packages/provider-sdk/src/durable_file.cpp");
  LMDJ_CHECK(durable_source.find("::fsync") != std::string::npos);

  const auto write_bytes_at =
      store_source.find("foundation::Result<void> write_bytes(");
  const auto write_new_at =
      store_source.find("foundation::Result<void> write_new_atomic(");
  const auto write_replace_at =
      store_source.find("foundation::Result<void> write_replace_atomic(");
  const auto read_settings_at =
      store_source.find("foundation::Result<nlohmann::json> read_host_settings(");
  LMDJ_CHECK(write_bytes_at != std::string::npos);
  LMDJ_CHECK(write_new_at > write_bytes_at);
  LMDJ_CHECK(write_replace_at > write_new_at);
  LMDJ_CHECK(read_settings_at > write_replace_at);

  const auto write_bytes_body =
      store_source.substr(write_bytes_at, write_new_at - write_bytes_at);
  LMDJ_CHECK(write_bytes_body.find("fsync") == std::string::npos);
  LMDJ_CHECK(
      write_bytes_body.find("write_bytes_durable") == std::string::npos);

  const auto write_new_body =
      store_source.substr(write_new_at, write_replace_at - write_new_at);
  LMDJ_CHECK(
      write_new_body.find("write_bytes_durable") != std::string::npos);
  LMDJ_CHECK(
      write_new_body.find("publish_new_link") != std::string::npos);
  LMDJ_CHECK(write_new_body.find("write_bytes(") == std::string::npos);

  const auto write_replace_body = store_source.substr(
      write_replace_at, read_settings_at - write_replace_at);
  LMDJ_CHECK(write_replace_body.find("write_bytes(") != std::string::npos);
  LMDJ_CHECK(
      write_replace_body.find("write_bytes_durable") == std::string::npos);
  LMDJ_CHECK(write_replace_body.find("fsync") == std::string::npos);

  LMDJ_CHECK(
      store_source.find(
          "std::ofstream stream(\n          temp_path") ==
      std::string::npos);
  LMDJ_CHECK(
      store_source.find("publish_replace") != std::string::npos);
}

void test_successful_proof_attempt_leaves_inspectable_terminal_record() {
  TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  LMDJ_CHECK(
      store
          .set_provider_selection(
              std::string(kCapability),
              "local.proof.success",
              registry)
          .has_value());
  const auto result = store.execute(
      AttemptId{"attempt-durable-success"}, proof_request(), registry);
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(result.value().candidate.has_value());
  const auto record_path =
      temp.path() / ".lmdj-workspace/attempts/attempt-durable-success.json";
  LMDJ_CHECK(std::filesystem::is_regular_file(record_path));
  const auto inspected =
      store.inspect(AttemptId{"attempt-durable-success"});
  LMDJ_CHECK(inspected.has_value());
  LMDJ_CHECK(inspected.value().status == AttemptStatus::succeeded);
  LMDJ_CHECK(!inspected.value().minted_outputs.empty());
  const auto artifact_path =
      temp.path() / ".lmdj-workspace/attempts/attempt-durable-success" /
      "artifacts" / inspected.value().minted_outputs.front().artifact.sha256;
  LMDJ_CHECK(std::filesystem::is_regular_file(artifact_path));
}
```

Call both from `main()` before the closing of the `try` block. `TerminalAttempt::minted_outputs` is the inspect field. Successful execute publishes `staging/artifacts/` to `attempts/<id>/artifacts/` before persist, so the sha256 path above is the post-publish location.

- [ ] **Step 2: Run spec regression and confirm the source pins fail**

```bash
scripts/core.sh build dev
ctest --preset dev -R '^provider\.spec_regression$' --output-on-failure
```

Expected: FAIL on `write_bytes_durable` / `publish_new_link` / missing `ofstream` sink.

- [ ] **Step 3: Wire Attempt persistence**

At the top of `attempt_store.cpp` add:

```cpp
#include "durable_file.hpp"
```

Replace the body of `write_new_atomic` after the temp-path availability check with:

```cpp
  const auto written =
      detail::write_bytes_durable(temp_path, bytes);
  if (!written.has_value()) {
    return written;
  }
  return detail::publish_new_link(temp_path, final_path, existing_code);
```

Do not change `write_bytes` or `write_replace_atomic`.

- [ ] **Step 4: Wire the artifact sink**

In the output-sink lambda, delete the `std::ofstream stream(temp_path, ...)` write/flush/close block. After `temporary_sibling(...)` succeeds, write:

```cpp
      const std::string_view payload{
          reinterpret_cast<const char*>(bytes.data()),
          bytes.size(),
      };
      const auto written =
          detail::write_bytes_durable(temp_path, payload);
      if (!written.has_value()) {
        return foundation::Result<ArtifactRef>::failure(written.error());
      }
```

Keep `describe_artifact` on `temp_path`. When the destination is absent, replace `std::filesystem::rename` with:

```cpp
        const auto published =
            detail::publish_replace(temp_path, final_path);
        if (!published.has_value()) {
          return foundation::Result<ArtifactRef>::failure(published.error());
        }
```

When the destination already matches, keep deleting `temp_path` and do not publish.

In `publish_attempt_outputs`, after `rename(staged_artifacts, final_artifacts)` succeeds and before removing `staging/`, call `detail::sync_directory(attempt_root)`. If that fails, return the `io_error`; `execute` already `remove_tree`s the reservation on publish failure.

- [ ] **Step 5: Re-run provider tests**

```bash
scripts/core.sh build dev
ctest --preset dev -R '^provider\.(durable_file|spec_regression|attempt_isolation|attempt_ledger_invariant|host_settings_invariant|conformance)$' --output-on-failure
```

Expected: all listed tests PASS. If the success-path artifact assertion used the wrong relative directory, fix the test to the path `inspect` actually records; do not change publication layout.

---

### Task 3: Version cascade, current Portal, canary snapshot

**Files:**
- Modify: `packages/provider-sdk/module.json` (`1.1.2` → `1.1.3`)
- Modify: `packages/application-facade/module.json` (module `1.4.1` → `1.4.2`, dep `provider-sdk` `1.1.3`)
- Modify: `apps/core-cli/module.json` (`1.0.13` → `1.0.14`, dep facade `1.4.2`)
- Modify: `apps/core-mcp/module.json`, `apps/core-mcp/pyproject.toml`, `apps/core-mcp/lmdj_core_mcp/__init__.py` (`1.1.10` → `1.1.11`, dep facade `1.4.2`)
- Modify: `apps/native-test-host/module.json` and any baked version literal in `apps/native-test-host/src/main.cpp` (`1.0.11` → `1.0.12`, dep facade `1.4.2`)
- Modify: `packages/web-runtime-platform/module.json` (`0.3.1` → `0.3.2`, dep facade `1.4.2`)
- Modify: `apps/web-runtime-host/module.json` (`1.2.10` → `1.2.11`, dep platform `0.3.2`)
- Modify: `apps/creator-web/module.json`, `apps/creator-web/package.json`, `apps/creator-web/package-lock.json` (`1.3.1` → `1.3.2`, dep platform `0.3.2`)
- Modify: `providers/local-proof-success/module.json` plus version literals in `src/provider.cpp` and `CMakeLists.txt` (`1.0.3` → `1.0.4`, dep `provider-sdk` `1.1.3`)
- Modify: `providers/local-proof-failure/module.json` plus the same two files (`1.0.3` → `1.0.4`, dep `provider-sdk` `1.1.3`)
- Modify: `products/lmdj/version.json` (`build` `24` → `25`)
- Modify: `products/lmdj/assembly.json` to the table in Version Management
- Modify: `products/lmdj/src/compiled_assembly.cpp` so it is byte-final **before** lock generation
- Modify: `products/lmdj/CMakeLists.txt` if it pins Host versions
- Modify: current Portal MDX listed in Documentation Impact (additive `1.0.25.0` prose only; do not rewrite `1.0.24.0` evidence)
- Generate: `products/lmdj/assembly.lock.json`, `products/lmdj/generated/web-runtime-identity.json`, `products/lmdj/generated/web-runtime-identity.mjs`
- Generate: Architecture Portal snapshot for `1.0.25.0` / `canary`
- Modify: every remaining gate that still pins the old identities (grep the from-column of the version table)

**Interfaces:**
- Consumes: behavioral durability from Tasks 1–2.
- Produces: consistent Product Build `1.0.25.0` assembly and current+frozen Portal facts.

- [ ] **Step 1: Apply the version table**

Edit manifests and identity literals to the Version Management table. Keep `products/lmdj/src/compiled_assembly.cpp` matching `assembly.json` before the lock command.

- [ ] **Step 2: Regenerate derived identity**

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --check
```

Expected: verify and `--check` exit 0.

- [ ] **Step 3: Update current Portal prose**

In `/core/modules/provider-sdk/` section 6, state that native terminal Attempt JSON and minted artifact bytes `fsync` the file and parent directory before success; `host-settings.json` stays flush-and-rename and missing selection remains `PROVIDER_NOT_FOUND`. G3 is still open.

In `/providers/overview/` 状态归属, add that Attempt evidence is native-durable; Web MEMFS still cannot run Providers.

In `/product/capability-map/`, `/operations/version-and-release/`, and `/assembly/lmdj/`, add a `1.0.25.0` sentence that this allocation is the G2 evidence-durability cascade, not a new product capability. Leave `1.0.24.0` sentences in place.

- [ ] **Step 4: Grep leftover pins**

```bash
rg -n '1\.1\.2|1\.4\.1|1\.0\.13|1\.1\.10|1\.0\.11|0\.3\.1|1\.2\.10|1\.3\.1|1\.0\.3|1\.0\.24\.0' \
  packages apps products tests
```

Update only assertions and baked identities that mean *current* Product/module versions. Do not rewrite historical plans, evidence, or immutable older snapshots.

- [ ] **Step 5: Freeze the canary snapshot**

```bash
scripts/architecture-portal.sh version 1.0.25.0 canary
scripts/architecture-portal.sh check
```

Expected: freeze prints `portal version: froze 1.0.25.0 (canary) at <HEAD>` and `check` exits 0. The recorded revision is the current branch HEAD (the docs commits). That is the existing freeze-before-implementation-commit pattern; do not add a second snapshot commit.

---

### Task 4: Full verification and the single implementation commit

**Files:**
- Stage only files that belong to this Task (durability sources/tests, version cascade, current Portal pages, generated identities, `1.0.25.0` snapshot). Do not stage unrelated worktree dirt.

**Interfaces:**
- Consumes: Tasks 1–3 complete on `fix/issue-203-workspace-evidence-durability`.
- Produces: one Conventional Commit. Final report must say real power-loss was not tested and G3 remains open.

- [ ] **Step 1: Create the fix branch if still on the docs branch**

```bash
git checkout -b fix/issue-203-workspace-evidence-durability
```

Only if `git branch --show-current` is not already that name.

- [ ] **Step 2: Run verification**

```bash
scripts/core.sh test dev full
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
python3 scripts/version.py verify \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --lock products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --check
scripts/architecture-portal.sh check
scripts/core.sh proof
```

Expected: all exit 0; proof reports `Assembly lock: MATCH`.

Stress is not required: this Task does not change lock-free audio paths.

- [ ] **Step 3: Inspect and commit**

Confirm the branch is not `main`. Stage the Task files. Run `git diff --cached --check`. Commit:

```bash
git commit -m "$(cat <<'EOF'
fix(provider-sdk): fsync attempt evidence writes

Persist Attempt records and minted artifacts with native file and
directory fsync. Leave host-settings on flush-and-rename. Cascade
provider-sdk 1.1.3 and Product Build 1.0.25.0.

Issue #203
EOF
)"
```

Inspect the committed file list and `git status`. Do not push.

---

## Spec coverage

| Spec section | Task |
| --- | --- |
| Evidence fsync + directory fsync | 1–2 |
| Host settings stay volatile | 2 source pins |
| No project-io / no public API | 1 internal header |
| No second Emscripten path | 1 POSIX-only helpers |
| Fail-closed publish | 1 `publish_*` cleanup |
| Native tests, no power-loss claim | 1–2, 4 report |
| Version cascade `1.0.25.0` | 3 |
| Portal pages + canary snapshot | 3 |
| G3 out of scope / Issue stays open | Global Constraints, Task 4 message |
