#include <lmdj/project_io/project_bundle_transfer.hpp>

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::uint64_t kMaximumIndexBytes = 4U * 1024U * 1024U;
constexpr std::uint32_t kMaximumEntries = 4096U;
constexpr std::uint64_t kMaximumEntryBytes = 64U * 1024U * 1024U;
constexpr std::uint64_t kMaximumPayloadBytes = 512U * 1024U * 1024U;
constexpr std::size_t kMaximumChunkBytes = 1024U * 1024U;
constexpr std::size_t kMaximumPathBytes = 255U;

Error invalid_argument(std::string message) {
  return Error{ErrorCode::invalid_argument, std::move(message)};
}

Error invalid_bundle(std::string message) {
  return Error{ErrorCode::invalid_project, std::move(message)};
}

Error resource_limit(std::string message) {
  return Error{
      ErrorCode::invalid_project,
      std::move(message),
      {{"transfer_condition",
        std::string{kProjectBundleConditionResourceLimit}}},
  };
}

Error session_not_found() {
  return Error{ErrorCode::not_found, "Project Bundle import session was not found"};
}

Error sanitized_storage_error(const Error& source, std::string message) {
  auto details = nlohmann::json::object();
  if (source.details.is_object() &&
      source.details.contains("storage_condition")) {
    details["storage_condition"] = source.details.at("storage_condition");
  }
  return Error{source.code, std::move(message), std::move(details)};
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64U &&
         std::all_of(
             value.begin(),
             value.end(),
             [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

std::string sha256(std::span<const std::byte> bytes) {
  picosha2::hash256_one_by_one hasher;
  if (!bytes.empty()) {
    const auto* begin =
        reinterpret_cast<const unsigned char*>(bytes.data());
    hasher.process(begin, begin + bytes.size());
  }
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

std::string sha256(std::string_view bytes) {
  return sha256({
      reinterpret_cast<const std::byte*>(bytes.data()),
      bytes.size(),
  });
}

std::string byte_string(std::span<const std::byte> bytes) {
  return {
      reinterpret_cast<const char*>(bytes.data()),
      bytes.size(),
  };
}

bool exact_keys(
    const nlohmann::json& value,
    std::initializer_list<std::string_view> keys) {
  if (!value.is_object() || value.size() != keys.size()) {
    return false;
  }
  return std::all_of(
      keys.begin(),
      keys.end(),
      [&value](std::string_view key) {
        return value.contains(std::string{key});
      });
}

std::optional<std::uint64_t> unsigned_value(const nlohmann::json& value) {
  if (value.is_number_unsigned()) {
    return value.get<std::uint64_t>();
  }
  if (!value.is_number_integer()) {
    return std::nullopt;
  }
  const auto signed_value = value.get<std::int64_t>();
  return signed_value < 0
             ? std::nullopt
             : std::optional<std::uint64_t>{
                   static_cast<std::uint64_t>(signed_value)};
}

bool portable_path(std::string_view path) {
  if (path.empty() || path.size() > kMaximumPathBytes ||
      path.front() == '/' || path.back() == '/') {
    return false;
  }
  std::size_t segment_begin = 0;
  for (std::size_t index = 0; index <= path.size(); ++index) {
    if (index != path.size() && path[index] != '/') {
      const auto byte = static_cast<unsigned char>(path[index]);
      const bool allowed =
          (byte >= 'A' && byte <= 'Z') ||
          (byte >= 'a' && byte <= 'z') ||
          (byte >= '0' && byte <= '9') || byte == '.' || byte == '_' ||
          byte == '-';
      if (!allowed) {
        return false;
      }
      continue;
    }
    const auto segment = path.substr(segment_begin, index - segment_begin);
    if (segment.empty() || segment == "." || segment == "..") {
      return false;
    }
    segment_begin = index + 1;
  }
  return true;
}

std::string ascii_fold(std::string_view value) {
  std::string result{value};
  std::transform(
      result.begin(),
      result.end(),
      result.begin(),
      [](unsigned char byte) {
        return static_cast<char>(
            byte >= 'A' && byte <= 'Z' ? byte + ('a' - 'A') : byte);
      });
  return result;
}

bool unsigned_byte_less(std::string_view left, std::string_view right) {
  return std::lexicographical_compare(
      left.begin(),
      left.end(),
      right.begin(),
      right.end(),
      [](char left_byte, char right_byte) {
        return static_cast<unsigned char>(left_byte) <
               static_cast<unsigned char>(right_byte);
      });
}

struct BundleEntry {
  std::string path;
  std::uint64_t bytes;
  std::uint64_t offset;
  std::string sha256;
};

struct ParsedIndex {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::vector<BundleEntry> entries;
};

foundation::Result<ParsedIndex> parse_index(std::string_view encoded) {
  auto parsed = foundation::parse_bounded_json(encoded);
  if (!parsed.has_value()) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle index is not valid bounded JSON"));
  }
  auto& index = parsed.value();
  if (foundation::canonical_json(index) != encoded ||
      !exact_keys(
          index,
          {"bundle_digest",
           "compression",
           "contract",
           "contract_version",
           "entries",
           "project_contract",
           "project_id",
           "uncompressed_bytes"}) ||
      index.at("contract") != "lmdj.project-bundle.v1" ||
      index.at("contract_version") != "1.0.0" ||
      index.at("compression") != "none" ||
      index.at("project_contract") != "lmdj.project.v1" ||
      !index.at("project_id").is_string() ||
      !index.at("bundle_digest").is_string() ||
      !index.at("entries").is_array()) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle index shape is invalid"));
  }
  const auto project_id = index.at("project_id").get<std::string>();
  const auto declared_digest = index.at("bundle_digest").get<std::string>();
  if (!domain::is_valid_uuid(project_id) ||
      !lowercase_sha256(declared_digest)) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle identity is invalid"));
  }
  const auto& encoded_entries = index.at("entries");
  if (encoded_entries.empty()) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle entries are empty"));
  }
  if (encoded_entries.size() > kMaximumEntries) {
    return foundation::Result<ParsedIndex>::failure(
        resource_limit("Project Bundle entry count exceeds 4096"));
  }

  std::vector<BundleEntry> entries;
  entries.reserve(encoded_entries.size());
  std::set<std::string> exact_paths;
  std::set<std::string> folded_paths;
  std::uint64_t expected_offset = 0;
  std::string previous_path;
  for (const auto& encoded_entry : encoded_entries) {
    if (!exact_keys(
            encoded_entry, {"bytes", "offset", "path", "sha256"}) ||
        !encoded_entry.at("path").is_string() ||
        !encoded_entry.at("sha256").is_string()) {
      return foundation::Result<ParsedIndex>::failure(
          invalid_bundle("Project Bundle entry shape is invalid"));
    }
    const auto path = encoded_entry.at("path").get<std::string>();
    const auto digest = encoded_entry.at("sha256").get<std::string>();
    const auto byte_length = unsigned_value(encoded_entry.at("bytes"));
    const auto offset = unsigned_value(encoded_entry.at("offset"));
    if (!portable_path(path) || !lowercase_sha256(digest) ||
        !byte_length.has_value() || !offset.has_value()) {
      return foundation::Result<ParsedIndex>::failure(
          invalid_bundle("Project Bundle entry value is invalid"));
    }
    if (*byte_length > kMaximumEntryBytes) {
      return foundation::Result<ParsedIndex>::failure(
          resource_limit("Project Bundle entry exceeds 64 MiB"));
    }
    if (*offset != expected_offset) {
      return foundation::Result<ParsedIndex>::failure(
          invalid_bundle("Project Bundle offsets are not contiguous"));
    }
    if (!previous_path.empty() &&
        !unsigned_byte_less(previous_path, path)) {
      return foundation::Result<ParsedIndex>::failure(
          invalid_bundle("Project Bundle paths are not canonically sorted"));
    }
    if (!exact_paths.insert(path).second ||
        !folded_paths.insert(ascii_fold(path)).second) {
      return foundation::Result<ParsedIndex>::failure(
          invalid_bundle("Project Bundle paths collide"));
    }
    expected_offset += *byte_length;
    if (expected_offset > kMaximumPayloadBytes) {
      return foundation::Result<ParsedIndex>::failure(
          resource_limit("Project Bundle payload exceeds 512 MiB"));
    }
    entries.push_back(BundleEntry{path, *byte_length, *offset, digest});
    previous_path = path;
  }
  const auto declared_total = unsigned_value(index.at("uncompressed_bytes"));
  if (!declared_total.has_value() || *declared_total != expected_offset) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle payload total is invalid"));
  }
  auto digest_source = index;
  digest_source.erase("bundle_digest");
  if (sha256(foundation::canonical_json(digest_source)) != declared_digest) {
    return foundation::Result<ParsedIndex>::failure(
        invalid_bundle("Project Bundle digest does not match its index"));
  }
  return foundation::Result<ParsedIndex>::success(
      ParsedIndex{
          foundation::ProjectId{project_id},
          declared_digest,
          std::move(entries),
      });
}

