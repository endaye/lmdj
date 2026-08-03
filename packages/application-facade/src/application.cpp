#include <lmdj/facade/application.hpp>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <limits>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <lmdj/audio/offline_renderer.hpp>
#include <lmdj/cooker/project_cooker.hpp>
#include <lmdj/domain/commands.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/project_store.hpp>
#include <lmdj/project_io/take_journal.hpp>
#include <lmdj/provider/capability.hpp>

namespace lmdj::facade {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint32_t kSampleRate = 48'000;

class InvalidRequest final : public std::runtime_error {
 public:
  explicit InvalidRequest(std::string message)
      : std::runtime_error(std::move(message)) {}
};

enum class OperationKind {
  command,
  query,
};

const std::map<std::string, OperationKind>& operations() {
  static const std::map<std::string, OperationKind> value{
      {"asset.import", OperationKind::command},
      {"attempt.inspect", OperationKind::query},
      {"pad.assign", OperationKind::command},
      {"project.create", OperationKind::command},
      {"project.inspect", OperationKind::query},
      {"provider.list", OperationKind::query},
      {"provider.run", OperationKind::command},
      {"provider.select", OperationKind::command},
      {"provider.selected", OperationKind::query},
      {"render.offline", OperationKind::command},
      {"snapshot.cook", OperationKind::query},
      {"take.append", OperationKind::command},
      {"take.begin", OperationKind::command},
      {"take.commit", OperationKind::command},
      {"take.recoverable.list", OperationKind::query},
  };
  return value;
}

bool valid_utf8(std::string_view value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const auto first = static_cast<unsigned char>(value[offset]);
    if (first == 0) {
      return false;
    }
    if (first <= 0x7fU) {
      ++offset;
      continue;
    }
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first >= 0xc2U && first <= 0xdfU) {
      length = 2;
      code_point = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      length = 3;
      code_point = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return false;
    }
    if (offset + length > value.size()) {
      return false;
    }
    for (std::size_t index = 1; index < length; ++index) {
      const auto byte =
          static_cast<unsigned char>(value[offset + index]);
      if ((byte & 0xc0U) != 0x80U) {
        return false;
      }
      code_point = (code_point << 6U) | (byte & 0x3fU);
    }
    if ((length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U) ||
        code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return false;
    }
    offset += length;
  }
  return true;
}

bool all_strings_valid(const nlohmann::json& value) {
  if (value.is_string()) {
    return valid_utf8(value.get_ref<const std::string&>());
  }
  if (value.is_array()) {
    return std::all_of(
        value.begin(), value.end(), all_strings_valid);
  }
  if (value.is_object()) {
    for (auto iterator = value.begin(); iterator != value.end(); ++iterator) {
      if (!valid_utf8(iterator.key()) || !all_strings_valid(iterator.value())) {
        return false;
      }
    }
  }
  return true;
}

[[noreturn]] void invalid(std::string message) {
  throw InvalidRequest(std::move(message));
}

void require(bool condition, std::string message) {
  if (!condition) {
    invalid(std::move(message));
  }
}

bool exact_keys(
    const nlohmann::json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(
      keys.begin(), keys.end(), [&value](const auto key) {
        return value.contains(std::string(key));
      });
}

const std::string& string_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto& value = request.at(std::string(key));
  require(value.is_string(), std::string(key) + " must be a string");
  const auto& result = value.get_ref<const std::string&>();
  require(valid_utf8(result), std::string(key) + " is not valid UTF-8");
  return result;
}

std::uint64_t unsigned_field(
    const nlohmann::json& request,
    std::string_view key,
    std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max()) {
  const auto& value = request.at(std::string(key));
  std::uint64_t parsed = 0;
  if (value.is_number_unsigned()) {
    parsed = value.get<std::uint64_t>();
  } else if (value.is_number_integer()) {
    const auto signed_value = value.get<std::int64_t>();
    require(signed_value >= 0, std::string(key) + " must be nonnegative");
    parsed = static_cast<std::uint64_t>(signed_value);
  } else {
    invalid(std::string(key) + " must be an integer");
  }
  require(parsed <= maximum, std::string(key) + " is out of range");
  return parsed;
}

std::filesystem::path absolute_path_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto path = std::filesystem::path(string_field(request, key));
  require(path.is_absolute(), std::string(key) + " must be absolute");
  require(
      path.lexically_normal() == path,
      std::string(key) + " must be normalized");
  return path;
}

std::string uuid_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto value = string_field(request, key);
  require(
      domain::is_valid_uuid(value),
      std::string(key) + " must be a lowercase UUID");
  return value;
}

bool windows_reserved_name(std::string_view value) {
  auto normalized = std::string(value);
  std::transform(
      normalized.begin(),
      normalized.end(),
      normalized.begin(),
      [](unsigned char character) {
        return static_cast<char>(std::toupper(character));
      });
  const auto dot = normalized.find('.');
  const auto base = normalized.substr(0, dot);
  if (base == "CON" || base == "PRN" || base == "AUX" ||
      base == "NUL") {
    return true;
  }
  return base.size() == 4 &&
         (base.starts_with("COM") || base.starts_with("LPT")) &&
         base.at(3) >= '1' && base.at(3) <= '9';
}

bool safe_file_id(std::string_view value) {
  if (value.empty() || value.size() > 128 || value == "." ||
      value == ".." || windows_reserved_name(value) ||
      value.back() == '.' || value.back() == ' ') {
    return false;
  }
  return std::all_of(
      value.begin(), value.end(), [](unsigned char character) {
        return std::isalnum(character) != 0 ||
               character == '.' || character == '_' ||
               character == '-';
      });
}

std::string file_id_field(
    const nlohmann::json& request,
    std::string_view key) {
  const auto value = string_field(request, key);
  require(safe_file_id(value), std::string(key) + " is unsafe");
  return value;
}

domain::PadSlotId slot_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"bank", "pad"}),
      "slot shape is invalid");
  const auto bank = unsigned_field(encoded, "bank", 3);
  const auto pad = unsigned_field(encoded, "pad", 15);
  return domain::PadSlotId{
      static_cast<std::uint8_t>(bank),
      static_cast<std::uint8_t>(pad),
  };
}

