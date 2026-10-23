#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <stop_token>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <lmdj/facade/application.hpp>
#include <lmdj/project_io/project_store.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using foundation::Result;
using foundation::ErrorCode;
using ReadResult = Result<facade::PerformanceRecordingRead>;
constexpr auto kProject = "00000000-0000-4000-8000-000000000001";
constexpr auto kPerformance = "10000000-0000-4000-8000-000000000001";
constexpr auto kOther = "10000000-0000-4000-8000-000000000002";
// Independent Python struct/hashlib literals for a 2158204-byte WAV: two 1 MiB
// windows plus 61052 bytes, so every scan crosses window boundaries.
constexpr auto kDigest = "b29079c0cf7adb348911ab9ebc7fb115f1870b6edf2990316956ad379a0dea99";

class TempDirectory {
 public:
  TempDirectory() : path_(std::filesystem::temp_directory_path() /
      ("lmdj-recording-metadata-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))) {
    LMDJ_CHECK(std::filesystem::create_directories(path_));
  }
  ~TempDirectory() { std::error_code ignored; std::filesystem::remove_all(path_, ignored); }
  const std::filesystem::path& path() const { return path_; }
 private:
  std::filesystem::path path_;
};

class ObservedLease final : public project_io::ProjectWriterLease {
 public:
  ObservedLease(std::unique_ptr<project_io::ProjectWriterLease> lease, std::atomic<unsigned>& count)
      : lease_(std::move(lease)), count_(count) { ++count_; }
  ~ObservedLease() override { lease_.reset(); --count_; }
 private:
  std::unique_ptr<project_io::ProjectWriterLease> lease_;
  std::atomic<unsigned>& count_;
};

// Real Native I/O, with atomic observations because Control and the reader
// intentionally use the same platform concurrently. The legacy form has no
// range capability, proving there is no implicit default-platform fallback.
class Storage : public project_io::ProjectStoragePlatform {
 public:
  explicit Storage(const std::filesystem::path& root)
      : actual(project_io::make_native_project_storage_platform(root)) {}
  Result<std::unique_ptr<project_io::ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    auto result=actual->acquire_writer(p);
    if(!result.has_value()) return Result<std::unique_ptr<project_io::ProjectWriterLease>>::failure(result.error());
    return Result<std::unique_ptr<project_io::ProjectWriterLease>>::success(
        std::make_unique<ObservedLease>(std::move(result.value()),leases));
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override { ++writes; return actual->ensure_directory(p); }
  Result<bool> exists(const std::filesystem::path& p) const override { ++reads; return actual->exists(p); }
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override { ++reads; return actual->byte_length(p); }
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    ++reads;
    if(forbid_whole_audio && p.parent_path().filename()=="assets") {
      ++whole_audio_reads;
      return Result<std::vector<std::byte>>::failure({ErrorCode::io_error,"whole audio read forbidden"});
    }
    return actual->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p,std::span<const std::byte> b) override { ++writes; return actual->create_immutable(p,b); }
  Result<void> replace_complete(const std::filesystem::path& p,std::span<const std::byte> b) override { ++writes; return actual->replace_complete(p,b); }
  Result<void> append_durable(const std::filesystem::path& p,std::uint64_t n,std::span<const std::byte> b) override { ++writes; return actual->append_durable(p,n,b); }
  Result<void> remove(const std::filesystem::path& p) override { ++writes; return actual->remove(p); }
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override { ++reads; return actual->list_names(p); }
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override { ++reads; return actual->list_directories(p); }
  Result<bool> directory_exists(const std::filesystem::path& p) const override { ++reads; return actual->directory_exists(p); }
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override { ++reads; return actual->validate_managed_tree(p); }
  Result<void> remove_tree(const std::filesystem::path& p) override { ++writes; return actual->remove_tree(p); }
  Result<void> publish_directory_if_absent(const std::filesystem::path& a,const std::filesystem::path& b) override { ++writes; return actual->publish_directory_if_absent(a,b); }
  std::shared_ptr<project_io::ProjectStoragePlatform> actual;
  std::atomic<unsigned> leases{},writes{};
  mutable std::atomic<unsigned> reads{},whole_audio_reads{};
  bool forbid_whole_audio{}; // Set before starting any worker; immutable thereafter.
};

