#include <lmdj/project_io/project_store.hpp>

#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cctype>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string_view>
#include <system_error>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/take_journal.hpp>

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
#include "testing_hooks.hpp"
#endif

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint64_t kMaximumArtifactBytes = 64U * 1024U * 1024U;

class BundleLock {
 public:
  explicit BundleLock(int descriptor) : descriptor_(descriptor) {}

  BundleLock(const BundleLock&) = delete;
  BundleLock& operator=(const BundleLock&) = delete;

  BundleLock(BundleLock&& other) noexcept
      : descriptor_(std::exchange(other.descriptor_, -1)) {}

  BundleLock& operator=(BundleLock&& other) noexcept {
    if (this != &other) {
      release();
      descriptor_ = std::exchange(other.descriptor_, -1);
    }
    return *this;
  }

  ~BundleLock() { release(); }

 private:
  void release() {
    if (descriptor_ < 0) {
      return;
    }
    ::flock(descriptor_, LOCK_UN);
    ::close(descriptor_);
    descriptor_ = -1;
  }

  int descriptor_;
};

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

struct LoadedProject {
  domain::ProjectState state;
  std::map<foundation::CommandId, domain::Command> commands;
  std::map<foundation::CommandId, domain::CommandReceipt> receipts;
  std::map<foundation::CommandId, foundation::TakeId> cleanup_obligations;
  std::vector<std::string> transactions;
};

struct ArtifactStage {
  std::filesystem::path source;
  foundation::ArtifactRef artifact;
  foundation::CommandId command_id;
};