domain::Pattern pattern_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"pattern_id", "bars", "events"}),
      "pattern shape is invalid");
  const auto pattern_id = uuid_field(encoded, "pattern_id");
  const auto bars = unsigned_field(encoded, "bars", 8);
  require(
      bars == 1 || bars == 2 || bars == 4 || bars == 8,
      "pattern bars are unsupported");
  const auto& events = encoded.at("events");
  require(events.is_array(), "pattern events must be an array");
  std::vector<domain::PatternEvent> parsed;
  parsed.reserve(events.size());
  const auto step_limit = bars * 16U;
  for (const auto& event : events) {
    require(
        exact_keys(event, {"slot", "step", "velocity"}),
        "pattern event shape is invalid");
    const auto step = unsigned_field(event, "step", step_limit - 1U);
    const auto velocity = unsigned_field(event, "velocity", 127);
    require(velocity > 0, "pattern velocity must be positive");
    parsed.push_back(
        domain::PatternEvent{
            slot_value(event.at("slot")),
            static_cast<std::uint32_t>(step),
            static_cast<std::uint8_t>(velocity),
        });
  }
  return domain::Pattern{
      foundation::PatternId{pattern_id},
      static_cast<std::uint8_t>(bars),
      std::move(parsed),
  };
}

domain::RawTakeEvent raw_event_value(const nlohmann::json& encoded) {
  require(
      exact_keys(encoded, {"slot", "frame_offset", "velocity"}),
      "raw event shape is invalid");
  const auto frame_offset =
      unsigned_field(
          encoded,
          "frame_offset",
          std::numeric_limits<std::uint32_t>::max());
  const auto velocity = unsigned_field(encoded, "velocity", 127);
  require(velocity > 0, "raw event velocity must be positive");
  return domain::RawTakeEvent{
      slot_value(encoded.at("slot")),
      static_cast<std::uint32_t>(frame_offset),
      static_cast<std::uint8_t>(velocity),
  };
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

nlohmann::json raw_event_json(const domain::RawTakeEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"frame_offset", event.frame_offset},
      {"velocity", event.velocity},
  };
}

nlohmann::json pattern_event_json(const domain::PatternEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"step", event.step},
      {"velocity", event.velocity},
  };
}

nlohmann::json project_json(const domain::ProjectState& state) {
  auto banks = nlohmann::json::array();
  for (std::size_t bank = 0; bank < state.banks.size(); ++bank) {
    auto pads = nlohmann::json::array();
    for (const auto& pad : state.banks.at(bank)) {
      pads.push_back(
          {
              {"pad", pad.id.pad},
              {"asset_id",
               pad.asset_id.has_value()
                   ? nlohmann::json(pad.asset_id->value())
                   : nlohmann::json(nullptr)},
          });
    }
    banks.push_back({{"bank", bank}, {"pads", std::move(pads)}});
  }
  auto assets = nlohmann::json::object();
  for (const auto& [id, asset] : state.assets) {
    assets[id.value()] = {{"artifact", asset.artifact}};
  }
  auto takes = nlohmann::json::object();
  for (const auto& [id, take] : state.takes) {
    auto events = nlohmann::json::array();
    for (const auto& event : take.events) {
      events.push_back(raw_event_json(event));
    }
    takes[id.value()] = {
        {"sample_rate", take.sample_rate},
        {"events", std::move(events)},
    };
  }
  auto patterns = nlohmann::json::object();
  for (const auto& [id, pattern] : state.patterns) {
    auto events = nlohmann::json::array();
    for (const auto& event : pattern.events) {
      events.push_back(pattern_event_json(event));
    }
    patterns[id.value()] = {
        {"bars", pattern.bars},
        {"events", std::move(events)},
    };
  }
  return {
      {"contract", "lmdj.project.v1"},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"bpm", state.bpm},
      {"banks", std::move(banks)},
      {"assets", std::move(assets)},
      {"takes", std::move(takes)},
      {"patterns", std::move(patterns)},
  };
}

nlohmann::json error_envelope(const Error& error) {
  const auto message =
      valid_utf8(error.message)
          ? error.message
          : std::string("module returned invalid UTF-8");
  auto details =
      all_strings_valid(error.details)
          ? error.details
          : nlohmann::json::object();
  return {
      {"ok", false},
      {"error",
       {
           {"code", foundation::error_code_name(error.code)},
           {"message", message},
           {"details", std::move(details)},
       }},
  };
}

nlohmann::json success_envelope(
    nlohmann::json result,
    std::optional<std::uint64_t> revision) {
  return {
      {"ok", true},
      {"result", std::move(result)},
      {"project_revision",
       revision.has_value()
           ? nlohmann::json(*revision)
           : nlohmann::json(nullptr)},
  };
}

nlohmann::json internal_error() {
  return error_envelope(
      Error{
          ErrorCode::internal_error,
          "unexpected application failure",
      });
}

nlohmann::json model_identity_json(
    const std::optional<provider::ModelIdentity>& identity) {
  if (!identity.has_value()) {
    return nullptr;
  }
  return {
      {"id", identity->id},
      {"version", identity->version},
      {"artifact_sha256", identity->artifact_sha256},
  };
}

nlohmann::json provider_descriptor_json(
    const provider::ProviderDescriptor& descriptor) {
  auto capabilities = nlohmann::json::array();
  for (const auto& capability : descriptor.capabilities) {
    capabilities.push_back(provider::capability_contract_json(capability));
  }
  return {
      {"id", descriptor.id},
      {"version", descriptor.version},
      {"artifact_sha256", descriptor.artifact_sha256},
      {"model_identity", model_identity_json(descriptor.model_identity)},
      {"capabilities", std::move(capabilities)},
  };
}

nlohmann::json terminal_attempt_json(
    const provider::TerminalAttempt& attempt) {
  auto candidate_ids = nlohmann::json::array();
  for (const auto& id : attempt.candidate_ids) {
    candidate_ids.push_back(id.value());
  }
  auto artifacts = nlohmann::json::array();
  for (const auto& artifact : attempt.artifacts) {
    artifacts.push_back(artifact);
  }
  auto inputs = nlohmann::json::array();
  for (const auto& input : attempt.request.inputs) {
    inputs.push_back(input);
  }
  auto minted_outputs = nlohmann::json::array();
  for (const auto& output : attempt.minted_outputs) {
    minted_outputs.push_back(output);
  }
  auto candidate_outputs = nlohmann::json::array();
  for (const auto& output : attempt.candidate_outputs) {
    candidate_outputs.push_back(output);
  }
  auto error = nlohmann::json(nullptr);
  if (attempt.error.has_value()) {
    error = {
        {"code", foundation::error_code_name(attempt.error->code)},
        {"message", attempt.error->message},
        {"details", attempt.error->details},
    };
  }
  return {
      {"attempt_id", attempt.attempt_id.value()},
      {"status",
       attempt.status == provider::AttemptStatus::succeeded
           ? "succeeded"
           : "failed"},
      {"started_at", attempt.started_at},
      {"ended_at", attempt.ended_at},
      {"provider",
       {
           {"id", attempt.provider.id},
           {"version", attempt.provider.version},
           {"artifact_sha256", attempt.provider.artifact_sha256},
           {"model_identity",
            model_identity_json(attempt.provider.model_identity)},
       }},
      {"capability",
       {
           {"id", attempt.capability.id},
           {"contract", attempt.capability.contract},
           {"version", attempt.capability.version},
       }},
      {"request",
       {
           {"capability", attempt.request.capability},
           {"inputs", std::move(inputs)},
           {"parameters_sha256", attempt.request.parameters_sha256},
           {"data_classification", attempt.request.data_classification},
           {"platform", attempt.request.platform},
           {"region", attempt.request.region},
           {"required_permissions", attempt.request.required_permissions},
       }},
      {"candidate_ids", std::move(candidate_ids)},
      {"candidate_outputs", std::move(candidate_outputs)},
      {"minted_outputs", std::move(minted_outputs)},
      {"artifacts", std::move(artifacts)},
      {"error", std::move(error)},
  };
}

