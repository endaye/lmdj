// Runtime invariant harness for the Attempt ledger.
//
// Track 3 Task 1 of docs/superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md.
//
// Everything here checks relations across a *completed sequence* of
// operations, which is what separates a runtime invariant from the load-time
// validation AttemptStore::inspect already performs on a single record. The
// adopted exclusion rule is binding: anything the type system, a schema, or a
// single-call unit test already guarantees does not belong here.
//
// The harness deliberately walks the workspace itself rather than adding an
// enumerate-attempts operation to the SDK or the Facade. There is no such
// operation today, and adding product API for a test's convenience would be
// the wrong trade.

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>
#include <lmdj/providers/local_proof_failure/factory.hpp>
#include <lmdj/providers/local_proof_success/factory.hpp>

#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AttemptId;
using lmdj::foundation::ErrorCode;
using lmdj::provider::ArtifactBinding;
using lmdj::provider::AttemptStore;
using lmdj::provider::CapabilityRequest;
using lmdj::provider::ProviderPolicy;
using lmdj::provider::Registry;

constexpr std::string_view kCapability = "proof.candidate.v2";

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-ledger-invariant-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  TempDirectory(const TempDirectory&) = delete;
  TempDirectory& operator=(const TempDirectory&) = delete;

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::string read_bytes(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("failed to read test file");
  }
  return {
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
}

// ---------------------------------------------------------------------------
// The harness
// ---------------------------------------------------------------------------

