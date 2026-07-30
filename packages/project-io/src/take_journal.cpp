#include <lmdj/project_io/take_journal.hpp>

#include <algorithm>
#include <array>
#include <cerrno>
#include <cctype>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string_view>
#include <system_error>
#include <utility>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <nlohmann/json.hpp>

#include <lmdj/foundation/json.hpp>

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

struct JournalDocument {
  domain::RawTake take;
  std::uint64_t expected_revision;
};

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

foundation::Result<void> validate_journal_bundle_tree(
    const std::filesystem::path& bundle) {
  std::error_code status_error;
  const auto bundle_status =
      std::filesystem::symlink_status(bundle, status_error);
  if (status_error || std::filesystem::is_symlink(bundle_status) ||
      !std::filesystem::is_directory(bundle_status)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "journal bundle root is missing, invalid, or symbolic",
            {
                {"path", bundle.generic_string()},
                {"system_error", status_error.message()},
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
    const auto status =
        std::filesystem::symlink_status(directory, status_error);
    if (status_error || std::filesystem::is_symlink(status) ||
        !std::filesystem::is_directory(status)) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_project,
              "journal managed directory is missing, invalid, or symbolic",
              {
                  {"path", directory.generic_string()},
                  {"system_error", status_error.message()},
              },
          });
    }
  }
  const auto manifest = bundle / "manifest.json";
  const auto manifest_status =
      std::filesystem::symlink_status(manifest, status_error);
  if (status_error || std::filesystem::is_symlink(manifest_status) ||
      !std::filesystem::is_regular_file(manifest_status)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "journal project manifest is missing, invalid, or symbolic",
            {
                {"path", manifest.generic_string()},
                {"system_error", status_error.message()},
            },
        });
  }

  std::error_code iterator_error;
  std::filesystem::recursive_directory_iterator iterator(
      bundle, std::filesystem::directory_options::none, iterator_error);
  const std::filesystem::recursive_directory_iterator end;
  while (iterator != end) {
    if (iterator_error) {
      return foundation::Result<void>::failure(
          io_error(
              "journal bundle tree could not be inspected",
              bundle,
              iterator_error.value()));
    }
    const auto entry_status =
        std::filesystem::symlink_status(iterator->path(), status_error);
    if (status_error) {
      return foundation::Result<void>::failure(
          io_error(
              "journal bundle entry could not be inspected",
              iterator->path(),
              status_error.value()));
    }
    if (std::filesystem::is_symlink(entry_status)) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_project,
              "journal bundle contains a symbolic link",
              {{"path", iterator->path().generic_string()}},
          });
    }
    iterator.increment(iterator_error);
  }
  if (iterator_error) {
    return foundation::Result<void>::failure(
        io_error(
            "journal bundle tree could not be inspected",
            bundle,
            iterator_error.value()));
  }
  return foundation::Result<void>::success();
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
          io_error("journal bytes could not be written", path));
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
        io_error("journal bytes could not be flushed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> fsync_directory(
    const std::filesystem::path& directory) {
  const int descriptor =
      ::open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (descriptor < 0) {
    return foundation::Result<void>::failure(
        io_error("journal directory could not be opened for flush", directory));
  }
  int sync_error = 0;
  while (::fsync(descriptor) != 0) {
    if (errno == EINTR) {
      continue;
    }
    sync_error = errno;
    break;
  }
  const int close_result = ::close(descriptor);
  const int close_error = close_result == 0 ? 0 : errno;
  const bool sync_unsupported =
      sync_error == EINVAL || sync_error == ENOTSUP ||
      sync_error == EOPNOTSUPP;
  if (sync_error != 0 && !sync_unsupported) {
    return foundation::Result<void>::failure(
        io_error(
            "journal directory could not be flushed",
            directory,
            sync_error));
  }
  if (close_error != 0) {
    return foundation::Result<void>::failure(
        io_error(
            "journal directory could not be closed",
            directory,
            close_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> truncate_unterminated_tail(
    int descriptor,
    const std::filesystem::path& path) {
  struct stat status {};
  if (::fstat(descriptor, &status) != 0) {
    return foundation::Result<void>::failure(
        io_error("active journal size could not be inspected", path));
  }
  if (status.st_size <= 0) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "active journal has no durable metadata record",
            {{"path", path.generic_string()}},
        });
  }
  std::string bytes(static_cast<std::size_t>(status.st_size), '\0');
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const auto read_count = ::pread(
        descriptor,
        bytes.data() + offset,
        bytes.size() - offset,
        static_cast<off_t>(offset));
    if (read_count < 0) {
      if (errno == EINTR) {
        continue;
      }
      return foundation::Result<void>::failure(
          io_error("active journal tail could not be inspected", path));
    }
    if (read_count == 0) {
      return foundation::Result<void>::failure(
          io_error("active journal changed while inspecting its tail", path));
    }
    offset += static_cast<std::size_t>(read_count);
  }
  if (bytes.back() == '\n') {
    return foundation::Result<void>::success();
  }
  const auto last_newline = bytes.find_last_of('\n');
  if (last_newline == std::string::npos) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "active journal metadata record is unterminated",
            {{"path", path.generic_string()}},
        });
  }
  if (::ftruncate(
          descriptor, static_cast<off_t>(last_newline + 1)) != 0) {
    return foundation::Result<void>::failure(
        io_error("torn active journal tail could not be truncated", path));
  }
  return fsync_descriptor(descriptor, path);
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
    const std::filesystem::path& bundle,
    const foundation::TakeId& take_id) {
  if (!domain::is_valid_uuid(take_id.value())) {
    return foundation::Result<JournalDocument>::failure(
        Error{ErrorCode::invalid_argument, "take id is not a safe file name"});
  }
  const auto tree = validate_journal_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<JournalDocument>::failure(tree.error());
  }
  const auto path = active_path(bundle, take_id);
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    const auto code = std::filesystem::exists(path)
                          ? ErrorCode::io_error
                          : ErrorCode::not_found;
    return foundation::Result<JournalDocument>::failure(
        Error{
            code,
            "active take journal could not be opened",
            {{"path", path.generic_string()}},
        });
  }

  const std::string bytes{
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
  if (stream.bad()) {
    return foundation::Result<JournalDocument>::failure(
        io_error("active take journal could not be read completely", path));
  }
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

foundation::Result<void> write_new_file(
    const std::filesystem::path& path,
    std::string_view bytes) {
  const int descriptor =
      ::open(
          path.c_str(),
          O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
          0644);
  if (descriptor < 0) {
    return foundation::Result<void>::failure(
        io_error("journal file could not be created", path));
  }
  const auto written = write_all(descriptor, bytes, path);
  const auto synced = written.has_value()
                          ? fsync_descriptor(descriptor, path)
                          : foundation::Result<void>::success();
  const int close_result = ::close(descriptor);
  if (!written.has_value()) {
    return written;
  }
  if (!synced.has_value()) {
    return synced;
  }
  if (close_result != 0) {
    return foundation::Result<void>::failure(
        io_error("journal file could not be closed", path));
  }
  return foundation::Result<void>::success();
}

std::string file_reason(std::string_view reason) {
  std::string result;
  result.reserve(reason.size());
  for (const unsigned char character : reason) {
    result.push_back(
        std::isalnum(character) != 0 || character == '-' ||
                character == '_'
            ? static_cast<char>(character)
            : '_');
  }
  return result.empty() ? "recovery" : result;
}

}  // namespace

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
  const auto tree = validate_journal_bundle_tree(bundle);
  if (!tree.has_value()) {
    return tree;
  }
  if (!std::filesystem::is_regular_file(bundle / "manifest.json")) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::not_found,
            "project bundle does not have a manifest",
            {{"path", bundle.generic_string()}},
        });
  }
  const auto directory = bundle / "recovery/active";
  std::error_code directory_error;
  std::filesystem::create_directories(directory, directory_error);
  if (directory_error) {
    return foundation::Result<void>::failure(
        io_error(
            "active journal directory could not be created",
            directory,
            directory_error.value()));
  }
  const auto path = active_path(bundle, take_id);
  const nlohmann::json header = {
      {"contract", "lmdj.take.journal.v1"},
      {"expected_revision", expected_revision},
      {"sample_rate", sample_rate},
      {"take_id", take_id.value()},
  };
  const auto created =
      write_new_file(path, foundation::canonical_json(header) + "\n");
  if (!created.has_value()) {
    if (std::filesystem::exists(path)) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::duplicate_id,
              "active take journal already exists",
              {{"path", path.generic_string()}},
          });
    }
    return created;
  }
  return fsync_directory(directory);
}

