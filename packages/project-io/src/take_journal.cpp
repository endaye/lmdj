#include <lmdj/project_io/take_journal.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <string_view>
#include <unordered_map>
#include <utility>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/json.hpp>

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

struct JournalDocument {
  domain::RawTake take;
  std::uint64_t expected_revision;
  std::uint64_t valid_prefix_length;
};

foundation::Result<void> validate_journal_bundle_tree(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto no_symlinks = platform.validate_managed_tree(bundle);
  if (!no_symlinks.has_value()) {
    return no_symlinks;
  }
  const auto root_names = platform.list_names(bundle);
  if (!root_names.has_value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "journal bundle root is missing, invalid, or symbolic",
            {
                {"path", bundle.generic_string()},
                {"detail", root_names.error().message},
            },
        });
  }
  const std::array required_directories{
      bundle / "assets",
      bundle / "history",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& directory : required_directories) {
    const auto names = platform.list_names(directory);
    if (!names.has_value()) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_project,
              "journal managed directory is missing, invalid, or symbolic",
              {
                  {"path", directory.generic_string()},
                  {"detail", names.error().message},
              },
          });
    }
  }
  const auto manifest = bundle / "manifest.json";
  const auto manifest_length = platform.byte_length(manifest);
  if (!manifest_length.has_value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "journal project manifest is missing, invalid, or symbolic",
            {
                {"path", manifest.generic_string()},
                {"detail", manifest_length.error().message},
            },
        });
  }
  return foundation::Result<void>::success();
}

std::span<const std::byte> byte_span(std::string_view bytes) {
  return {
      reinterpret_cast<const std::byte*>(bytes.data()),
      bytes.size(),
  };
}

std::string byte_string(std::span<const std::byte> bytes) {
  if (bytes.empty()) {
    return {};
  }
  return {
      reinterpret_cast<const char*>(bytes.data()),
      bytes.size(),
  };
}

std::shared_ptr<std::mutex> journal_append_mutex(
    const std::shared_ptr<ProjectStoragePlatform>& platform) {
  static std::mutex registry_mutex;
  static std::unordered_map<
      const ProjectStoragePlatform*,
      std::weak_ptr<std::mutex>> registry;

  std::lock_guard lock(registry_mutex);
  for (auto entry = registry.begin(); entry != registry.end();) {
    if (entry->second.expired()) {
      entry = registry.erase(entry);
    } else {
      ++entry;
    }
  }
  const auto found = registry.find(platform.get());
  if (found != registry.end()) {
    if (auto existing = found->second.lock()) {
      return existing;
    }
  }
  auto created = std::make_shared<std::mutex>();
  registry[platform.get()] = created;
  return created;
}

std::optional<std::string_view> opaque_temp_destination(
    std::string_view name) {
  constexpr std::string_view marker = ".tmp.";
  const auto marker_position = name.rfind(marker);
  if (marker_position == std::string_view::npos) {
    return std::nullopt;
  }
  const auto token = name.substr(marker_position + marker.size());
  if (token.size() != 32 ||
      !std::all_of(
          token.begin(),
          token.end(),
          [](unsigned char character) {
            return (character >= '0' && character <= '9') ||
                   (character >= 'a' && character <= 'f');
          })) {
    return std::nullopt;
  }
  return name.substr(0, marker_position);
}

bool is_file_reason_character(unsigned char character) {
  return std::isalnum(character) != 0 || character == '-' ||
         character == '_';
}

bool is_generated_sealed_destination(std::string_view destination) {
  constexpr std::size_t uuid_length = 36;
  constexpr std::string_view extension = ".json";
  if (!destination.ends_with(extension)) {
    return false;
  }
  const auto stem = destination.substr(
      0, destination.size() - extension.size());
  if (stem.size() <= uuid_length + 1 || stem.at(uuid_length) != '-' ||
      !domain::is_valid_uuid(stem.substr(0, uuid_length))) {
    return false;
  }
  const auto reason = stem.substr(uuid_length + 1);
  return std::all_of(
      reason.begin(), reason.end(), is_file_reason_character);
}