bool path_is_inside_bundle(const std::filesystem::path& path) {
  for (const auto& component : path) {
    if (component.extension() == ".lmdj") {
      return true;
    }
  }
  return false;
}

class OwnedDescriptor {
 public:
  explicit OwnedDescriptor(int descriptor) : descriptor_(descriptor) {}
  OwnedDescriptor(const OwnedDescriptor&) = delete;
  OwnedDescriptor& operator=(const OwnedDescriptor&) = delete;
  OwnedDescriptor(OwnedDescriptor&& other) noexcept
      : descriptor_(std::exchange(other.descriptor_, -1)) {}
  OwnedDescriptor& operator=(OwnedDescriptor&& other) noexcept {
    if (this != &other) {
      close();
      descriptor_ = std::exchange(other.descriptor_, -1);
    }
    return *this;
  }
  ~OwnedDescriptor() { close(); }

  int get() const noexcept { return descriptor_; }

 private:
  void close() noexcept {
    if (descriptor_ >= 0) {
      ::close(descriptor_);
      descriptor_ = -1;
    }
  }

  int descriptor_;
};

struct RenderDestination {
  OwnedDescriptor parent;
  std::string filename;
};

RenderDestination open_render_destination(
    const std::filesystem::path& output) {
  auto parent = output.parent_path();
#if defined(__APPLE__)
  const auto relative = parent.relative_path();
  if (parent.is_absolute() && !relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      parent = std::filesystem::path("/private") / relative;
    }
  }
#endif
  const int root = ::open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  require(root >= 0, "render output root could not be opened");
  OwnedDescriptor current(root);
  for (const auto& component : parent.relative_path()) {
    if (component.empty() || component == ".") {
      continue;
    }
    const int next = ::openat(
        current.get(),
        component.c_str(),
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    require(
        next >= 0,
        "render output parent contains a symbolic, missing, or invalid directory");
    current = OwnedDescriptor(next);
  }

  const auto filename = output.filename().string();
  require(!filename.empty(), "render output filename must not be empty");
  struct stat output_metadata {};
  if (::fstatat(
          current.get(),
          filename.c_str(),
          &output_metadata,
          AT_SYMLINK_NOFOLLOW) == 0) {
    invalid("render output already exists");
  }
  require(
      errno == ENOENT,
      "render output cannot be safely inspected through its parent");
  return RenderDestination{
      std::move(current),
      filename,
  };
}

std::string descriptor_path(int descriptor) {
#if defined(__linux__)
  return "/proc/self/fd/" + std::to_string(descriptor);
#else
  return "/dev/fd/" + std::to_string(descriptor);
#endif
}

class TempRender {
 public:
  TempRender(
      int parent_descriptor,
      int descriptor,
      std::string name)
      : parent_descriptor_(parent_descriptor),
        descriptor_(descriptor),
        name_(std::move(name)) {}
  TempRender(const TempRender&) = delete;
  TempRender& operator=(const TempRender&) = delete;
  TempRender(TempRender&& other) noexcept
      : parent_descriptor_(other.parent_descriptor_),
        descriptor_(std::move(other.descriptor_)),
        name_(std::move(other.name_)),
        linked_(other.linked_) {
    other.linked_ = true;
  }
  ~TempRender() {
    if (!linked_) {
      ::unlinkat(parent_descriptor_, name_.c_str(), 0);
    }
  }

  int descriptor() const noexcept { return descriptor_.get(); }
  std::filesystem::path path() const {
    return descriptor_path(descriptor_.get());
  }
  const std::string& name() const noexcept { return name_; }
  void published() noexcept {
    if (::unlinkat(parent_descriptor_, name_.c_str(), 0) == 0 ||
        errno == ENOENT) {
      linked_ = true;
    }
  }

 private:
  int parent_descriptor_;
  OwnedDescriptor descriptor_;
  std::string name_;
  bool linked_{false};
};

foundation::Result<TempRender> create_temp_render(
    int parent_descriptor) {
  std::random_device random;
  for (std::uint32_t attempt = 0; attempt < 128; ++attempt) {
    const auto name =
        std::string(".lmdj-render-") +
        std::to_string(static_cast<unsigned long long>(::getpid())) +
        "-" +
        std::to_string(
            static_cast<unsigned long long>(random())) +
        "-" + std::to_string(attempt) + ".tmp";
    const int descriptor = ::openat(
        parent_descriptor,
        name.c_str(),
        O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
        0600);
    if (descriptor >= 0) {
      return foundation::Result<TempRender>::success(
          TempRender{parent_descriptor, descriptor, name});
    }
    if (errno != EEXIST && errno != EINTR) {
      return foundation::Result<TempRender>::failure(
          Error{
              ErrorCode::io_error,
              "exclusive render temporary file could not be created",
              {{"system_error", std::strerror(errno)}},
          });
    }
  }
  return foundation::Result<TempRender>::failure(
      Error{
          ErrorCode::io_error,
          "exclusive render temporary name attempts were exhausted",
      });
}

class ScratchRender {
 public:
  explicit ScratchRender(std::filesystem::path directory)
      : directory_(std::move(directory)),
        path_(directory_ / "render.wav") {}
  ScratchRender(const ScratchRender&) = delete;
  ScratchRender& operator=(const ScratchRender&) = delete;
  ScratchRender(ScratchRender&& other) noexcept
      : directory_(std::move(other.directory_)),
        path_(std::move(other.path_)) {
    other.path_.clear();
    other.directory_.clear();
  }
  ~ScratchRender() {
    if (!path_.empty()) {
      ::unlink(path_.c_str());
    }
    if (!directory_.empty()) {
      ::rmdir(directory_.c_str());
    }
  }

  const std::filesystem::path& path() const noexcept { return path_; }

 private:
  std::filesystem::path directory_;
  std::filesystem::path path_;
};

