#include <lmdj/web_runtime/control_runtime.hpp>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <thread>

#include <lmdj/project_io/project_store.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using Json = nlohmann::json;
using foundation::Result;
using foundation::ErrorCode;
using web_runtime::ControlRuntime;
using namespace web_runtime::detail;
constexpr auto kProject = "00000000-0000-4000-8000-000000000001";
constexpr auto kPattern = "00000000-0000-4000-8000-000000000010";
constexpr auto kPerformance = "10000000-0000-4000-8000-000000000001";
constexpr auto kDigest = "985ee1bbde8458eeb675cff7bb99b6bd61278b9646a127c7c39b1fb7634cb2d5";
constexpr audio::RuntimePreparationLimits kLimits{1'048'576,240'000,67'108'864,134'217'728};
std::string id(unsigned n) { auto tail=std::to_string(n);return "20000000-0000-4000-8000-"+std::string(12-tail.size(),'0')+tail; }

struct Gate {
  std::mutex mutex;
  std::condition_variable changed;
  bool paused=false,released=false,expired=false;
  unsigned entered=0;
  void read() {
    std::unique_lock lock(mutex);if(!paused) return;
    ++entered;changed.notify_all();
    if(!changed.wait_for(lock,std::chrono::seconds{5},[&]{return released;})) expired=true;
  }
  void await(unsigned count) {
    std::unique_lock lock(mutex);
    LMDJ_CHECK(changed.wait_for(lock,std::chrono::seconds{5},[&]{return entered>=count;}));
    LMDJ_CHECK(!expired);
  }
  void release() { std::lock_guard lock(mutex);released=true;changed.notify_all(); }
};

class Lease final : public project_io::ProjectWriterLease {
 public:
  Lease(std::unique_ptr<project_io::ProjectWriterLease> value,std::atomic<unsigned>& count)
      : value_(std::move(value)),count_(count) { ++count_; }
  ~Lease() override { value_.reset();--count_; }
 private:
  std::unique_ptr<project_io::ProjectWriterLease> value_;
  std::atomic<unsigned>& count_;
};

// Forward every operation to real Native storage. Only read_range's first
// window is held; no synthetic Project, callback completion or writer fate.
class Storage : public project_io::ProjectStoragePlatform {
 public:
  explicit Storage(const std::filesystem::path& root)
      : actual(project_io::make_native_project_storage_platform(root)) {}
  Result<std::unique_ptr<project_io::ProjectWriterLease>> acquire_writer(const std::filesystem::path& p) override {
    auto lease=actual->acquire_writer(p);
    if(!lease.has_value()) return Result<std::unique_ptr<project_io::ProjectWriterLease>>::failure(lease.error());
    return Result<std::unique_ptr<project_io::ProjectWriterLease>>::success(std::make_unique<Lease>(std::move(lease.value()),leases));
  }
  Result<std::size_t> read_window(const std::filesystem::path& p,std::uint64_t at,std::span<std::byte> output) const {
    const auto* reader=dynamic_cast<const project_io::ProjectStorageRangeReader*>(actual.get());
    LMDJ_CHECK(reader && output.size()<=1048576);
    auto result=reader->read_range(p,at,output);++ranges;
    if(at==0) gate->read();
    return result;
  }
  Result<void> ensure_directory(const std::filesystem::path& p) override {++writes;return actual->ensure_directory(p);}
  Result<bool> exists(const std::filesystem::path& p) const override {return actual->exists(p);}
  Result<std::uint64_t> byte_length(const std::filesystem::path& p) const override {return actual->byte_length(p);}
  Result<std::vector<std::byte>> read_complete(const std::filesystem::path& p) const override {
    if(forbid_audio && p.parent_path().filename()=="assets") {++whole_audio;return Result<std::vector<std::byte>>::failure({ErrorCode::io_error,"whole audio forbidden"});}
    return actual->read_complete(p);
  }
  Result<void> create_immutable(const std::filesystem::path& p,std::span<const std::byte> b) override {++writes;return actual->create_immutable(p,b);}
  Result<void> replace_complete(const std::filesystem::path& p,std::span<const std::byte> b) override {++writes;return actual->replace_complete(p,b);}
  Result<void> append_durable(const std::filesystem::path& p,std::uint64_t n,std::span<const std::byte> b) override {++writes;return actual->append_durable(p,n,b);}
  Result<void> remove(const std::filesystem::path& p) override {++writes;return actual->remove(p);}
  Result<std::vector<std::string>> list_names(const std::filesystem::path& p) const override {return actual->list_names(p);}
  Result<std::vector<std::string>> list_directories(const std::filesystem::path& p) const override {return actual->list_directories(p);}
  Result<bool> directory_exists(const std::filesystem::path& p) const override {return actual->directory_exists(p);}
  Result<void> validate_managed_tree(const std::filesystem::path& p) const override {return actual->validate_managed_tree(p);}
  Result<void> remove_tree(const std::filesystem::path& p) override {++writes;return actual->remove_tree(p);}
  Result<void> publish_directory_if_absent(const std::filesystem::path& a,const std::filesystem::path& b) override {++writes;return actual->publish_directory_if_absent(a,b);}
  std::shared_ptr<project_io::ProjectStoragePlatform> actual;
  std::shared_ptr<Gate> gate=std::make_shared<Gate>();
  std::atomic<unsigned> leases{},writes{};
  mutable std::atomic<unsigned> ranges{},whole_audio{};
  bool forbid_audio=false;
};

class RangeStorage final : public Storage, public project_io::ProjectStorageRangeReader {
 public:
  using Storage::Storage;
  Result<std::size_t> read_range(const std::filesystem::path& p,std::uint64_t at,
                                std::span<std::byte> output) const override {
    return read_window(p,at,output);
  }
};

struct Proxy {
  struct Task {void(*function)(void*) noexcept;void* argument;};
  std::deque<Task> tasks;
  std::function<void()> before_response;
  static void before(void* context) {
    const auto& callback=static_cast<Proxy*>(context)->before_response;
    if(callback) callback();
  }
  static bool schedule(void* context,void(*function)(void*) noexcept,void* argument) noexcept {
    static_cast<Proxy*>(context)->tasks.push_back({function,argument});return true;
  }
  static bool on_control(void*) noexcept {return true;}
  void pump() { for(auto n=tasks.size();n>0;--n) {auto task=tasks.front();tasks.pop_front();task.function(task.argument);} }
};

struct Fixture {
  std::filesystem::path root=std::filesystem::temp_directory_path()/
      ("lmdj-metadata-query-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::path bundle=root/"projects"/(std::string(kProject)+".lmdj");
  std::shared_ptr<Storage> platform;
  foundation::ArtifactRef artifact{kDigest,"audio/wav",192124};
  std::unique_ptr<ControlRuntime> runtime;
  Proxy proxy;
  std::unique_ptr<ControlBridge> bridge;
  std::map<std::string,Json> replies;

  explicit Fixture(unsigned variant=0,bool ranges=true)
      : platform(ranges ? std::static_pointer_cast<Storage>(std::make_shared<RangeStorage>(root/"coordination"))
                        : std::make_shared<Storage>(root/"coordination")) {
    std::filesystem::create_directories(root/"projects");
    if(variant==1) artifact.sha256="62aedd330eea859b7e3725d842cf089a97177d8a0f2918ad0d151212230c9d19";
    auto project=std::make_unique<Result<domain::ProjectState>>(domain::create_project(foundation::ProjectId{kProject},120));
    LMDJ_CHECK(project->has_value());
    project->value().patterns.emplace(foundation::PatternId{kPattern},domain::Pattern{foundation::PatternId{kPattern},1,{}});
    project->value().performances.emplace(domain::PerformanceId{kPerformance},domain::Performance{
        domain::PerformanceId{kPerformance},"silent",120,17,artifact,{}});
    project_io::ProjectStore store(platform);LMDJ_CHECK(store.create(bundle,project->value()).has_value());
    std::vector<std::byte> bytes(192124);
    auto text=[&](unsigned at,std::string_view value){for(std::size_t i=0;i<value.size();++i) bytes[at+i]=static_cast<std::byte>(value[i]);};
    auto number=[&](unsigned at,unsigned value,unsigned size){for(unsigned i=0;i<size;++i) bytes[at+i]=static_cast<std::byte>(value>>(8*i));};
    const unsigned rate=variant==1?32000:48000;
    text(0,"RIFF");number(4,192116,4);text(8,"WAVE");text(12,"fmt ");number(16,16,4);
    number(20,1,2);number(22,2,2);number(24,rate,4);number(28,rate*4,4);number(32,4,2);number(34,16,2);
    text(36,"JUNK");number(40,3,4);bytes[44]=std::byte{1};bytes[45]=std::byte{2};bytes[46]=std::byte{3};bytes[47]=std::byte{0xab};
    text(48,"data");number(52,192068,4);if(variant==2) bytes.back()=std::byte{1};
    {auto lease=platform->acquire_writer(bundle);LMDJ_CHECK(lease.has_value());
      LMDJ_CHECK(platform->create_immutable(bundle/"assets"/(artifact.sha256+".wav"),bytes).has_value());}
    facade::ApplicationConfig config{};config.workspace_root=root;config.storage_platform=platform;
    auto created=ControlRuntime::create(root,std::move(config),kLimits);LMDJ_CHECK(created.has_value());runtime=std::move(created.value());
    auto opened=runtime->dispatch("project.open",{{"project_id",kProject},{"pattern_id",kPattern}},{});
    LMDJ_CHECK(opened.value("ok",false));
    platform->forbid_audio=true;
    bridge=std::make_unique<ControlBridge>(*runtime,BridgeHooks{&proxy,&Proxy::schedule,&Proxy::on_control,&Proxy::before,nullptr,nullptr});
  }
  ~Fixture() {
    platform->gate->release();
    const auto until=std::chrono::steady_clock::now()+std::chrono::seconds{5};
    bool stopped=false;
    if(runtime) {
      runtime->fail_and_seal("test_cleanup");
      while(!runtime->recording_metadata_workers_stopped() && std::chrono::steady_clock::now()<until) {
        runtime->service_recording_metadata();std::this_thread::yield();
      }
      stopped=runtime->recording_metadata_workers_stopped();
    } else {
      while(platform.use_count()!=1 && std::chrono::steady_clock::now()<until) std::this_thread::yield();
      stopped=platform.use_count()==1;
    }
    // A failed teardown never removes bytes an unfinished worker still owns.
    bridge.reset();runtime.reset();
    if(stopped) {std::error_code ignored;std::filesystem::remove_all(root,ignored);}
  }
  Json payload() const {return {{"project_id",kProject},{"performance_id",kPerformance},
      {"expected_revision",0},{"recording_artifact",artifact}};}
  void submit(std::string request_id,std::string_view operation,const Json& payload,
              std::optional<std::chrono::steady_clock::time_point> deadline=std::nullopt) {
    const auto text=Json{{"protocol_version",1},{"request_id",request_id},{"operation",operation},{"payload",payload}}.dump();
    LMDJ_CHECK(bridge->submit({reinterpret_cast<const std::byte*>(text.data()),text.size()},{},deadline)==BridgeSubmitStatus::accepted);
    proxy.pump();
  }
  void tick(bool terminal_failure=false) {
    std::array<std::byte,65536> output{};std::size_t length=0;
    auto status=bridge->poll(output,length);
    if(status==BridgePollStatus::message) {
      auto reply=Json::parse(reinterpret_cast<const char*>(output.data()),reinterpret_cast<const char*>(output.data()+length));
      if(reply.contains("request_id")) replies.insert_or_assign(reply.at("request_id").get<std::string>(),std::move(reply));
    } else if(status==BridgePollStatus::failed && terminal_failure) {
      LMDJ_CHECK(bridge->failed() && runtime->failed());
    } else {
      if(status!=BridgePollStatus::empty) std::cerr<<"bridge poll status="<<static_cast<int>(status)
          <<" failed="<<bridge->failed()<<" runtime_failed="<<runtime->failed()<<'\n';
      LMDJ_CHECK(status==BridgePollStatus::empty);
    }
    proxy.pump();
  }
  Json reply(const std::string& request_id,bool terminal_failure=false) {
    const auto until=std::chrono::steady_clock::now()+std::chrono::seconds{5};
    while(!replies.contains(request_id) && std::chrono::steady_clock::now()<until) {tick(terminal_failure);std::this_thread::yield();}
    LMDJ_CHECK(replies.contains(request_id));auto result=replies.at(request_id);replies.erase(request_id);tick(terminal_failure);return result;
  }
  void stopped() {
    const auto until=std::chrono::steady_clock::now()+std::chrono::seconds{5};
    while(!runtime->recording_metadata_workers_stopped() && std::chrono::steady_clock::now()<until) {tick();std::this_thread::yield();}
    LMDJ_CHECK(runtime->recording_metadata_workers_stopped());
  }
};

void test_public_bridge_metadata_and_read_only_reopen() {
  for(unsigned variant=0;variant<3;++variant) {
    Fixture f{variant};const auto writes=f.platform->writes.load();
    for(unsigned pass=0;pass<2;++pass) {
      f.submit(id(1),"performance.recording.metadata",f.payload());const auto response=f.reply(id(1));
      if(variant==2) {
        LMDJ_CHECK(!response.at("ok").get<bool>() && response.at("error").at("code")=="COOK_FAILED");
        LMDJ_CHECK(response.at("error").at("details")==Json({{"storage_condition","artifact_mismatch"}}));
      } else {
        LMDJ_CHECK(response.at("ok").get<bool>());const auto& value=response.at("result");
        LMDJ_CHECK(value.at("project_id")==kProject && value.at("performance_id")==kPerformance);
        LMDJ_CHECK(value.at("project_revision")==0 && value.at("recording_revision")==17);
        LMDJ_CHECK(value.at("recording_artifact")==Json(f.artifact));
        if(variant==0) LMDJ_CHECK(value.at("audio_metadata")==Json({{"sample_rate",48000},{"channels",2},{"source_frames",48017}}) && value.at("audio_error").is_null());
        else LMDJ_CHECK(value.at("audio_metadata").is_null() && value.at("audio_error").at("code")=="UNSUPPORTED_AUDIO");
      }
      LMDJ_CHECK(f.platform->writes.load()==writes && f.platform->whole_audio.load()==0);
      LMDJ_CHECK(f.platform->leases.load()==1 && f.runtime->recording_metadata_workers_stopped());
    }
    const auto opened=f.runtime->dispatch("project.open",{{"project_id",kProject},{"pattern_id",kPattern}},{});
    LMDJ_CHECK(opened.at("ok").get<bool>());
    f.submit(id(2),"performance.recording.metadata",f.payload());LMDJ_CHECK(f.reply(id(2)).at("ok")== (variant!=2));
  }
}

void test_query_does_not_hold_control_and_rejects_concurrent_revision() {
  Fixture f;f.platform->gate->paused=true;
  f.submit(id(10),"performance.recording.metadata",f.payload());f.platform->gate->await(1);
  LMDJ_CHECK(!f.runtime->recording_metadata_workers_stopped());
  f.submit(id(11),"performance.rename",{{"performance_id",kPerformance},{"command_id",id(12)},{"expected_revision",0},{"name","Control progressed"}});
  LMDJ_CHECK(f.reply(id(11)).at("ok").get<bool>());
  {std::lock_guard lock(f.platform->gate->mutex);LMDJ_CHECK(!f.platform->gate->released && !f.platform->gate->expired);}
  f.platform->gate->release();const auto response=f.reply(id(10));
  LMDJ_CHECK(!response.at("ok").get<bool>() && response.at("error").at("code")=="REVISION_CONFLICT");
  LMDJ_CHECK(!f.bridge->failed() && !f.runtime->failed());
}

void test_missing_range_capability_remains_a_typed_refusal_without_fallback() {
  Fixture f{0,false};const auto writes=f.platform->writes.load();
  f.submit(id(8),"performance.recording.metadata",f.payload());const auto result=f.reply(id(8));
  LMDJ_CHECK(!result.at("ok").get<bool>() && result.at("error").at("code")=="IO_ERROR");
  LMDJ_CHECK(result.at("error").at("details")==Json({{"reason","bounded_read_unavailable"}}));
  LMDJ_CHECK(f.platform->ranges.load()==0 && f.platform->whole_audio.load()==0);
  LMDJ_CHECK(f.platform->writes.load()==writes && f.platform->leases.load()==1);
  LMDJ_CHECK(f.runtime->recording_metadata_workers_stopped() && !f.runtime->failed());
}

void test_cancel_reuse_and_close_keep_actual_worker_custody() {
  Fixture f;f.platform->gate->paused=true;
  f.submit(id(20),"performance.recording.metadata",f.payload());f.platform->gate->await(1);
  LMDJ_CHECK(f.bridge->cancel_query(id(20))==BridgeCancelStatus::cancelled);
  LMDJ_CHECK(!f.reply(id(20)).at("ok").get<bool>());
  LMDJ_CHECK(f.platform->leases.load()==2 && !f.runtime->recording_metadata_workers_stopped());
  f.submit(id(20),"performance.recording.metadata",f.payload()); // Original unfinished cell cannot be adopted.
  LMDJ_CHECK(!f.reply(id(20)).at("ok").get<bool>());
  f.submit(id(21),"host.close",Json::object());LMDJ_CHECK(f.reply(id(21)).at("result").at("state")=="closed");
  LMDJ_CHECK(!f.bridge->terminal_release_ready() && f.platform->leases.load()==1);
  auto foreign=project_io::make_native_project_storage_platform(f.root/"coordination");
  const auto busy=foreign->acquire_writer(f.bundle);LMDJ_CHECK(!busy.has_value());
  LMDJ_CHECK(busy.error().details.at("storage_condition")=="project_busy");
  f.platform->gate->release();f.stopped();
  for(unsigned i=0;i<5;++i) f.tick();
  LMDJ_CHECK(f.platform->leases.load()==0 && f.bridge->terminal_release_ready());
  LMDJ_CHECK(foreign->acquire_writer(f.bundle).has_value());
}

void test_same_project_reopen_retires_old_observer() {
  Fixture f;f.platform->gate->paused=true;
  f.submit(id(30),"performance.recording.metadata",f.payload());f.platform->gate->await(1);
  f.submit(id(31),"project.open",{{"project_id",kProject},{"pattern_id",kPattern}});
  LMDJ_CHECK(f.reply(id(31)).at("ok").get<bool>());
  for(unsigned n=0;n<4;++n) f.tick();
  LMDJ_CHECK(f.replies.contains(id(30))); // Owner retirement does not wait for the held read.
  LMDJ_CHECK(!f.reply(id(30)).at("ok").get<bool>());
  LMDJ_CHECK(!f.runtime->recording_metadata_workers_stopped());
  f.platform->gate->release();f.stopped();
  f.submit(id(32),"performance.recording.metadata",f.payload());LMDJ_CHECK(f.reply(id(32)).at("ok").get<bool>());
}

void test_cancelled_unfinished_jobs_retain_the_original_capacity() {
  Fixture f;f.platform->gate->paused=true;
  for(unsigned n=0;n<16;++n) {
    f.submit(id(100+n),"performance.recording.metadata",f.payload());f.platform->gate->await(n+1);
    LMDJ_CHECK(f.bridge->cancel_query(id(100+n))==BridgeCancelStatus::cancelled);
    LMDJ_CHECK(!f.reply(id(100+n)).at("ok").get<bool>());
  }
  f.submit(id(120),"performance.recording.metadata",f.payload());
  const auto full=f.reply(id(120));LMDJ_CHECK(full.at("error").at("code")=="WEB_RUNTIME_RESOURCE_LIMIT");
  LMDJ_CHECK(full.at("error").at("details").at("limit")==16);
  f.submit(id(121),"host.status",Json::object());LMDJ_CHECK(f.reply(id(121)).at("ok").get<bool>());
  LMDJ_CHECK(!f.runtime->failed());f.platform->gate->release();f.stopped();
  f.submit(id(100),"performance.recording.metadata",f.payload());LMDJ_CHECK(f.reply(id(100)).at("ok").get<bool>());
}

void test_original_deadline_expires_without_pretending_worker_exit() {
  Fixture f;f.platform->gate->paused=true;
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds{200};
  f.submit(id(40),"performance.recording.metadata",f.payload(),deadline);f.platform->gate->await(1);
  std::this_thread::sleep_until(deadline+std::chrono::milliseconds{1});
  LMDJ_CHECK(f.reply(id(40),true).at("error").at("code")=="HOST_TIMEOUT");
  LMDJ_CHECK(f.runtime->failed() && !f.bridge->terminal_release_ready());
  LMDJ_CHECK(!f.runtime->recording_metadata_workers_stopped());
  f.platform->gate->release();
  const auto until=std::chrono::steady_clock::now()+std::chrono::seconds{5};
  while(!f.runtime->recording_metadata_workers_stopped() && std::chrono::steady_clock::now()<until) {
    LMDJ_CHECK(f.bridge->service_terminal_retirement());std::this_thread::yield();
  }
  LMDJ_CHECK(f.runtime->recording_metadata_workers_stopped());
}

void test_cancellation_wins_during_continuation_serialization(unsigned iterations=1) {
  Fixture f;
  for(unsigned n=0;n<iterations;++n) {
    std::mutex mutex;std::condition_variable changed;
    bool serializing=false,cancelled=false,expired=false;
    auto cancel_result=BridgeCancelStatus::not_found;
    f.proxy.before_response=[&] {
      std::unique_lock lock(mutex);serializing=true;changed.notify_all();
      if(!changed.wait_for(lock,std::chrono::seconds{5},[&]{return cancelled;})) expired=true;
    };
    std::jthread caller([&] {
      {std::unique_lock lock(mutex);
        if(!changed.wait_for(lock,std::chrono::seconds{5},[&]{return serializing;})) return;}
      cancel_result=f.bridge->cancel_query(id(500+n));
      {std::lock_guard lock(mutex);cancelled=true;}changed.notify_all();
    });
    f.submit(id(500+n),"performance.recording.metadata",f.payload());
    const auto response=f.reply(id(500+n));caller.join();f.proxy.before_response={};
    LMDJ_CHECK(!expired && cancel_result==BridgeCancelStatus::cancelled);
    LMDJ_CHECK(!response.at("ok").get<bool>());
    LMDJ_CHECK(response.at("error").at("code")=="HOST_STATE_INVALID");
    LMDJ_CHECK(f.runtime->recording_metadata_workers_stopped() && f.platform->leases.load()==1);
    LMDJ_CHECK(!f.bridge->failed() && !f.runtime->failed());
  }
}

void test_direct_native_destruction_does_not_destroy_borrowed_worker_inputs() {
  Fixture f;f.platform->gate->paused=true;
  f.submit(id(700),"performance.recording.metadata",f.payload());f.platform->gate->await(1);
  f.proxy.tasks.clear();f.bridge.reset();f.runtime.reset();
  LMDJ_CHECK(f.platform->leases.load()==1); // Unprotected direct destruction did not release I/O.
  auto foreign=project_io::make_native_project_storage_platform(f.root/"coordination");
  LMDJ_CHECK(!foreign->acquire_writer(f.bundle).has_value());
  f.platform->gate->release();
  const auto until=std::chrono::steady_clock::now()+std::chrono::seconds{5};
  while(f.platform.use_count()!=1 && std::chrono::steady_clock::now()<until) std::this_thread::yield();
  LMDJ_CHECK(f.platform.use_count()==1 && f.platform->leases.load()==0);
  LMDJ_CHECK(foreign->acquire_writer(f.bundle).has_value());
  // This proves heap/platform lifetime, not join or formal Module disposal.
}
}  // namespace

int main(int argc,char** argv) {
  try {
    if(argc==2 && std::string_view(argv[1])=="--stress") {
      test_cancellation_wins_during_continuation_serialization(64);
      std::cout<<"Recording metadata cancellation race stress: PASS\n";return 0;
    }
    std::cout<<"metadata/reopen\n"<<std::flush;
    test_public_bridge_metadata_and_read_only_reopen();
    test_missing_range_capability_remains_a_typed_refusal_without_fallback();
    std::cout<<"concurrent Control\n"<<std::flush;
    test_query_does_not_hold_control_and_rejects_concurrent_revision();
    std::cout<<"cancel/reuse/close\n"<<std::flush;
    test_cancel_reuse_and_close_keep_actual_worker_custody();
    std::cout<<"same owner replacement\n"<<std::flush;
    test_same_project_reopen_retires_old_observer();
    std::cout<<"retained capacity\n"<<std::flush;
    test_cancelled_unfinished_jobs_retain_the_original_capacity();
    std::cout<<"original deadline\n"<<std::flush;
    test_original_deadline_expires_without_pretending_worker_exit();
    std::cout<<"cancellation publication race\n"<<std::flush;
    test_cancellation_wins_during_continuation_serialization();
    std::cout<<"Native detached input lifetime\n"<<std::flush;
    test_direct_native_destruction_does_not_destroy_borrowed_worker_inputs();
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
  std::cout<<"Recording metadata query integration: PASS\n";
}