bool valid_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(
             value.begin(),
             value.end(),
             [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

Error io_error(
    std::string message,
    const std::filesystem::path& path,
    int system_error = errno) {
  return Error{
      ErrorCode::io_error,
      std::move(message),
      {
          {"path", path.generic_string()},
          {"system_error", std::strerror(system_error)},
      },
  };
}

Error invalid_project(
    std::string message,
    const std::filesystem::path& path,
    std::string detail = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (!detail.empty()) {
    details["detail"] = std::move(detail);
  }
  return Error{
      ErrorCode::invalid_project,
      std::move(message),
      std::move(details),
  };
}

foundation::Result<void> reject_symlinks_in_existing_tree(
    const std::filesystem::path& root) {
  std::error_code status_error;
  const auto root_status = std::filesystem::symlink_status(root, status_error);
  if (status_error) {
    if (status_error ==
        std::make_error_code(std::errc::no_such_file_or_directory)) {
      return foundation::Result<void>::success();
    }
    return foundation::Result<void>::failure(
        io_error(
            "project path could not be inspected without following links",
            root,
            status_error.value()));
  }
  if (root_status.type() == std::filesystem::file_type::not_found) {
    return foundation::Result<void>::success();
  }
  if (std::filesystem::is_symlink(root_status)) {
    return foundation::Result<void>::failure(
        invalid_project("project bundle contains a symbolic link", root));
  }
  if (!std::filesystem::is_directory(root_status)) {
    return foundation::Result<void>::success();
  }

  std::error_code iterator_error;
  std::filesystem::recursive_directory_iterator iterator(
      root, std::filesystem::directory_options::none, iterator_error);
  const std::filesystem::recursive_directory_iterator end;
  while (iterator != end) {
    if (iterator_error) {
      return foundation::Result<void>::failure(
          io_error(
              "project tree could not be inspected without following links",
              root,
              iterator_error.value()));
    }
    const auto entry_status =
        std::filesystem::symlink_status(iterator->path(), status_error);
    if (status_error) {
      return foundation::Result<void>::failure(
          io_error(
              "project entry could not be inspected without following links",
              iterator->path(),
              status_error.value()));
    }
    if (std::filesystem::is_symlink(entry_status)) {
      return foundation::Result<void>::failure(
          invalid_project(
              "project bundle contains a symbolic link",
              iterator->path()));
    }
    iterator.increment(iterator_error);
  }
  if (iterator_error) {
    return foundation::Result<void>::failure(
        io_error(
            "project tree could not be inspected without following links",
            root,
            iterator_error.value()));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> validate_managed_bundle_tree(
    const std::filesystem::path& bundle) {
  const auto no_symlinks = reject_symlinks_in_existing_tree(bundle);
  if (!no_symlinks.has_value()) {
    return no_symlinks;
  }
  const std::array managed_directories{
      bundle,
      bundle / "assets",
      bundle / "history",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& directory : managed_directories) {
    std::error_code status_error;
    const auto status =
        std::filesystem::symlink_status(directory, status_error);
    if (status_error || !std::filesystem::is_directory(status)) {
      return foundation::Result<void>::failure(
          invalid_project(
              "project managed directory is missing or invalid",
              directory,
              status_error.message()));
    }
  }
  std::error_code manifest_error;
  const auto manifest_status = std::filesystem::symlink_status(
      bundle / "manifest.json", manifest_error);
  if (manifest_error ||
      !std::filesystem::is_regular_file(manifest_status)) {
    return foundation::Result<void>::failure(
        invalid_project(
            "project manifest is missing or invalid",
            bundle / "manifest.json",
            manifest_error.message()));
  }
  return foundation::Result<void>::success();
}

foundation::Result<BundleLock> acquire_lock(
    const std::filesystem::path& bundle) {
  std::error_code status_error;
  if (!std::filesystem::is_directory(bundle, status_error)) {
    return foundation::Result<BundleLock>::failure(
        Error{
            status_error ? ErrorCode::io_error : ErrorCode::not_found,
            "project bundle directory does not exist",
            {
                {"path", bundle.generic_string()},
                {"system_error", status_error.message()},
            },
        });
  }
  const auto path = bundle / ".lock";
  const int descriptor =
      ::open(
          path.c_str(),
          O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW,
          0644);
  if (descriptor < 0) {
    return foundation::Result<BundleLock>::failure(
        io_error("project lock file could not be opened", path));
  }
  while (::flock(descriptor, LOCK_EX) != 0) {
    if (errno == EINTR) {
      continue;
    }
    const auto error =
        io_error("project lock could not be acquired", path);
    ::close(descriptor);
    return foundation::Result<BundleLock>::failure(error);
  }
  return foundation::Result<BundleLock>::success(BundleLock{descriptor});
}

foundation::Result<OwnedDescriptor> open_directory_without_symlinks(
    const std::filesystem::path& path) {
  auto normalized = path.lexically_normal();
#if defined(__APPLE__)
  const auto relative = normalized.relative_path();
  if (normalized.is_absolute() && !relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      normalized = std::filesystem::path("/private") / relative;
    }
  }
#endif
  if (normalized.empty()) {
    return foundation::Result<OwnedDescriptor>::failure(
        invalid_project("directory path is empty", path));
  }
  const int start = ::open(
      normalized.is_absolute() ? "/" : ".",
      O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (start < 0) {
    return foundation::Result<OwnedDescriptor>::failure(
        io_error("directory traversal root could not be opened", path));
  }
  OwnedDescriptor current(start);
  for (const auto& component : normalized.relative_path()) {
    if (component.empty() || component == ".") {
      continue;
    }
    if (component == "..") {
      return foundation::Result<OwnedDescriptor>::failure(
          invalid_project(
              "directory traversal cannot contain parent components",
              path));
    }
    const int next = ::openat(
        current.get(),
        component.c_str(),
        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (next < 0) {
      if (errno == ELOOP || errno == ENOTDIR) {
        return foundation::Result<OwnedDescriptor>::failure(
            invalid_project(
                "directory traversal encountered a symbolic or invalid component",
                path,
                component.generic_string()));
      }
      return foundation::Result<OwnedDescriptor>::failure(
          io_error(
              "directory traversal component could not be opened",
              path));
    }
    current = OwnedDescriptor(next);
  }
  return foundation::Result<OwnedDescriptor>::success(std::move(current));
}

foundation::Result<BundleLock> acquire_lock_at(
    int bundle_descriptor,
    const std::filesystem::path& bundle) {
  const int descriptor = ::openat(
      bundle_descriptor,
      ".lock",
      O_RDWR | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) {
    return foundation::Result<BundleLock>::failure(
        io_error(
            "project lock file could not be opened through bundle handle",
            bundle / ".lock"));
  }
  struct stat metadata {};
  if (::fstat(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode)) {
    const auto error = invalid_project(
        "project lock is not a regular file",
        bundle / ".lock");
    ::close(descriptor);
    return foundation::Result<BundleLock>::failure(error);
  }
  while (::flock(descriptor, LOCK_EX) != 0) {
    if (errno == EINTR) {
      continue;
    }
    const auto error =
        io_error("project lock could not be acquired", bundle / ".lock");
    ::close(descriptor);
    return foundation::Result<BundleLock>::failure(error);
  }
  return foundation::Result<BundleLock>::success(BundleLock{descriptor});
}

foundation::Result<void> write_all(
    int descriptor,
    std::string_view bytes,
    const std::filesystem::path& path) {
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto written = ::write(
        descriptor,
        bytes.data() + offset,
        bytes.size() - offset);
    if (written < 0) {
      if (errno == EINTR) {
        continue;
      }
      return foundation::Result<void>::failure(
          io_error("project bytes could not be written", path));
    }
    offset += static_cast<std::size_t>(written);
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> fsync_descriptor(
    int descriptor,
    const std::filesystem::path& path) {
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    return foundation::Result<void>::failure(
        io_error("project bytes could not be flushed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> fsync_directory(
    const std::filesystem::path& directory) {
  const int descriptor =
      ::open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (descriptor < 0) {
    return foundation::Result<void>::failure(
        io_error("project directory could not be opened for flush", directory));
  }
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    if (errno == EINVAL || errno == ENOTSUP) {
      ::close(descriptor);
      return foundation::Result<void>::success();
    }
    const auto error =
        io_error("project directory could not be flushed", directory);
    ::close(descriptor);
    return foundation::Result<void>::failure(error);
  }
  if (::close(descriptor) != 0) {
    return foundation::Result<void>::failure(
        io_error("project directory could not be closed", directory));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> fsync_active_directory(
    const std::filesystem::path& directory) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::active_directory_sync, directory);
  if (!intercepted.has_value()) {
    return intercepted;
  }
#endif
  return fsync_directory(directory);
}

foundation::Result<void> write_new_file(
    const std::filesystem::path& path,
    std::string_view bytes
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    ,
    std::optional<testing::FaultPoint> sync_fault = std::nullopt
#endif
    ) {
  const int descriptor =
      ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
  if (descriptor < 0) {
    return foundation::Result<void>::failure(
        io_error("project file could not be created", path));
  }
  const auto written = write_all(descriptor, bytes, path);
  auto synced = foundation::Result<void>::success();
  if (written.has_value()) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    if (sync_fault.has_value()) {
      synced = testing::detail::invoke_fault(*sync_fault, path);
    }
#endif
    if (synced.has_value()) {
      synced = fsync_descriptor(descriptor, path);
    }
  }
  const int close_result = ::close(descriptor);
  if (!written.has_value()) {
    return written;
  }
  if (!synced.has_value()) {
    return synced;
  }
  if (close_result != 0) {
    return foundation::Result<void>::failure(
        io_error("project file could not be closed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> rename_file(
    const std::filesystem::path& source,
    const std::filesystem::path& destination) {
  std::error_code error;
  std::filesystem::rename(source, destination, error);
  if (error) {
    return foundation::Result<void>::failure(
        io_error(
            "project file could not be published",
            destination,
            error.value()));
  }
  return foundation::Result<void>::success();
}

foundation::Result<nlohmann::json> read_json(
    const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    const auto code = std::filesystem::exists(path)
                          ? ErrorCode::io_error
                          : ErrorCode::not_found;
    return foundation::Result<nlohmann::json>::failure(
        Error{
            code,
            "project JSON file could not be opened",
            {{"path", path.generic_string()}},
        });
  }
  try {
    return foundation::Result<nlohmann::json>::success(
        nlohmann::json::parse(stream));
  } catch (const std::exception& exception) {
    return foundation::Result<nlohmann::json>::failure(
        invalid_project(
            "project JSON file could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<std::string> read_file_bytes(
    const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    return foundation::Result<std::string>::failure(
        io_error("project file could not be opened", path));
  }
  std::string bytes{
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
  if (stream.bad()) {
    return foundation::Result<std::string>::failure(
        io_error("project file could not be read completely", path));
  }
  return foundation::Result<std::string>::success(std::move(bytes));
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

nlohmann::json pattern_event_json(const domain::PatternEvent& event) {
  return {
      {"slot", slot_json(event.slot)},
      {"step", event.step},
      {"velocity", event.velocity},
  };
}

nlohmann::json raw_take_event_json(const domain::RawTakeEvent& event) {
  return {
      {"frame_offset", event.frame_offset},
      {"slot", slot_json(event.slot)},
      {"velocity", event.velocity},
  };
}

nlohmann::json pattern_value_json(const domain::Pattern& pattern) {
  auto events = nlohmann::json::array();
  for (const auto& event : pattern.events) {
    events.push_back(pattern_event_json(event));
  }
  return {
      {"bars", pattern.bars},
      {"events", std::move(events)},
  };
}

nlohmann::json pattern_json(const domain::Pattern& pattern) {
  auto encoded = pattern_value_json(pattern);
  encoded["id"] = pattern.id.value();
  return encoded;
}

nlohmann::json take_value_json(const domain::RawTake& take) {
  auto events = nlohmann::json::array();
  for (const auto& event : take.events) {
    events.push_back(raw_take_event_json(event));
  }
  return {
      {"events", std::move(events)},
      {"sample_rate", take.sample_rate},
  };
}

nlohmann::json take_json(const domain::RawTake& take) {
  auto encoded = take_value_json(take);
  encoded["id"] = take.id.value();
  return encoded;
}

nlohmann::json project_json(const domain::ProjectState& state) {
  auto banks = nlohmann::json::array();
  for (std::size_t bank = 0; bank < state.banks.size(); ++bank) {
    auto pads = nlohmann::json::array();
    for (const auto& slot : state.banks.at(bank)) {
      pads.push_back(
          {
              {"asset_id",
               slot.asset_id.has_value()
                   ? nlohmann::json(slot.asset_id->value())
                   : nlohmann::json(nullptr)},
              {"pad", slot.id.pad},
          });
    }
    banks.push_back(
        {
            {"bank", bank},
            {"pads", std::move(pads)},
        });
  }

  auto assets = nlohmann::json::object();
  for (const auto& [id, asset] : state.assets) {
    assets[id.value()] = {{"artifact", asset.artifact}};
  }
  auto takes = nlohmann::json::object();
  for (const auto& [id, take] : state.takes) {
    takes[id.value()] = take_value_json(take);
  }
  auto patterns = nlohmann::json::object();
  for (const auto& [id, pattern] : state.patterns) {
    patterns[id.value()] = pattern_value_json(pattern);
  }
  return {
      {"assets", std::move(assets)},
      {"banks", std::move(banks)},
      {"bpm", state.bpm},
      {"contract", "lmdj.project.v1"},
      {"patterns", std::move(patterns)},
      {"project_id", state.id.value()},
      {"revision", state.revision},
      {"takes", std::move(takes)},
  };
}

bool exact_object_keys(
    const nlohmann::json& input,
    std::initializer_list<std::string_view> keys) {
  if (!input.is_object() || input.size() != keys.size()) {
    return false;
  }
  return std::all_of(
      keys.begin(),
      keys.end(),
      [&input](std::string_view key) {
        return input.contains(std::string(key));
      });
}

std::optional<std::uint64_t> unsigned_integer_value(
    const nlohmann::json& input) {
  if (input.is_number_unsigned()) {
    return input.get<std::uint64_t>();
  }
  if (!input.is_number_integer()) {
    return std::nullopt;
  }
  const auto value = input.get<std::int64_t>();
  if (value < 0) {
    return std::nullopt;
  }
  return static_cast<std::uint64_t>(value);
}

bool nonnegative_integer(const nlohmann::json& input) {
  return unsigned_integer_value(input).has_value();
}

foundation::Result<domain::PadSlotId> parse_slot(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(input, {"bank", "pad"})) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project pad slot shape is invalid", path));
    }
    const auto bank = unsigned_integer_value(input.at("bank"));
    const auto pad = unsigned_integer_value(input.at("pad"));
    if (!bank.has_value() || !pad.has_value() ||
        *bank > 3 || *pad > 15) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project contains an invalid pad slot", path));
    }
    domain::PadSlotId slot{
        static_cast<std::uint8_t>(*bank),
        static_cast<std::uint8_t>(*pad),
    };
    if (!domain::is_valid_slot(slot)) {
      return foundation::Result<domain::PadSlotId>::failure(
          invalid_project("project contains an invalid pad slot", path));
    }
    return foundation::Result<domain::PadSlotId>::success(slot);
  } catch (const std::exception& exception) {
    return foundation::Result<domain::PadSlotId>::failure(
        invalid_project(
            "project pad slot could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::Pattern> parse_pattern(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(input, {"bars", "events", "id"}) ||
        !input.at("events").is_array()) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern shape is invalid", path));
    }
    const auto bars = unsigned_integer_value(input.at("bars"));
    if (!bars.has_value() ||
        (*bars != 1 && *bars != 2 && *bars != 4 && *bars != 8)) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern metadata is invalid", path));
    }
    domain::Pattern pattern{
        foundation::PatternId{input.at("id").get<std::string>()},
        static_cast<std::uint8_t>(*bars),
        {},
    };
    if (!domain::is_valid_uuid(pattern.id.value()) ||
        (pattern.bars != 1 && pattern.bars != 2 &&
         pattern.bars != 4 && pattern.bars != 8)) {
      return foundation::Result<domain::Pattern>::failure(
          invalid_project("project pattern metadata is invalid", path));
    }
    const auto step_limit =
        static_cast<std::uint32_t>(pattern.bars) * 16;
    for (const auto& encoded : input.at("events")) {
      if (!exact_object_keys(
              encoded, {"slot", "step", "velocity"})) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event shape is invalid", path));
      }
      const auto step = unsigned_integer_value(encoded.at("step"));
      const auto velocity =
          unsigned_integer_value(encoded.at("velocity"));
      if (!step.has_value() || !velocity.has_value() ||
          *step > std::numeric_limits<std::uint32_t>::max() ||
          *velocity > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      auto slot = parse_slot(encoded.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::Pattern>::failure(slot.error());
      }
      domain::PatternEvent event{
          slot.value(),
          static_cast<std::uint32_t>(*step),
          static_cast<std::uint8_t>(*velocity),
      };
      if (event.velocity < 1 || event.velocity > 127 ||
          event.step >= step_limit) {
        return foundation::Result<domain::Pattern>::failure(
            invalid_project("project pattern event is invalid", path));
      }
      pattern.events.push_back(event);
    }
    return foundation::Result<domain::Pattern>::success(std::move(pattern));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::Pattern>::failure(
        invalid_project(
            "project pattern could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::RawTake> parse_take(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(
            input, {"events", "id", "sample_rate"}) ||
        !input.at("events").is_array()) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take shape is invalid", path));
    }
    const auto sample_rate =
        unsigned_integer_value(input.at("sample_rate"));
    if (!sample_rate.has_value() || *sample_rate != 48000) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take metadata is invalid", path));
    }
    domain::RawTake take{
        foundation::TakeId{input.at("id").get<std::string>()},
        static_cast<std::uint32_t>(*sample_rate),
        {},
    };
    if (!domain::is_valid_uuid(take.id.value()) ||
        take.sample_rate != 48000) {
      return foundation::Result<domain::RawTake>::failure(
          invalid_project("project raw take metadata is invalid", path));
    }
    for (const auto& encoded : input.at("events")) {
      if (!exact_object_keys(
              encoded, {"frame_offset", "slot", "velocity"})) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event shape is invalid", path));
      }
      const auto frame_offset =
          unsigned_integer_value(encoded.at("frame_offset"));
      const auto velocity =
          unsigned_integer_value(encoded.at("velocity"));
      if (!frame_offset.has_value() || !velocity.has_value() ||
          *frame_offset >
              std::numeric_limits<std::uint32_t>::max() ||
          *velocity > std::numeric_limits<std::uint8_t>::max()) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event is invalid", path));
      }
      auto slot = parse_slot(encoded.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::RawTake>::failure(slot.error());
      }
      domain::RawTakeEvent event{
          slot.value(),
          static_cast<std::uint32_t>(*frame_offset),
          static_cast<std::uint8_t>(*velocity),
      };
      if (event.velocity < 1 || event.velocity > 127) {
        return foundation::Result<domain::RawTake>::failure(
            invalid_project("project raw take event is invalid", path));
      }
      take.events.push_back(event);
    }
    return foundation::Result<domain::RawTake>::success(std::move(take));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::RawTake>::failure(
        invalid_project(
            "project raw take could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::Pattern> parse_project_pattern(
    std::string_view id,
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  if (!domain::is_valid_uuid(id) ||
      !exact_object_keys(input, {"bars", "events"})) {
    return foundation::Result<domain::Pattern>::failure(
        invalid_project("project pattern entry is invalid", path));
  }
  auto encoded = input;
  encoded["id"] = id;
  return parse_pattern(encoded, path);
}

foundation::Result<domain::RawTake> parse_project_take(
    std::string_view id,
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  if (!domain::is_valid_uuid(id) ||
      !exact_object_keys(input, {"events", "sample_rate"})) {
    return foundation::Result<domain::RawTake>::failure(
        invalid_project("project raw take entry is invalid", path));
  }
  auto encoded = input;
  encoded["id"] = id;
  return parse_take(encoded, path);
}

foundation::Result<domain::ProjectState> parse_project(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    if (!exact_object_keys(
            input,
            {
                "assets",
                "banks",
                "bpm",
                "contract",
                "patterns",
                "project_id",
                "revision",
                "takes",
            }) ||
        input.at("contract") != "lmdj.project.v1" ||
        !nonnegative_integer(input.at("revision")) ||
        !nonnegative_integer(input.at("bpm")) ||
        !input.at("banks").is_array() ||
        !input.at("assets").is_object() ||
        !input.at("takes").is_object() ||
        !input.at("patterns").is_object()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project checkpoint contract is invalid", path));
    }
    const auto bpm = unsigned_integer_value(input.at("bpm"));
    const auto revision =
        unsigned_integer_value(input.at("revision"));
    if (!bpm.has_value() || *bpm > 240 ||
        !revision.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project metadata is invalid", path));
    }
    auto created = domain::create_project(
        foundation::ProjectId{
            input.at("project_id").get<std::string>()},
        static_cast<std::uint16_t>(*bpm));
    if (!created.has_value()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project metadata is invalid", path));
    }
    auto state = std::move(created.value());
    state.revision = *revision;

    const auto& banks = input.at("banks");
    if (banks.size() != state.banks.size()) {
      return foundation::Result<domain::ProjectState>::failure(
          invalid_project("project bank count is invalid", path));
    }
    std::array<bool, 4> seen_banks{};
    for (const auto& encoded_bank : banks) {
      if (!exact_object_keys(encoded_bank, {"bank", "pads"}) ||
          !nonnegative_integer(encoded_bank.at("bank")) ||
          !encoded_bank.at("pads").is_array()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project bank shape is invalid", path));
      }
      const auto bank =
          unsigned_integer_value(encoded_bank.at("bank"));
      if (!bank.has_value() ||
          *bank >= state.banks.size() || seen_banks.at(*bank) ||
          encoded_bank.at("pads").size() !=
              state.banks.at(*bank).size()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project bank layout is invalid", path));
      }
      seen_banks.at(*bank) = true;
      std::array<bool, 16> seen_pads{};
      for (const auto& encoded_pad : encoded_bank.at("pads")) {
        if (!exact_object_keys(
                encoded_pad, {"asset_id", "pad"}) ||
            !nonnegative_integer(encoded_pad.at("pad"))) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project pad shape is invalid", path));
        }
        const auto pad =
            unsigned_integer_value(encoded_pad.at("pad"));
        if (!pad.has_value() ||
            *pad >= state.banks.at(*bank).size() ||
            seen_pads.at(*pad)) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project("project pad layout is invalid", path));
        }
        seen_pads.at(*pad) = true;
        if (encoded_pad.at("asset_id").is_null()) {
          state.banks.at(*bank).at(*pad).asset_id =
              std::nullopt;
        } else {
          const auto asset_id =
              encoded_pad.at("asset_id").get<std::string>();
          if (!domain::is_valid_uuid(asset_id)) {
            return foundation::Result<domain::ProjectState>::failure(
                invalid_project(
                    "project pad asset reference is invalid",
                    path));
          }
          state.banks.at(*bank).at(*pad).asset_id =
              foundation::AssetId{asset_id};
        }
      }
    }

    for (auto iterator = input.at("assets").begin();
         iterator != input.at("assets").end();
         ++iterator) {
      const auto& encoded = iterator.value();
      if (!domain::is_valid_uuid(iterator.key()) ||
          !exact_object_keys(encoded, {"artifact"}) ||
          !exact_object_keys(
              encoded.at("artifact"),
              {"byte_length", "media_type", "sha256"}) ||
          !nonnegative_integer(
              encoded.at("artifact").at("byte_length")) ||
          !encoded.at("artifact").at("media_type").is_string() ||
          encoded.at("artifact").at("media_type")
              .get<std::string>()
              .empty() ||
          !encoded.at("artifact").at("sha256").is_string()) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project asset entry is invalid", path));
      }
      domain::Asset asset{
          foundation::AssetId{iterator.key()},
          foundation::ArtifactRef{
              encoded.at("artifact")
                  .at("sha256")
                  .get<std::string>(),
              encoded.at("artifact")
                  .at("media_type")
                  .get<std::string>(),
              encoded.at("artifact")
                  .at("byte_length")
                  .get<std::uint64_t>(),
          },
      };
      if (!valid_sha256(asset.artifact.sha256)) {
        return foundation::Result<domain::ProjectState>::failure(
            invalid_project("project artifact reference is invalid", path));
      }
      state.assets.emplace(asset.id, asset);
    }
    for (const auto& bank : state.banks) {
      for (const auto& slot : bank) {
        if (slot.asset_id.has_value() &&
            !state.assets.contains(*slot.asset_id)) {
          return foundation::Result<domain::ProjectState>::failure(
              invalid_project(
                  "project pad references a missing asset",
                  path));
        }
      }
    }

    for (auto iterator = input.at("takes").begin();
         iterator != input.at("takes").end();
         ++iterator) {
      auto take =
          parse_project_take(iterator.key(), iterator.value(), path);
      if (!take.has_value()) {
        return foundation::Result<domain::ProjectState>::failure(take.error());
      }
      state.takes.emplace(take.value().id, take.value());
    }
    for (auto iterator = input.at("patterns").begin();
         iterator != input.at("patterns").end();
         ++iterator) {
      auto pattern = parse_project_pattern(
          iterator.key(), iterator.value(), path);
      if (!pattern.has_value()) {
        return foundation::Result<domain::ProjectState>::failure(
            pattern.error());
      }
      state.patterns.emplace(pattern.value().id, pattern.value());
    }
    return foundation::Result<domain::ProjectState>::success(std::move(state));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::ProjectState>::failure(
        invalid_project(
            "project checkpoint could not be parsed",
            path,
            exception.what()));
  }
}

nlohmann::json meta_json(const domain::CommandMeta& meta) {
  return {
      {"command_id", meta.command_id.value()},
      {"expected_revision", meta.expected_revision},
  };
}

const domain::CommandMeta& command_meta(const domain::Command& command) {
  return std::visit(
      [](const auto& value) -> const domain::CommandMeta& {
        return value.meta;
      },
      command);
}

nlohmann::json command_json(const domain::Command& command) {
  return std::visit(
      [](const auto& value) -> nlohmann::json {
        using Type = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Type, domain::ImportAsset>) {
          return {
              {"asset",
               {
                   {"artifact", value.asset.artifact},
                   {"id", value.asset.id.value()},
               }},
              {"meta", meta_json(value.meta)},
              {"type", "ImportAsset"},
          };
        } else if constexpr (std::is_same_v<Type, domain::AssignPad>) {
          return {
              {"asset_id",
               value.asset_id.has_value()
                   ? nlohmann::json(value.asset_id->value())
                   : nlohmann::json(nullptr)},
              {"meta", meta_json(value.meta)},
              {"slot", slot_json(value.slot)},
              {"type", "AssignPad"},
          };
        } else if constexpr (std::is_same_v<Type, domain::RecordTake>) {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern", pattern_json(value.pattern)},
              {"take", take_json(value.take)},
              {"type", "RecordTake"},
          };
        } else {
          return {
              {"meta", meta_json(value.meta)},
              {"pattern", pattern_json(value.pattern)},
              {"type", "CreatePattern"},
          };
        }
      },
      command);
}