struct InventoryEntry {
  std::string path;
  std::uint64_t bytes;
  std::string digest;
};

foundation::Result<void> collect_inventory(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& root,
    const std::filesystem::path& relative,
    std::vector<InventoryEntry>& entries,
    std::uint64_t& total) {
  const auto directory = relative.empty() ? root : root / relative;
  const auto names = platform.list_names(directory);
  if (!names.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            names.error(), "Project inventory could not list files"));
  }
  for (const auto& name : names.value()) {
    const auto child_relative = relative / name;
    const auto portable = child_relative.generic_string();
    if (!portable_path(portable)) {
      return foundation::Result<void>::failure(
          invalid_bundle("Project inventory contains an invalid path"));
    }
    const auto content = platform.read_complete(root / child_relative);
    if (!content.has_value()) {
      return foundation::Result<void>::failure(
          sanitized_storage_error(
              content.error(), "Project inventory file could not be read"));
    }
    if (content.value().size() > kMaximumEntryBytes) {
      return foundation::Result<void>::failure(
          resource_limit("Project inventory entry exceeds 64 MiB"));
    }
    total += content.value().size();
    if (total > kMaximumPayloadBytes) {
      return foundation::Result<void>::failure(
          resource_limit("Project inventory exceeds 512 MiB"));
    }
    entries.push_back(
        InventoryEntry{
            portable,
            content.value().size(),
            sha256(content.value()),
        });
    if (entries.size() > kMaximumEntries) {
      return foundation::Result<void>::failure(
          resource_limit("Project inventory entry count exceeds 4096"));
    }
  }
  const auto directories = platform.list_directories(directory);
  if (!directories.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            directories.error(), "Project inventory could not list directories"));
  }
  for (const auto& name : directories.value()) {
    const auto child_relative = relative / name;
    const auto collected = collect_inventory(
        platform, root, child_relative, entries, total);
    if (!collected.has_value()) {
      return collected;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<std::string> project_digest(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& path,
    const foundation::ProjectId& project_id) {
  const auto tree = platform.validate_managed_tree(path);
  if (!tree.has_value()) {
    return foundation::Result<std::string>::failure(
        sanitized_storage_error(
            tree.error(), "Project inventory tree is invalid"));
  }
  std::vector<InventoryEntry> entries;
  std::uint64_t total = 0;
  const auto collected = collect_inventory(
      platform, path, {}, entries, total);
  if (!collected.has_value()) {
    return foundation::Result<std::string>::failure(collected.error());
  }
  std::sort(
      entries.begin(),
      entries.end(),
      [](const auto& left, const auto& right) {
        return unsigned_byte_less(left.path, right.path);
      });
  auto encoded_entries = nlohmann::json::array();
  std::uint64_t offset = 0;
  for (const auto& entry : entries) {
    encoded_entries.push_back(
        {
            {"bytes", entry.bytes},
            {"offset", offset},
            {"path", entry.path},
            {"sha256", entry.digest},
        });
    offset += entry.bytes;
  }
  nlohmann::json index{
      {"compression", "none"},
      {"contract", "lmdj.project-bundle.v1"},
      {"contract_version", "1.0.0"},
      {"entries", std::move(encoded_entries)},
      {"project_contract", "lmdj.project.v1"},
      {"project_id", project_id.value()},
      {"uncompressed_bytes", offset},
  };
  return foundation::Result<std::string>::success(
      sha256(foundation::canonical_json(index)));
}

}  // namespace

struct ProjectBundleTransfer::Impl {
  struct Session {
    std::filesystem::path workspace;
    std::filesystem::path root;
    std::filesystem::path bundle;
    std::filesystem::path index_path;
    std::string token;
    std::uint64_t expected_index_bytes;
    std::string expected_index_sha256;
    std::uint64_t index_written = 0;
    std::optional<ParsedIndex> index;
    std::size_t next_entry = 0;
    std::uint64_t entry_written = 0;
    std::unique_ptr<ProjectWriterLease> lease;
  };

  explicit Impl(std::shared_ptr<ProjectStoragePlatform> selected)
      : platform(
            selected != nullptr
                ? std::move(selected)
                : make_default_project_storage_platform()) {}

  std::shared_ptr<ProjectStoragePlatform> platform;
  mutable std::mutex mutex;
  std::map<std::string, Session> sessions;
  std::set<std::string> used_tokens;
};

namespace {

foundation::Result<LocalProjectSummary> summarize_project(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& path) {
  ProjectStore store{platform};
  const auto loaded = store.load(path);
  if (!loaded.has_value()) {
    return foundation::Result<LocalProjectSummary>::failure(
        sanitized_storage_error(
            loaded.error(), "Project could not be validated"));
  }
  const auto& state = loaded.value();
  if (state.patterns.empty()) {
    return foundation::Result<LocalProjectSummary>::failure(
        invalid_bundle("Project has no playable Pattern"));
  }
  const auto digest = project_digest(*platform, path, state.id);
  if (!digest.has_value()) {
    return foundation::Result<LocalProjectSummary>::failure(digest.error());
  }
  std::size_t assigned = 0;
  for (const auto& bank : state.banks) {
    assigned += static_cast<std::size_t>(std::count_if(
        bank.begin(),
        bank.end(),
        [](const auto& slot) { return slot.asset_id.has_value(); }));
  }
  return foundation::Result<LocalProjectSummary>::success(
      LocalProjectSummary{
          state.id,
          state.patterns.begin()->first,
          state.revision,
          state.bpm,
          state.assets.size(),
          assigned,
          digest.value(),
      });
}

std::filesystem::path staging_root(
    const std::filesystem::path& workspace) {
  return workspace / ".lmdj-host/import-staging";
}

std::filesystem::path projects_root(
    const std::filesystem::path& workspace) {
  return workspace / "projects";
}

bool valid_workspace(const std::filesystem::path& path) {
  return path.is_absolute() && path.lexically_normal() == path &&
         path != path.root_path();
}

}  // namespace

ProjectBundleTransfer::ProjectBundleTransfer(
    std::shared_ptr<ProjectStoragePlatform> platform)
    : impl_(std::make_unique<Impl>(std::move(platform))) {}

ProjectBundleTransfer::~ProjectBundleTransfer() = default;

foundation::Result<std::vector<LocalProjectSummary>>
ProjectBundleTransfer::list_local_projects(
    const std::filesystem::path& workspace_root) const {
  std::lock_guard lock(impl_->mutex);
  if (!valid_workspace(workspace_root)) {
    return foundation::Result<std::vector<LocalProjectSummary>>::failure(
        invalid_argument("Workspace root must be a normalized absolute path"));
  }
  const auto root = projects_root(workspace_root);
  const auto present = impl_->platform->directory_exists(root);
  if (!present.has_value()) {
    return foundation::Result<std::vector<LocalProjectSummary>>::failure(
        sanitized_storage_error(
            present.error(), "Local Project root could not be inspected"));
  }
  if (!present.value()) {
    return foundation::Result<std::vector<LocalProjectSummary>>::success({});
  }
  const auto names = impl_->platform->list_directories(root);
  if (!names.has_value()) {
    return foundation::Result<std::vector<LocalProjectSummary>>::failure(
        sanitized_storage_error(
            names.error(), "Local Projects could not be listed"));
  }
  std::vector<LocalProjectSummary> summaries;
  for (const auto& name : names.value()) {
    const std::filesystem::path directory{name};
    if (directory.extension() != ".lmdj") {
      continue;
    }
    const auto summary = summarize_project(impl_->platform, root / directory);
    if (!summary.has_value()) {
      return foundation::Result<std::vector<LocalProjectSummary>>::failure(
          summary.error());
    }
    if (directory.stem().string() != summary.value().project_id.value()) {
      return foundation::Result<std::vector<LocalProjectSummary>>::failure(
          invalid_bundle("Local Project directory identity is invalid"));
    }
    summaries.push_back(summary.value());
  }
  std::sort(
      summaries.begin(),
      summaries.end(),
      [](const auto& left, const auto& right) {
        return left.project_id.value() < right.project_id.value();
      });
  return foundation::Result<std::vector<LocalProjectSummary>>::success(
      std::move(summaries));
}

foundation::Result<BundleImportSession> ProjectBundleTransfer::begin(
    const std::filesystem::path& workspace_root,
    std::string token,
    std::uint64_t index_bytes,
    std::string index_sha256) {
  std::lock_guard lock(impl_->mutex);
  if (!valid_workspace(workspace_root) || !domain::is_valid_uuid(token) ||
      !lowercase_sha256(index_sha256) || index_bytes == 0) {
    return foundation::Result<BundleImportSession>::failure(
        invalid_argument("Project Bundle import identity is invalid"));
  }
  if (index_bytes > kMaximumIndexBytes) {
    return foundation::Result<BundleImportSession>::failure(
        resource_limit("Project Bundle index exceeds 4 MiB"));
  }
  if (impl_->used_tokens.contains(token)) {
    return foundation::Result<BundleImportSession>::failure(
        invalid_argument("Project Bundle import token was already used"));
  }
  impl_->used_tokens.insert(token);
  const auto root = staging_root(workspace_root) / token;
  auto lease = impl_->platform->acquire_writer(root);
  if (!lease.has_value()) {
    return foundation::Result<BundleImportSession>::failure(
        sanitized_storage_error(
            lease.error(), "Project Bundle staging writer is busy"));
  }
  const auto bundle = root / "project.lmdj";
  const std::vector<std::filesystem::path> directories{
      root,
      bundle,
      bundle / "assets",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& directory : directories) {
    const auto ensured = impl_->platform->ensure_directory(directory);
    if (!ensured.has_value()) {
      lease.value().reset();
      (void)impl_->platform->remove_tree(root);
      return foundation::Result<BundleImportSession>::failure(
          sanitized_storage_error(
              ensured.error(), "Project Bundle staging could not be created"));
    }
  }
  const auto index_path = root / "index.json";
  const auto created = impl_->platform->create_immutable(index_path, {});
  if (!created.has_value()) {
    lease.value().reset();
    (void)impl_->platform->remove_tree(root);
    return foundation::Result<BundleImportSession>::failure(
        sanitized_storage_error(
            created.error(), "Project Bundle index staging could not be created"));
  }
  impl_->sessions.emplace(
      token,
      Impl::Session{
          workspace_root,
          root,
          bundle,
          index_path,
          token,
          index_bytes,
          std::move(index_sha256),
          0,
          std::nullopt,
          0,
          0,
          std::move(lease.value()),
      });
  return foundation::Result<BundleImportSession>::success(
      BundleImportSession{std::move(token), index_bytes});
}

foundation::Result<std::optional<BundleImportIdentity>>
ProjectBundleTransfer::append_index(
    std::string_view token,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final) {
  std::lock_guard lock(impl_->mutex);
  const auto found = impl_->sessions.find(std::string{token});
  if (found == impl_->sessions.end()) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        session_not_found());
  }
  auto& session = found->second;
  if (session.index.has_value() || offset != session.index_written ||
      bytes.empty() || bytes.size() > kMaximumChunkBytes ||
      session.index_written + bytes.size() > session.expected_index_bytes ||
      final !=
          (session.index_written + bytes.size() ==
           session.expected_index_bytes)) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        invalid_argument("Project Bundle index chunk is invalid"));
  }
  const auto appended = impl_->platform->append_durable(
      session.index_path, session.index_written, bytes);
  if (!appended.has_value()) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        sanitized_storage_error(
            appended.error(), "Project Bundle index chunk could not be staged"));
  }
  session.index_written += bytes.size();
  if (!final) {
    return foundation::Result<std::optional<BundleImportIdentity>>::success(
        std::nullopt);
  }
  const auto staged = impl_->platform->read_complete(session.index_path);
  if (!staged.has_value()) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        sanitized_storage_error(
            staged.error(), "Project Bundle index could not be read"));
  }
  if (sha256(staged.value()) != session.expected_index_sha256) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        invalid_bundle("Project Bundle index hash does not match"));
  }
  const auto parsed = parse_index(byte_string(staged.value()));
  if (!parsed.has_value()) {
    return foundation::Result<std::optional<BundleImportIdentity>>::failure(
        parsed.error());
  }
  session.index = parsed.value();
  return foundation::Result<std::optional<BundleImportIdentity>>::success(
      BundleImportIdentity{
          session.index->project_id,
          session.index->bundle_digest,
          static_cast<std::uint32_t>(session.index->entries.size()),
      });
}

