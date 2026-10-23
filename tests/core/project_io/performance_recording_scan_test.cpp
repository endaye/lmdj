#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <tuple>
#include <vector>

#include <lmdj/project_io/project_store.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using foundation::Result;
using foundation::ErrorCode;
using project_io::ProjectStoragePlatform;
using project_io::ProjectWriterLease;
using project_io::ProjectStore;
using project_io::PerformanceRecordingSelector;
constexpr auto kProject = "00000000-0000-4000-8000-000000000001";
constexpr auto kPerformance = "10000000-0000-4000-8000-000000000001";
constexpr auto kOther = "10000000-0000-4000-8000-000000000002";
// Independent literal SHA-256 of 2097169 bytes (two 1 MiB windows plus 17).
constexpr auto kDigest = "766a883d0da35388bacc197ea8d30667d5e1708f829e8a426f7b32fdec332447";
constexpr std::array kPattern{std::byte{97}, std::byte{98}, std::byte{0}, std::byte{255},
                              std::byte{99}, std::byte{100}, std::byte{120}, std::byte{121}};

class TempDirectory {
 public:
  TempDirectory() : path_(std::filesystem::temp_directory_path() /
      ("lmdj-recording-scan-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))) {
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

// Observe the real Native boundary. This also remains a genuine legacy
// platform with no optional range companion for the unavailable-capability case.
class ForwardStorage : public ProjectStoragePlatform {
 public:
  explicit ForwardStorage(const std::filesystem::path& root)
      : actual(project_io::make_native_project_storage_platform(root)) {}
  Result<std::unique_ptr<ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    auto lease = actual->acquire_writer(p);
    if (!lease.has_value()) return Result<std::unique_ptr<ProjectWriterLease>>::failure(lease.error());
    ++acquisitions;
    return Result<std::unique_ptr<ProjectWriterLease>>::success(
        std::make_unique<ObservedLease>(std::move(lease.value()), live_leases));
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { ++writes; return actual->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { return actual->exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override {
    if (observe && p.parent_path().filename() == "assets") {
      LMDJ_CHECK(live_leases > 0);
      if (reported_length) return Result<std::uint64_t>::success(*reported_length);
    }
    return actual->byte_length(p);
  }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    if (observe) {
      LMDJ_CHECK(live_leases > 0);
      complete_reads.push_back(p);
      if (p.parent_path().filename() == "assets") return Result<std::vector<std::byte>>::failure(
          {ErrorCode::io_error, "whole audio read forbidden by scan observer"});
    }
    return actual->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return actual->create_immutable(p,b); }
  Result<void> replace_complete(const std::filesystem::path& p, std::span<const std::byte> b) override { ++writes; return actual->replace_complete(p,b); }
  Result<void> append_durable(const std::filesystem::path& p, std::uint64_t n, std::span<const std::byte> b) override { ++writes; return actual->append_durable(p,n,b); }
  Result<void> remove(const std::filesystem::path& p) override { ++writes; return actual->remove(p); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { return actual->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { return actual->list_directories(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { return actual->directory_exists(p); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { return actual->validate_managed_tree(p); }
  Result<void> remove_tree(const std::filesystem::path& p) override { ++writes; return actual->remove_tree(p); }
  Result<void> publish_directory_if_absent(const std::filesystem::path& a, const std::filesystem::path& b) override { ++writes; return actual->publish_directory_if_absent(a,b); }
  std::shared_ptr<ProjectStoragePlatform> actual;
  bool observe = false;
  int live_leases = 0;
  std::size_t acquisitions = 0, writes = 0;
  std::optional<std::uint64_t> reported_length;
  mutable std::vector<std::filesystem::path> complete_reads;
};

class RangeStorage final : public ForwardStorage, public project_io::ProjectStorageRangeReader {
 public:
  using ForwardStorage::ForwardStorage;
  Result<std::size_t> read_range(const std::filesystem::path& p, std::uint64_t offset,
                               std::span<std::byte> output) const override {
    LMDJ_CHECK(live_leases > 0);
    LMDJ_CHECK(output.size() <= 1048576);
    if (read_error && offset >= error_offset) return Result<std::size_t>::failure(*read_error);
    if (zero_progress && !output.empty()) return Result<std::size_t>::success(0);
    if (invalid_count) return Result<std::size_t>::success(output.size() + 1);
    const auto* reader = dynamic_cast<const project_io::ProjectStorageRangeReader*>(actual.get());
    LMDJ_CHECK(reader != nullptr);
    auto result = reader->read_range(p, offset, output.first(std::min(output.size(), short_limit)));
    if (result.has_value()) reads.emplace_back(offset, output.size(), result.value());
    return result;
  }
  mutable std::vector<std::tuple<std::uint64_t,std::size_t,std::size_t>> reads;
  std::size_t short_limit = std::numeric_limits<std::size_t>::max();
  bool zero_progress = false, invalid_count = false;
  std::optional<foundation::Error> read_error;
  std::uint64_t error_offset = 0;
};

struct Fixture {
  TempDirectory temp;
  std::filesystem::path bundle = temp.path() / "recorded.lmdj";
  std::shared_ptr<ForwardStorage> platform;
  ProjectStore store;
  foundation::ArtifactRef artifact;
  std::vector<std::byte> payload;
  explicit Fixture(bool ranges = true, bool bound = true,
      std::optional<foundation::ArtifactRef> custom = std::nullopt)
      : platform(ranges ? std::static_pointer_cast<ForwardStorage>(std::make_shared<RangeStorage>(temp.path()/"metadata"))
                        : std::make_shared<ForwardStorage>(temp.path()/"metadata")),
        store(platform), artifact(custom.value_or(foundation::ArtifactRef{kDigest,"audio/wav",2097169})) {
    auto project = domain::create_project(foundation::ProjectId{kProject},120);
    LMDJ_CHECK(project.has_value());
    project.value().performances.emplace(domain::PerformanceId{kPerformance}, domain::Performance{
        domain::PerformanceId{kPerformance},"recorded",120,0,
        bound ? std::optional{artifact} : std::nullopt,{}});
    LMDJ_CHECK(store.create(bundle,project.value()).has_value());
    if (!custom) {
      payload.resize(2097169);
      for (std::size_t i=0;i<payload.size();++i) payload[i]=kPattern[i%kPattern.size()];
      auto lease=platform->acquire_writer(bundle);
      LMDJ_CHECK(lease.has_value());
      LMDJ_CHECK(platform->create_immutable(path(),payload).has_value());
    }
    platform->observe=true;
  }
  std::filesystem::path path() const { return bundle/"assets"/(artifact.sha256+".wav"); }
  PerformanceRecordingSelector selector() const {
    return {foundation::ProjectId{kProject},domain::PerformanceId{kPerformance},0,artifact};
  }
  RangeStorage& ranges() { auto* value=dynamic_cast<RangeStorage*>(platform.get()); LMDJ_CHECK(value); return *value; }
};

Result<void> ignore(std::span<const std::byte>) { return Result<void>::success(); }

void test_exact_stream_receipt_and_custody(bool short_reads) {
  Fixture f;
  if(short_reads) f.ranges().short_limit=4093;
  std::uint64_t consumed=0;
  const auto writes=f.platform->writes, acquisitions=f.platform->acquisitions;
  auto competitor=project_io::make_native_project_storage_platform(f.temp.path()/"metadata");
  const auto scanned=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto input) {
    LMDJ_CHECK(f.platform->live_leases==1);
    const auto refused=competitor->acquire_writer(f.bundle);
    LMDJ_CHECK(!refused.has_value());
    LMDJ_CHECK(refused.error().details.at("storage_condition")=="project_busy");
    LMDJ_CHECK(!input.empty() && input.size()<=1048576);
    for(const auto byte:input) { LMDJ_CHECK(byte==kPattern[consumed%8]); ++consumed; }
    return Result<void>::success();
  });
  LMDJ_CHECK(scanned.has_value());
  LMDJ_CHECK(scanned.value()==(project_io::PerformanceRecordingVerification{
      foundation::ProjectId{kProject},domain::PerformanceId{kPerformance},0,0,f.artifact}));
  LMDJ_CHECK(consumed==2097169);
  std::uint64_t next=0;
  for(const auto& [offset,capacity,actual]:f.ranges().reads) {
    LMDJ_CHECK(offset==next && capacity<=1048576); next+=actual;
  }
  LMDJ_CHECK(std::get<1>(f.ranges().reads.back())==1 && std::get<2>(f.ranges().reads.back())==0);
  LMDJ_CHECK(f.platform->writes==writes && f.platform->acquisitions==acquisitions+1);
  LMDJ_CHECK(f.platform->live_leases==0);
  LMDJ_CHECK(competitor->acquire_writer(f.bundle).has_value());
}

void test_wrong_selector_never_reads_audio(int field) {
  Fixture f;
  auto selector=f.selector();
  auto expected=ErrorCode::not_found;
  if(field==0) selector.project_id=foundation::ProjectId{kOther};
  if(field==1) selector.performance_id=domain::PerformanceId{kOther};
  if(field==2) selector.artifact.sha256=std::string(64,'f');
  if(field==3) { selector.artifact.media_type="text/plain"; expected=ErrorCode::invalid_argument; }
  if(field==4) ++selector.artifact.byte_length;
  if(field==5) { ++selector.expected_revision; expected=ErrorCode::revision_conflict; }
  const auto result=f.store.scan_performance_recording(f.bundle,selector,ignore);
  LMDJ_CHECK(!result.has_value() && result.error().code==expected);
  LMDJ_CHECK(f.ranges().reads.empty() && f.platform->live_leases==0);
}

void test_absent_binding_and_file() {
  Fixture unbound(true,false);
  const auto result=unbound.store.scan_performance_recording(unbound.bundle,unbound.selector(),ignore);
  LMDJ_CHECK(!result.has_value() && result.error().code==ErrorCode::not_found);
  LMDJ_CHECK(unbound.ranges().reads.empty());
  Fixture missing;
  std::filesystem::remove(missing.path());
  const auto absent=missing.store.scan_performance_recording(missing.bundle,missing.selector(),ignore);
  LMDJ_CHECK(!absent.has_value() && absent.error().code==ErrorCode::not_found);
  LMDJ_CHECK(missing.ranges().reads.empty());
}

void test_late_byte_corruption_rejects_complete_hash() {
  Fixture f;
  std::fstream file(f.path(),std::ios::in|std::ios::out|std::ios::binary);
  file.seekp(131080); file.put('!'); file.close();
  std::uint64_t seen=0;
  const auto result=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto b){seen+=b.size();return Result<void>::success();});
  LMDJ_CHECK(seen==f.artifact.byte_length);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().details.at("storage_condition")=="artifact_mismatch");
  LMDJ_CHECK(result.error().message=="Performance recording hash does not match its reference");
}

void test_length_progress_and_extra_bytes() {
  for(int mode=0;mode<4;++mode) {
    Fixture f;
    if(mode==0) std::filesystem::resize_file(f.path(),f.artifact.byte_length-1);
    if(mode==1) f.ranges().zero_progress=true;
    if(mode==2) f.ranges().invalid_count=true;
    if(mode==3) { std::filesystem::resize_file(f.path(),f.artifact.byte_length+1); f.platform->reported_length=f.artifact.byte_length; }
    const auto result=f.store.scan_performance_recording(f.bundle,f.selector(),ignore);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().details.at("storage_condition")== (mode==2 ? "invalid_state":"artifact_mismatch"));
    LMDJ_CHECK(f.platform->live_leases==0);
  }
}

void test_length_change_between_windows_cannot_receive_receipt() {
  for (bool grow : {false,true}) {
    Fixture f;
    bool changed=false;
    const auto result=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto) {
      if(!changed) {std::filesystem::resize_file(f.path(),grow ? f.artifact.byte_length+1 : 1048575);changed=true;}
      return Result<void>::success();
    });
    LMDJ_CHECK(changed && !result.has_value());
    LMDJ_CHECK(result.error().details.at("storage_condition")=="artifact_mismatch");
    LMDJ_CHECK(f.platform->live_leases==0);
  }
}

void test_storage_and_consumer_errors_release_lease() {
  Fixture f;
  const foundation::Error sentinel{ErrorCode::io_error,"exact scan I/O failure",{{"storage_condition","quota_exceeded"}}};
  f.ranges().read_error=sentinel; f.ranges().error_offset=1048576;
  std::size_t calls=0;
  const auto failed=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto){++calls;return Result<void>::success();});
  LMDJ_CHECK(!failed.has_value() && failed.error().message==sentinel.message && failed.error().details==sentinel.details);
  LMDJ_CHECK(calls==1 && f.platform->live_leases==0);
  f.ranges().read_error.reset(); calls=0;
  const auto consumer=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto){++calls;return Result<void>::failure(sentinel);});
  LMDJ_CHECK(!consumer.has_value() && consumer.error().message==sentinel.message && consumer.error().details==sentinel.details);
  LMDJ_CHECK(calls==1 && f.platform->live_leases==0);
  LMDJ_CHECK(f.store.scan_performance_recording(f.bundle,f.selector(),ignore).has_value());
}