foundation::Result<ScratchRender> create_scratch_render(
    const std::filesystem::path& workspace_root) {
  auto scratch_template =
      (workspace_root / ".core-render-XXXXXX").string();
  std::vector<char> writable(
      scratch_template.begin(), scratch_template.end());
  writable.push_back('\0');
  const char* directory = ::mkdtemp(writable.data());
  if (directory == nullptr) {
    return foundation::Result<ScratchRender>::failure(
        Error{
            ErrorCode::io_error,
            "private render scratch directory could not be created",
            {{"system_error", std::strerror(errno)}},
        });
  }
  ScratchRender scratch{std::filesystem::path(directory)};
  const int descriptor = ::open(
      scratch.path().c_str(),
      O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      0600);
  if (descriptor < 0) {
    return foundation::Result<ScratchRender>::failure(
        Error{
            ErrorCode::io_error,
            "private render scratch file could not be created",
            {{"system_error", std::strerror(errno)}},
        });
  }
  ::close(descriptor);
  return foundation::Result<ScratchRender>::success(
      std::move(scratch));
}

struct VerifiedScratch {
  foundation::ArtifactRef artifact;
  std::vector<std::byte> bytes;
};

foundation::Result<VerifiedScratch> read_verified_scratch(
    const ScratchRender& scratch,
    const foundation::ArtifactRef& expected) {
  const int value =
      ::open(scratch.path().c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (value < 0) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch file could not be reopened safely",
            {{"system_error", std::strerror(errno)}},
        });
  }
  OwnedDescriptor descriptor(value);
  struct stat before {};
  if (::fstat(descriptor.get(), &before) != 0 ||
      !S_ISREG(before.st_mode) || before.st_size < 0 ||
      static_cast<std::uint64_t>(before.st_size) != expected.byte_length ||
      static_cast<std::uint64_t>(before.st_size) >
          std::numeric_limits<std::size_t>::max()) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch metadata does not match its Artifact",
        });
  }
  const auto stable_artifact = foundation::describe_artifact(
      descriptor_path(descriptor.get()), expected.media_type);
  if (!stable_artifact.has_value()) {
    return foundation::Result<VerifiedScratch>::failure(
        stable_artifact.error());
  }
  if (stable_artifact.value() != expected) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch bytes do not match its Artifact",
        });
  }
  if (::lseek(descriptor.get(), 0, SEEK_SET) < 0) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch descriptor could not be rewound",
        });
  }
  std::vector<std::byte> bytes(
      static_cast<std::size_t>(before.st_size));
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto count = ::read(
        descriptor.get(),
        bytes.data() + offset,
        bytes.size() - offset);
    if (count < 0 && errno == EINTR) {
      continue;
    }
    if (count <= 0) {
      return foundation::Result<VerifiedScratch>::failure(
          Error{
              ErrorCode::io_error,
              "render scratch could not be read completely",
          });
    }
    offset += static_cast<std::size_t>(count);
  }
  struct stat after {};
  if (::fstat(descriptor.get(), &after) != 0 ||
      !S_ISREG(after.st_mode) || after.st_dev != before.st_dev ||
      after.st_ino != before.st_ino || after.st_size != before.st_size) {
    return foundation::Result<VerifiedScratch>::failure(
        Error{
            ErrorCode::io_error,
            "render scratch changed while it was being read",
        });
  }
  return foundation::Result<VerifiedScratch>::success(
      VerifiedScratch{
          stable_artifact.value(),
          std::move(bytes),
      });
}

foundation::Result<void> write_verified_staging(
    TempRender& staging,
    const VerifiedScratch& scratch) {
  std::size_t offset = 0;
  while (offset < scratch.bytes.size()) {
    const auto count = ::write(
        staging.descriptor(),
        scratch.bytes.data() + offset,
        scratch.bytes.size() - offset);
    if (count < 0 && errno == EINTR) {
      continue;
    }
    if (count <= 0) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::io_error,
              "render staging file could not be written completely",
          });
    }
    offset += static_cast<std::size_t>(count);
  }
  if (::fsync(staging.descriptor()) != 0 ||
      ::lseek(staging.descriptor(), 0, SEEK_SET) < 0) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "render staging file could not be durably verified",
            {{"system_error", std::strerror(errno)}},
        });
  }
  const auto staged = foundation::describe_artifact(
      staging.path(), scratch.artifact.media_type);
  if (!staged.has_value()) {
    return foundation::Result<void>::failure(staged.error());
  }
  if (staged.value() != scratch.artifact) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "render staging bytes do not match the verified scratch Artifact",
        });
  }
  return foundation::Result<void>::success();
}

provider::TimestampSource default_timestamp_source() {
  return [] {
    const auto ticks =
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count();
    return std::string("unix-ms:") + std::to_string(ticks);
  };
}

Error runtime_preparation_limit_error(
    std::string resource,
    std::uint64_t observed,
    std::uint64_t limit) {
  return Error{
      ErrorCode::cook_failed,
      "runtime preparation limit exceeded",
      {
          {"resource", std::move(resource)},
          {"observed", observed},
          {"limit", limit},
      },
  };
}

bool valid_host_project_path(const std::filesystem::path& path) {
  const auto encoded = path.generic_string();
  return valid_utf8(encoded) && path.is_absolute() &&
         path.lexically_normal() == path;
}

}  // namespace

struct RuntimeProjectWriterLease::Impl {
  explicit Impl(std::unique_ptr<project_io::ProjectWriterLease> owned)
      : owned(std::move(owned)) {}

  std::unique_ptr<project_io::ProjectWriterLease> owned;
};

struct Application::Impl {
  explicit Impl(ApplicationConfig config)
      : workspace_root(std::move(config.workspace_root)),
        registry(
            config.providers
                ? std::move(config.providers)
                : std::make_shared<provider::Registry>()),
        storage_platform(
            project_io::make_default_project_storage_platform()),
        projects(storage_platform),
        journals(storage_platform),
        attempts(
            workspace_root,
            std::move(config.provider_policy),
            config.timestamp_source
                ? std::move(config.timestamp_source)
                : default_timestamp_source()) {
    if (!workspace_root.is_absolute()) {
      throw std::invalid_argument("workspace_root must be absolute");
    }
  }