foundation::Result<void> ProjectBundleTransfer::append_entry(
    std::string_view token,
    std::uint32_t entry_index,
    std::uint64_t offset,
    std::span<const std::byte> bytes,
    bool final) {
  std::lock_guard lock(impl_->mutex);
  const auto found = impl_->sessions.find(std::string{token});
  if (found == impl_->sessions.end()) {
    return foundation::Result<void>::failure(session_not_found());
  }
  auto& session = found->second;
  if (!session.index.has_value() ||
      entry_index != session.next_entry ||
      entry_index >= session.index->entries.size() ||
      offset != session.entry_written || bytes.size() > kMaximumChunkBytes) {
    return foundation::Result<void>::failure(
        invalid_argument("Project Bundle entry chunk is invalid"));
  }
  const auto& entry = session.index->entries.at(entry_index);
  if (session.entry_written + bytes.size() > entry.bytes ||
      final != (session.entry_written + bytes.size() == entry.bytes) ||
      (!final && bytes.empty())) {
    return foundation::Result<void>::failure(
        invalid_argument("Project Bundle entry boundary is invalid"));
  }
  const auto destination = session.bundle / entry.path;
  const auto ensured = impl_->platform->ensure_directory(
      destination.parent_path());
  if (!ensured.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            ensured.error(), "Project Bundle entry directory could not be created"));
  }
  foundation::Result<void> written = foundation::Result<void>::success();
  if (session.entry_written == 0) {
    written = impl_->platform->create_immutable(destination, bytes);
  } else {
    written = impl_->platform->append_durable(
        destination, session.entry_written, bytes);
  }
  if (!written.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            written.error(), "Project Bundle entry chunk could not be staged"));
  }
  session.entry_written += bytes.size();
  if (!final) {
    return foundation::Result<void>::success();
  }
  const auto staged = impl_->platform->read_complete(destination);
  if (!staged.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            staged.error(), "Project Bundle entry could not be read"));
  }
  if (sha256(staged.value()) != entry.sha256) {
    return foundation::Result<void>::failure(
        invalid_bundle("Project Bundle entry hash does not match"));
  }
  ++session.next_entry;
  session.entry_written = 0;
  return foundation::Result<void>::success();
}