foundation::Result<void> remove_temporary_destination(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& directory,
    std::string_view destination) {
  auto names = platform.list_names(directory);
  if (!names.has_value()) {
    return foundation::Result<void>::failure(names.error());
  }
  for (const auto& name : names.value()) {
    const auto recovered_destination = opaque_temp_destination(name);
    if (!recovered_destination.has_value() ||
        *recovered_destination != destination) {
      continue;
    }
    const auto removed = platform.remove(directory / name);
    if (!removed.has_value()) {
      return removed;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> remove_sealed_temporary_files(
    ProjectStoragePlatform& platform,
    const std::filesystem::path& directory) {
  auto names = platform.list_names(directory);
  if (!names.has_value()) {
    return foundation::Result<void>::failure(names.error());
  }
  for (const auto& name : names.value()) {
    const auto destination = opaque_temp_destination(name);
    if (!destination.has_value() ||
        !is_generated_sealed_destination(*destination)) {
      continue;
    }
    const auto removed = platform.remove(directory / name);
    if (!removed.has_value()) {
      return removed;
    }
  }
  return foundation::Result<void>::success();
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

nlohmann::json event_json(const domain::RawTakeEvent& event) {
  return {
      {"frame_offset", event.frame_offset},
      {"slot", slot_json(event.slot)},
      {"velocity", event.velocity},
  };
}

nlohmann::json take_json(const domain::RawTake& take) {
  auto events = nlohmann::json::array();
  for (const auto& event : take.events) {
    events.push_back(event_json(event));
  }
  return {
      {"events", std::move(events)},
      {"id", take.id.value()},
      {"sample_rate", take.sample_rate},
  };
}

foundation::Result<domain::RawTakeEvent> parse_event(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    const auto& slot = input.at("slot");
    domain::RawTakeEvent event{
        domain::PadSlotId{
            slot.at("bank").get<std::uint8_t>(),
            slot.at("pad").get<std::uint8_t>(),
        },
        input.at("frame_offset").get<std::uint32_t>(),
        input.at("velocity").get<std::uint8_t>(),
    };
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127) {
      return foundation::Result<domain::RawTakeEvent>::failure(
          Error{
              ErrorCode::invalid_project,
              "journal event is invalid",
              {{"path", path.generic_string()}},
          });
    }
    return foundation::Result<domain::RawTakeEvent>::success(event);
  } catch (const std::exception& exception) {
    return foundation::Result<domain::RawTakeEvent>::failure(
        Error{
            ErrorCode::invalid_project,
            "journal event could not be parsed",
            {
                {"path", path.generic_string()},
                {"parse_error", exception.what()},
            },
        });
  }
}

foundation::Result<domain::RawTake> parse_take(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    domain::RawTake take{
        foundation::TakeId{input.at("id").get<std::string>()},
        input.at("sample_rate").get<std::uint32_t>(),
        {},
    };
    if (take.sample_rate != 48000 ||
        !domain::is_valid_uuid(take.id.value())) {
      return foundation::Result<domain::RawTake>::failure(
          Error{
              ErrorCode::invalid_project,
              "recovery take metadata is invalid",
              {{"path", path.generic_string()}},
          });
    }
    for (const auto& encoded : input.at("events")) {
      auto event = parse_event(encoded, path);
      if (!event.has_value()) {
        return foundation::Result<domain::RawTake>::failure(event.error());
      }
      take.events.push_back(event.value());
    }
    return foundation::Result<domain::RawTake>::success(std::move(take));
  } catch (const std::exception& exception) {
    return foundation::Result<domain::RawTake>::failure(
        Error{
            ErrorCode::invalid_project,
            "recovery take could not be parsed",
            {
                {"path", path.generic_string()},
                {"parse_error", exception.what()},
            },
        });
  }
}

std::filesystem::path active_path(
    const std::filesystem::path& bundle,
    const foundation::TakeId& take_id) {
  return bundle / "recovery/active" / (take_id.value() + ".jsonl");
}

foundation::Result<JournalDocument> read_journal(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    const foundation::TakeId& take_id) {
  if (!domain::is_valid_uuid(take_id.value())) {
    return foundation::Result<JournalDocument>::failure(
        Error{ErrorCode::invalid_argument, "take id is not a safe file name"});
  }
  const auto tree = validate_journal_bundle_tree(platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<JournalDocument>::failure(tree.error());
  }
  const auto path = active_path(bundle, take_id);
  auto existing = platform.exists(path);
  if (!existing.has_value()) {
    return foundation::Result<JournalDocument>::failure(existing.error());
  }
  if (!existing.value()) {
    return foundation::Result<JournalDocument>::failure(
        Error{
            ErrorCode::not_found,
            "active take journal could not be opened",
            {{"path", path.generic_string()}},
        });
  }
  auto read = platform.read_complete(path);
  if (!read.has_value()) {
    return foundation::Result<JournalDocument>::failure(
        read.error());
  }
  const auto bytes = byte_string(read.value());
  const auto header_end = bytes.find('\n');
  if (header_end == std::string::npos) {
    return foundation::Result<JournalDocument>::failure(
        Error{
            ErrorCode::invalid_project,
            "active take journal has no durable metadata line",
            {{"path", path.generic_string()}},
        });
  }

  try {
    const auto line = bytes.substr(0, header_end);
    const auto header = nlohmann::json::parse(line);
    if (header.at("contract") != "lmdj.take.journal.v1" ||
        header.at("take_id").get<std::string>() != take_id.value()) {
      return foundation::Result<JournalDocument>::failure(
          Error{
              ErrorCode::invalid_project,
              "active take journal metadata is invalid",
              {{"path", path.generic_string()}},
          });
    }
    JournalDocument document{
        domain::RawTake{
            take_id,
            header.at("sample_rate").get<std::uint32_t>(),
            {},
        },
        header.at("expected_revision").get<std::uint64_t>(),
        static_cast<std::uint64_t>(header_end + 1),
    };
    if (document.take.sample_rate != 48000) {
      return foundation::Result<JournalDocument>::failure(
          Error{
              ErrorCode::invalid_project,
              "active take journal sample rate is invalid",
              {{"path", path.generic_string()}},
          });
    }
    std::size_t cursor = header_end + 1;
    while (cursor < bytes.size()) {
      const auto line_end = bytes.find('\n', cursor);
      if (line_end == std::string::npos) {
        break;
      }
      const auto event_line = bytes.substr(cursor, line_end - cursor);
      cursor = line_end + 1;
      document.valid_prefix_length =
          static_cast<std::uint64_t>(cursor);
      if (event_line.empty()) {
        continue;
      }
      auto parsed =
          parse_event(nlohmann::json::parse(event_line), path);
      if (!parsed.has_value()) {
        return foundation::Result<JournalDocument>::failure(parsed.error());
      }
      document.take.events.push_back(parsed.value());
    }
    return foundation::Result<JournalDocument>::success(std::move(document));
  } catch (const std::exception& exception) {
    return foundation::Result<JournalDocument>::failure(
        Error{
            ErrorCode::invalid_project,
            "active take journal could not be parsed",
            {
                {"path", path.generic_string()},
                {"parse_error", exception.what()},
            },
        });
  }
}

std::string file_reason(std::string_view reason) {
  std::string result;
  result.reserve(reason.size());
  for (const unsigned char character : reason) {
    result.push_back(
        is_file_reason_character(character)
            ? static_cast<char>(character)
            : '_');
  }
  return result.empty() ? "recovery" : result;
}

}  // namespace