foundation::Result<domain::CommandMeta> parse_meta(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    domain::CommandMeta meta{
        foundation::CommandId{input.at("command_id").get<std::string>()},
        input.at("expected_revision").get<std::uint64_t>(),
    };
    if (!domain::is_valid_uuid(meta.command_id.value())) {
      return foundation::Result<domain::CommandMeta>::failure(
          invalid_project("transaction command id is invalid", path));
    }
    return foundation::Result<domain::CommandMeta>::success(std::move(meta));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::CommandMeta>::failure(
        invalid_project(
            "transaction command metadata could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<domain::Command> parse_command(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    auto meta = parse_meta(input.at("meta"), path);
    if (!meta.has_value()) {
      return foundation::Result<domain::Command>::failure(meta.error());
    }
    const auto type = input.at("type").get<std::string>();
    if (type == "ImportAsset") {
      const auto& encoded = input.at("asset");
      return foundation::Result<domain::Command>::success(
          domain::Command{domain::ImportAsset{
              std::move(meta.value()),
              domain::Asset{
                  foundation::AssetId{
                      encoded.at("id").get<std::string>()},
                  encoded.at("artifact")
                      .get<foundation::ArtifactRef>(),
              },
          }});
    }
    if (type == "AssignPad") {
      auto slot = parse_slot(input.at("slot"), path);
      if (!slot.has_value()) {
        return foundation::Result<domain::Command>::failure(slot.error());
      }
      std::optional<foundation::AssetId> asset_id;
      if (!input.at("asset_id").is_null()) {
        asset_id = foundation::AssetId{
            input.at("asset_id").get<std::string>()};
      }
      return foundation::Result<domain::Command>::success(
          domain::Command{domain::AssignPad{
              std::move(meta.value()),
              slot.value(),
              std::move(asset_id),
          }});
    }
    if (type == "RecordTake") {
      auto take = parse_take(input.at("take"), path);
      auto pattern = parse_pattern(input.at("pattern"), path);
      if (!take.has_value()) {
        return foundation::Result<domain::Command>::failure(take.error());
      }
      if (!pattern.has_value()) {
        return foundation::Result<domain::Command>::failure(pattern.error());
      }
      return foundation::Result<domain::Command>::success(
          domain::Command{domain::RecordTake{
              std::move(meta.value()),
              std::move(take.value()),
              std::move(pattern.value()),
          }});
    }
    if (type == "CreatePattern") {
      auto pattern = parse_pattern(input.at("pattern"), path);
      if (!pattern.has_value()) {
        return foundation::Result<domain::Command>::failure(pattern.error());
      }
      return foundation::Result<domain::Command>::success(
          domain::Command{domain::CreatePattern{
              std::move(meta.value()),
              std::move(pattern.value()),
          }});
    }
    return foundation::Result<domain::Command>::failure(
        invalid_project("transaction command type is unknown", path));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::Command>::failure(
        invalid_project(
            "transaction command could not be parsed",
            path,
            exception.what()));
  }
}

bool safe_relative_path(
    const std::filesystem::path& relative,
    const std::filesystem::path& required_parent) {
  if (relative.empty() || relative.is_absolute() ||
      relative.lexically_normal() != relative) {
    return false;
  }
  auto iterator = relative.begin();
  auto parent_iterator = required_parent.begin();
  for (; parent_iterator != required_parent.end(); ++parent_iterator) {
    if (iterator == relative.end() || *iterator != *parent_iterator) {
      return false;
    }
    ++iterator;
  }
  return iterator != relative.end();
}

foundation::Result<LoadedProject> load_project(
    const std::filesystem::path& bundle) {
  const auto manifest_path = bundle / "manifest.json";
  auto manifest_result = read_json(manifest_path);
  if (!manifest_result.has_value()) {
    return foundation::Result<LoadedProject>::failure(
        manifest_result.error());
  }

  try {
    const auto& manifest = manifest_result.value();
    if (manifest.at("contract") != "lmdj.project.manifest.v1") {
      return foundation::Result<LoadedProject>::failure(
          invalid_project("project manifest contract is invalid", manifest_path));
    }
    const auto head_revision =
        manifest.at("head_revision").get<std::uint64_t>();
    const auto head_checkpoint =
        std::filesystem::path{
            manifest.at("head_checkpoint").get<std::string>()};
    const auto expected_head =
        std::filesystem::path{"history/checkpoints"} /
        (std::to_string(head_revision) + ".json");
    if (head_checkpoint != expected_head ||
        !safe_relative_path(
            head_checkpoint, "history/checkpoints")) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project("project manifest checkpoint path is invalid", manifest_path));
    }

    auto initial_json =
        read_json(bundle / "history/checkpoints/0.json");
    if (!initial_json.has_value()) {
      return foundation::Result<LoadedProject>::failure(initial_json.error());
    }
    auto initial = parse_project(
        initial_json.value(), bundle / "history/checkpoints/0.json");
    if (!initial.has_value()) {
      return foundation::Result<LoadedProject>::failure(initial.error());
    }
    if (initial.value().revision != 0) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "initial checkpoint revision is not zero",
              bundle / "history/checkpoints/0.json"));
    }

    LoadedProject loaded{
        std::move(initial.value()),
        {},
        {},
        {},
        {},
    };
    for (const auto& encoded_path : manifest.at("transactions")) {
      const auto relative =
          std::filesystem::path{encoded_path.get<std::string>()};
      if (!safe_relative_path(relative, "history/transactions")) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project("project transaction path is invalid", manifest_path));
      }
      auto transaction = read_json(bundle / relative);
      if (!transaction.has_value()) {
        return foundation::Result<LoadedProject>::failure(
            transaction.error());
      }
      auto command =
          parse_command(transaction.value().at("command"), bundle / relative);
      if (!command.has_value()) {
        return foundation::Result<LoadedProject>::failure(command.error());
      }
      const auto applied =
          domain::apply(loaded.state, command.value(), loaded.receipts);
      if (!applied.has_value() || applied.value().replayed) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project transaction could not be replayed",
                bundle / relative));
      }
      const auto revision =
          transaction.value().at("revision").get<std::uint64_t>();
      if (revision != applied.value().state.revision ||
          transaction.value().at("event") != applied.value().event) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project transaction receipt does not match replay",
                bundle / relative));
      }
      const auto& meta = command_meta(command.value());
      loaded.commands.emplace(meta.command_id, command.value());
      loaded.receipts.emplace(
          meta.command_id,
          domain::CommandReceipt{revision, applied.value().event});
      if (transaction.value().contains("cleanup_take_id")) {
        const auto cleanup_take_id =
            foundation::TakeId{
                transaction.value()
                    .at("cleanup_take_id")
                    .get<std::string>()};
        const auto* record =
            std::get_if<domain::RecordTake>(&command.value());
        if (record == nullptr ||
            !domain::is_valid_uuid(cleanup_take_id.value()) ||
            cleanup_take_id != record->take.id) {
          return foundation::Result<LoadedProject>::failure(
              invalid_project(
                  "project transaction cleanup obligation is invalid",
                  bundle / relative));
        }
        loaded.cleanup_obligations.emplace(
            meta.command_id, cleanup_take_id);
      }
      loaded.state = applied.value().state;
      loaded.transactions.push_back(relative.generic_string());
    }
    if (loaded.state.revision != head_revision) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "project manifest head does not match transaction replay",
              manifest_path));
    }

    auto checkpoint_json = read_json(bundle / head_checkpoint);
    if (!checkpoint_json.has_value()) {
      return foundation::Result<LoadedProject>::failure(
          checkpoint_json.error());
    }
    auto checkpoint =
        parse_project(checkpoint_json.value(), bundle / head_checkpoint);
    if (!checkpoint.has_value()) {
      return foundation::Result<LoadedProject>::failure(checkpoint.error());
    }
    if (checkpoint.value() != loaded.state ||
        foundation::canonical_json(checkpoint_json.value()) !=
            foundation::canonical_json(project_json(loaded.state))) {
      return foundation::Result<LoadedProject>::failure(
          invalid_project(
              "project checkpoint does not match transaction replay",
              bundle / head_checkpoint));
    }

    for (const auto& [asset_id, asset] : loaded.state.assets) {
      (void)asset_id;
      const auto blob =
          bundle / "assets" / (asset.artifact.sha256 + ".wav");
      const auto described =
          foundation::describe_artifact(blob, asset.artifact.media_type);
      if (!described.has_value() ||
          described.value() != asset.artifact) {
        return foundation::Result<LoadedProject>::failure(
            invalid_project(
                "project asset blob is missing or corrupt",
                blob));
      }
    }
    return foundation::Result<LoadedProject>::success(std::move(loaded));
  } catch (const std::exception& exception) {
    return foundation::Result<LoadedProject>::failure(
        invalid_project(
            "project manifest could not be validated",
            manifest_path,
            exception.what()));
  }
}