class RangeStorage final : public Storage, public project_io::ProjectStorageRangeReader {
 public:
  using Storage::Storage;
  Result<std::size_t> read_range(const std::filesystem::path& p,std::uint64_t at,
                               std::span<std::byte> output) const override {
    LMDJ_CHECK(leases.load()>0 && output.size()<=1048576);
    const auto* reader=dynamic_cast<const project_io::ProjectStorageRangeReader*>(actual.get());
    LMDJ_CHECK(reader!=nullptr);
    auto result=reader->read_range(p,at,output);
    ++range_calls;
    if(result.has_value()) bytes_seen+=result.value();
    if(after_range) after_range(at);
    return result;
  }
  mutable std::atomic<unsigned> range_calls{};
  mutable std::atomic<std::uint64_t> bytes_seen{};
  std::function<void(std::uint64_t)> after_range; // Configure before launching a worker.
};

enum class Variant { valid, unsupported, bad_header, mismatch, bad_header_mismatch };

struct Fixture {
  TempDirectory temp;
  std::filesystem::path bundle=temp.path()/"recorded.lmdj";
  std::shared_ptr<Storage> platform;
  project_io::ProjectStore store;
  foundation::ArtifactRef artifact;
  std::unique_ptr<facade::Application> app;

  explicit Fixture(Variant variant=Variant::valid,bool ranges=true,std::uint64_t recording_revision=0)
      : platform(ranges ? std::static_pointer_cast<Storage>(std::make_shared<RangeStorage>(temp.path()/"coordination"))
                        : std::make_shared<Storage>(temp.path()/"coordination")), store(platform),
        artifact{variant==Variant::unsupported ? "e120c174c9077ae537a908a6ffd42b7d56daef6518f3d891fca612403bf93be0"
            : (variant==Variant::bad_header || variant==Variant::bad_header_mismatch)
                ? "1c4adbe87653893bc454def91e5e6c89f8eda6a43db2fa8a29bdcbf9950c39e3" : kDigest,
            "audio/wav",2158204} {
    auto project=std::make_unique<Result<domain::ProjectState>>(domain::create_project(foundation::ProjectId{kProject},120));
    LMDJ_CHECK(project->has_value());
    project->value().performances.emplace(domain::PerformanceId{kPerformance},domain::Performance{
        domain::PerformanceId{kPerformance},"silence",120,recording_revision,artifact,{}});
    LMDJ_CHECK(store.create(bundle,project->value()).has_value());
    std::vector<std::byte> payload(2158204);
    const auto tag=[&](std::size_t at,std::string_view text) {
      for(std::size_t i=0;i<text.size();++i) payload[at+i]=static_cast<std::byte>(text[i]);
    };
    const auto number=[&](std::size_t at,std::uint32_t n,unsigned width) {
      for(unsigned i=0;i<width;++i) payload[at+i]=static_cast<std::byte>(n>>(8*i));
    };
    const std::uint32_t rate=variant==Variant::unsupported ? 32000 : 48000;
    tag(0,(variant==Variant::bad_header || variant==Variant::bad_header_mismatch)?"XIFF":"RIFF");
    number(4,2158196,4);tag(8,"WAVE");tag(12,"fmt ");number(16,16,4);
    number(20,1,2);number(22,2,2);number(24,rate,4);number(28,rate*4,4);number(32,4,2);number(34,16,2);
    tag(36,"JUNK");number(40,3,4);payload[44]=std::byte{1};payload[45]=std::byte{2};payload[46]=std::byte{3};
    payload[47]=std::byte{0xab};tag(48,"data");number(52,2158148,4);
    if(variant==Variant::mismatch || variant==Variant::bad_header_mismatch) payload.back()=std::byte{1};
    {
      auto lease=platform->acquire_writer(bundle);LMDJ_CHECK(lease.has_value());
      LMDJ_CHECK(platform->create_immutable(bundle/"assets"/(artifact.sha256+".wav"),payload).has_value());
    }
    app=std::make_unique<facade::Application>(config());
    platform->forbid_whole_audio=true;
  }
  facade::ApplicationConfig config() const {
    facade::ApplicationConfig config{};
    config.workspace_root=temp.path();config.storage_platform=platform;
    config.performance_replay_controller=facade::make_unavailable_performance_replay_controller();
    return config;
  }
  facade::PerformanceRecordingMetadataRequest request() const {
    return {bundle,foundation::ProjectId{kProject},domain::PerformanceId{kPerformance},0,artifact};
  }
  RangeStorage& ranges() { auto* range=dynamic_cast<RangeStorage*>(platform.get());LMDJ_CHECK(range);return *range; }
};