TakeJournal::TakeJournal()
    : TakeJournal(make_default_project_storage_platform()) {}

TakeJournal::TakeJournal(std::shared_ptr<ProjectStoragePlatform> platform)
    : platform_(platform != nullptr
                    ? std::move(platform)
                    : make_default_project_storage_platform()) {}

foundation::Result<void> TakeJournal::begin(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    std::uint64_t expected_revision,
    std::uint32_t sample_rate) {
  if (!domain::is_valid_uuid(take_id.value()) ||
      sample_rate != 48000) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "take journal metadata is invalid",
        });
  }
  auto tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  const auto directory = bundle / "recovery/active";
  const auto ensured = platform_->ensure_directory(directory);
  if (!ensured.has_value()) {
    return ensured;
  }
  const auto path = active_path(bundle, take_id);
  const auto recovered_temporary = remove_temporary_destination(
      *platform_,
      directory,
      path.filename().string());
  if (!recovered_temporary.has_value()) {
    return recovered_temporary;
  }
  auto existing = platform_->exists(path);
  if (!existing.has_value()) {
    return foundation::Result<void>::failure(existing.error());
  }
  if (existing.value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::duplicate_id,
            "active take journal already exists",
            {{"path", path.generic_string()}},
        });
  }
  const nlohmann::json header = {
      {"contract", "lmdj.take.journal.v1"},
      {"expected_revision", expected_revision},
      {"sample_rate", sample_rate},
      {"take_id", take_id.value()},
  };
  const auto header_bytes = foundation::canonical_json(header) + "\n";
  const auto created =
      platform_->create_immutable(path, byte_span(header_bytes));
  if (!created.has_value()) {
    const auto condition = created.error().details.find("storage_condition");
    if (condition != created.error().details.end() &&
        condition->is_string() &&
        condition->get<std::string>() ==
            std::string{kStorageConditionAlreadyExists}) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::duplicate_id,
              "active take journal already exists",
              {{"path", path.generic_string()}},
          });
    }
    return created;
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> TakeJournal::append(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    const domain::RawTakeEvent& event) {
  return append_batch(
      bundle,
      std::move(take_id),
      std::span<const domain::RawTakeEvent>{&event, 1});
}