std::optional<std::uint64_t> leading_revision(std::string_view name) {
  const auto end = name.find_first_of("-.");
  if (end == std::string_view::npos || end == 0) {
    return std::nullopt;
  }
  std::uint64_t value = 0;
  const auto parsed =
      std::from_chars(name.data(), name.data() + end, value);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != name.data() + end) {
    return std::nullopt;
  }
  return value;
}

bool checkpoint_temp_name(std::string_view name) {
  constexpr std::string_view suffix = ".json.tmp";
  if (!name.ends_with(suffix)) {
    return false;
  }
  const auto revision = name.substr(0, name.size() - suffix.size());
  std::uint64_t parsed_revision = 0;
  const auto parsed = std::from_chars(
      revision.data(), revision.data() + revision.size(), parsed_revision);
  return parsed.ec == std::errc{} &&
         parsed.ptr == revision.data() + revision.size();
}

bool transaction_temp_name(std::string_view name) {
  constexpr std::string_view suffix = ".json.tmp";
  if (!name.ends_with(suffix)) {
    return false;
  }
  const auto stem = name.substr(0, name.size() - suffix.size());
  const auto separator = stem.find('-');
  if (separator == std::string_view::npos || separator == 0) {
    return false;
  }
  std::uint64_t revision = 0;
  const auto parsed = std::from_chars(
      stem.data(), stem.data() + separator, revision);
  return parsed.ec == std::errc{} &&
         parsed.ptr == stem.data() + separator &&
         domain::is_valid_uuid(stem.substr(separator + 1));
}