void test_consumer_revision_change_cannot_receive_stale_receipt() {
  Fixture f;
  bool changed=false;
  const auto result=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto) {
    if(!changed) {
      const auto renamed=f.store.rename_performance(f.bundle,{
          {foundation::CommandId{"30000000-0000-4000-8000-000000000001"},0},domain::PerformanceId{kPerformance},"renamed"});
      LMDJ_CHECK(renamed.has_value()); changed=true;
    }
    return Result<void>::success();
  });
  LMDJ_CHECK(changed && !result.has_value() && result.error().code==ErrorCode::revision_conflict);
  LMDJ_CHECK(result.error().details.at("actual_revision")==1);
  auto current=f.selector(); current.expected_revision=1;
  LMDJ_CHECK(f.store.scan_performance_recording(f.bundle,current,ignore).has_value());
}

void test_consumer_cannot_retarget_callers_selector() {
  Fixture f;
  auto selector=f.selector();
  auto requested_bundle=f.bundle;
  std::uint64_t bytes=0;
  const auto result=f.store.scan_performance_recording(requested_bundle,selector,[&](auto input) {
    bytes+=input.size();
    requested_bundle=f.temp.path()/"different.lmdj";
    selector.project_id=foundation::ProjectId{kOther};
    selector.performance_id=domain::PerformanceId{kOther};
    selector.expected_revision=99;
    selector.artifact.byte_length=1;
    selector.artifact.sha256=std::string(64,'f');
    return Result<void>::success();
  });
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(bytes==2097169 && result.value().project_revision==0);
  LMDJ_CHECK(result.value().project_id==foundation::ProjectId{kProject});
  LMDJ_CHECK(result.value().performance_id==domain::PerformanceId{kPerformance});
  LMDJ_CHECK(result.value().artifact==f.artifact);
}

