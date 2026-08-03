#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <filesystem>
#include <fstream>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <emscripten.h>
#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/project_io/take_journal.hpp>

namespace lmdj::project_io {
std::shared_ptr<ProjectStoragePlatform> make_web_project_storage_platform();
}

extern "C" int lmdj_opfs_append_flush_count();

namespace {

using lmdj::foundation::Result;

void require(bool condition, std::string message) {
  if (!condition) throw std::runtime_error(std::move(message));
}

template <typename T>
T value(Result<T> result, const char* operation) {
  if (!result.has_value()) throw std::runtime_error(operation);
  return std::move(result.value());
}

void success(Result<void> result, const char* operation) {
  if (!result.has_value()) throw std::runtime_error(operation);
}

std::span<const std::byte> bytes(const std::string& input) {
  return {reinterpret_cast<const std::byte*>(input.data()), input.size()};
}

std::string text(const std::vector<std::byte>& input) {
  return {reinterpret_cast<const char*>(input.data()), input.size()};
}

std::string uuid(std::string_view suffix) {
  return "00000000-0000-4000-8000-" + std::string(12 - suffix.size(), '0') +
         std::string{suffix};
}

std::string query(std::string_view name) {
  std::array<char, 192> output{};
  MAIN_THREAD_EM_ASM({
    const value = new URL(window.location.href).searchParams.get(UTF8ToString($0)) ?? "";
    stringToUTF8(value, $1, $2);
  }, name.data(), output.data(), output.size());
  return output.data();
}

nlohmann::json run_suite() {
  using namespace lmdj;
  auto platform = project_io::make_web_project_storage_platform();
  require(platform != nullptr, "Web platform factory returned null");

  const auto action = query("action");
  const auto requested_bundle = query("bundle");
  if (!action.empty()) {
    require(!requested_bundle.empty(), "fault bundle is missing");
    const auto fault_bundle = std::filesystem::path{"/lmdj-workspace"} /
        (requested_bundle + ".lmdj");
    project_io::ProjectStore fault_store{platform};
    if (action == "prepare") {
      const auto present = value(platform->exists(fault_bundle / "manifest.json"), "fault exists");
      if (!present) {
        auto initial = value(domain::create_project(
            foundation::ProjectId{uuid("11")}, 120), "fault create state");
        success(fault_store.create(fault_bundle, initial), "fault prepare");
      }
    } else if (action == "advance") {
      const auto current = value(fault_store.load(fault_bundle), "fault advance load");
      domain::CreatePattern command{
          domain::CommandMeta{foundation::CommandId{uuid("12")}, current.revision},
          domain::Pattern{foundation::PatternId{uuid("13")}, 1,
                          {domain::PatternEvent{domain::PadSlotId{0, 0}, 0, 100}}}};
      (void)value(fault_store.execute(fault_bundle, domain::Command{command}),
                  "fault advance execute");
    } else if (action != "reopen") {
      throw std::runtime_error("unknown fault action");
    }
    const auto reopened = value(fault_store.load(fault_bundle), "fault common reopen");
    return {{"complete", true}, {"result", {{"revision", reopened.revision},
                                             {"bundle", requested_bundle}}}};
  }

  const auto sequence = std::chrono::steady_clock::now().time_since_epoch().count();
  const auto bundle = std::filesystem::path{"/lmdj-workspace"} /
      ("parity-" + std::to_string(sequence) + ".lmdj");

  project_io::ProjectStore store{platform};
  auto initial = value(domain::create_project(
      foundation::ProjectId{uuid("1")}, 120), "create project state");
  success(store.create(bundle, initial), "ProjectStore create");
  const auto loaded = value(store.load(bundle), "ProjectStore initial load");
  require(loaded == initial, "ProjectStore initial parity");

  domain::CreatePattern command{
      domain::CommandMeta{foundation::CommandId{uuid("2")}, 0},
      domain::Pattern{
          foundation::PatternId{uuid("3")}, 1,
          {domain::PatternEvent{domain::PadSlotId{0, 0}, 0, 100}}}};
  const auto applied = value(store.execute(bundle, domain::Command{command}),
                             "ProjectStore execute");
  require(applied.state.revision == 1, "ProjectStore transaction revision");
  require(value(store.load(bundle), "ProjectStore replay load").revision == 1,
          "ProjectStore replay revision");

  project_io::TakeJournal journal{platform};
  const foundation::TakeId take_id{uuid("4")};
  success(journal.begin(bundle, take_id, 1, 48000), "TakeJournal begin");
  success(journal.append(
      bundle, take_id, domain::RawTakeEvent{domain::PadSlotId{0, 0}, 12, 101}),
      "TakeJournal append");
  const auto active = value(journal.read_active(bundle, take_id), "TakeJournal read");
  require(active.events.size() == 1 && active.events.front().frame_offset == 12,
          "TakeJournal parity");

  project_io::TakeJournal concurrent_a{platform};
  project_io::TakeJournal concurrent_b{platform};
  bool append_a = false;
  bool append_b = false;
  std::thread first_append([&] {
    append_a = concurrent_a.append(
        bundle, take_id, domain::RawTakeEvent{domain::PadSlotId{0, 1}, 20, 90})
                   .has_value();
  });
  std::thread second_append([&] {
    append_b = concurrent_b.append(
        bundle, take_id, domain::RawTakeEvent{domain::PadSlotId{0, 2}, 20, 91})
                   .has_value();
  });
  first_append.join();
  second_append.join();
  require(append_a && append_b, "concurrent TakeJournal append");
  require(value(journal.read_active(bundle, take_id), "concurrent read").events.size() == 3,
          "concurrent append lost acknowledgement");

  const auto contract = bundle / "contract";
  success(platform->ensure_directory(contract), "contract directory");
  const auto bridge_file = contract / "bridge-visible.bin";
  success(platform->create_immutable(bridge_file, bytes("bridge")), "bridge coherence seed");
  std::ifstream mounted_read{bridge_file, std::ios::binary};
  require(std::string{std::istreambuf_iterator<char>{mounted_read}, {}} == "bridge",
          "platform write is not visible through WasmFS mount");
  const auto mounted_file = contract / "mount-visible.bin";
  {
    std::ofstream mounted_write{mounted_file, std::ios::binary | std::ios::trunc};
    mounted_write << "mount";
    require(mounted_write.good(), "WasmFS mount write failed");
  }
  require(text(value(platform->read_complete(mounted_file), "mount coherence read")) == "mount",
          "WasmFS write is not visible through platform bridge");
  const auto append_path = contract / "append.bin";
  success(platform->create_immutable(append_path, bytes("abc")), "append seed");
  int flushes = lmdj_opfs_append_flush_count();
  success(platform->append_durable(append_path, 3, bytes("d")), "clean append");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "clean append flush count");
  flushes += 1;
  require(text(value(platform->read_complete(append_path), "read clean")) == "abcd",
          "clean-prefix append");
  success(platform->append_durable(append_path, 2, bytes("XY")), "torn repair");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "repair flush count");
  flushes += 1;
  require(text(value(platform->read_complete(append_path), "read repaired")) == "abXY",
          "torn-tail repair");
  const std::array<std::byte, 3> binary{std::byte{0}, std::byte{0xff}, std::byte{10}};
  success(platform->append_durable(append_path, 4, binary), "binary append");
  require(lmdj_opfs_append_flush_count() == flushes + 1, "binary flush count");
  flushes += 1;
  const auto before_oversized = value(platform->read_complete(append_path), "pre oversized");
  require(!platform->append_durable(append_path, 999, bytes("bad")).has_value(),
          "oversized prefix accepted");
  require(lmdj_opfs_append_flush_count() == flushes, "oversized prefix flushed");
  require(value(platform->read_complete(append_path), "post oversized") == before_oversized,
          "oversized prefix mutated file");

  const auto replacement = contract / "replacement.bin";
  success(platform->replace_complete(replacement, bytes("old")), "old replacement");
  success(platform->replace_complete(replacement, bytes("new")), "new replacement");
  require(text(value(platform->read_complete(replacement), "replacement read")) == "new",
          "complete replacement");

  success(platform->create_immutable(contract / "z", bytes("")), "sort z");
  success(platform->create_immutable(contract / "a", bytes("")), "sort a");
  success(platform->create_immutable(contract / "\xc3\xa9", bytes("")), "sort utf8");
  const auto names = value(platform->list_names(contract), "sorted iteration");
  const auto a = std::find(names.begin(), names.end(), "a");
  const auto z = std::find(names.begin(), names.end(), "z");
  const auto accented = std::find(names.begin(), names.end(), "\xc3\xa9");
  require(a < z && z < accented, "unsigned UTF-8 sorting");

  auto first_lease = value(platform->acquire_writer(bundle), "first lease");
  const auto competing = project_io::make_web_project_storage_platform()->acquire_writer(bundle);
  require(!competing.has_value() &&
              competing.error().details.value("storage_condition", "") == "project_busy",
          "competing writer did not fail fast");
  first_lease.reset();
  auto reacquired = value(platform->acquire_writer(bundle), "lease reacquire");
  reacquired.reset();

  return {
      {"complete", true},
      {"result", {
          {"projectStore", "pass"}, {"takeJournal", "pass"},
          {"replay", "pass"}, {"recovery", "pass"},
          {"appendContracts", "pass"}, {"lease", "pass"},
          {"directoryBarrier", "absent"},
          {"replacementFaultPoints", {"before_write", "during_write", "before_close",
                                        "after_close", "before_cleanup"}}
      }}
  };
}

}  // namespace

int main() {
  nlohmann::json report;
  try {
    report = run_suite();
  } catch (const std::exception& error) {
    report = {{"complete", true}, {"result", {{"error", error.what()}}}};
  }
  const std::string encoded = report.dump();
  MAIN_THREAD_EM_ASM({ window.lmdjProjectIoWeb = JSON.parse(UTF8ToString($0)); },
                     encoded.c_str());
  emscripten_exit_with_live_runtime();
  return 0;
}