bool asset_temp_name(std::string_view name) {
  constexpr std::string_view marker = ".wav.tmp.";
  return name.size() > 64 + marker.size() &&
         valid_sha256(name.substr(0, 64)) &&
         name.substr(64, marker.size()) == marker &&
         domain::is_valid_uuid(name.substr(64 + marker.size()));
}

bool manifest_temp_name(std::string_view name) {
  constexpr std::string_view prefix = "manifest.json.tmp.";
  return name.starts_with(prefix) &&
         domain::is_valid_uuid(name.substr(prefix.size()));
}

foundation::Result<void> recover_uncommitted(
    const std::filesystem::path& bundle,
    const LoadedProject& loaded) {
  const auto checkpoints = bundle / "history/checkpoints";
  const auto transactions = bundle / "history/transactions";
  const auto assets = bundle / "assets";
  bool checkpoints_changed = false;
  bool transactions_changed = false;
  bool assets_changed = false;
  bool bundle_changed = false;
  const std::set<std::string> committed_transactions(
      loaded.transactions.begin(), loaded.transactions.end());

  std::error_code error;
  for (const auto& entry : std::filesystem::directory_iterator(checkpoints)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    const auto name = entry.path().filename().string();
    const auto revision = leading_revision(name);
    if (checkpoint_temp_name(name) ||
        (revision.has_value() && *revision > loaded.state.revision)) {
      std::filesystem::remove(entry.path(), error);
      if (error) {
        return foundation::Result<void>::failure(
            io_error(
                "orphan checkpoint could not be removed",
                entry.path(),
                error.value()));
      }
      checkpoints_changed = true;
    }
  }
  for (const auto& entry : std::filesystem::directory_iterator(transactions)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    const auto name = entry.path().filename().string();
    const auto relative =
        std::filesystem::relative(entry.path(), bundle).generic_string();
    if (committed_transactions.contains(relative)) {
      continue;
    }
    const auto revision = leading_revision(name);
    if (transaction_temp_name(name) ||
        (revision.has_value() && *revision > loaded.state.revision)) {
      std::filesystem::remove(entry.path(), error);
      if (error) {
        return foundation::Result<void>::failure(
            io_error(
                "orphan transaction could not be removed",
                entry.path(),
                error.value()));
      }
      transactions_changed = true;
    }
  }

  std::set<std::string> referenced_assets;
  for (const auto& [asset_id, asset] : loaded.state.assets) {
    (void)asset_id;
    referenced_assets.insert(asset.artifact.sha256);
  }
  for (const auto& entry : std::filesystem::directory_iterator(assets)) {
    if (!entry.is_regular_file()) {
      continue;
    }
    const auto name = entry.path().filename().string();
    const auto stem = entry.path().stem().string();
    if (asset_temp_name(name) ||
        (entry.path().extension() == ".wav" &&
         valid_sha256(stem) &&
         !referenced_assets.contains(stem))) {
      std::filesystem::remove(entry.path(), error);
      if (error) {
        return foundation::Result<void>::failure(
            io_error(
                "orphan asset could not be removed",
                entry.path(),
                error.value()));
      }
      assets_changed = true;
    }
  }
  for (const auto& entry : std::filesystem::directory_iterator(bundle)) {
    const auto name = entry.path().filename().string();
    if (entry.is_regular_file() && manifest_temp_name(name)) {
      std::filesystem::remove(entry.path(), error);
      if (error) {
        return foundation::Result<void>::failure(
            io_error(
                "orphan manifest temp file could not be removed",
                entry.path(),
                error.value()));
      }
      bundle_changed = true;
    }
  }

  if (checkpoints_changed) {
    const auto synced = fsync_directory(checkpoints);
    if (!synced.has_value()) {
      return synced;
    }
  }
  if (transactions_changed) {
    const auto synced = fsync_directory(transactions);
    if (!synced.has_value()) {
      return synced;
    }
  }
  if (assets_changed) {
    const auto synced = fsync_directory(assets);
    if (!synced.has_value()) {
      return synced;
    }
  }
  if (bundle_changed) {
    return fsync_directory(bundle);
  }
  return foundation::Result<void>::success();
}

nlohmann::json manifest_json(
    std::uint64_t revision,
    const std::vector<std::string>& transactions) {
  return {
      {"contract", "lmdj.project.manifest.v1"},
      {"head_checkpoint",
       "history/checkpoints/" + std::to_string(revision) + ".json"},
      {"head_revision", revision},
      {"transactions", transactions},
  };
}

foundation::Result<void> publish_artifact(
    const std::filesystem::path& bundle,
    const ArtifactStage& stage) {
  const auto directory = bundle / "assets";
  const auto final_path =
      directory / (stage.artifact.sha256 + ".wav");
  if (std::filesystem::exists(final_path)) {
    const auto described = foundation::describe_artifact(
        final_path, stage.artifact.media_type);
    if (!described.has_value() ||
        described.value() != stage.artifact) {
      return foundation::Result<void>::failure(
          invalid_project(
              "content-addressed asset path contains different bytes",
              final_path));
    }
    return foundation::Result<void>::success();
  }

  const auto temp_path =
      final_path.string() + ".tmp." + stage.command_id.value();
  const int source =
      ::open(stage.source.c_str(), O_RDONLY | O_CLOEXEC);
  if (source < 0) {
    return foundation::Result<void>::failure(
        io_error("source artifact could not be opened", stage.source));
  }
  const int destination = ::open(
      temp_path.c_str(),
      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC,
      0644);
  if (destination < 0) {
    const auto error =
        io_error("staged artifact could not be created", temp_path);
    ::close(source);
    return foundation::Result<void>::failure(error);
  }

  std::array<char, 64U * 1024U> buffer{};
  foundation::Result<void> copied =
      foundation::Result<void>::success();
  while (copied.has_value()) {
    const auto count = ::read(source, buffer.data(), buffer.size());
    if (count == 0) {
      break;
    }
    if (count < 0) {
      if (errno == EINTR) {
        continue;
      }
      copied = foundation::Result<void>::failure(
          io_error("source artifact could not be read", stage.source));
      break;
    }
    copied = write_all(
        destination,
        std::string_view(buffer.data(), static_cast<std::size_t>(count)),
        temp_path);
  }
  if (copied.has_value()) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    copied = testing::detail::invoke_fault(
        testing::FaultPoint::artifact_temp_sync, temp_path);
#endif
  }
  if (copied.has_value()) {
    copied = fsync_descriptor(destination, temp_path);
  }
  const int source_close = ::close(source);
  const int destination_close = ::close(destination);
  if (!copied.has_value()) {
    return copied;
  }
  if (source_close != 0 || destination_close != 0) {
    return foundation::Result<void>::failure(
        io_error("artifact file could not be closed", temp_path));
  }
  const auto described =
      foundation::describe_artifact(temp_path, stage.artifact.media_type);
  if (!described.has_value() ||
      described.value() != stage.artifact) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "source artifact changed while it was imported",
            {{"path", stage.source.generic_string()}},
        });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto publish_intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::artifact_publish, final_path);
  if (!publish_intercepted.has_value()) {
    return publish_intercepted;
  }
