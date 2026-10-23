#include <algorithm>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <vector>

#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/sequence_journal.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using foundation::ErrorCode;
using foundation::Result;
using project_io::ProjectStoragePlatform;
using project_io::ProjectStore;
using project_io::ProjectWriterLease;
constexpr auto kProject = "00000000-0000-4000-8000-000000000001";
constexpr auto kPerformance = "10000000-0000-4000-8000-000000000001";
constexpr auto kSession = "20000000-0000-4000-8000-000000000001";
constexpr auto kBegin = "30000000-0000-4000-8000-000000000001";
constexpr auto kSave = "30000000-0000-4000-8000-000000000002";
constexpr auto kStop = "30000000-0000-4000-8000-000000000003";
// Independent literal SHA-256 of 2097169 bytes (two 1 MiB windows plus 17)
// repeating a,b,NUL,FF,c,d,x,y.
// The verifier checks raw identity, not RIFF encoding; preserve that contract.
const foundation::ArtifactRef kArtifact{
    "766a883d0da35388bacc197ea8d30667d5e1708f829e8a426f7b32fdec332447",
    "audio/wav", 2097169};
constexpr std::array kPattern{'a', 'b', '\0', '\xff', 'c', 'd', 'x', 'y'};

class TempDirectory {
 public:
  TempDirectory() : path_(std::filesystem::temp_directory_path() /
      ("lmdj-recording-verify-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))) {
    std::filesystem::create_directories(path_);
  }
  ~TempDirectory() { std::error_code error; std::filesystem::remove_all(path_, error); }
  const std::filesystem::path& path() const { return path_; }
 private:
  std::filesystem::path path_;
};

class ObservedLease final : public ProjectWriterLease {
 public:
  ObservedLease(std::unique_ptr<ProjectWriterLease> actual, int& count)
      : actual_(std::move(actual)), count_(count) { ++count_; }
  ~ObservedLease() override { actual_.reset(); --count_; }
 private:
  std::unique_ptr<ProjectWriterLease> actual_;
  int& count_;
};

// A genuine legacy platform has no range companion. Observe the real Native
// boundary rather than replacing the Store with a stub that agrees with it.
class ForwardStorage : public ProjectStoragePlatform {
 public:
  explicit ForwardStorage(const std::filesystem::path& root)
      : actual(project_io::make_native_project_storage_platform(root)) {}
  Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    auto lease = actual->acquire_writer(p);
    if (!lease.has_value()) return Result<std::unique_ptr<ProjectWriterLease>>::failure(lease.error());
    return Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<ObservedLease>(std::move(lease.value()), live_leases));
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { return actual->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return actual->exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override {
    if (p.parent_path().filename() == "assets") {
      LMDJ_CHECK(live_leases > 0);
      if (wrong_length) return Result<std::uint64_t>::success(kArtifact.byte_length + 1);
    }
    return actual->byte_length(p);
  }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    if (p.parent_path().filename() == "assets") {
      LMDJ_CHECK(live_leases > 0);
      ++complete_audio_reads;
      if (forbid_complete_audio) return Result<std::vector<std::byte>>::failure(
          {ErrorCode::io_error, "complete audio reads are forbidden by bounded verification oracle"});
    }
    return actual->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { return actual->create_immutable(p,b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override { return actual->replace_complete(p,b); }
  Result<void> append_durable(const std::filesystem::path& p, std::uint64_t n, std::span<const std::byte> b) override { return actual->append_durable(p,n,b); }
  Result<void> remove(const std::filesystem::path& p) override { return actual->remove(p); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return actual->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return actual->list_directories(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return actual->directory_exists(p); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return actual->validate_managed_tree(p); }
  Result<void> remove_tree(const std::filesystem::path& p) override { return actual->remove_tree(p); }
  Result<void> publish_directory_if_absent(const std::filesystem::path& a, const std::filesystem::path& b) override { return actual->publish_directory_if_absent(a,b); }
  std::shared_ptr<ProjectStoragePlatform> actual;
  int live_leases = 0;
  bool forbid_complete_audio = true, wrong_length = false;
  mutable unsigned complete_audio_reads = 0;
};

enum class Fault { none, read, zero, oversized, grow, extra };
class RangeStorage final : public ForwardStorage, public project_io::ProjectStorageRangeReader {
 public:
  using ForwardStorage::ForwardStorage;
  Result<std::size_t> read_range(const std::filesystem::path& p, std::uint64_t offset,
                               std::span<std::byte> output) const override {
    LMDJ_CHECK(live_leases > 0);
    LMDJ_CHECK(output.size() <= 1048576);
    ++range_reads;
    maximum_request = std::max(maximum_request, output.size());
    if (fault == Fault::read && offset >= 1048576) return Result<std::size_t>::failure(
        {ErrorCode::io_error, "injected range read error"});
    if (fault == Fault::zero) return Result<std::size_t>::success(0);
    if (fault == Fault::oversized) return Result<std::size_t>::success(output.size() + 1);
    if (fault == Fault::extra && offset == kArtifact.byte_length) {
      output.front() = std::byte{1};
      return Result<std::size_t>::success(1);
    }
    const auto* reader = dynamic_cast<const project_io::ProjectStorageRangeReader*>(actual.get());
    LMDJ_CHECK(reader != nullptr);
    auto result = reader->read_range(p, offset, output.first(std::min(output.size(), short_limit)));
    if (result.has_value()) {
      total_read += result.value();
      if (fault == Fault::grow && offset == 0)
        std::filesystem::resize_file(p, kArtifact.byte_length + 1);
    }
    return result;
  }
  Fault fault = Fault::none;
  std::size_t short_limit = std::numeric_limits<std::size_t>::max();
  mutable unsigned range_reads = 0;
  mutable std::size_t maximum_request = 0;
  mutable std::uint64_t total_read = 0;
};

struct Fixture {
  TempDirectory temp;
  std::filesystem::path bundle = temp.path() / "recorded.lmdj";
  std::shared_ptr<ForwardStorage> platform;
  ProjectStore store;
  bool draft;
  explicit Fixture(bool is_draft = true, bool ranges = true)
      : platform(ranges ? std::static_pointer_cast<ForwardStorage>(std::make_shared<RangeStorage>(temp.path()/"metadata"))
                        : std::make_shared<ForwardStorage>(temp.path()/"metadata")),
        store(platform), draft(is_draft) {
    auto project = domain::create_project(foundation::ProjectId{kProject},120);
    LMDJ_CHECK(project.has_value());
    project.value().contract = domain::ProjectContract::v4;
    LMDJ_CHECK(store.create(bundle, project.value()).has_value());
    if (draft) {
      LMDJ_CHECK(store.begin_performance_draft(bundle,
          {{foundation::CommandId{kBegin},0},foundation::SequenceSessionId{kSession},domain::PerformanceId{kPerformance}}).has_value());
      LMDJ_CHECK(store.stop_performance_session(bundle,
          foundation::SequenceSessionId{kSession},foundation::CommandId{kStop}).has_value());
    } else LMDJ_CHECK(store.create_performance(bundle,
        {{foundation::CommandId{kBegin},0},domain::PerformanceId{kPerformance},"saved"}).has_value());
    std::ofstream output(path(), std::ios::binary);
    for (std::uint64_t n = 0; n < kArtifact.byte_length; ++n) output.put(kPattern[n % kPattern.size()]);
    output.close();
    LMDJ_CHECK(output.good());
  }
  std::filesystem::path path() const { return bundle/"assets"/(kArtifact.sha256+".wav"); }
  RangeStorage& ranges() { auto* value = dynamic_cast<RangeStorage*>(platform.get()); LMDJ_CHECK(value); return *value; }
  auto commit(const foundation::ArtifactRef& artifact = kArtifact) {
    return draft ? store.save_performance_draft(bundle,{foundation::CommandId{kSave},1},
                      domain::PerformanceId{kPerformance},"saved",artifact)
                 : store.bind_performance_recording(bundle,{foundation::CommandId{kSave},1},
                      domain::PerformanceId{kPerformance},artifact);
  }
  void check_failed_admission() {
    const auto result = commit();
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == ErrorCode::missing_asset);
    LMDJ_CHECK(result.error().details.at("reason") == "performance_recording_artifact_unverified");
    const auto truth = store.load(bundle);
    LMDJ_CHECK(truth.has_value());
    LMDJ_CHECK(truth.value().revision == 1);
    LMDJ_CHECK(!truth.value().performances.at(domain::PerformanceId{kPerformance}).recording_artifact);
    if (draft) {
      auto active = project_io::SequenceJournal{platform}.read_active_performance(bundle);
      LMDJ_CHECK(active.has_value());
      LMDJ_CHECK(active.value().state == project_io::SequenceSessionState::stopped);
    }
  }
};

void bounded_save_and_bind_reopen_with_exact_identity() {
  for (bool draft : {true, false}) {
    Fixture f(draft);
    const auto result = f.commit();
    // Original verifier fails here: read_complete is rejected by the real
    // platform observer. A positive commit and exact persisted identity are
    // independent of the byte-count/maximum-request checks below.
    LMDJ_CHECK(result.has_value());
    LMDJ_CHECK(result.value().committed_revision == 2);
    LMDJ_CHECK(f.platform->complete_audio_reads == 0);
    LMDJ_CHECK(f.ranges().maximum_request == 1048576);
    LMDJ_CHECK(f.ranges().total_read == kArtifact.byte_length);
    LMDJ_CHECK(f.ranges().range_reads == 4); // three windows plus EOF
    ProjectStore reopened(f.platform);
    const auto truth = reopened.load(f.bundle);
    LMDJ_CHECK(truth.has_value());
    LMDJ_CHECK(truth.value().revision == 2);
    LMDJ_CHECK(truth.value().performances.at(domain::PerformanceId{kPerformance}).recording_artifact == kArtifact);
    LMDJ_CHECK(f.commit().has_value());
    LMDJ_CHECK(reopened.load(f.bundle).value().revision == 2);
  }
}

void short_reads_continue_to_the_full_digest() {
  Fixture f;
  f.ranges().short_limit = 97;
  LMDJ_CHECK(f.commit().has_value());
  LMDJ_CHECK(f.ranges().total_read == kArtifact.byte_length);
  LMDJ_CHECK(f.ranges().range_reads > 1000);
}

void range_failures_never_fall_back_or_publish() {
  for (bool draft : {true, false}) for (auto fault : {Fault::read, Fault::zero, Fault::oversized, Fault::grow, Fault::extra}) {
    Fixture f(draft);
    f.ranges().fault = fault;
    f.check_failed_admission();
    LMDJ_CHECK(f.platform->complete_audio_reads == 0);
  }
}

void wrong_length_fails_before_reading_audio() {
  Fixture f;
  f.platform->wrong_length = true;
  f.check_failed_admission();
  LMDJ_CHECK(f.ranges().range_reads == 0);
}

void tail_corruption_and_truncation_are_not_published() {
  for (bool truncate : {false, true}) {
    Fixture f;
    if (truncate) std::filesystem::resize_file(f.path(), kArtifact.byte_length - 1);
    else {
      std::fstream output(f.path(), std::ios::binary | std::ios::in | std::ios::out);
      output.seekp(-1, std::ios::end); output.put('!');
    }
    f.check_failed_admission();
  }
}

void empty_raw_identity_preserves_the_existing_contract() {
  Fixture f;
  const foundation::ArtifactRef empty{
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "audio/wav",0};
  const auto path = f.bundle/"assets"/(empty.sha256+".wav");
  std::ofstream output(path, std::ios::binary);output.close();
  LMDJ_CHECK(f.commit(empty).has_value());
  LMDJ_CHECK(f.ranges().total_read == 0);
  LMDJ_CHECK(f.ranges().range_reads == 1);
}

void legacy_platform_without_companion_keeps_complete_read_behavior() {
  for (bool draft : {true, false}) {
    Fixture f(draft, false);
    f.platform->forbid_complete_audio = false;
    LMDJ_CHECK(f.commit().has_value());
    LMDJ_CHECK(f.platform->complete_audio_reads == 1);
  }
}
} // namespace

int main() {
  try {
    bounded_save_and_bind_reopen_with_exact_identity();
    short_reads_continue_to_the_full_digest();
    range_failures_never_fall_back_or_publish();
    wrong_length_fails_before_reading_audio();
    tail_corruption_and_truncation_are_not_published();
    empty_raw_identity_preserves_the_existing_contract();
    legacy_platform_without_companion_keeps_complete_read_behavior();
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
  return 0;
}