// Every relation the ledger must satisfy after a completed sequence. Returns
// one string per violation so a test can assert both "no violations" and
// "exactly this violation was detected"; a bare bool would make the second
// assertion impossible to write honestly.
std::vector<std::string> ledger_violations(
    const std::filesystem::path& workspace_root) {
  std::vector<std::string> violations;
  const auto attempts = workspace_root / ".lmdj-workspace/attempts";
  if (!std::filesystem::exists(attempts)) {
    return violations;
  }

  const auto note = [&violations](
                        std::string_view id, std::string_view relation) {
    violations.push_back(std::string(id) + ": " + std::string(relation));
  };

  std::set<std::string> terminal_ids;
  std::set<std::string> reserved_ids;
  for (const auto& entry : std::filesystem::directory_iterator(attempts)) {
    const auto name = entry.path().filename().string();
    if (entry.is_directory()) {
      reserved_ids.insert(name);
    } else if (entry.path().extension() == ".json") {
      terminal_ids.insert(entry.path().stem().string());
    } else {
      note(name, "unexpected entry in the attempts root");
    }
  }

  // Relation 1: a reservation directory without a terminal record means the
  // attempt never reached a terminal state, and nothing ever reclaims it. See
  // finding G1 in the plan.
  for (const auto& reserved : reserved_ids) {
    if (!terminal_ids.contains(reserved)) {
      note(reserved, "reservation directory has no terminal record");
    }
  }

  for (const auto& id : terminal_ids) {
    const auto record_path = attempts / (id + ".json");
    const auto reservation = attempts / id;
    const auto bytes = read_bytes(record_path);
    nlohmann::json record;
    try {
      record = nlohmann::json::parse(bytes);
    } catch (const nlohmann::json::exception&) {
      note(id, "terminal record is not valid JSON");
      continue;
    }

    // Relation 2: the record is stored in canonical form with a trailing
    // newline. inspect() re-checks this on every read, so a violation here
    // means a completed write produced a state the next read would reject.
    if (bytes != lmdj::foundation::canonical_json(record) + "\n") {
      note(id, "terminal record is not canonical on disk");
    }

    if (record.value("attempt_id", std::string{}) != id) {
      note(id, "terminal record attempt_id does not match its filename");
    }
    if (record.value("format", std::string{}) != "terminal-attempt-v2") {
      note(id, "terminal record has an unexpected private format");
    }

    const auto status = record.value("status", std::string{});
    const auto& candidate_ids = record.at("candidate_ids");
    const auto& minted = record.at("minted_outputs");
    const auto& candidate_outputs = record.at("candidate_outputs");
    const auto has_error = !record.at("error").is_null();

    // Relation 3: the outcome fields agree with the status, in both
    // directions.
    if (status == "succeeded") {
      if (candidate_ids.size() != 1 || has_error) {
        note(id, "succeeded attempt has an inconsistent outcome");
      }
      // Relation 4: a succeeded attempt's candidate outputs are exactly what
      // was minted -- no fabrication, no dropped output.
      if (candidate_outputs != minted) {
        note(id, "candidate outputs do not equal minted outputs");
      }
    } else if (status == "failed") {
      if (!candidate_ids.empty() || !has_error || !minted.empty() ||
          !candidate_outputs.empty()) {
        note(id, "failed attempt has an inconsistent outcome");
      }
      // Relation 5: a failed attempt keeps no bytes and no reservation.
      if (std::filesystem::exists(reservation)) {
        note(id, "failed attempt left its reservation directory behind");
      }
    } else {
      note(id, "terminal record status is not terminal");
      continue;
    }

    // Relation 6: staging never survives a terminal attempt.
    if (std::filesystem::exists(reservation / "staging")) {
      note(id, "terminal attempt left a staging directory behind");
    }

    // Relation 7: every minted binding resolves to a real, correctly sized
    // file whose content re-hashes to the recorded digest. This is the check
    // that makes the ledger a ledger rather than a log.
    std::set<std::string> expected_files;
    for (const auto& binding : minted) {
      const auto& artifact = binding.at("artifact");
      const auto sha256 = artifact.value("sha256", std::string{});
      const auto media_type = artifact.value("media_type", std::string{});
      const auto byte_length = artifact.value("byte_length", std::uint64_t{0});
      expected_files.insert(sha256);
      const auto artifact_path = reservation / "artifacts" / sha256;
      const auto status_result = std::filesystem::symlink_status(artifact_path);
      if (!std::filesystem::exists(status_result)) {
        note(id, "minted artifact " + sha256 + " is missing on disk");
        continue;
      }
      if (std::filesystem::is_symlink(status_result) ||
          !std::filesystem::is_regular_file(status_result)) {
        note(id, "minted artifact " + sha256 + " is not a regular file");
        continue;
      }
      const auto described =
          lmdj::foundation::describe_artifact(artifact_path, media_type);
      if (!described.has_value()) {
        note(id, "minted artifact " + sha256 + " could not be described");
        continue;
      }
      if (described.value().sha256 != sha256) {
        note(id, "minted artifact " + sha256 + " does not match its content");
      }
      if (described.value().byte_length != byte_length) {
        note(id, "minted artifact " + sha256 + " has an unexpected length");
      }
    }

    // Relation 8: the artifacts directory holds nothing the ledger does not
    // account for.
    const auto artifacts_dir = reservation / "artifacts";
    if (std::filesystem::exists(artifacts_dir)) {
      for (const auto& entry :
           std::filesystem::directory_iterator(artifacts_dir)) {
        const auto name = entry.path().filename().string();
        if (!expected_files.contains(name)) {
          note(id, "unaccounted file " + name + " in the artifacts directory");
        }
      }
    }

    // Relation 9: the artifacts union is the deduplicated set of request
    // inputs plus minted outputs, and it is sorted.
    std::vector<nlohmann::json> expected_union;
    for (const auto& binding : record.at("request").at("inputs")) {
      expected_union.push_back(binding.at("artifact"));
    }
    for (const auto& binding : minted) {
      expected_union.push_back(binding.at("artifact"));
    }
    const auto artifact_less = [](const nlohmann::json& left,
                                  const nlohmann::json& right) {
      return std::tuple(
                 left.value("sha256", std::string{}),
                 left.value("media_type", std::string{}),
                 left.value("byte_length", std::uint64_t{0})) <
             std::tuple(
                 right.value("sha256", std::string{}),
                 right.value("media_type", std::string{}),
                 right.value("byte_length", std::uint64_t{0}));
    };
    std::sort(expected_union.begin(), expected_union.end(), artifact_less);
    expected_union.erase(
        std::unique(expected_union.begin(), expected_union.end()),
        expected_union.end());
    const auto recorded_union =
        record.at("artifacts").get<std::vector<nlohmann::json>>();
    if (recorded_union != expected_union) {
      note(id, "artifacts union does not equal inputs plus minted outputs");
    }

    // Relation 10: minted output digests are unique, and the bindings are in
    // canonical order.
    std::set<std::string> seen_digests;
    for (const auto& binding : minted) {
      const auto sha256 = binding.at("artifact").value("sha256", std::string{});
      if (!seen_digests.insert(sha256).second) {
        note(id, "minted outputs repeat digest " + sha256);
      }
    }
    const auto binding_less = [&artifact_less](const nlohmann::json& left,
                                               const nlohmann::json& right) {
      const auto left_port = left.value("port", std::string{});
      const auto right_port = right.value("port", std::string{});
      if (left_port != right_port) {
        return left_port < right_port;
      }
      return artifact_less(left.at("artifact"), right.at("artifact"));
    };
    for (const auto* bindings : {&minted, &candidate_outputs}) {
      const auto values = bindings->get<std::vector<nlohmann::json>>();
      if (!std::is_sorted(values.begin(), values.end(), binding_less)) {
        note(id, "bindings are not in canonical order");
      }
    }

    // Relation 11: the request's capability matches the recorded capability
    // identity, and the timestamps do not run backwards.
    if (record.at("request").value("capability", std::string{}) !=
        record.at("capability").value("id", std::string{})) {
      note(id, "request capability does not match the capability identity");
    }
    if (record.value("started_at", std::string{}) >
        record.value("ended_at", std::string{})) {
      note(id, "attempt ended before it started");
    }
  }

  // Relation 12: no temporary sibling survives a completed sequence anywhere
  // in the workspace.
  for (const auto& entry : std::filesystem::recursive_directory_iterator(
           workspace_root / ".lmdj-workspace")) {
    const auto name = entry.path().filename().string();
    if (name.starts_with(".") && name.find(".tmp.") != std::string::npos) {
      violations.push_back(name + ": temporary sibling survived the sequence");
    }
  }

  return violations;
}