#endif
  const auto renamed = rename_file(temp_path, final_path);
  if (!renamed.has_value()) {
    return renamed;
  }
  return fsync_directory(directory);
}

foundation::Result<bool> matching_active_journal(
    const std::filesystem::path& bundle,
    const domain::RecordTake& record) {
  const auto path =
      bundle / "recovery/active" /
      (record.take.id.value() + ".jsonl");
  if (!std::filesystem::exists(path)) {
    return foundation::Result<bool>::success(false);
  }
  if (!domain::is_valid_uuid(record.take.id.value())) {
    return foundation::Result<bool>::failure(
        Error{ErrorCode::invalid_argument, "take id is not a safe file name"});
  }
  std::ifstream stream(path, std::ios::binary);
  std::string first_line;
  if (!stream || !std::getline(stream, first_line)) {
    return foundation::Result<bool>::failure(
        invalid_project("active take journal could not be read", path));
  }
  try {
    const auto header = nlohmann::json::parse(first_line);
    TakeJournal journal;
    const auto take =
        journal.read_active(bundle, record.take.id);
    if (!take.has_value()) {
      return foundation::Result<bool>::failure(take.error());
    }
    return foundation::Result<bool>::success(
        header.at("expected_revision").get<std::uint64_t>() ==
            record.meta.expected_revision &&
        take.value() == record.take);
  } catch (const std::exception& exception) {
    return foundation::Result<bool>::failure(
        invalid_project(
            "active take journal metadata could not be parsed",
            path,
            exception.what()));
  }
}

foundation::Result<void> complete_journal_cleanup(
    const std::filesystem::path& bundle,
    const std::optional<foundation::TakeId>& cleanup_take_id) {
  if (!cleanup_take_id.has_value()) {
    return foundation::Result<void>::success();
  }
  const auto path =
      bundle / "recovery/active" /
      (cleanup_take_id->value() + ".jsonl");
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto remove_intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::active_journal_remove, path);
  if (!remove_intercepted.has_value()) {
    return remove_intercepted;
  }
#endif
  std::error_code error;
  std::filesystem::remove(path, error);
  if (error) {
    return foundation::Result<void>::failure(
        io_error(
            "active journal could not be removed after Project commit",
            path,
            error.value()));
  }
  return fsync_active_directory(path.parent_path());
}

foundation::Result<domain::AppliedCommand> commit_loaded(
    const std::filesystem::path& bundle,
    LoadedProject loaded,
    const domain::Command& command,
    const std::optional<ArtifactStage>& artifact_stage,
    domain::Command* persisted_identity) {
  const auto& meta = command_meta(command);
  if (!domain::is_valid_uuid(meta.command_id.value())) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id is not a safe file name",
        });
  }

  const bool replay_candidate =
      loaded.receipts.contains(meta.command_id);
  if (replay_candidate) {
    const auto original = loaded.commands.find(meta.command_id);
    if (original == loaded.commands.end()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          invalid_project(
              "persisted command identity is missing",
              bundle / "manifest.json"));
    }
    if (command_json(original->second) != command_json(command)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id is already bound to a different command identity",
          });
    }
    if (persisted_identity != nullptr) {
      *persisted_identity = original->second;
    }
  } else if (persisted_identity != nullptr) {
    *persisted_identity = command;
  }
  bool journal_matches = false;
  std::optional<foundation::TakeId> cleanup_take_id;
  if (!replay_candidate) {
    const auto* record = std::get_if<domain::RecordTake>(&command);
    if (record != nullptr) {
      const auto matching = matching_active_journal(bundle, *record);
      if (!matching.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            matching.error());
      }
      journal_matches = matching.value();
      if (journal_matches) {
        cleanup_take_id = record->take.id;
      }
    }
  }

  const auto applied =
      domain::apply(loaded.state, command, loaded.receipts);
  if (!applied.has_value()) {
    if (applied.error().code == ErrorCode::revision_conflict &&
        journal_matches) {
      const auto& record = std::get<domain::RecordTake>(command);
      TakeJournal journal;
      const auto sealed =
          journal.seal(bundle, record.take.id, "revision_conflict");
      if (!sealed.has_value()) {
        return foundation::Result<domain::AppliedCommand>::failure(
            sealed.error());
      }
    }
    return foundation::Result<domain::AppliedCommand>::failure(
        applied.error());
  }
  if (applied.value().replayed) {
    const auto obligation =
        loaded.cleanup_obligations.find(meta.command_id);
    if (obligation != loaded.cleanup_obligations.end()) {
      cleanup_take_id = obligation->second;
    }
    const auto cleanup =
        complete_journal_cleanup(bundle, cleanup_take_id);
    if (!cleanup.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          cleanup.error());
    }
    return applied;
  }

  const auto encoded_state = project_json(applied.value().state);
  const auto validated_state =
      parse_project(encoded_state, bundle / "manifest.json");
  if (!validated_state.has_value() ||
      validated_state.value() != applied.value().state) {
    return foundation::Result<domain::AppliedCommand>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command result cannot be persisted as valid Project Truth",
        });
  }

  if (artifact_stage.has_value()) {
    const auto published = publish_artifact(bundle, *artifact_stage);
    if (!published.has_value()) {
      return foundation::Result<domain::AppliedCommand>::failure(
          published.error());
    }
  } else if (const auto* import =
                 std::get_if<domain::ImportAsset>(&command)) {
    if (!valid_sha256(import->asset.artifact.sha256)) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::invalid_argument,
              "ImportAsset SHA-256 is invalid",
          });
    }
    const auto blob =
        bundle / "assets" /
        (import->asset.artifact.sha256 + ".wav");
    const auto described = foundation::describe_artifact(
        blob, import->asset.artifact.media_type);
    if (!described.has_value() ||
        described.value() != import->asset.artifact) {
      return foundation::Result<domain::AppliedCommand>::failure(
          Error{
              ErrorCode::missing_asset,
              "ImportAsset must reference an existing bundle artifact",
              {{"path", blob.generic_string()}},
          });
    }
  }

  const auto revision = applied.value().state.revision;
  const auto transaction_relative =
      std::filesystem::path{"history/transactions"} /
      (std::to_string(revision) + "-" +
       meta.command_id.value() + ".json");
  const auto checkpoint_relative =
      std::filesystem::path{"history/checkpoints"} /
      (std::to_string(revision) + ".json");
  const auto transaction_final = bundle / transaction_relative;
  const auto checkpoint_final = bundle / checkpoint_relative;
  const auto transaction_temp =
      std::filesystem::path{transaction_final.string() + ".tmp"};
  const auto checkpoint_temp =
      std::filesystem::path{checkpoint_final.string() + ".tmp"};

  nlohmann::json transaction = {
      {"command", command_json(command)},
      {"event", applied.value().event},
      {"revision", revision},
  };
  if (cleanup_take_id.has_value()) {
    transaction["cleanup_take_id"] = cleanup_take_id->value();
  }
  auto written = write_new_file(
      transaction_temp,
      foundation::canonical_json(transaction) + "\n"
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
      ,
      testing::FaultPoint::transaction_temp_sync
#endif
  );
  if (!written.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }
  written = write_new_file(
      checkpoint_temp,
      foundation::canonical_json(project_json(applied.value().state)) +
          "\n"
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
      ,
      testing::FaultPoint::checkpoint_temp_sync
#endif
  );
  if (!written.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  auto publish_intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::transaction_publish, transaction_final);
  if (!publish_intercepted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        publish_intercepted.error());
  }
#endif
  auto renamed = rename_file(transaction_temp, transaction_final);
  if (!renamed.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        renamed.error());
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  publish_intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::checkpoint_publish, checkpoint_final);
  if (!publish_intercepted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        publish_intercepted.error());
  }
