#include <lmdj/facade/application.hpp>

#include <chrono>
#include <filesystem>
#include <map>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "tests/core/support/test.hpp"
#include "packages/application-facade/src/testing_hooks.hpp"

namespace {
using namespace lmdj;

std::string uuid(std::uint32_t suffix) {
  const auto tail = std::to_string(suffix);
  return "00000000-0000-4000-8000-" +
         std::string(12 - tail.size(), '0') + tail;
}

class TempDirectory {
 public:
  TempDirectory() {
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-runtime-export-" + std::to_string(
                std::chrono::steady_clock::now().time_since_epoch().count()));
    LMDJ_CHECK(std::filesystem::create_directory(path_));
  }
  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }
  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

facade::ApplicationConfig config(const std::filesystem::path& root) {
  return facade::ApplicationConfig{
      root, std::make_shared<provider::Registry>(),
      provider::ProviderPolicy{{"local"}, {"public"}, {"proof.execute"}},
      [] { return std::string("2026-09-08T00:00:00.000Z"); },
      std::nullopt, nullptr, nullptr, nullptr, nullptr,
      facade::make_unavailable_performance_replay_controller()};
}

std::vector<std::byte> wave(std::uint16_t first) {
  std::vector<std::byte> bytes;
  const auto word = [&bytes](std::uint32_t value, unsigned width) {
    for (unsigned index = 0; index < width; ++index) {
      bytes.push_back(static_cast<std::byte>((value >> (index * 8U)) & 255U));
    }
  };
  const auto tag = [&bytes](std::string_view value) {
    for (const char ch : value) bytes.push_back(static_cast<std::byte>(ch));
  };
  tag("RIFF"); word(44, 4); tag("WAVEfmt "); word(16, 4);
  word(1, 2); word(1, 2); word(48000, 4); word(96000, 4);
  word(2, 2); word(16, 2); tag("data"); word(8, 4);
  word(first, 2); word(32767, 2); word(0, 2); word(65535, 2);
  return bytes;
}

// Test-only byte inventory proves export never writes authoring state. No Host
// parses a Project: all creation, imports and edits go through the Facade.
std::map<std::filesystem::path, std::string> inventory(
    const std::filesystem::path& root) {
  std::map<std::filesystem::path, std::string> result;
  for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
    if (!entry.is_regular_file()) continue;
    std::ifstream input(entry.path(), std::ios::binary);
    result.emplace(entry.path().lexically_relative(root),
                   std::string(std::istreambuf_iterator<char>(input), {}));
  }
  return result;
}