void check_ledger_holds(const std::filesystem::path& workspace_root) {
  const auto violations = ledger_violations(workspace_root);
  for (const auto& violation : violations) {
    std::cerr << "ledger violation: " << violation << '\n';
  }
  LMDJ_CHECK(violations.empty());
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

Registry proof_registry() {
  Registry registry;
  LMDJ_CHECK(
      registry.add(lmdj::providers::local_proof_success_registration())
          .has_value());
  LMDJ_CHECK(
      registry.add(lmdj::providers::local_proof_failure_registration())
          .has_value());
  return registry;
}

AttemptStore store_at(const std::filesystem::path& workspace_root) {
  return AttemptStore(
      workspace_root,
      ProviderPolicy{{"local"}, {"public"}, {"proof.execute"}},
      [] { return std::string("2026-08-19T12:00:00.000Z"); });
}

CapabilityRequest valid_request() {
  return CapabilityRequest{
      std::string(kCapability),
      {
          ArtifactBinding{
              "inputs",
              ArtifactRef{
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "audio/wav",
                  12,
              },
          },
      },
      nlohmann::json::object(),
      "public",
      "test",
      "local",
      {"proof.execute"},
  };
}

void select(AttemptStore& store, const Registry& registry, std::string id) {
  LMDJ_CHECK(store
                 .set_provider_selection(
                     std::string(kCapability), std::move(id), registry)
                 .has_value());
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// A succeeded attempt leaves a coherent ledger. This is the baseline: if it
// ever fails, one of the twelve relations disagrees with the producer.
void test_succeeded_attempt_leaves_a_coherent_ledger() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");

  const auto executed =
      store.execute(AttemptId{"ledger-success"}, valid_request(), registry);
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(executed.value().candidate.has_value());

  check_ledger_holds(temp.path());
}

// A failed attempt keeps no bytes and no reservation, and the ledger still
// holds. Failure isolation is the relation under test, not the error itself.
void test_failed_attempt_leaves_a_coherent_ledger() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.failure");

  const auto executed =
      store.execute(AttemptId{"ledger-failure"}, valid_request(), registry);
  LMDJ_CHECK(executed.has_value());
  LMDJ_CHECK(!executed.value().candidate.has_value());
  LMDJ_CHECK(executed.value().error.has_value());

  const auto attempts = temp.path() / ".lmdj-workspace/attempts";
  LMDJ_CHECK(std::filesystem::exists(attempts / "ledger-failure.json"));
  LMDJ_CHECK(!std::filesystem::exists(attempts / "ledger-failure"));

  check_ledger_holds(temp.path());
}