#endif
  renamed = rename_file(checkpoint_temp, checkpoint_final);
  if (!renamed.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        renamed.error());
  }
  auto synced = fsync_directory(transaction_final.parent_path());
  if (!synced.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        synced.error());
  }
  synced = fsync_directory(checkpoint_final.parent_path());
  if (!synced.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        synced.error());
  }

  loaded.transactions.push_back(transaction_relative.generic_string());
  const auto manifest_temp =
      bundle /
      ("manifest.json.tmp." + meta.command_id.value());
  written = write_new_file(
      manifest_temp,
      foundation::canonical_json(
          manifest_json(revision, loaded.transactions)) +
          "\n"
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
      ,
      testing::FaultPoint::manifest_temp_sync
#endif
  );
  if (!written.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        written.error());
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  publish_intercepted = testing::detail::invoke_fault(
      testing::FaultPoint::manifest_publish, bundle / "manifest.json");
  if (!publish_intercepted.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        publish_intercepted.error());
  }
#endif
  renamed = rename_file(manifest_temp, bundle / "manifest.json");
  if (!renamed.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        renamed.error());
  }
  synced = fsync_directory(bundle);
  if (!synced.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        synced.error());
  }

  const auto cleanup =
      complete_journal_cleanup(bundle, cleanup_take_id);
  if (!cleanup.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        cleanup.error());
  }
  return applied;
}

foundation::Result<void> create_bundle_directories(
    const std::filesystem::path& bundle) {
  const std::array paths{
      bundle,
      bundle / "assets",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& path : paths) {
    std::error_code error;
    std::filesystem::create_directories(path, error);
    if (error) {
      return foundation::Result<void>::failure(
          io_error(
              "project bundle directory could not be created",
              path,
              error.value()));
    }
  }
  return foundation::Result<void>::success();
}

}  // namespace

foundation::Result<void> ProjectStore::create(
    const std::filesystem::path& bundle,
    const domain::ProjectState& initial) {
  if (bundle.extension() != ".lmdj" || initial.revision != 0) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "project bundle must end in .lmdj and start at revision zero",
        });
  }
  const auto encoded = project_json(initial);
  const auto validated = parse_project(encoded, bundle);
  if (!validated.has_value() || validated.value() != initial) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "initial project state is invalid",
        });
  }
  const auto existing_tree = reject_symlinks_in_existing_tree(bundle);
  if (!existing_tree.has_value()) {
    return existing_tree;
  }
  auto directories = create_bundle_directories(bundle);
  if (!directories.has_value()) {
    return directories;
  }
  auto lock_result = acquire_lock(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<void>::failure(lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  const auto locked_tree = reject_symlinks_in_existing_tree(bundle);
  if (!locked_tree.has_value()) {
    return locked_tree;
  }
  if (std::filesystem::exists(bundle / "manifest.json")) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::duplicate_id,
            "project bundle already has a manifest",
            {{"path", bundle.generic_string()}},
        });
  }

  const auto checkpoint_temp =
      bundle / "history/checkpoints/0.json.tmp.create";
  const auto checkpoint_final =
      bundle / "history/checkpoints/0.json";
  const auto manifest_temp =
      bundle / "manifest.json.tmp.create";
  std::error_code remove_error;
  const bool checkpoint_temp_removed =
      std::filesystem::remove(checkpoint_temp, remove_error);
  if (remove_error) {
    return foundation::Result<void>::failure(
        io_error(
            "stale initial checkpoint temp could not be removed",
            checkpoint_temp,
            remove_error.value()));
  }
  if (checkpoint_temp_removed) {
    const auto synced =
        fsync_directory(checkpoint_temp.parent_path());
    if (!synced.has_value()) {
      return synced;
    }
  }
  remove_error.clear();
  const bool manifest_temp_removed =
      std::filesystem::remove(manifest_temp, remove_error);
  if (remove_error) {
    return foundation::Result<void>::failure(
        io_error(
            "stale initial manifest temp could not be removed",
            manifest_temp,
            remove_error.value()));
  }
  if (manifest_temp_removed) {
    const auto synced = fsync_directory(bundle);
    if (!synced.has_value()) {
      return synced;
    }
  }

  const auto checkpoint_bytes =
      foundation::canonical_json(encoded) + "\n";
  if (std::filesystem::exists(checkpoint_final)) {
    auto existing_json = read_json(checkpoint_final);
    auto existing_bytes = read_file_bytes(checkpoint_final);
    if (!existing_json.has_value() || !existing_bytes.has_value()) {
      return foundation::Result<void>::failure(
          invalid_project(
              "existing initial checkpoint could not be validated",
              checkpoint_final));
    }
    auto existing_state =
        parse_project(existing_json.value(), checkpoint_final);
    if (!existing_state.has_value() ||
        existing_state.value() != initial ||
        existing_bytes.value() != checkpoint_bytes) {
      return foundation::Result<void>::failure(
          invalid_project(
              "existing initial checkpoint does not match requested Project",
              checkpoint_final));
    }
  } else {
    auto written =
        write_new_file(checkpoint_temp, checkpoint_bytes);
    if (!written.has_value()) {
      return written;
    }
    auto renamed =
        rename_file(checkpoint_temp, checkpoint_final);
    if (!renamed.has_value()) {
      return renamed;
    }
    const auto synced =
        fsync_directory(checkpoint_final.parent_path());
    if (!synced.has_value()) {
      return synced;
    }
  }

  auto written = write_new_file(
      manifest_temp,
      foundation::canonical_json(manifest_json(0, {})) + "\n");
  if (!written.has_value()) {
    return written;
  }
  auto renamed =
      rename_file(manifest_temp, bundle / "manifest.json");
  if (!renamed.has_value()) {
    return renamed;
  }
  return fsync_directory(bundle);
}

foundation::Result<domain::ProjectState> ProjectStore::load(
    const std::filesystem::path& bundle) const {
  const auto tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<domain::ProjectState>::failure(tree.error());
  }
  auto loaded = load_project(bundle);
  if (!loaded.has_value()) {
    return foundation::Result<domain::ProjectState>::failure(
        loaded.error());
  }
  return foundation::Result<domain::ProjectState>::success(
      std::move(loaded.value().state));
}

foundation::Result<CommandExecution> ProjectStore::execute_with_identity(
    const std::filesystem::path& bundle,
    const domain::Command& command) {
  auto tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<CommandExecution>::failure(tree.error());
  }
  auto lock_result = acquire_lock(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<CommandExecution>::failure(tree.error());
  }
  auto loaded = load_project(bundle);
  if (!loaded.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        recovered.error());
  }
  auto persisted_identity = command;
  auto outcome = commit_loaded(
      bundle,
      std::move(loaded.value()),
      command,
      std::nullopt,
      &persisted_identity);
  if (!outcome.has_value()) {
    return foundation::Result<CommandExecution>::failure(
        outcome.error());
  }
  return foundation::Result<CommandExecution>::success(
      CommandExecution{
          std::move(persisted_identity),
          std::move(outcome.value()),
      });
}

foundation::Result<domain::AppliedCommand> ProjectStore::execute(
    const std::filesystem::path& bundle,
    const domain::Command& command) {
  auto executed = execute_with_identity(bundle, command);
  if (!executed.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        executed.error());
  }
  return foundation::Result<domain::AppliedCommand>::success(
      std::move(executed.value().outcome));
}

foundation::Result<std::optional<RecordTakeReplay>>
ProjectStore::replay_record_take(
    const std::filesystem::path& bundle,
    const RecordTakeReplayIdentity& identity) {
  if (!domain::is_valid_uuid(identity.meta.command_id.value())) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id is not a safe file name",
        });
  }
  auto tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        tree.error());
  }
  auto lock_result = acquire_lock(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        tree.error());
  }
  auto loaded = load_project(bundle);
  if (!loaded.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        recovered.error());
  }
  const auto original =
      loaded.value().commands.find(identity.meta.command_id);
  if (original == loaded.value().commands.end()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::success(
        std::nullopt);
  }
  const auto* record =
      std::get_if<domain::RecordTake>(&original->second);
  if (record == nullptr) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id belongs to a different command type",
        });
  }
  if (record->meta.expected_revision != identity.meta.expected_revision ||
      record->take.id != identity.take_id ||
      record->pattern != identity.pattern) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "take commit replay identity does not match persisted RecordTake",
        });
  }
  const auto receipt =
      loaded.value().receipts.find(identity.meta.command_id);
  if (receipt == loaded.value().receipts.end()) {
    return foundation::Result<std::optional<RecordTakeReplay>>::failure(
        invalid_project(
            "persisted RecordTake receipt is missing",
            bundle / "manifest.json"));
  }
  const auto cleanup =
      loaded.value().cleanup_obligations.find(identity.meta.command_id);
  if (cleanup != loaded.value().cleanup_obligations.end()) {
    const auto completed =
        complete_journal_cleanup(bundle, cleanup->second);
    if (!completed.has_value()) {
      return foundation::Result<std::optional<RecordTakeReplay>>::failure(
          completed.error());
    }
  }
  return foundation::Result<std::optional<RecordTakeReplay>>::success(
      RecordTakeReplay{
          *record,
          domain::AppliedCommand{
              std::move(loaded.value().state),
              receipt->second.event,
              true,
          },
      });
}