const facade::PerformanceRecordingMetadata& verified(const ReadResult& result) {
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(std::holds_alternative<facade::PerformanceRecordingMetadata>(result.value()));
  return std::get<facade::PerformanceRecordingMetadata>(result.value());
}
void identity(const facade::PerformanceRecordingMetadata& result,const foundation::ArtifactRef& artifact) {
  LMDJ_CHECK(result.project_id.value()==kProject && result.performance_id.value()==kPerformance);
  LMDJ_CHECK(result.project_revision==0 && result.recording_revision==0);
  LMDJ_CHECK(result.artifact==artifact);
}
void cancelled(const ReadResult& result) {
  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(std::holds_alternative<facade::PerformanceRecordingReadCancelled>(result.value()));
}

void test_exact_metadata_and_read_only_reopen() {
  Fixture f;
  const auto writes=f.platform->writes.load(),reads=f.platform->reads.load();
  auto reader=f.app->make_performance_recording_metadata_reader();
  LMDJ_CHECK(f.platform->writes.load()==writes && f.platform->reads.load()==reads);
  const auto result=reader->inspect(f.request());const auto& value=verified(result);identity(value,f.artifact);
  LMDJ_CHECK(value.audio.has_value());
  LMDJ_CHECK(value.audio.value().sample_rate==48000 && value.audio.value().channels==2);
  LMDJ_CHECK(value.audio.value().source_frames==539537); // data size / 4, excluding odd JUNK and padding.
  LMDJ_CHECK(f.ranges().bytes_seen.load()==2158204 && f.ranges().range_calls.load()==4);
  LMDJ_CHECK(f.platform->whole_audio_reads.load()==0 && f.platform->leases.load()==0);
  LMDJ_CHECK(f.platform->writes.load()==writes);
  reader.reset();f.app.reset();
  facade::Application reopened(f.config());auto reopened_reader=reopened.make_performance_recording_metadata_reader();
  const auto again=reopened_reader->inspect(f.request());identity(verified(again),f.artifact);
  LMDJ_CHECK(verified(again).audio.value().source_frames==539537);
}

void test_format_is_published_only_after_complete_integrity() {
  for(auto variant:{Variant::unsupported,Variant::bad_header}) {
    Fixture f{variant};auto reader=f.app->make_performance_recording_metadata_reader();
    const auto result=reader->inspect(f.request());const auto& value=verified(result);identity(value,f.artifact);
    LMDJ_CHECK(!value.audio.has_value() && value.audio.error().code==ErrorCode::unsupported_audio);
    LMDJ_CHECK(f.ranges().bytes_seen.load()==2158204 && f.ranges().range_calls.load()==4);
    LMDJ_CHECK(f.platform->leases.load()==0);
  }
  for(auto variant:{Variant::mismatch,Variant::bad_header_mismatch}) {
    Fixture f{variant};auto reader=f.app->make_performance_recording_metadata_reader();
    const auto result=reader->inspect(f.request());
    LMDJ_CHECK(!result.has_value() && result.error().code==ErrorCode::cook_failed);
    LMDJ_CHECK(result.error().details.at("storage_condition")=="artifact_mismatch");
    LMDJ_CHECK(f.ranges().bytes_seen.load()==2158204 && f.platform->leases.load()==0);
  }
}

void test_project_and_recording_revisions_are_distinct_verified_facts() {
  // Imported/duplicated Performance Truth retains its original recording
  // revision independently of the destination Project's current revision.
  Fixture f{Variant::valid,true,17};
  const auto renamed=f.app->command({{"operation","performance.rename"},{"project_path",f.bundle.generic_string()},
      {"command_id","20000000-0000-4000-8000-000000000002"},{"expected_revision",0},
      {"performance_id",kPerformance},{"name","new Project revision"}});
  LMDJ_CHECK(renamed.at("ok").get<bool>());
  auto request=f.request();request.expected_revision=1;
  auto reader=f.app->make_performance_recording_metadata_reader();
  const auto result=reader->inspect(request);const auto& value=verified(result);
  LMDJ_CHECK(value.project_id.value()==kProject && value.performance_id.value()==kPerformance);
  LMDJ_CHECK(value.project_revision==1);
  LMDJ_CHECK(value.recording_revision==17);
  LMDJ_CHECK(value.artifact==f.artifact && value.audio.has_value());
  LMDJ_CHECK(value.audio.value().source_frames==539537);
}