foundation::Result<void> TakeJournal::append(
    const std::filesystem::path& bundle,
    foundation::TakeId take_id,
    const domain::RawTakeEvent& event) {
  if (!domain::is_valid_uuid(take_id.value()) ||
      !domain::is_valid_slot(event.slot) || event.velocity < 1 ||
      event.velocity > 127) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "take journal event is invalid"});
  }
  const auto tree = validate_journal_bundle_tree(bundle);
  if (!tree.has_value()) {
    return tree;
  }
  const auto path = active_path(bundle, take_id);
  const int descriptor =
      ::open(path.c_str(), O_RDWR | O_APPEND | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) {
    const auto code = errno == ENOENT ? ErrorCode::not_found
                                     : ErrorCode::io_error;
    return foundation::Result<void>::failure(
        Error{
            code,
            "active take journal could not be opened for append",
            {
                {"path", path.generic_string()},
                {"system_error", std::strerror(errno)},
            },
        });
  }
  const auto repaired = truncate_unterminated_tail(descriptor, path);
  if (!repaired.has_value()) {
    ::close(descriptor);
    return repaired;
  }
  const auto line = foundation::canonical_json(event_json(event)) + "\n";
  const auto written = write_all(descriptor, line, path);
  const auto synced = written.has_value()
                          ? fsync_descriptor(descriptor, path)
                          : foundation::Result<void>::success();
  const int close_result = ::close(descriptor);
  if (!written.has_value()) {
    return written;
  }
  if (!synced.has_value()) {
    return synced;
  }
  if (close_result != 0) {
    return foundation::Result<void>::failure(
        io_error("active take journal could not be closed", path));
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
  auto document = read_journal(bundle, take_id);
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
  auto journal = read_journal(bundle, take_id);
  if (!journal.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        journal.error());
  }
  if (reason.empty()) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{ErrorCode::invalid_argument, "recovery reason is empty"});
  }

  const auto sealed_directory = bundle / "recovery/sealed";
  std::error_code directory_error;
  std::filesystem::create_directories(sealed_directory, directory_error);
  if (directory_error) {
    return foundation::Result<std::filesystem::path>::failure(
        io_error(
            "sealed recovery directory could not be created",
            sealed_directory,
            directory_error.value()));
  }

  const auto base_name =
      take_id.value() + "-" + file_reason(reason);
  auto final_path = sealed_directory / (base_name + ".json");
  std::uint64_t suffix = 1;
  while (std::filesystem::exists(final_path)) {
    final_path =
        sealed_directory /
        (base_name + "-" + std::to_string(suffix++) + ".json");
  }
  const auto temp_path = final_path.string() + ".tmp";
  const nlohmann::json candidate = {
      {"contract", "lmdj.take.recovery.v1"},
      {"expected_revision", journal.value().expected_revision},
      {"reason", reason},
      {"take", take_json(journal.value().take)},
  };
  const auto written = write_new_file(
      temp_path, foundation::canonical_json(candidate) + "\n");
  if (!written.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        written.error());
  }
  std::error_code rename_error;
  std::filesystem::rename(temp_path, final_path, rename_error);
  if (rename_error) {
    std::filesystem::remove(temp_path);
    return foundation::Result<std::filesystem::path>::failure(
        io_error(
            "sealed recovery file could not be published",
            final_path,
            rename_error.value()));
  }
  const auto sealed_sync = fsync_directory(sealed_directory);
  if (!sealed_sync.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        sealed_sync.error());
  }

  const auto active = active_path(bundle, take_id);
  std::error_code remove_error;
  const bool removed = std::filesystem::remove(active, remove_error);
  if (remove_error || !removed) {
    return foundation::Result<std::filesystem::path>::failure(
        io_error(
            "active journal could not be removed after sealing",
            active,
            remove_error ? remove_error.value() : ENOENT));
  }
  const auto active_sync = fsync_directory(active.parent_path());
  if (!active_sync.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        active_sync.error());
  }
  return foundation::Result<std::filesystem::path>::success(
      std::move(final_path));
}

foundation::Result<std::vector<RecoveryCandidate>>
TakeJournal::list_recoverable(
    const std::filesystem::path& bundle) const {
  const auto tree = validate_journal_bundle_tree(bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        tree.error());
  }
  const auto directory = bundle / "recovery/sealed";
  std::error_code status_error;
  if (!std::filesystem::is_directory(directory, status_error)) {
    if (!status_error) {
      return foundation::Result<std::vector<RecoveryCandidate>>::success({});
    }
    return foundation::Result<std::vector<RecoveryCandidate>>::failure(
        io_error(
            "sealed recovery directory could not be inspected",
            directory,
            status_error.value()));
  }

  std::vector<std::filesystem::path> paths;
  for (const auto& entry : std::filesystem::directory_iterator(directory)) {
    if (entry.is_regular_file() && entry.path().extension() == ".json") {
      paths.push_back(entry.path());
    }
  }
  std::sort(paths.begin(), paths.end());

  std::vector<RecoveryCandidate> candidates;
  for (const auto& path : paths) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
      return foundation::Result<std::vector<RecoveryCandidate>>::failure(
          io_error("sealed recovery file could not be opened", path));
    }
    try {
      const auto encoded = nlohmann::json::parse(stream);
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