  nlohmann::json dispatch(
      const nlohmann::json& request,
      OperationKind requested_kind) {
    require(request.is_object(), "request must be an object");
    require(all_strings_valid(request), "request contains invalid UTF-8");
    require(request.contains("operation"), "operation is required");
    const auto operation = string_field(request, "operation");
    const auto registered = operations().find(operation);
    require(registered != operations().end(), "operation is unknown");
    require(
        registered->second == requested_kind,
        "operation was sent to the wrong Application method");

    if (operation == "project.create") {
      return project_create(request);
    }
    if (operation == "asset.import") {
      return asset_import(request);
    }
    if (operation == "pad.assign") {
      return pad_assign(request);
    }
    if (operation == "take.begin") {
      return take_begin(request);
    }
    if (operation == "take.append") {
      return take_append(request);
    }
    if (operation == "take.commit") {
      return take_commit(request);
    }
    if (operation == "render.offline") {
      return render_offline(request);
    }
    if (operation == "provider.select") {
      return provider_select(request);
    }
    if (operation == "provider.run") {
      return provider_run(request);
    }
    if (operation == "project.inspect") {
      return project_inspect(request);
    }
    if (operation == "take.recoverable.list") {
      return recoverable_list(request);
    }
    if (operation == "snapshot.cook") {
      return snapshot_cook(request);
    }
    if (operation == "provider.list") {
      return provider_list(request);
    }
    if (operation == "provider.selected") {
      return provider_selected(request);
    }
    return attempt_inspect(request);
  }

  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  prepare_runtime_snapshot(const RuntimeSnapshotRequest& request) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.pattern_id.value())) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          Error{
              ErrorCode::invalid_argument,
              "runtime snapshot request is invalid",
          });
    }
    const auto loaded = projects.load(request.project_path);
    if (!loaded.has_value()) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          loaded.error());
    }
    return cook_project(
        request.project_path,
        loaded.value(),
        request.pattern_id,
        request.limits);
  }

  foundation::Result<std::unique_ptr<project_io::ProjectWriterLease>>
  acquire_project_writer(const std::filesystem::path& project_path) {
    if (!valid_host_project_path(project_path)) {
      return foundation::Result<
          std::unique_ptr<project_io::ProjectWriterLease>>::failure(
          Error{
              ErrorCode::invalid_argument,
              "project writer request is invalid",
          });
    }
    auto acquired = storage_platform->acquire_writer(project_path);
    if (acquired.has_value()) {
      return acquired;
    }
    const auto& error = acquired.error();
    if (error.details.is_object() &&
        error.details.value("storage_condition", std::string{}) ==
            project_io::kStorageConditionProjectBusy) {
      return foundation::Result<
          std::unique_ptr<project_io::ProjectWriterLease>>::failure(
          Error{
              ErrorCode::io_error,
              "project writer is already acquired",
              {{"storage_condition", "project_busy"}},
          });
    }
    return foundation::Result<
        std::unique_ptr<project_io::ProjectWriterLease>>::failure(
        Error{
            error.code,
            "project writer could not be acquired",
        });
  }

  foundation::Result<domain::AppliedCommand> import_artifact_bytes(
      const ArtifactBytesImportRequest& request) {
    if (!valid_host_project_path(request.project_path) ||
        !domain::is_valid_uuid(request.meta.command_id.value()) ||
        !domain::is_valid_uuid(request.asset_id.value()) ||
        request.media_type.empty() || !valid_utf8(request.media_type)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "byte-backed artifact import request is invalid",
          });
    }
    return projects.import_artifact_bytes(
        request.project_path,
        project_io::ProjectStore::ImportArtifactBytesRequest{
            request.meta,
            request.asset_id,
            request.media_type,
            request.bytes,
        });
  }

  foundation::Result<void> append_realtime_take_events(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::span<const domain::RawTakeEvent> events) {
    const auto encoded_path = project_path.generic_string();
    if (!valid_utf8(encoded_path) || !project_path.is_absolute() ||
        project_path.lexically_normal() != project_path ||
        !domain::is_valid_uuid(take_id.value())) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_argument,
              "realtime take append request is invalid",
          });
    }
    return journals.append_batch(project_path, std::move(take_id), events);
  }

  foundation::Result<std::filesystem::path> seal_realtime_take(
      const std::filesystem::path& project_path,
      foundation::TakeId take_id,
      std::string_view reason) {
    const auto encoded_path = project_path.generic_string();
    if (!valid_utf8(encoded_path) || !project_path.is_absolute() ||
        project_path.lexically_normal() != project_path ||
        !domain::is_valid_uuid(take_id.value()) ||
        reason != "capture_incomplete") {
      return foundation::Result<std::filesystem::path>::failure(
          Error{
              ErrorCode::invalid_argument,
              "realtime take seal request is invalid",
          });
    }
    return journals.seal(
        project_path, std::move(take_id), std::string(reason));
  }

  nlohmann::json project_create(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "project_id", "bpm"}),
        "project.create request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto id = uuid_field(request, "project_id");
    const auto bpm = unsigned_field(request, "bpm", 240);
    require(bpm >= 40, "bpm is out of range");
    auto project = domain::create_project(
        foundation::ProjectId{id},
        static_cast<std::uint16_t>(bpm));
    if (!project.has_value()) {
      return error_envelope(project.error());
    }
    const auto created = projects.create(path, project.value());
    if (!created.has_value()) {
      return error_envelope(created.error());
    }
    return success_envelope({{"project_id", id}}, 0);
  }

  nlohmann::json asset_import(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "asset_id",
                "source_path",
                "media_type",
            }),
        "asset.import request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto source = absolute_path_field(request, "source_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto asset_id = uuid_field(request, "asset_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto media_type = string_field(request, "media_type");
    require(!media_type.empty(), "media_type must not be empty");
    const auto imported = projects.import_artifact_with_identity(
        path,
        project_io::ProjectStore::ImportArtifactRequest{
            domain::CommandMeta{
                foundation::CommandId{command_id},
                revision,
            },
            foundation::AssetId{asset_id},
            source,
            media_type,
        });
    if (!imported.has_value()) {
      return error_envelope(imported.error());
    }
    const auto& persisted = imported.value().command;
    const auto& applied = imported.value().outcome;
    return success_envelope(
        {
            {"asset_id", persisted.asset.id.value()},
            {"artifact", persisted.asset.artifact},
            {"committed_revision",
             applied.event.at("revision").get<std::uint64_t>()},
            {"replayed", applied.replayed},
        },
        applied.state.revision);
  }

  nlohmann::json pad_assign(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "slot",
                "asset_id",
            }),
        "pad.assign request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto pad_slot = slot_value(request.at("slot"));
    std::optional<foundation::AssetId> asset_id;
    if (!request.at("asset_id").is_null()) {
      asset_id = foundation::AssetId{uuid_field(request, "asset_id")};
    }
    const auto assigned = projects.execute_with_identity(
        path,
        domain::Command{
            domain::AssignPad{
                {
                    foundation::CommandId{command_id},
                    revision,
                },
                pad_slot,
                asset_id,
            },
        });
    if (!assigned.has_value()) {
      return error_envelope(assigned.error());
    }
    const auto* persisted =
        std::get_if<domain::AssignPad>(&assigned.value().command);
    if (persisted == nullptr) {
      return error_envelope(
          Error{
              ErrorCode::invalid_project,
              "persisted pad assignment has the wrong command type",
          });
    }
    const auto& applied = assigned.value().outcome;
    return success_envelope(
        {
            {"slot", slot_json(persisted->slot)},
            {"asset_id",
             persisted->asset_id.has_value()
                 ? nlohmann::json(persisted->asset_id->value())
                 : nlohmann::json(nullptr)},
            {"committed_revision",
             applied.event.at("revision").get<std::uint64_t>()},
            {"replayed", applied.replayed},
        },
        applied.state.revision);
  }

  nlohmann::json take_begin(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "take_id",
                "expected_revision",
                "sample_rate",
            }),
        "take.begin request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto take_id = uuid_field(request, "take_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto sample_rate =
        unsigned_field(request, "sample_rate", kSampleRate);
    require(sample_rate == kSampleRate, "sample_rate must be 48000");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    if (loaded.value().revision != revision) {
      return error_envelope(
          Error{
              ErrorCode::revision_conflict,
              "take begin expected a different project revision",
              {
                  {"actual_revision", loaded.value().revision},
                  {"expected_revision", revision},
              },
          });
    }
    const auto begun = journals.begin(
        path,
        foundation::TakeId{take_id},
        revision,
        static_cast<std::uint32_t>(sample_rate));
    if (!begun.has_value()) {
      return error_envelope(begun.error());
    }
    return success_envelope({{"take_id", take_id}}, loaded.value().revision);
  }

  nlohmann::json take_append(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "take_id", "event"}),
        "take.append request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto take_id = uuid_field(request, "take_id");
    const auto event = raw_event_value(request.at("event"));
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto appended = journals.append(
        path, foundation::TakeId{take_id}, event);
    if (!appended.has_value()) {
      return error_envelope(appended.error());
    }
    const auto take =
        journals.read_active(path, foundation::TakeId{take_id});
    if (!take.has_value()) {
      return error_envelope(take.error());
    }
    return success_envelope(
        {
            {"take_id", take_id},
            {"event_count", take.value().events.size()},
        },
        loaded.value().revision);
  }

  nlohmann::json take_commit(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "project_path",
                "command_id",
                "expected_revision",
                "take_id",
                "pattern",
            }),
        "take.commit request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto command_id = uuid_field(request, "command_id");
    const auto revision = unsigned_field(request, "expected_revision");
    const auto take_id = uuid_field(request, "take_id");
    const auto pattern = pattern_value(request.at("pattern"));
    const project_io::RecordTakeReplayIdentity replay_identity{
        {
            foundation::CommandId{command_id},
            revision,
        },
        foundation::TakeId{take_id},
        pattern,
    };
    const auto replay = projects.replay_record_take(
        path, replay_identity);
    if (!replay.has_value()) {
      return error_envelope(replay.error());
    }
    if (replay.value().has_value()) {
      const auto& persisted = *replay.value();
      return success_envelope(
          {
              {"take_id", persisted.command.take.id.value()},
              {"pattern_id", persisted.command.pattern.id.value()},
              {"committed_revision",
               persisted.outcome.event.at("revision")
                   .get<std::uint64_t>()},
              {"replayed", true},
          },
          persisted.outcome.state.revision);
    }
    const auto active = journals.read_active_journal(
        path, foundation::TakeId{take_id});
    if (!active.has_value()) {
      return error_envelope(active.error());
    }
    if (revision != active.value().expected_revision) {
      const auto sealed = journals.seal(
          path,
          foundation::TakeId{take_id},
          "revision_conflict");
      if (!sealed.has_value()) {
        return error_envelope(sealed.error());
      }
      return error_envelope(
          Error{
              ErrorCode::revision_conflict,
              "take commit revision does not match its captured revision",
              {
                  {"captured_revision",
                   active.value().expected_revision},
                  {"expected_revision", revision},
              },
          });
    }
    const auto committed = projects.execute_with_identity(
        path,
        domain::Command{
            domain::RecordTake{
                {
                    foundation::CommandId{command_id},
                    active.value().expected_revision,
                },
                active.value().take,
                pattern,
            },
        });
    if (!committed.has_value()) {
      return error_envelope(committed.error());
    }
    const auto* persisted =
        std::get_if<domain::RecordTake>(&committed.value().command);
    if (persisted == nullptr) {
      return error_envelope(
          Error{
              ErrorCode::invalid_project,
              "persisted Take commit has the wrong command type",
          });
    }
    const auto& applied = committed.value().outcome;
    return success_envelope(
        {
            {"take_id", persisted->take.id.value()},
            {"pattern_id", persisted->pattern.id.value()},
            {"committed_revision",
             applied.event.at("revision").get<std::uint64_t>()},
            {"replayed", applied.replayed},
        },
        applied.state.revision);
  }

  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  cook_project(
      const std::filesystem::path& path,
      const domain::ProjectState& project,
      const foundation::PatternId& pattern_id,
      std::optional<audio::RuntimePreparationLimits> limits = std::nullopt) {
    auto cooked = cooker::cook(
        project,
        pattern_id,
        [this, path, limits](const foundation::ArtifactRef& artifact) {
          if (limits.has_value() &&
              !limits->allows_artifact_bytes(artifact.byte_length)) {
            return foundation::Result<std::vector<std::byte>>::failure(
                runtime_preparation_limit_error(
                    "artifact_bytes",
                    artifact.byte_length,
                    limits->maximum_artifact_bytes));
          }
          return projects.read_artifact(path, artifact);
        });
    if (!cooked.has_value() || !limits.has_value()) {
      return cooked;
    }

    std::uint64_t prospective_bank_bytes = 0;
    for (const auto& pad : cooked.value()->pads) {
      if (pad.sample == nullptr || pad.sample->channels == 0 ||
          pad.sample->interleaved.size() % pad.sample->channels != 0) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::cook_failed,
                "cooked runtime Snapshot PCM shape is invalid",
            });
      }
      const auto frames = static_cast<std::uint64_t>(
          pad.sample->interleaved.size() / pad.sample->channels);
      if (!limits->allows_decoded_frames_per_pad(frames)) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            runtime_preparation_limit_error(
                "decoded_frames_per_pad",
                frames,
                limits->maximum_decoded_frames_per_pad));
      }
      const auto sample_bytes = audio::checked_mono_float_bytes(frames);
      if (!sample_bytes.has_value()) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime preparation PCM byte length overflowed",
            });
      }
      const auto total = audio::checked_runtime_byte_sum(
          prospective_bank_bytes, sample_bytes.value());
      if (!total.has_value()) {
        return foundation::Result<
            std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
            Error{
                ErrorCode::invalid_argument,
                "runtime preparation Bank byte length overflowed",
            });
      }
      prospective_bank_bytes = total.value();
    }
    if (!limits->allows_prepared_bank_bytes(prospective_bank_bytes)) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          runtime_preparation_limit_error(
              "prepared_bank_bytes",
              prospective_bank_bytes,
              limits->maximum_prepared_bank_bytes));
    }
    if (!limits->allows_live_bank_bytes(prospective_bank_bytes)) {
      return foundation::Result<
          std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
          runtime_preparation_limit_error(
              "live_bank_bytes",
              prospective_bank_bytes,
              limits->maximum_live_bank_bytes));
    }
    return cooked;
  }

  nlohmann::json render_offline(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {"operation", "project_path", "pattern_id", "output_path"}),
        "render.offline request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto pattern_id = uuid_field(request, "pattern_id");
    const auto output = absolute_path_field(request, "output_path");
    require(
        !path_is_inside_bundle(output),
        "render output must be outside every .lmdj bundle");
    auto destination = open_render_destination(output);

    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto cooked = cook_project(
        path,
        loaded.value(),
        foundation::PatternId{pattern_id});
    if (!cooked.has_value()) {
      return error_envelope(cooked.error());
    }
    auto scratch_result = create_scratch_render(workspace_root);
    if (!scratch_result.has_value()) {
      return error_envelope(scratch_result.error());
    }
    auto scratch = std::move(scratch_result.value());
    const auto rendered = audio::render_offline(
        audio::OfflineRenderRequest{
            cooked.value(),
            scratch.path(),
        });
    if (!rendered.has_value()) {
      return error_envelope(rendered.error());
    }
    const auto verified =
        read_verified_scratch(scratch, rendered.value().artifact);
    if (!verified.has_value()) {
      return error_envelope(verified.error());
    }
    auto staging_result =
        create_temp_render(destination.parent.get());
    if (!staging_result.has_value()) {
      return error_envelope(staging_result.error());
    }
    auto staging = std::move(staging_result.value());
    const auto staged = write_verified_staging(
        staging, verified.value());
    if (!staged.has_value()) {
      return error_envelope(staged.error());
    }
    if (::linkat(
            destination.parent.get(),
            staging.name().c_str(),
            destination.parent.get(),
            destination.filename.c_str(),
            0) != 0) {
      return error_envelope(
          Error{
              ErrorCode::io_error,
              "render output could not be atomically published",
              {
                  {"path", output.generic_string()},
                  {"system_error", std::strerror(errno)},
              },
          });
    }
    staging.published();
    return success_envelope(
        {
            {"artifact", verified.value().artifact},
            {"output_path", output.generic_string()},
            {"frame_count", rendered.value().frame_count},
            {"sample_rate", rendered.value().sample_rate},
            {"channels", rendered.value().channels},
        },
        loaded.value().revision);
  }

  nlohmann::json provider_select(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "capability", "provider_id"}),
        "provider.select request shape is invalid");
    const auto capability = file_id_field(request, "capability");
    const auto provider_id = file_id_field(request, "provider_id");
    const auto selected = attempts.set_provider_selection(
        capability, provider_id, *registry);
    if (!selected.has_value()) {
      return error_envelope(selected.error());
    }
    return success_envelope(
        {
            {"capability", capability},
            {"provider_id", provider_id},
        },
        std::nullopt);
  }

  nlohmann::json provider_run(const nlohmann::json& request) {
    require(
        exact_keys(
            request,
            {
                "operation",
                "attempt_id",
                "capability",
                "inputs",
                "parameters",
                "data_classification",
                "platform",
                "region",
                "required_permissions",
            }),
        "provider.run request shape is invalid");
    const auto attempt_id = file_id_field(request, "attempt_id");
    const auto capability = file_id_field(request, "capability");
    const auto classification =
        file_id_field(request, "data_classification");
    const auto platform = file_id_field(request, "platform");
    const auto region = file_id_field(request, "region");
    const auto& encoded_inputs = request.at("inputs");
    require(encoded_inputs.is_array(), "inputs must be an array");
    std::vector<provider::ArtifactBinding> inputs;
    std::set<std::string> input_hashes;
    for (const auto& input : encoded_inputs) {
      require(
          exact_keys(input, {"port", "artifact"}),
          "input Artifact binding shape is invalid");
      require(input.at("port").is_string(), "input port is invalid");
      const auto port = string_field(input, "port");
      require(provider::valid_port_name(port), "input port is invalid");
      const auto& encoded_artifact = input.at("artifact");
      require(
          exact_keys(
              encoded_artifact,
              {"sha256", "media_type", "byte_length"}),
          "input Artifact shape is invalid");
      require(
          encoded_artifact.at("sha256").is_string() &&
              encoded_artifact.at("media_type").is_string(),
          "input Artifact strings are invalid");
      foundation::ArtifactRef artifact{
          string_field(encoded_artifact, "sha256"),
          string_field(encoded_artifact, "media_type"),
          unsigned_field(encoded_artifact, "byte_length"),
      };
      require(
          artifact.sha256.size() == 64 &&
              std::all_of(
                  artifact.sha256.begin(),
                  artifact.sha256.end(),
                  [](unsigned char character) {
                    return (character >= '0' && character <= '9') ||
                           (character >= 'a' && character <= 'f');
                  }),
          "input Artifact hash is invalid");
      require(
          !artifact.media_type.empty(),
          "input Artifact media type is empty");
      require(
          input_hashes.insert(artifact.sha256).second,
          "input Artifact hashes must be unique");
      inputs.push_back(provider::ArtifactBinding{
          port,
          std::move(artifact),
      });
    }
    const auto& encoded_permissions = request.at("required_permissions");
    require(
        encoded_permissions.is_array(),
        "required_permissions must be an array");
    std::vector<std::string> permissions;
    std::set<std::string> unique_permissions;
    for (const auto& encoded : encoded_permissions) {
      require(encoded.is_string(), "permission must be a string");
      const auto value = encoded.get<std::string>();
      require(safe_file_id(value), "permission is invalid");
      require(
          unique_permissions.insert(value).second,
          "permissions must be unique");
      permissions.push_back(value);
    }
    const auto& parameters = request.at("parameters");
    require(
        parameters.is_object(),
        "parameters must be an object");
    const auto executed = attempts.execute(
        foundation::AttemptId{attempt_id},
        provider::CapabilityRequest{
            capability,
            std::move(inputs),
            parameters,
            classification,
            platform,
            region,
            std::move(permissions),
        },
        *registry);
    if (!executed.has_value()) {
      return error_envelope(executed.error());
    }
    if (executed.value().error.has_value()) {
      auto error = *executed.value().error;
      error.details["attempt_id"] = attempt_id;
      return error_envelope(error);
    }
    require(
        executed.value().candidate.has_value(),
        "Provider result has no Candidate");
    const auto& candidate = *executed.value().candidate;
    return success_envelope(
        {
            {"attempt_id", attempt_id},
            {"candidate_id", candidate.id.value()},
            {"outputs", candidate.outputs},
            {"provenance", candidate.provenance},
        },
        std::nullopt);
  }

  nlohmann::json project_inspect(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path"}),
        "project.inspect request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    return success_envelope(
        {{"project", project_json(loaded.value())}},
        loaded.value().revision);
  }

  nlohmann::json recoverable_list(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "project_path"}),
        "take.recoverable.list request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto listed = journals.list_recoverable(path);
    if (!listed.has_value()) {
      return error_envelope(listed.error());
    }
    auto candidates = nlohmann::json::array();
    for (const auto& candidate : listed.value()) {
      auto events = nlohmann::json::array();
      for (const auto& event : candidate.take.events) {
        events.push_back(raw_event_json(event));
      }
      candidates.push_back(
          {
              {"take_id", candidate.take.id.value()},
              {"expected_revision", candidate.expected_revision},
              {"reason", candidate.reason},
              {"sample_rate", candidate.take.sample_rate},
              {"events", std::move(events)},
          });
    }
    std::sort(
        candidates.begin(),
        candidates.end(),
        [](const auto& left, const auto& right) {
          return left.at("take_id").template get<std::string>() <
                 right.at("take_id").template get<std::string>();
        });
    return success_envelope(
        {{"candidates", std::move(candidates)}},
        loaded.value().revision);
  }

  nlohmann::json snapshot_cook(const nlohmann::json& request) {
    require(
        exact_keys(
            request, {"operation", "project_path", "pattern_id"}),
        "snapshot.cook request shape is invalid");
    const auto path = absolute_path_field(request, "project_path");
    const auto pattern_id = uuid_field(request, "pattern_id");
    const auto loaded = projects.load(path);
    if (!loaded.has_value()) {
      return error_envelope(loaded.error());
    }
    const auto cooked = cook_project(
        path,
        loaded.value(),
        foundation::PatternId{pattern_id});
    if (!cooked.has_value()) {
      return error_envelope(cooked.error());
    }
    std::set<std::string> hashes;
    const auto pattern =
        loaded.value().patterns.find(foundation::PatternId{pattern_id});
    if (pattern != loaded.value().patterns.end()) {
      for (const auto& event : pattern->second.events) {
        const auto asset =
            domain::resolve_slot_asset(loaded.value(), event.slot);
        if (asset.has_value()) {
          hashes.insert(asset->artifact.sha256);
        }
      }
    }
    return success_envelope(
        {
            {"pattern_id", pattern_id},
            {"event_count", cooked.value()->events.size()},
            {"artifact_sha256s", hashes},
        },
        loaded.value().revision);
  }

  nlohmann::json provider_list(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation"}),
        "provider.list request shape is invalid");
    auto providers = nlohmann::json::array();
    for (const auto& descriptor : registry->list()) {
      providers.push_back(provider_descriptor_json(descriptor));
    }
    return success_envelope(
        {{"providers", std::move(providers)}},
        std::nullopt);
  }

  nlohmann::json provider_selected(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "capability"}),
        "provider.selected request shape is invalid");
    const auto capability = file_id_field(request, "capability");
    const auto selected = attempts.selected_provider(capability);
    if (!selected.has_value()) {
      return error_envelope(selected.error());
    }
    return success_envelope(
        {
            {"capability", capability},
            {"provider_id", selected.value()},
        },
        std::nullopt);
  }

  nlohmann::json attempt_inspect(const nlohmann::json& request) {
    require(
        exact_keys(request, {"operation", "attempt_id"}),
        "attempt.inspect request shape is invalid");
    const auto attempt_id = file_id_field(request, "attempt_id");
    const auto inspected =
        attempts.inspect(foundation::AttemptId{attempt_id});
    if (!inspected.has_value()) {
      return error_envelope(inspected.error());
    }
    return success_envelope(
        terminal_attempt_json(inspected.value()),
        std::nullopt);
  }

  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> registry;
  std::shared_ptr<project_io::ProjectStoragePlatform> storage_platform;
  project_io::ProjectStore projects;
  project_io::TakeJournal journals;
  provider::AttemptStore attempts;
};