void test_selectors_missing_capability_and_request_snapshot() {
  Fixture f;auto reader=f.app->make_performance_recording_metadata_reader();
  auto request=f.request();request.expected_revision=1;
  const auto stale=reader->inspect(request);LMDJ_CHECK(!stale.has_value() && stale.error().code==ErrorCode::revision_conflict);
  request=f.request();request.performance_id=domain::PerformanceId{kOther};
  const auto absent=reader->inspect(request);LMDJ_CHECK(!absent.has_value() && absent.error().code==ErrorCode::not_found);
  request=f.request();request.project_path="relative.lmdj";
  const auto relative=reader->inspect(request);LMDJ_CHECK(!relative.has_value() && relative.error().code==ErrorCode::invalid_argument);
  LMDJ_CHECK(f.ranges().range_calls.load()==0);
  request=f.request();
  f.ranges().after_range=[&](std::uint64_t at) {
    if(at==0) { request.project_id=foundation::ProjectId{kOther};request.expected_revision=17;request.artifact.byte_length=1; }
  };
  const auto snapshotted=reader->inspect(request);identity(verified(snapshotted),f.artifact);
  f.ranges().after_range=[](std::uint64_t) { throw std::runtime_error("private-test-detail"); };
  const auto exception=reader->inspect(f.request());
  LMDJ_CHECK(!exception.has_value() && exception.error().code==ErrorCode::internal_error);
  LMDJ_CHECK(exception.error().message=="unexpected Application Facade Host API failure");
  LMDJ_CHECK(exception.error().details.empty() && f.platform->leases.load()==0);
  Fixture legacy{Variant::valid,false};auto legacy_reader=legacy.app->make_performance_recording_metadata_reader();
  const auto unavailable=legacy_reader->inspect(legacy.request());
  LMDJ_CHECK(!unavailable.has_value() && unavailable.error().code==ErrorCode::io_error);
  LMDJ_CHECK(unavailable.error().details.at("reason")=="bounded_read_unavailable");
}

void test_cancellation_before_window_and_after_final_input() {
  for(auto point:{0,1,2}) {
    Fixture f;auto reader=f.app->make_performance_recording_metadata_reader();std::stop_source stop;
    const auto writes=f.platform->writes.load(),reads=f.platform->reads.load();
    if(point==0) stop.request_stop();
    f.ranges().after_range=[&,point](std::uint64_t at) {
      if((point==1 && at==0) || (point==2 && at==2158204)) stop.request_stop();
    };
    const auto result=reader->inspect(f.request(),stop.get_token());cancelled(result);
    LMDJ_CHECK(f.platform->leases.load()==0 && f.platform->writes.load()==writes);
    if(point==0) LMDJ_CHECK(f.platform->reads.load()==reads && f.ranges().range_calls.load()==0);
    if(point==1) LMDJ_CHECK(f.ranges().range_calls.load()==1);
    if(point==2) LMDJ_CHECK(f.ranges().range_calls.load()==4 && f.ranges().bytes_seen.load()==2158204);
  }
}

void test_worker_read_does_not_lock_control_and_rejects_changed_owner() {
  Fixture f;auto reader=f.app->make_performance_recording_metadata_reader();
  auto root=f.app->acquire_project_writer(f.bundle);LMDJ_CHECK(root.has_value());
  std::mutex mutex;std::condition_variable changed;
  bool reached=false,released=false,expired=false;
  f.ranges().after_range=[&](std::uint64_t at) {
    if(at!=0) return;
    std::unique_lock lock(mutex);reached=true;changed.notify_all();
    if(!changed.wait_for(lock,std::chrono::seconds{5},[&]{return released;})) expired=true;
  };
  std::optional<ReadResult> result;
  std::jthread worker([reader=std::move(reader),request=f.request(),&result]() mutable {
    result.emplace(reader->inspect(request));reader.reset();
  });
  try {
    { std::unique_lock lock(mutex);LMDJ_CHECK(changed.wait_for(lock,std::chrono::seconds{5},[&]{return reached;})); }
    const auto renamed=f.app->command({{"operation","performance.rename"},{"project_path",f.bundle.generic_string()},
        {"command_id","20000000-0000-4000-8000-000000000001"},{"expected_revision",0},
        {"performance_id",kPerformance},{"name","Control continued"}});
    LMDJ_CHECK(renamed.at("ok").get<bool>());
    { std::lock_guard lock(mutex);LMDJ_CHECK(!expired && !released);released=true; }
    changed.notify_all();worker.join();
  } catch(...) {
    { std::lock_guard lock(mutex);released=true; } changed.notify_all();worker.join();throw;
  }
  LMDJ_CHECK(result && !result->has_value() && result->error().code==ErrorCode::revision_conflict);
  const auto truth=f.store.inspect_committed(f.bundle);LMDJ_CHECK(truth.has_value());
  LMDJ_CHECK(truth.value().revision==1 && truth.value().performances.at(domain::PerformanceId{kPerformance}).name=="Control continued");
  LMDJ_CHECK(f.platform->leases.load()==1); // Only the original Control root remains.
}