foundation::Result<void> TakeJournal::append_batch(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events) {
  if (!domain::is_valid_uuid(take_id.value()) || events.empty()) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "take journal batch is invalid"});
  }
  std::uint32_t previous_frame = 0;
  bool has_previous_frame = false;
  for (const auto& event : events) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 ||
        (has_previous_frame && event.frame_offset < previous_frame)) {
      return foundation::Result<void>::failure(
          Error{ErrorCode::invalid_argument, "take journal batch is invalid"});
    }
    previous_frame = event.frame_offset;
    has_previous_frame = true;
  }
  std::string payload;
  for (const auto& event : events) {
    payload += foundation::canonical_json(event_json(event));
    payload.push_back('\n');
  }
  auto append_mutex = journal_append_mutex(platform_);
  std::lock_guard append_operation(*append_mutex);
  auto tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  const auto path = active_path(bundle, take_id);
  auto existing = platform_->exists(path);
  if (!existing.has_value()) {
    return foundation::Result<void>::failure(existing.error());
  }
  if (!existing.value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::not_found,
            "active take journal could not be opened for append",
            {{"path", path.generic_string()}},
        });
  }
  auto journal = read_journal(*platform_, bundle, take_id);
  if (!journal.has_value()) {
    return foundation::Result<void>::failure(journal.error());
  }
  const auto appended = platform_->append_durable(
      path,
      journal.value().valid_prefix_length,
      byte_span(payload));
  if (!appended.has_value()) {
    return appended;
  }
  return foundation::Result<void>::success();
}

foundation::Result<domain::RawTake> TakeJournal::read_active(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id) const {
  auto active = read_active_journal(bundle, take_id);
  if (!active.has_value()) {
    return foundation::Result<domain::RawTake>::failure(active.error());
  }
  return foundation::Result<domain::RawTake>::success(
      std::move(active.value().take));
}

foundation::Result<ActiveTakeJournal> TakeJournal::read_active_journal(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id) const {
  auto document = read_journal(*platform_, bundle, take_id);
  if (!document.has_value()) {
    return foundation::Result<ActiveTakeJournal>::failure(document.error());
  }
  return foundation::Result<ActiveTakeJournal>::success(
      ActiveTakeJournal{
          std::move(document.value().take),
          document.value().expected_revision,
      });
}