void test_busy_and_legacy_capability_refusal() {
  Fixture f;
  auto competitor=project_io::make_native_project_storage_platform(f.temp.path()/"metadata");
  auto held=competitor->acquire_writer(f.bundle); LMDJ_CHECK(held.has_value());
  const auto busy=f.store.scan_performance_recording(f.bundle,f.selector(),ignore);
  LMDJ_CHECK(!busy.has_value() && busy.error().details.at("storage_condition")=="project_busy");
  LMDJ_CHECK(f.ranges().reads.empty());
  Fixture legacy(false);
  const auto unavailable=legacy.store.scan_performance_recording(legacy.bundle,legacy.selector(),ignore);
  LMDJ_CHECK(!unavailable.has_value() && unavailable.error().details.at("reason")=="bounded_read_unavailable");
  LMDJ_CHECK(legacy.platform->live_leases==0);
}

void test_read_preserves_orphans_and_ignores_unselected_audio() {
  Fixture f;
  f.platform->observe=false;
  const foundation::AssetId other_asset{kOther};
  const auto imported=f.store.import_artifact_bytes(f.bundle,{
      {foundation::CommandId{"30000000-0000-4000-8000-000000000001"},0},
      other_asset,"audio/wav",kPattern});
  LMDJ_CHECK(imported.has_value());
  const auto other_ref=imported.value().state.assets.at(other_asset).artifact;
  const auto orphan=f.bundle/"history/checkpoints/999.json";
  const auto other=f.bundle/"assets"/(other_ref.sha256+".wav");
  {std::ofstream file(orphan);file<<"uncommitted";}
  {std::ofstream file(other);file<<"corrupt unrelated WAV";}
  f.platform->observe=true;
  const auto writes=f.platform->writes;
  auto selector=f.selector();selector.expected_revision=1;
  LMDJ_CHECK(f.store.scan_performance_recording(f.bundle,selector,ignore).has_value());
  LMDJ_CHECK(f.platform->writes==writes && std::filesystem::file_size(orphan)==11);
  LMDJ_CHECK(std::filesystem::file_size(other)==21);
  LMDJ_CHECK(std::none_of(f.platform->complete_reads.begin(),f.platform->complete_reads.end(),
      [](auto& p){return p.parent_path().filename()=="assets";}));
}