// A sequence of attempts through both providers stays coherent. A single
// execute() cannot show interference between attempts; only a sequence can.
void test_mixed_attempt_sequence_stays_coherent() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());

  select(store, registry, "local.proof.success");
  LMDJ_CHECK(store.execute(AttemptId{"seq-a"}, valid_request(), registry)
                 .has_value());
  select(store, registry, "local.proof.failure");
  LMDJ_CHECK(store.execute(AttemptId{"seq-b"}, valid_request(), registry)
                 .has_value());
  select(store, registry, "local.proof.success");
  LMDJ_CHECK(store.execute(AttemptId{"seq-c"}, valid_request(), registry)
                 .has_value());

  const auto attempts = temp.path() / ".lmdj-workspace/attempts";
  LMDJ_CHECK(std::filesystem::exists(attempts / "seq-a.json"));
  LMDJ_CHECK(std::filesystem::exists(attempts / "seq-b.json"));
  LMDJ_CHECK(std::filesystem::exists(attempts / "seq-c.json"));

  check_ledger_holds(temp.path());
}

// The harness must detect a real violation, or its passing cases prove
// nothing. Each case below corrupts one relation and asserts the harness
// notices, so a future refactor that silently weakens a check turns this red.
void test_harness_detects_each_corruption() {
  const auto prepare = [](const TempDirectory& temp) {
    const auto registry = proof_registry();
    auto store = store_at(temp.path());
    select(store, registry, "local.proof.success");
    LMDJ_CHECK(store.execute(AttemptId{"probe"}, valid_request(), registry)
                   .has_value());
    return temp.path() / ".lmdj-workspace/attempts";
  };

  // A stray file in the artifacts directory is unaccounted for.
  {
    const TempDirectory temp;
    const auto attempts = prepare(temp);
    std::ofstream(attempts / "probe/artifacts/stray") << "x";
    LMDJ_CHECK(!ledger_violations(temp.path()).empty());
  }

  // A surviving staging directory means promotion did not complete.
  {
    const TempDirectory temp;
    const auto attempts = prepare(temp);
    std::filesystem::create_directories(attempts / "probe/staging");
    LMDJ_CHECK(!ledger_violations(temp.path()).empty());
  }

  // A missing minted artifact breaks the ledger's central claim.
  {
    const TempDirectory temp;
    const auto attempts = prepare(temp);
    std::filesystem::remove_all(attempts / "probe/artifacts");
    LMDJ_CHECK(!ledger_violations(temp.path()).empty());
  }

  // A surviving temporary sibling means a write sequence did not finish.
  {
    const TempDirectory temp;
    const auto attempts = prepare(temp);
    std::ofstream(attempts / ".probe.tmp.1.1") << "x";
    LMDJ_CHECK(!ledger_violations(temp.path()).empty());
  }

  // A non-canonical record is a state the next inspect() would reject.
  {
    const TempDirectory temp;
    const auto attempts = prepare(temp);
    const auto record = attempts / "probe.json";
    const auto decoded = nlohmann::json::parse(read_bytes(record));
    std::ofstream(record, std::ios::binary | std::ios::trunc)
        << decoded.dump(2) << "\n";
    LMDJ_CHECK(!ledger_violations(temp.path()).empty());
  }
}

// The harness should continue to flag orphan reservations, but after G1 the
// duplicate-id result now means "that reservation still exists", not "the
// product leaked and burned the id on its own failure path".
void test_orphan_reservation_is_detected_and_blocks_reuse() {
  const TempDirectory temp;
  const auto registry = proof_registry();
  auto store = store_at(temp.path());
  select(store, registry, "local.proof.success");

  // Reserve the id the way an interrupted run leaves it: a directory with no
  // terminal record beside it.
  const auto attempts = temp.path() / ".lmdj-workspace/attempts";
  std::filesystem::create_directories(attempts / "orphaned");

  // The harness sees it.
  const auto violations = ledger_violations(temp.path());
  LMDJ_CHECK(violations.size() == 1);
  LMDJ_CHECK(
      violations.front() ==
      "orphaned: reservation directory has no terminal record");

  // Retrying the same id still fails because the directory remains a live
  // reservation from the store's point of view.
  const auto retried =
      store.execute(AttemptId{"orphaned"}, valid_request(), registry);
  LMDJ_CHECK(!retried.has_value());
  LMDJ_CHECK(retried.error().code == ErrorCode::duplicate_id);
}

}  // namespace

int main() {
  try {
    test_succeeded_attempt_leaves_a_coherent_ledger();
    test_failed_attempt_leaves_a_coherent_ledger();
    test_mixed_attempt_sequence_stays_coherent();
    test_harness_detects_each_corruption();
    test_orphan_reservation_is_detected_and_blocks_reuse();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "attempt ledger invariant tests: PASS\n";
  return 0;
}