foundation::Result<std::filesystem::path> TakeJournal::seal(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    std::string reason) {
  auto tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(tree.error());
  }
  auto journal = read_journal(*platform_, bundle, take_id);
  if (!journal.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        journal.error());
  }
  if (reason.empty()) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{ErrorCode::invalid_argument, "recovery reason is empty"});
  }

  const auto sealed_directory = bundle / "recovery/sealed";
  const auto ensured = platform_->ensure_directory(sealed_directory);
  if (!ensured.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        ensured.error());
  }

  const auto base_name =
      take_id.value() + "-" + file_reason(reason);
  auto final_path = sealed_directory / (base_name + ".json");
  std::uint64_t suffix = 1;
  auto candidate_exists = platform_->exists(final_path);
  if (!candidate_exists.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        candidate_exists.error());
  }
  while (candidate_exists.value()) {
    final_path =
        sealed_directory /
        (base_name + "-" + std::to_string(suffix++) + ".json");
    candidate_exists = platform_->exists(final_path);
    if (!candidate_exists.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          candidate_exists.error());
    }
  }
  const nlohmann::json candidate = {
      {"contract", "lmdj.take.recovery.v1"},
      {"expected_revision", journal.value().expected_revision},
      {"reason", reason},
      {"take", take_json(journal.value().take)},
  };
  const auto candidate_bytes = foundation::canonical_json(candidate) + "\n";
  const auto written = platform_->create_immutable(
      final_path, byte_span(candidate_bytes));
  if (!written.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        written.error());
  }
  const auto active = active_path(bundle, take_id);
  auto active_exists = platform_->exists(active);
  if (!active_exists.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        active_exists.error());
  }
  if (!active_exists.value()) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{
            ErrorCode::io_error,
            "active journal could not be removed after sealing",
            {{"path", active.generic_string()}},
        });
  }
  const auto removed = platform_->remove(active);
  if (!removed.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        removed.error());
  }
  return foundation::Result<std::filesystem::path>::success(
      std::move(final_path));
}

foundation::Result<std::vector<RecoveryCandidate>>
TakeJournal::list_recoverable(
    const std::filesystem::path& bundle) const {
  auto tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        tree.error());
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  tree = validate_journal_bundle_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        tree.error());
  }
  const auto directory = bundle / "recovery/sealed";
  const auto recovered = remove_sealed_temporary_files(*platform_, directory);
  if (!recovered.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        recovered.error());
  }
  auto names = platform_->list_names(directory);
  if (!names.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        names.error());
  }

  std::vector<std::filesystem::path> paths;
  for (const auto& name : names.value()) {
    const auto path = directory / name;
    if (path.extension() == ".json") {
      paths.push_back(path);
    }
  }

  std::vector<RecoveryCandidate> candidates;
  for (const auto& path : paths) {
    auto bytes = platform_->read_complete(path);
    if (!bytes.has_value()) {
      return foundation::Result<std::vector<RecoveryCandidate>>::failure(
          bytes.error());
    }
    try {
      const auto encoded = nlohmann::json::parse(byte_string(bytes.value()));
      if (encoded.at("contract") != "lmdj.take.recovery.v1") {
        return foundation::Result<std::vector<RecoveryCandidate>>::failure(
            Error{
                ErrorCode::invalid_project,
                "sealed recovery contract is invalid",
                {{"path", path.generic_string()}},
            });
      }
      auto take = parse_take(encoded.at("take"), path);
      if (!take.has_value()) {
        return foundation::Result<std::vector<RecoveryCandidate>>::failure(
            take.error());
      }
      candidates.push_back(
          RecoveryCandidate{
              std::move(take.value()),
              encoded.at("expected_revision").get<std::uint64_t>(),
              encoded.at("reason").get<std::string>(),
              path,
          });
    } catch (const std::exception& exception) {
      return foundation::Result<std::vector<RecoveryCandidate>>::failure(
          Error{
              ErrorCode::invalid_project,
              "sealed recovery file could not be parsed",
              {
                  {"path", path.generic_string()},
                  {"parse_error", exception.what()},
              },
          });
    }
  }
  return foundation::Result<std::vector<RecoveryCandidate>>::success(
      std::move(candidates));
}

}  // namespace lmdj::project_io