foundation::Result<ImportArtifactExecution>
ProjectStore::import_artifact_with_identity(
    const std::filesystem::path& bundle,
    const ImportArtifactRequest& request) {
  if (!domain::is_valid_uuid(request.meta.command_id.value())) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "command id must be a lowercase UUID",
        });
  }
  if (!domain::is_valid_uuid(request.asset_id.value())) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "asset id must be a lowercase UUID",
        });
  }
  if (request.media_type.empty()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact media type must not be empty",
        });
  }
  auto tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        tree.error());
  }
  auto lock_result = acquire_lock(bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;
  tree = validate_managed_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        tree.error());
  }
  auto loaded = load_project(bundle);
  if (!loaded.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        loaded.error());
  }
  const auto recovered = recover_uncommitted(bundle, loaded.value());
  if (!recovered.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        recovered.error());
  }

  const auto original =
      loaded.value().commands.find(request.meta.command_id);
  if (original != loaded.value().commands.end()) {
    const auto* import =
        std::get_if<domain::ImportAsset>(&original->second);
    if (import == nullptr) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "command id belongs to a different command type",
          });
    }
    if (import->meta.expected_revision !=
            request.meta.expected_revision ||
        import->asset.id != request.asset_id ||
        import->asset.artifact.media_type != request.media_type) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset import replay identity does not match persisted ImportAsset",
          });
    }
    const auto described = foundation::describe_artifact(
        request.source, request.media_type);
    if (described.has_value() &&
        described.value() != import->asset.artifact) {
      return foundation::Result<ImportArtifactExecution>::failure(
          Error{
              ErrorCode::invalid_argument,
              "asset import source bytes do not match persisted ImportAsset",
          });
    }
    const auto receipt =
        loaded.value().receipts.find(request.meta.command_id);
    if (receipt == loaded.value().receipts.end()) {
      return foundation::Result<ImportArtifactExecution>::failure(
          invalid_project(
              "persisted ImportAsset receipt is missing",
              bundle / "manifest.json"));
    }
    return foundation::Result<ImportArtifactExecution>::success(
        ImportArtifactExecution{
            *import,
            domain::AppliedCommand{
                std::move(loaded.value().state),
                receipt->second.event,
                true,
            },
        });
  }
  const auto described =
      foundation::describe_artifact(request.source, request.media_type);
  if (!described.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        described.error());
  }
  const domain::Command command = domain::ImportAsset{
      request.meta,
      domain::Asset{request.asset_id, described.value()},
  };
  auto persisted_identity = command;
  auto outcome = commit_loaded(
      bundle,
      std::move(loaded.value()),
      command,
      ArtifactStage{
          request.source,
          described.value(),
          request.meta.command_id,
      },
      &persisted_identity);
  if (!outcome.has_value()) {
    return foundation::Result<ImportArtifactExecution>::failure(
        outcome.error());
  }
  const auto* import =
      std::get_if<domain::ImportAsset>(&persisted_identity);
  if (import == nullptr) {
    return foundation::Result<ImportArtifactExecution>::failure(
        invalid_project(
            "persisted import outcome has the wrong command type",
            bundle / "manifest.json"));
  }
  return foundation::Result<ImportArtifactExecution>::success(
      ImportArtifactExecution{
          *import,
          std::move(outcome.value()),
      });
}

foundation::Result<domain::AppliedCommand> ProjectStore::import_artifact(
    const std::filesystem::path& bundle,
    const ImportArtifactRequest& request) {
  auto imported = import_artifact_with_identity(bundle, request);
  if (!imported.has_value()) {
    return foundation::Result<domain::AppliedCommand>::failure(
        imported.error());
  }
  return foundation::Result<domain::AppliedCommand>::success(
      std::move(imported.value().outcome));
}

foundation::Result<std::vector<std::byte>> ProjectStore::read_artifact(
    const std::filesystem::path& bundle,
    const foundation::ArtifactRef& artifact) const {
  if (!valid_sha256(artifact.sha256) || artifact.media_type.empty()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact reference is invalid",
        });
  }
  if (artifact.byte_length > kMaximumArtifactBytes) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::invalid_argument,
            "artifact exceeds the Project read limit",
            {{"maximum_byte_length", kMaximumArtifactBytes}},
        });
  }

  if (bundle.extension() != ".lmdj") {
    return foundation::Result<std::vector<std::byte>>::failure(
        invalid_project("project bundle extension is invalid", bundle));
  }
  auto bundle_result = open_directory_without_symlinks(bundle);
  if (!bundle_result.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        bundle_result.error());
  }
  auto bundle_descriptor = std::move(bundle_result.value());
  auto lock_result = acquire_lock_at(bundle_descriptor.get(), bundle);
  if (!lock_result.has_value()) {
    return foundation::Result<std::vector<std::byte>>::failure(
        lock_result.error());
  }
  auto lock = std::move(lock_result.value());
  (void)lock;

  const int manifest_value = ::openat(
      bundle_descriptor.get(),
      "manifest.json",
      O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (manifest_value < 0) {
    return foundation::Result<std::vector<std::byte>>::failure(
        invalid_project(
            "project manifest could not be opened through bundle handle",
            bundle / "manifest.json"));
  }
  OwnedDescriptor manifest(manifest_value);
  struct stat manifest_metadata {};
  if (::fstat(manifest.get(), &manifest_metadata) != 0 ||
      !S_ISREG(manifest_metadata.st_mode)) {
    return foundation::Result<std::vector<std::byte>>::failure(
        invalid_project(
            "project manifest is not a regular file",
            bundle / "manifest.json"));
  }

  const int assets_value = ::openat(
      bundle_descriptor.get(),
      "assets",
      O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (assets_value < 0) {
    return foundation::Result<std::vector<std::byte>>::failure(
        invalid_project(
            "project assets directory could not be opened through bundle handle",
            bundle / "assets"));
  }
  OwnedDescriptor assets(assets_value);

  const auto path =
      bundle / "assets" / (artifact.sha256 + ".wav");
  const auto filename = artifact.sha256 + ".wav";
  const int artifact_value = ::openat(
      assets.get(),
      filename.c_str(),
      O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (artifact_value < 0) {
    if (errno == ENOENT) {
      return foundation::Result<std::vector<std::byte>>::failure(
          Error{
              ErrorCode::not_found,
              "project artifact does not exist",
              {{"path", path.generic_string()}},
          });
    }
    if (errno == ELOOP) {
      return foundation::Result<std::vector<std::byte>>::failure(
          invalid_project(
              "project artifact must not be a symbolic link",
              path));
    }
    return foundation::Result<std::vector<std::byte>>::failure(
        io_error("project artifact could not be opened", path));
  }
  OwnedDescriptor descriptor(artifact_value);

  struct stat before {};
  if (::fstat(descriptor.get(), &before) != 0) {
    return foundation::Result<std::vector<std::byte>>::failure(
        io_error("project artifact metadata could not be read", path));
  }
  if (!S_ISREG(before.st_mode) || before.st_size < 0 ||
      static_cast<std::uint64_t>(before.st_size) != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact byte length does not match its reference",
            {{"path", path.generic_string()}},
        });
  }

  std::vector<std::byte> bytes(
      static_cast<std::size_t>(artifact.byte_length));
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto count = ::read(
        descriptor.get(),
        bytes.data() + offset,
        bytes.size() - offset);
    if (count < 0) {
      if (errno == EINTR) {
        continue;
      }
      return foundation::Result<std::vector<std::byte>>::failure(
          io_error(
              "project artifact could not be read completely",
              path));
    }
    if (count == 0) {
      return foundation::Result<std::vector<std::byte>>::failure(
          Error{
              ErrorCode::cook_failed,
              "project artifact ended before its declared byte length",
              {{"path", path.generic_string()}},
          });
    }
    offset += static_cast<std::size_t>(count);
  }

  struct stat after {};
  if (::fstat(descriptor.get(), &after) != 0) {
    return foundation::Result<std::vector<std::byte>>::failure(
        io_error(
            "project artifact metadata could not be verified after reading",
            path));
  }
  if (!S_ISREG(after.st_mode) || after.st_dev != before.st_dev ||
      after.st_ino != before.st_ino || after.st_size != before.st_size ||
      after.st_size < 0 ||
      static_cast<std::uint64_t>(after.st_size) != artifact.byte_length) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact changed while it was being read",
            {{"path", path.generic_string()}},
        });
  }

  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* hash_begin =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(hash_begin, hash_begin + bytes.size());
  }
  hasher.finish();
  if (picosha2::get_hash_hex_string(hasher) != artifact.sha256) {
    return foundation::Result<std::vector<std::byte>>::failure(
        Error{
            ErrorCode::cook_failed,
            "project artifact hash does not match its reference",
            {{"path", path.generic_string()}},
        });
  }
  return foundation::Result<std::vector<std::byte>>::success(
      std::move(bytes));
}

}  // namespace lmdj::project_io