void test_export() {
  TempDirectory temporary;
  facade::Application application(config(temporary.path() / "workspace"));
  const auto path = temporary.path() / "source.lmdj";
  const foundation::ProjectId project_id{uuid(1)};
  const foundation::PatternId pattern_id{uuid(2)};
  LMDJ_CHECK(application.create_initial_project({
      path, project_id, 120,
      domain::Pattern{pattern_id, 1, {{{0, 0}, 0, 240, 127}}}}).has_value());
  std::uint64_t revision = 0;
  std::uint32_t command = 100;
  const auto import = [&](std::uint32_t asset, std::uint16_t first) {
    const auto bytes = wave(first);
    auto result = application.import_artifact_bytes({
        path, {foundation::CommandId{uuid(command++)}, revision},
        foundation::AssetId{uuid(asset)}, "audio/wav", bytes});
    LMDJ_CHECK(result.has_value());
    LMDJ_CHECK(result.value().state.revision == ++revision);
  };
  const auto assign = [&](unsigned bank, unsigned pad, std::uint32_t asset) {
    const auto result = application.command({
        {"operation", "pad.assign"}, {"project_path", path.generic_string()},
        {"command_id", uuid(command++)}, {"expected_revision", revision},
        {"slot", {{"bank", bank}, {"pad", pad}}}, {"asset_id", uuid(asset)}});
    LMDJ_CHECK(result.at("ok") == true);
    ++revision;
  };
  import(10, 32768); import(11, 123); import(12, 456);
  assign(0, 0, 10); assign(2, 3, 11); assign(3, 15, 12);
  facade::RuntimeContentExportRequest request{
      path, project_id, pattern_id, revision, {{2, 3}},
      {4096, 4096, 1024, 64, 1024}};
  const auto before = inventory(path);
  const auto exported = application.export_runtime_content(request);
  LMDJ_CHECK(exported.has_value());
  const auto decoded = cooker::decode_runtime_content(
      exported.value().bytes, exported.value().identity, request.limits);
  LMDJ_CHECK(decoded.has_value());
  const auto& snapshot = *decoded.value();
  LMDJ_CHECK(snapshot.project_id == project_id);
  LMDJ_CHECK(snapshot.pattern_id == pattern_id);
  LMDJ_CHECK(snapshot.project_revision == revision);
  LMDJ_CHECK(snapshot.pads.size() == 2);
  LMDJ_CHECK((snapshot.pads.at(0).slot == domain::PadSlotId{0, 0}));
  LMDJ_CHECK((snapshot.pads.at(1).slot == domain::PadSlotId{2, 3}));
  LMDJ_CHECK(snapshot.events.size() == 1);
  LMDJ_CHECK(snapshot.pads.at(0).sample->interleaved.at(0) == -32768);
  LMDJ_CHECK(snapshot.pads.at(1).sample->interleaved.at(0) == 123);
  const auto repeated = application.export_runtime_content(request);
  LMDJ_CHECK(repeated.has_value());
  LMDJ_CHECK(repeated.value().bytes == exported.value().bytes);
  LMDJ_CHECK(inventory(path) == before);
  auto union_selection = request;
  union_selection.live_pad_slots = {{2, 3}, {0, 0}};
  const auto same_union = application.export_runtime_content(union_selection);
  LMDJ_CHECK(same_union.has_value());
  LMDJ_CHECK(same_union.value().identity == exported.value().identity);
  facade::Application reopened(config(temporary.path() / "second-workspace"));
  const auto reopened_export = reopened.export_runtime_content(request);
  LMDJ_CHECK(reopened_export.has_value());
  LMDJ_CHECK(reopened_export.value().identity == exported.value().identity);
  auto events_only = request;
  events_only.live_pad_slots.clear();
  const auto minimal = application.export_runtime_content(events_only);
  LMDJ_CHECK(minimal.has_value());
  const auto minimal_snapshot = cooker::decode_runtime_content(
      minimal.value().bytes, minimal.value().identity, request.limits);
  LMDJ_CHECK(minimal_snapshot.has_value());
  LMDJ_CHECK(minimal_snapshot.value()->pads.size() == 1);

  const auto rejects = [&](const facade::RuntimeContentExportRequest& invalid,
                           foundation::ErrorCode code) {
    const auto result = application.export_runtime_content(invalid);
    LMDJ_CHECK(!result.has_value());
    LMDJ_CHECK(result.error().code == code);
    LMDJ_CHECK(inventory(path) == before);
  };
  auto invalid = request; invalid.project_path = "relative.lmdj";
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.project_id = foundation::ProjectId{uuid(99)};
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.project_id = foundation::ProjectId{"invalid"};
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.pattern_id = foundation::PatternId{"invalid"};
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.expected_revision = revision - 1;
  rejects(invalid, foundation::ErrorCode::revision_conflict);
  invalid = request; invalid.pattern_id = foundation::PatternId{uuid(99)};
  rejects(invalid, foundation::ErrorCode::not_found);
  invalid = request; invalid.live_pad_slots = {{4, 0}};
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.live_pad_slots = {{2, 3}, {2, 3}};
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.live_pad_slots.resize(65);
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  invalid = request; invalid.live_pad_slots = {{0, 1}};
  rejects(invalid, foundation::ErrorCode::missing_asset);
  invalid = request; invalid.limits.maximum_encoded_bytes = 1;
  rejects(invalid, foundation::ErrorCode::invalid_argument);
  facade::testing::ApiEntryHook fault{
      nullptr, [](void*) { throw std::runtime_error("injected export entry failure"); }};
  facade::testing::set_api_entry_hook(&fault);
  rejects(request, foundation::ErrorCode::internal_error);
  const auto after_fault = application.export_runtime_content(request);
  LMDJ_CHECK(after_fault.has_value());
  LMDJ_CHECK(after_fault.value().identity == exported.value().identity);

  // Corrupt a fixture Artifact in place without changing its declared identity.
  const auto corrupt = [&](std::uint16_t first) {
    const auto original = wave(first);
    const std::string original_bytes(
        reinterpret_cast<const char*>(original.data()), original.size());
    std::size_t matches = 0;
    std::filesystem::path target;
    for (const auto& [relative, contents] : inventory(path / "assets")) {
      if (contents != original_bytes) continue;
      std::fstream file(path / "assets" / relative,
                        std::ios::in | std::ios::out | std::ios::binary);
      file.seekp(-1, std::ios::end);
      file.put('\0');
      file.flush();
      LMDJ_CHECK(file.good());
      ++matches;
      target = path / "assets" / relative;
    }
    LMDJ_CHECK(matches == 1);
    return target;
  };
  // Existing ProjectStore load validates every Asset before detached Cook.
  // Export must not bypass that integrity boundary, even for an unused Pad.
  for (const std::uint16_t first : {456, 123, 32768}) {
    const auto target = corrupt(first);
    const auto damaged = inventory(path);
    LMDJ_CHECK(!application.export_runtime_content(request).has_value());
    LMDJ_CHECK(!application.export_runtime_content(events_only).has_value());
    LMDJ_CHECK(inventory(path) == damaged);
    const auto original = wave(first);
    std::ofstream restored(target, std::ios::binary | std::ios::trunc);
    restored.write(reinterpret_cast<const char*>(original.data()),
                   static_cast<std::streamsize>(original.size()));
    restored.close();
    LMDJ_CHECK(restored.good());
    LMDJ_CHECK(inventory(path) == before);
    const auto retry = application.export_runtime_content(request);
    LMDJ_CHECK(retry.has_value());
    LMDJ_CHECK(retry.value().bytes == exported.value().bytes);
  }
}
}  // namespace

int main() {
  test_export();
  return 0;
}