foundation::Result<LocalProjectSummary> ProjectBundleTransfer::commit(
    std::string_view token) {
  std::lock_guard lock(impl_->mutex);
  const auto found = impl_->sessions.find(std::string{token});
  if (found == impl_->sessions.end()) {
    return foundation::Result<LocalProjectSummary>::failure(
        session_not_found());
  }
  auto& session = found->second;
  const auto root = session.root;
  const auto cleanup = [&]() {
    session.lease.reset();
    (void)impl_->platform->remove_tree(root);
    impl_->sessions.erase(found);
  };
  if (!session.index.has_value() ||
      session.next_entry != session.index->entries.size() ||
      session.entry_written != 0) {
    const auto error = invalid_argument("Project Bundle import is incomplete");
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  auto staged_summary = summarize_project(impl_->platform, session.bundle);
  if (!staged_summary.has_value()) {
    const auto error = staged_summary.error();
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  if (staged_summary.value().project_id != session.index->project_id ||
      staged_summary.value().bundle_digest != session.index->bundle_digest) {
    const auto error = invalid_bundle(
        "Project Bundle identity does not match its validated Project");
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  const auto destination_root = projects_root(session.workspace);
  const auto ensured = impl_->platform->ensure_directory(destination_root);
  if (!ensured.has_value()) {
    const auto error = sanitized_storage_error(
        ensured.error(), "Local Project root could not be created");
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  const auto destination =
      destination_root /
      (session.index->project_id.value() + ".lmdj");
  auto destination_lease = impl_->platform->acquire_writer(destination);
  if (!destination_lease.has_value()) {
    const auto error = sanitized_storage_error(
        destination_lease.error(), "Local Project writer is busy");
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  const auto present = impl_->platform->directory_exists(destination);
  if (!present.has_value()) {
    const auto error = sanitized_storage_error(
        present.error(), "Local Project destination could not be inspected");
    cleanup();
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  if (present.value()) {
    const auto existing = summarize_project(impl_->platform, destination);
    if (!existing.has_value()) {
      const auto error = existing.error();
      cleanup();
      return foundation::Result<LocalProjectSummary>::failure(error);
    }
    if (existing.value().bundle_digest != session.index->bundle_digest) {
      const auto error = Error{
          ErrorCode::duplicate_id,
          "A different local Project already uses this Project ID",
      };
      cleanup();
      return foundation::Result<LocalProjectSummary>::failure(error);
    }
    const auto summary = existing.value();
    cleanup();
    return foundation::Result<LocalProjectSummary>::success(summary);
  }

  session.lease.reset();
  const auto published = impl_->platform->publish_directory_if_absent(
      session.bundle, destination);
  if (!published.has_value()) {
    const auto error = sanitized_storage_error(
        published.error(), "Project Bundle could not be published atomically");
    (void)impl_->platform->remove_tree(root);
    impl_->sessions.erase(found);
    return foundation::Result<LocalProjectSummary>::failure(error);
  }
  const auto summary = staged_summary.value();
  (void)impl_->platform->remove_tree(root);
  impl_->sessions.erase(found);
  return foundation::Result<LocalProjectSummary>::success(summary);
}

foundation::Result<void> ProjectBundleTransfer::abort(std::string_view token) {
  std::lock_guard lock(impl_->mutex);
  const auto found = impl_->sessions.find(std::string{token});
  if (found == impl_->sessions.end()) {
    return foundation::Result<void>::failure(session_not_found());
  }
  const auto root = found->second.root;
  found->second.lease.reset();
  const auto removed = impl_->platform->remove_tree(root);
  impl_->sessions.erase(found);
  if (!removed.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            removed.error(), "Project Bundle staging could not be removed"));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> ProjectBundleTransfer::cleanup_incomplete(
    const std::filesystem::path& workspace_root) {
  std::lock_guard lock(impl_->mutex);
  if (!valid_workspace(workspace_root)) {
    return foundation::Result<void>::failure(
        invalid_argument("Workspace root must be a normalized absolute path"));
  }
  const auto root = staging_root(workspace_root);
  const auto present = impl_->platform->directory_exists(root);
  if (!present.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            present.error(), "Project Bundle staging root could not be inspected"));
  }
  if (!present.value()) {
    return foundation::Result<void>::success();
  }
  const auto directories = impl_->platform->list_directories(root);
  if (!directories.has_value()) {
    return foundation::Result<void>::failure(
        sanitized_storage_error(
            directories.error(), "Project Bundle staging could not be listed"));
  }
  for (const auto& name : directories.value()) {
    if (impl_->sessions.contains(name)) {
      continue;
    }
    const auto path = root / name;
    auto lease = impl_->platform->acquire_writer(path);
    if (!lease.has_value()) {
      if (lease.error().details.is_object() &&
          lease.error().details.value("storage_condition", std::string{}) ==
              kStorageConditionProjectBusy) {
        continue;
      }
      return foundation::Result<void>::failure(
          sanitized_storage_error(
              lease.error(), "Project Bundle staging cleanup is busy"));
    }
    lease.value().reset();
    const auto removed = impl_->platform->remove_tree(path);
    if (!removed.has_value()) {
      return foundation::Result<void>::failure(
          sanitized_storage_error(
              removed.error(), "Project Bundle staging cleanup failed"));
    }
  }
  return foundation::Result<void>::success();
}

}  // namespace lmdj::project_io