void test_sparse_wav_above_old_vector_read_limit() {
  // Independently calculated with Python hashlib over this PCM16 header and
  // 70MiB of zeros; the fixture and observer never allocate the full file.
  constexpr std::uint64_t data_bytes=70U*1024U*1024U;
  const foundation::ArtifactRef ref{"975c1f757d4cd3f3b5494b0d749b9235af34ee9b28bdf5e8552d81ea5c594e32","audio/wav",data_bytes+44};
  Fixture f(true,true,ref);
  const std::array<unsigned char,44> header{0x52,0x49,0x46,0x46,0x24,0,0x60,0x04,
      0x57,0x41,0x56,0x45,0x66,0x6d,0x74,0x20,0x10,0,0,0,1,0,2,0,0x80,0xbb,0,0,
      0,0xee,2,0,4,0,0x10,0,0x64,0x61,0x74,0x61,0,0,0x60,0x04};
  {std::ofstream file(f.path(),std::ios::binary);file.write(reinterpret_cast<const char*>(header.data()),header.size());file.seekp(ref.byte_length-1);file.put(0);LMDJ_CHECK(bool(file));}
  const auto old=f.store.read_artifact(f.bundle,ref);
  LMDJ_CHECK(!old.has_value() && old.error().message=="artifact exceeds the Project read limit");
  std::uint64_t count=0;
  const auto scanned=f.store.scan_performance_recording(f.bundle,f.selector(),[&](auto input){count+=input.size();return Result<void>::success();});
  LMDJ_CHECK(scanned.has_value() && scanned.value().artifact==ref && count==ref.byte_length);
  LMDJ_CHECK(f.payload.empty() && f.platform->live_leases==0);
}
}  // namespace

int main() {
  try {
    test_exact_stream_receipt_and_custody(false);
    test_exact_stream_receipt_and_custody(true);
    for(int field=0;field<6;++field) test_wrong_selector_never_reads_audio(field);
    test_absent_binding_and_file();
    test_late_byte_corruption_rejects_complete_hash();
    test_length_progress_and_extra_bytes();
    test_length_change_between_windows_cannot_receive_receipt();
    test_storage_and_consumer_errors_release_lease();
    test_consumer_revision_change_cannot_receive_stale_receipt();
    test_consumer_cannot_retarget_callers_selector();
    test_busy_and_legacy_capability_refusal();
    test_read_preserves_orphans_and_ignores_unselected_audio();
    test_sparse_wav_above_old_vector_read_limit();
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
  std::cout<<"Performance recording scan: PASS\n";
}