void test_reader_survives_application_and_retires_on_worker() {
  Fixture f;const auto owners=f.platform.use_count();
  auto reader=f.app->make_performance_recording_metadata_reader();
  LMDJ_CHECK(f.platform.use_count()==owners+1); // Reader retains the exact platform itself.
  f.app.reset();
  std::optional<ReadResult> result;const auto control=std::this_thread::get_id();bool distinct=false;
  std::jthread worker([reader=std::move(reader),request=f.request(),&result,&distinct,control]() mutable {
    distinct=std::this_thread::get_id()!=control;result.emplace(reader->inspect(request));reader.reset();
  });
  worker.join();LMDJ_CHECK(distinct && result);identity(verified(*result),f.artifact);
  LMDJ_CHECK(verified(*result).audio.has_value() && f.platform->leases.load()==0);
}

void test_external_cancel_keeps_custody_until_the_worker_really_returns() {
  Fixture f;auto reader=f.app->make_performance_recording_metadata_reader();std::stop_source stop;
  std::mutex mutex;std::condition_variable changed;
  bool reached=false,released=false;
  f.ranges().after_range=[&](std::uint64_t at) {
    if(at!=0) return;
    std::unique_lock lock(mutex);reached=true;changed.notify_all();
    LMDJ_CHECK(changed.wait_for(lock,std::chrono::seconds{5},[&]{return released;}));
  };
  std::optional<ReadResult> result;std::atomic<bool> finished=false;
  std::jthread worker([reader=std::move(reader),request=f.request(),token=stop.get_token(),&result,&finished]() mutable {
    result.emplace(reader->inspect(request,token));reader.reset();finished.store(true,std::memory_order_release);
  });
  auto foreign=project_io::make_native_project_storage_platform(f.temp.path()/"coordination");
  try {
    { std::unique_lock lock(mutex);LMDJ_CHECK(changed.wait_for(lock,std::chrono::seconds{5},[&]{return reached;})); }
    LMDJ_CHECK(stop.request_stop());
    LMDJ_CHECK(!finished.load(std::memory_order_acquire) && f.platform->leases.load()==1);
    const auto busy=foreign->acquire_writer(f.bundle);
    LMDJ_CHECK(!busy.has_value() && busy.error().details.at("storage_condition")=="project_busy");
    { std::lock_guard lock(mutex);released=true; } changed.notify_all();worker.join();
  } catch(...) {
    { std::lock_guard lock(mutex);released=true; } changed.notify_all();worker.join();throw;
  }
  LMDJ_CHECK(finished.load() && result);cancelled(*result);
  LMDJ_CHECK(f.platform->leases.load()==0 && f.ranges().range_calls.load()==1);
  const auto acquired=foreign->acquire_writer(f.bundle);LMDJ_CHECK(acquired.has_value());
}
}  // namespace

int main() {
  try {
    test_exact_metadata_and_read_only_reopen();
    test_format_is_published_only_after_complete_integrity();
    test_project_and_recording_revisions_are_distinct_verified_facts();
    test_selectors_missing_capability_and_request_snapshot();
    test_cancellation_before_window_and_after_final_input();
    test_worker_read_does_not_lock_control_and_rejects_changed_owner();
    test_reader_survives_application_and_retires_on_worker();
    test_external_cancel_keeps_custody_until_the_worker_really_returns();
  } catch(const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
  std::cout<<"Performance recording metadata reader: PASS\n";
}