Application::Application(ApplicationConfig config)
    : impl_(std::make_unique<Impl>(std::move(config))) {}

RuntimeProjectWriterLease::RuntimeProjectWriterLease(
    std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}

RuntimeProjectWriterLease::~RuntimeProjectWriterLease() = default;
RuntimeProjectWriterLease::RuntimeProjectWriterLease(
    RuntimeProjectWriterLease&&) noexcept = default;
RuntimeProjectWriterLease& RuntimeProjectWriterLease::operator=(
    RuntimeProjectWriterLease&&) noexcept = default;

Application::~Application() = default;
Application::Application(Application&&) noexcept = default;
Application& Application::operator=(Application&&) noexcept = default;

nlohmann::json Application::command(const nlohmann::json& request) {
  try {
    return impl_->dispatch(request, OperationKind::command);
  } catch (const InvalidRequest& error) {
    return error_envelope(
        Error{ErrorCode::invalid_argument, error.what()});
  } catch (...) {
    return internal_error();
  }
}

nlohmann::json Application::query(
    const nlohmann::json& request) const {
  try {
    return impl_->dispatch(request, OperationKind::query);
  } catch (const InvalidRequest& error) {
    return error_envelope(
        Error{ErrorCode::invalid_argument, error.what()});
  } catch (...) {
    return internal_error();
  }
}

foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
Application::prepare_runtime_snapshot(
    const RuntimeSnapshotRequest& request) {
  try {
    return impl_->prepare_runtime_snapshot(request);
  } catch (...) {
    return foundation::Result<
        std::shared_ptr<const cooker::RuntimeSnapshot>>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<RuntimeProjectWriterLease>
Application::acquire_project_writer(
    const std::filesystem::path& project_path) {
  try {
    auto acquired = impl_->acquire_project_writer(project_path);
    if (!acquired.has_value()) {
      return foundation::Result<RuntimeProjectWriterLease>::failure(
          acquired.error());
    }
    return foundation::Result<RuntimeProjectWriterLease>::success(
        RuntimeProjectWriterLease{
            std::make_unique<RuntimeProjectWriterLease::Impl>(
                std::move(acquired.value()))});
  } catch (...) {
    return foundation::Result<RuntimeProjectWriterLease>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<domain::AppliedCommand>
Application::import_artifact_bytes(
    const ArtifactBytesImportRequest& request) {
  try {
    return impl_->import_artifact_bytes(request);
  } catch (...) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<void> Application::append_realtime_take_events(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events) {
  try {
    return impl_->append_realtime_take_events(
        project_path, std::move(take_id), events);
  } catch (...) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

foundation::Result<std::filesystem::path>
Application::seal_realtime_take(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::string_view reason) {
  try {
    return impl_->seal_realtime_take(
        project_path, std::move(take_id), reason);
  } catch (...) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{
            ErrorCode::internal_error,
            "unexpected Application Facade Host API failure",
        });
  }
}

}  // namespace lmdj::facade
