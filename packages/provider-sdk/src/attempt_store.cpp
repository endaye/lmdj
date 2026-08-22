#include <lmdj/provider/attempt_store.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <limits>
#include <mutex>
#include <random>
#include <set>
#include <span>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <tuple>
#include <utility>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/provider.hpp>

#include "durable_file.hpp"

namespace lmdj::provider {
namespace {

// Every JSON document below arrives from disk and is therefore external input.
// Deep nesting is a stack-overflow vector that a try/catch cannot contain, so
// parse through the depth-bounded Foundation entry point. These paths already
// convert exceptions into typed failures, so signalling by exception keeps the
// existing error contract intact.
template <typename Source>
nlohmann::json parse_bounded_or_throw(Source&& source) {
  auto parsed = foundation::parse_bounded_json(std::forward<Source>(source));
  if (!parsed.has_value()) {
    throw std::runtime_error(
        "JSON is malformed or exceeds the maximum container depth");
  }
  return std::move(*parsed);
}

using foundation::ArtifactRef;
using foundation::Error;
using foundation::ErrorCode;

std::atomic<std::uint64_t> temporary_file_sequence{0};
std::mutex host_settings_mutex;

std::uint64_t per_process_temp_nonce() {
  static const std::uint64_t nonce = [] {
    std::random_device device;
    return (static_cast<std::uint64_t>(device()) << 32U) ^
           static_cast<std::uint64_t>(device());
  }();
  return nonce;
}

Error invalid_argument(std::string message) {
  return Error{
      ErrorCode::invalid_argument,
      std::move(message),
  };
}

Error io_error(
    std::string message,
    const std::filesystem::path& path,
    const std::error_code& system_error = {}) {
  auto details = nlohmann::json{{"path", path.generic_string()}};
  if (system_error) {
    details["system_error"] = system_error.message();
  }
  return Error{
      ErrorCode::io_error,
      std::move(message),
      std::move(details),
  };
}

bool valid_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

nlohmann::json model_identity_json(
    const std::optional<ModelIdentity>& identity) {
  if (!identity.has_value()) {
    return nullptr;
  }
  return {
      {"id", identity->id},
      {"version", identity->version},
      {"artifact_sha256", identity->artifact_sha256},
  };
}

bool valid_media_type(std::string_view value) {
  return !value.empty() && value.size() <= 128 &&
         value.find('/') != std::string_view::npos &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return character >= 0x21 && character <= 0x7e;
             });
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
  if (base.size() == 4 &&
      (base.starts_with("COM") || base.starts_with("LPT")) &&
      base.at(3) >= '1' && base.at(3) <= '9') {
    return true;
  }
  return false;
}

bool valid_file_id(std::string_view value) {
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

bool valid_artifact(const ArtifactRef& artifact) {
  return valid_sha256(artifact.sha256) &&
         valid_media_type(artifact.media_type);
}

template <typename T>
bool contains(const std::vector<T>& values, const T& value) {
  return std::find(values.begin(), values.end(), value) != values.end();
}

bool unique_nonempty(const std::vector<std::string>& values) {
  if (std::any_of(values.begin(), values.end(), [](const auto& value) {
        return value.empty();
      })) {
    return false;
  }
  auto sorted = values;
  std::sort(sorted.begin(), sorted.end());
  return std::adjacent_find(sorted.begin(), sorted.end()) == sorted.end();
}

const ArtifactPortDescriptor* find_port(
    const std::vector<ArtifactPortDescriptor>& ports,
    std::string_view name) {
  const auto found = std::find_if(
      ports.begin(), ports.end(), [name](const auto& port) {
        return port.name == name;
      });
  return found == ports.end() ? nullptr : &*found;
}

bool media_type_allowed(
    const ArtifactPortDescriptor& port,
    std::string_view media_type) {
  return std::any_of(
      port.media_types.begin(),
      port.media_types.end(),
      [media_type](const auto& allowed) {
        return allowed == "*/*" || allowed == media_type;
      });
}

foundation::Result<void> ensure_directory(
    const std::filesystem::path& path) {
  std::error_code status_error;
  auto status = std::filesystem::symlink_status(path, status_error);
  if (status_error &&
      status_error !=
          std::make_error_code(std::errc::no_such_file_or_directory)) {
    return foundation::Result<void>::failure(
        io_error("workspace path could not be inspected", path, status_error));
  }
  if (!status_error &&
      status.type() != std::filesystem::file_type::not_found) {
    if (std::filesystem::is_symlink(status) ||
        !std::filesystem::is_directory(status)) {
      return foundation::Result<void>::failure(
          io_error("workspace path is not a safe directory", path));
    }
    return foundation::Result<void>::success();
  }

  std::error_code create_error;
  if (!std::filesystem::create_directories(path, create_error) &&
      create_error) {
    return foundation::Result<void>::failure(
        io_error("workspace directory could not be created", path, create_error));
  }
  status_error.clear();
  status = std::filesystem::symlink_status(path, status_error);
  if (status_error || std::filesystem::is_symlink(status) ||
      !std::filesystem::is_directory(status)) {
    return foundation::Result<void>::failure(
        io_error("workspace directory is unsafe after creation", path, status_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<std::filesystem::path> prepare_workspace(
    const std::filesystem::path& workspace_root) {
  if (workspace_root.empty() ||
      workspace_root.extension() == ".lmdj") {
    return foundation::Result<std::filesystem::path>::failure(
        invalid_argument(
            "workspace root must be a Host workspace parent, not a Project"));
  }
  for (const auto& directory : {
           workspace_root,
           workspace_root / ".lmdj-workspace",
           workspace_root / ".lmdj-workspace/attempts",
       }) {
    const auto ensured = ensure_directory(directory);
    if (!ensured.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          ensured.error());
    }
  }
  return foundation::Result<std::filesystem::path>::success(
      workspace_root / ".lmdj-workspace");
}

foundation::Result<void> reject_existing_or_symlink(
    const std::filesystem::path& path,
    ErrorCode existing_code);

foundation::Result<std::filesystem::path> reserve_attempt(
    const std::filesystem::path& attempts_root,
    const foundation::AttemptId& attempt_id) {
  const auto terminal_path =
      attempts_root / (attempt_id.value() + ".json");
  const auto terminal_available =
      reject_existing_or_symlink(
          terminal_path, ErrorCode::duplicate_id);
  if (!terminal_available.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        terminal_available.error());
  }

  const auto attempt_root = attempts_root / attempt_id.value();
  std::error_code create_error;
  if (std::filesystem::create_directory(attempt_root, create_error)) {
    return foundation::Result<std::filesystem::path>::success(
        attempt_root);
  }
  if (create_error &&
      create_error != std::make_error_code(std::errc::file_exists)) {
    return foundation::Result<std::filesystem::path>::failure(
        io_error(
            "Attempt reservation could not be created",
            attempt_root,
            create_error));
  }
  std::error_code status_error;
  const auto status =
      std::filesystem::symlink_status(attempt_root, status_error);
  if (!status_error && !std::filesystem::is_symlink(status) &&
      std::filesystem::is_directory(status)) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{
            ErrorCode::duplicate_id,
            "Attempt id is already reserved",
            {{"path", attempt_root.generic_string()}},
        });
  }
  return foundation::Result<std::filesystem::path>::failure(
      io_error(
          "Attempt reservation path is unsafe",
          attempt_root,
          status_error));
}

foundation::Result<void> remove_tree(
    const std::filesystem::path& path,
    std::string message) {
  std::error_code remove_error;
  std::filesystem::remove_all(path, remove_error);
  if (remove_error) {
    return foundation::Result<void>::failure(
        io_error(std::move(message), path, remove_error));
  }
  std::error_code status_error;
  const auto status = std::filesystem::symlink_status(path, status_error);
  if (!status_error &&
      status.type() != std::filesystem::file_type::not_found) {
    return foundation::Result<void>::failure(
        io_error(std::move(message), path));
  }
  if (status_error &&
      status_error !=
          std::make_error_code(std::errc::no_such_file_or_directory)) {
    return foundation::Result<void>::failure(
        io_error(std::move(message), path, status_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> cleanup_attempt_outputs(
    const std::filesystem::path& attempt_root) {
  for (const auto& path : {
           attempt_root / "staging",
           attempt_root / "artifacts",
       }) {
    const auto removed =
        remove_tree(path, "Attempt output cleanup failed");
    if (!removed.has_value()) {
      return removed;
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> publish_attempt_outputs(
    const std::filesystem::path& attempt_root) {
  const auto staging_root = attempt_root / "staging";
  const auto staged_artifacts = staging_root / "artifacts";
  const auto final_artifacts = attempt_root / "artifacts";
  const auto available =
      reject_existing_or_symlink(final_artifacts, ErrorCode::io_error);
  if (!available.has_value()) {
    return available;
  }
  std::error_code rename_error;
  std::filesystem::rename(
      staged_artifacts, final_artifacts, rename_error);
  if (rename_error) {
    return foundation::Result<void>::failure(
        io_error(
            "Attempt outputs could not be published",
            final_artifacts,
            rename_error));
  }
  const auto synced = detail::sync_directory(attempt_root);
  if (!synced.has_value()) {
    return synced;
  }
  std::error_code remove_error;
  if (!std::filesystem::remove(staging_root, remove_error) ||
      remove_error) {
    return foundation::Result<void>::failure(
        io_error(
            "Attempt staging directory could not be removed",
            staging_root,
            remove_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> acquire_settings_lock(
    const std::filesystem::path& lock_path) {
  std::error_code create_error;
  if (std::filesystem::create_directory(lock_path, create_error)) {
    return foundation::Result<void>::success();
  }
  if (!create_error ||
      create_error == std::make_error_code(std::errc::file_exists)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::io_error,
            "host settings are busy",
            {{"path", lock_path.generic_string()}},
        });
  }
  return foundation::Result<void>::failure(
      io_error(
          "host settings lock could not be created",
          lock_path,
          create_error));
}

foundation::Result<void> release_settings_lock(
    const std::filesystem::path& lock_path) {
  std::error_code remove_error;
  if (!std::filesystem::remove(lock_path, remove_error) ||
      remove_error) {
    return foundation::Result<void>::failure(
        io_error(
            "host settings lock could not be released",
            lock_path,
            remove_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> reject_existing_or_symlink(
    const std::filesystem::path& path,
    ErrorCode existing_code) {
  std::error_code status_error;
  const auto status = std::filesystem::symlink_status(path, status_error);
  if (status_error &&
      status_error !=
          std::make_error_code(std::errc::no_such_file_or_directory)) {
    return foundation::Result<void>::failure(
        io_error("destination could not be inspected", path, status_error));
  }
  if (!status_error &&
      status.type() != std::filesystem::file_type::not_found) {
    return foundation::Result<void>::failure(
        Error{
            existing_code,
            "destination already exists",
            {{"path", path.generic_string()}},
        });
  }
  return foundation::Result<void>::success();
}

std::filesystem::path temporary_sibling(
    const std::filesystem::path& final_path) {
  const auto sequence =
      temporary_file_sequence.fetch_add(1, std::memory_order_relaxed);
  const auto timestamp =
      std::chrono::steady_clock::now().time_since_epoch().count();
  const auto nonce = per_process_temp_nonce();
  return final_path.parent_path() /
         ("." + final_path.filename().generic_string() + ".tmp." +
          std::to_string(timestamp) + "." + std::to_string(nonce) + "." +
          std::to_string(sequence));
}

foundation::Result<void> write_bytes(
    const std::filesystem::path& path,
    std::string_view bytes) {
  if (bytes.size() >
      static_cast<std::size_t>(
          std::numeric_limits<std::streamsize>::max())) {
    return foundation::Result<void>::failure(
        invalid_argument("temporary file exceeds stream size limits"));
  }
  const auto available =
      reject_existing_or_symlink(path, ErrorCode::io_error);
  if (!available.has_value()) {
    return available;
  }
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  if (!stream) {
    return foundation::Result<void>::failure(
        io_error("temporary file could not be opened", path));
  }
  stream.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  stream.flush();
  if (!stream) {
    stream.close();
    std::error_code cleanup_error;
    std::filesystem::remove(path, cleanup_error);
    return foundation::Result<void>::failure(
        io_error("temporary file could not be written", path));
  }
  stream.close();
  if (stream.fail()) {
    std::error_code cleanup_error;
    std::filesystem::remove(path, cleanup_error);
    return foundation::Result<void>::failure(
        io_error("temporary file could not be closed", path));
  }
  return foundation::Result<void>::success();
}

foundation::Result<void> write_new_atomic(
    const std::filesystem::path& final_path,
    std::string_view bytes,
    ErrorCode existing_code) {
  const auto available =
      reject_existing_or_symlink(final_path, existing_code);
  if (!available.has_value()) {
    return available;
  }
  const auto temp_path = temporary_sibling(final_path);
  const auto temp_available =
      reject_existing_or_symlink(temp_path, ErrorCode::io_error);
  if (!temp_available.has_value()) {
    return temp_available;
  }
  const auto written =
      detail::write_bytes_durable(temp_path, bytes);
  if (!written.has_value()) {
    return written;
  }
  return detail::publish_new_link(temp_path, final_path, existing_code);
}

foundation::Result<void> write_replace_atomic(
    const std::filesystem::path& final_path,
    std::string_view bytes) {
  std::error_code status_error;
  const auto status =
      std::filesystem::symlink_status(final_path, status_error);
  if (!status_error &&
      status.type() != std::filesystem::file_type::not_found &&
      (std::filesystem::is_symlink(status) ||
       !std::filesystem::is_regular_file(status))) {
    return foundation::Result<void>::failure(
        io_error("settings destination is unsafe", final_path));
  }
  if (status_error &&
      status_error !=
          std::make_error_code(std::errc::no_such_file_or_directory)) {
    return foundation::Result<void>::failure(
        io_error("settings destination could not be inspected", final_path));
  }
  const auto temp_path = temporary_sibling(final_path);
  const auto written = write_bytes(temp_path, bytes);
  if (!written.has_value()) {
    return written;
  }
  std::error_code rename_error;
  std::filesystem::rename(temp_path, final_path, rename_error);
  if (rename_error) {
    std::error_code cleanup_error;
    std::filesystem::remove(temp_path, cleanup_error);
    return foundation::Result<void>::failure(
        io_error("settings could not be published", final_path, rename_error));
  }
  return foundation::Result<void>::success();
}

foundation::Result<nlohmann::json> read_host_settings(
    const std::filesystem::path& path,
    bool allow_missing) {
  std::error_code status_error;
  const auto status = std::filesystem::symlink_status(path, status_error);
  if (status_error ||
      status.type() == std::filesystem::file_type::not_found) {
    if (allow_missing &&
        (!status_error ||
         status_error ==
             std::make_error_code(std::errc::no_such_file_or_directory))) {
      return foundation::Result<nlohmann::json>::success(
          {
              {"format", "provider-selections"},
              {"provider_selections", nlohmann::json::object()},
          });
    }
    return foundation::Result<nlohmann::json>::failure(
        Error{
            ErrorCode::provider_not_found,
            "provider selection is not configured",
        });
  }
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return foundation::Result<nlohmann::json>::failure(
        io_error("host settings path is unsafe", path));
  }
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    return foundation::Result<nlohmann::json>::failure(
        io_error("host settings could not be opened", path));
  }
  try {
    const auto bytes = std::string{
        std::istreambuf_iterator<char>(stream),
        std::istreambuf_iterator<char>(),
    };
    const auto settings = parse_bounded_or_throw(bytes);
    if (settings.size() != 2 ||
        settings.at("format") != "provider-selections" ||
        !settings.at("provider_selections").is_object() ||
        bytes != foundation::canonical_json(settings) + "\n") {
      return foundation::Result<nlohmann::json>::failure(
          invalid_argument("host settings have an invalid shape"));
    }
    for (const auto& [capability, provider] :
         settings.at("provider_selections").items()) {
      if (!valid_file_id(capability) || !provider.is_string() ||
          !valid_file_id(provider.get<std::string>())) {
        return foundation::Result<nlohmann::json>::failure(
            invalid_argument("host settings contain an invalid selection"));
      }
    }
    return foundation::Result<nlohmann::json>::success(settings);
  } catch (const nlohmann::json::exception&) {
    return foundation::Result<nlohmann::json>::failure(
        invalid_argument("host settings are not valid JSON"));
  }
}

const CapabilityDescriptor& selected_capability(
    const ProviderDescriptor& provider,
    const std::string& capability) {
  return *std::find_if(
      provider.capabilities.begin(),
      provider.capabilities.end(),
      [&capability](const auto& descriptor) {
        return descriptor.id == capability;
      });
}

Error validate_request(
    const CapabilityRequest& request,
    const CapabilityDescriptor& capability,
    const ProviderPolicy& policy) {
  if (request.capability != capability.id ||
      request.data_classification.empty() ||
      request.platform.empty() || request.region.empty()) {
    return invalid_argument("capability request metadata is invalid");
  }
  std::set<std::string> input_hashes;
  for (const auto& input : request.inputs) {
    if (!valid_port_name(input.port)) {
      return invalid_argument("capability request port name is invalid");
    }
    const auto* port = find_port(
        capability.input_artifacts, input.port);
    if (port == nullptr) {
      return invalid_argument(
          "capability request names a port the Capability does not declare");
    }
    if (!valid_artifact(input.artifact) ||
        !media_type_allowed(*port, input.artifact.media_type) ||
        !input_hashes.insert(input.artifact.sha256).second) {
      return invalid_argument("capability request artifacts are invalid");
    }
  }
  for (const auto& port : capability.input_artifacts) {
    const auto count = static_cast<std::size_t>(std::count_if(
        request.inputs.begin(),
        request.inputs.end(),
        [&port](const auto& input) {
          return input.port == port.name;
        }));
    const auto minimum =
        port.required ? std::size_t{1} : std::size_t{0};
    if (count < minimum || count > port.max_count) {
      return invalid_argument("capability request input count is invalid");
    }
  }
  if (!unique_nonempty(request.required_permissions)) {
    return invalid_argument("required permissions are invalid");
  }
  if (!contains(capability.policy.regions, request.region) ||
      !contains(policy.allowed_regions, request.region) ||
      !contains(
          capability.policy.data_classifications,
          request.data_classification) ||
      !contains(
          policy.allowed_data_classifications,
          request.data_classification) ||
      !contains(capability.platforms, request.platform)) {
    return Error{
        ErrorCode::permission_denied,
        "capability request is not allowed by Provider policy",
    };
  }
  for (const auto& required :
       capability.policy.required_permissions) {
    if (!contains(request.required_permissions, required) ||
        !contains(policy.granted_permissions, required)) {
      return Error{
          ErrorCode::permission_denied,
          "capability permission is not granted",
      };
    }
  }
  for (const auto& requested : request.required_permissions) {
    if (!contains(
            capability.policy.required_permissions, requested) ||
        !contains(policy.granted_permissions, requested)) {
      return Error{
          ErrorCode::permission_denied,
          "capability permission is not granted",
      };
    }
  }
  return Error{ErrorCode::internal_error, ""};
}

bool validation_passed(const Error& error) {
  return error.code == ErrorCode::internal_error && error.message.empty();
}

foundation::Result<std::string> hash_parameters(
    const nlohmann::json& parameters) {
  std::string canonical;
  try {
    canonical = foundation::canonical_json(parameters);
  } catch (const nlohmann::json::exception&) {
    return foundation::Result<std::string>::failure(
        invalid_argument("capability parameters are not serializable"));
  }
  picosha2::hash256_one_by_one hasher;
  hasher.process(canonical.begin(), canonical.end());
  hasher.finish();
  return foundation::Result<std::string>::success(
      picosha2::get_hash_hex_string(hasher));
}

void sort_artifacts(std::vector<ArtifactRef>& artifacts) {
  std::sort(
      artifacts.begin(), artifacts.end(), [](const auto& left, const auto& right) {
        return std::tie(
                   left.sha256, left.media_type, left.byte_length) <
               std::tie(
                   right.sha256, right.media_type, right.byte_length);
      });
}

bool binding_less(
    const ArtifactBinding& left,
    const ArtifactBinding& right) {
  return std::tie(
             left.port,
             left.artifact.sha256,
             left.artifact.media_type,
             left.artifact.byte_length) <
         std::tie(
             right.port,
             right.artifact.sha256,
             right.artifact.media_type,
             right.artifact.byte_length);
}

void sort_bindings(std::vector<ArtifactBinding>& bindings) {
  std::sort(bindings.begin(), bindings.end(), binding_less);
}

nlohmann::json binding_array(std::vector<ArtifactBinding> bindings) {
  sort_bindings(bindings);
  auto output = nlohmann::json::array();
  for (const auto& binding : bindings) {
    output.push_back(binding);
  }
  return output;
}

nlohmann::json artifact_array(std::vector<ArtifactRef> artifacts) {
  sort_artifacts(artifacts);
  auto output = nlohmann::json::array();
  for (const auto& artifact : artifacts) {
    output.push_back(artifact);
  }
  return output;
}

nlohmann::json error_json(
    const std::optional<Error>& error,
    bool redact_provider_error) {
  if (!error.has_value()) {
    return nullptr;
  }
  return {
      {"code", foundation::error_code_name(error->code)},
      {"details",
       redact_provider_error
           ? nlohmann::json::object()
           : error->details},
      {"message",
       redact_provider_error
           ? "provider execution failed"
           : error->message},
  };
}

foundation::Result<void> persist_attempt(
    const std::filesystem::path& attempts_root,
    const ProviderDescriptor& provider,
    const CapabilityDescriptor& capability,
    const CapabilityRequest& request,
    const AttemptResult& result,
    std::string parameters_sha256,
    std::string started_at,
    std::string ended_at,
    const std::vector<ArtifactBinding>& minted,
    bool redact_provider_error) {
  auto permissions = request.required_permissions;
  std::sort(permissions.begin(), permissions.end());
  auto inputs = request.inputs;
  sort_bindings(inputs);
  auto candidate_outputs = result.candidate.has_value()
                               ? result.candidate->outputs
                               : std::vector<ArtifactBinding>{};
  sort_bindings(candidate_outputs);
  auto artifacts = std::vector<ArtifactRef>{};
  for (const auto& binding : inputs) {
    if (!contains(artifacts, binding.artifact)) {
      artifacts.push_back(binding.artifact);
    }
  }
  for (const auto& binding : minted) {
    if (!contains(artifacts, binding.artifact)) {
      artifacts.push_back(binding.artifact);
    }
  }
  auto candidate_ids = nlohmann::json::array();
  if (result.candidate.has_value()) {
    candidate_ids.push_back(result.candidate->id.value());
  }
  const auto encoded = nlohmann::json{
      {"artifacts", artifact_array(std::move(artifacts))},
      {"attempt_id", result.attempt_id.value()},
      {"candidate_ids", std::move(candidate_ids)},
      {"candidate_outputs", binding_array(std::move(candidate_outputs))},
      {"capability",
       {
           {"contract", "lmdj.capability.v2"},
           {"id", capability.id},
           {"version", capability.contract_version},
       }},
      {"ended_at", std::move(ended_at)},
      {"error", error_json(result.error, redact_provider_error)},
      {"format", "terminal-attempt-v2"},
      {"minted_outputs", binding_array(minted)},
      {"provider",
       {
           {"artifact_sha256", provider.artifact_sha256},
           {"id", provider.id},
           {"model_identity",
            model_identity_json(provider.model_identity)},
           {"version", provider.version},
       }},
      {"request",
       {
           {"capability", request.capability},
           {"data_classification", request.data_classification},
           {"inputs", binding_array(std::move(inputs))},
           {"parameters_sha256", std::move(parameters_sha256)},
           {"platform", request.platform},
           {"region", request.region},
           {"required_permissions", std::move(permissions)},
       }},
      {"started_at", std::move(started_at)},
      {"status", result.candidate.has_value() ? "succeeded" : "failed"},
  };
  const auto final_path =
      attempts_root / (result.attempt_id.value() + ".json");
  return write_new_atomic(
      final_path,
      foundation::canonical_json(encoded) + "\n",
      ErrorCode::duplicate_id);
}

Error invalid_provider_outcome() {
  return Error{
      ErrorCode::provider_failed,
      "provider returned an invalid terminal outcome",
  };
}

bool same_bindings(
    std::vector<ArtifactBinding> left,
    std::vector<ArtifactBinding> right) {
  sort_bindings(left);
  sort_bindings(right);
  return left == right;
}

bool valid_output_bindings(
    const std::vector<ArtifactBinding>& bindings,
    const std::vector<ArtifactPortDescriptor>& ports) {
  std::set<std::string> artifact_hashes;
  for (const auto& binding : bindings) {
    const auto* port = find_port(ports, binding.port);
    if (port == nullptr || !valid_artifact(binding.artifact) ||
        !media_type_allowed(*port, binding.artifact.media_type) ||
        !artifact_hashes.insert(binding.artifact.sha256).second) {
      return false;
    }
  }
  return std::all_of(
      ports.begin(), ports.end(), [&bindings](const auto& port) {
        const auto count = static_cast<std::size_t>(std::count_if(
            bindings.begin(),
            bindings.end(),
            [&port](const auto& binding) {
              return binding.port == port.name;
            }));
        const auto minimum = port.required ? std::size_t{1} : std::size_t{0};
        return count >= minimum && count <= port.max_count;
      });
}

foundation::Result<std::filesystem::path> existing_attempts_root(
    const std::filesystem::path& workspace_root) {
  if (workspace_root.empty() ||
      workspace_root.extension() == ".lmdj") {
    return foundation::Result<std::filesystem::path>::failure(
        invalid_argument(
            "workspace root must be a Host workspace parent, not a Project"));
  }
  const auto attempts =
      workspace_root / ".lmdj-workspace/attempts";
  for (const auto& directory : {
           workspace_root,
           workspace_root / ".lmdj-workspace",
           attempts,
       }) {
    std::error_code status_error;
    const auto status =
        std::filesystem::symlink_status(directory, status_error);
    if (status_error || std::filesystem::is_symlink(status) ||
        !std::filesystem::is_directory(status)) {
      return foundation::Result<std::filesystem::path>::failure(
          io_error(
              "Workspace directory is missing or unsafe",
              directory,
              status_error));
    }
  }
  return foundation::Result<std::filesystem::path>::success(attempts);
}

bool exact_keys(
    const nlohmann::json& value,
    std::initializer_list<std::string_view> expected) {
  if (!value.is_object() || value.size() != expected.size()) {
    return false;
  }
  return std::all_of(
      expected.begin(), expected.end(), [&value](const auto key) {
        return value.contains(std::string(key));
      });
}

bool exact_artifact_shape(const nlohmann::json& encoded) {
  return exact_keys(
      encoded, {"byte_length", "media_type", "sha256"});
}

bool exact_binding_shape(const nlohmann::json& encoded) {
  return exact_keys(encoded, {"artifact", "port"}) &&
         exact_artifact_shape(encoded.at("artifact"));
}

bool all_exact_shapes(
    const nlohmann::json& encoded,
    bool (*predicate)(const nlohmann::json&)) {
  return std::all_of(encoded.begin(), encoded.end(), predicate);
}

bool valid_semver(std::string_view value) {
  std::size_t start = 0;
  int components = 0;
  while (start <= value.size()) {
    const auto separator = value.find('.', start);
    const auto end =
        separator == std::string_view::npos ? value.size() : separator;
    if (end == start ||
        (end - start > 1 && value.at(start) == '0') ||
        !std::all_of(
            value.begin() + static_cast<std::ptrdiff_t>(start),
            value.begin() + static_cast<std::ptrdiff_t>(end),
            [](unsigned char character) {
              return std::isdigit(character) != 0;
            })) {
      return false;
    }
    ++components;
    if (separator == std::string_view::npos) {
      break;
    }
    start = separator + 1;
  }
  return components == 3;
}

std::optional<ErrorCode> parse_error_code(std::string_view value) {
  for (const auto code : {
           ErrorCode::invalid_argument,
           ErrorCode::not_found,
           ErrorCode::revision_conflict,
           ErrorCode::duplicate_id,
           ErrorCode::unsupported_audio,
           ErrorCode::missing_asset,
           ErrorCode::invalid_project,
           ErrorCode::cook_failed,
           ErrorCode::provider_not_found,
           ErrorCode::provider_failed,
           ErrorCode::permission_denied,
           ErrorCode::io_error,
           ErrorCode::internal_error,
       }) {
    if (foundation::error_code_name(code) == value) {
      return code;
    }
  }
  return std::nullopt;
}

foundation::Result<std::string> read_canonical_file(
    const std::filesystem::path& path) {
  std::error_code status_error;
  const auto status =
      std::filesystem::symlink_status(path, status_error);
  if (status_error || std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return foundation::Result<std::string>::failure(
        Error{
            ErrorCode::not_found,
            "terminal Attempt does not exist as a safe regular file",
            {{"path", path.generic_string()}},
        });
  }
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    return foundation::Result<std::string>::failure(
        io_error("terminal Attempt could not be opened", path));
  }
  auto bytes = std::string{
      std::istreambuf_iterator<char>(stream),
      std::istreambuf_iterator<char>(),
  };
  if (stream.bad()) {
    return foundation::Result<std::string>::failure(
        io_error("terminal Attempt could not be read", path));
  }
  return foundation::Result<std::string>::success(std::move(bytes));
}

std::vector<ArtifactRef> decode_artifacts(
    const nlohmann::json& encoded) {
  std::vector<ArtifactRef> artifacts;
  artifacts.reserve(encoded.size());
  for (const auto& artifact : encoded) {
    artifacts.push_back(artifact.get<ArtifactRef>());
  }
  return artifacts;
}

std::vector<ArtifactBinding> decode_bindings(
    const nlohmann::json& encoded) {
  std::vector<ArtifactBinding> bindings;
  bindings.reserve(encoded.size());
  for (const auto& binding : encoded) {
    bindings.push_back(binding.get<ArtifactBinding>());
  }
  return bindings;
}

}  // namespace

AttemptStore::AttemptStore(
    std::filesystem::path workspace_root,
    ProviderPolicy policy,
    TimestampSource timestamp_source)
    : workspace_root_(std::move(workspace_root)),
      policy_(std::move(policy)),
      timestamp_source_(std::move(timestamp_source)) {}

foundation::Result<void> AttemptStore::set_provider_selection(
    std::string capability,
    std::string provider_id,
    const Registry& registry) {
  const auto selected = registry.select(provider_id, capability);
  if (!selected.has_value()) {
    return foundation::Result<void>::failure(selected.error());
  }
  const auto workspace = prepare_workspace(workspace_root_);
  if (!workspace.has_value()) {
    return foundation::Result<void>::failure(workspace.error());
  }
  const std::lock_guard process_lock(host_settings_mutex);
  const auto lock_path =
      workspace.value() / ".host-settings.lock";
  const auto acquired = acquire_settings_lock(lock_path);
  if (!acquired.has_value()) {
    return acquired;
  }
  const auto settings_path = workspace.value() / "host-settings.json";
  const auto loaded = read_host_settings(settings_path, true);
  if (!loaded.has_value()) {
    const auto released = release_settings_lock(lock_path);
    if (!released.has_value()) {
      return released;
    }
    return foundation::Result<void>::failure(loaded.error());
  }
  auto settings = loaded.value();
  settings["provider_selections"][std::move(capability)] =
      std::move(provider_id);
  const auto written = write_replace_atomic(
      settings_path,
      foundation::canonical_json(settings) + "\n");
  const auto released = release_settings_lock(lock_path);
  if (!released.has_value()) {
    return released;
  }
  return written;
}

foundation::Result<std::string> AttemptStore::selected_provider(
    const std::string& capability) const {
  if (!valid_file_id(capability)) {
    return foundation::Result<std::string>::failure(
        invalid_argument("capability id is invalid"));
  }
  const auto attempts = existing_attempts_root(workspace_root_);
  if (!attempts.has_value()) {
    return foundation::Result<std::string>::failure(attempts.error());
  }
  const auto settings = read_host_settings(
      attempts.value().parent_path() / "host-settings.json", false);
  if (!settings.has_value()) {
    return foundation::Result<std::string>::failure(settings.error());
  }
  const auto& selections = settings.value().at("provider_selections");
  if (!selections.contains(capability) ||
      !selections.at(capability).is_string()) {
    return foundation::Result<std::string>::failure(
        Error{
            ErrorCode::provider_not_found,
            "provider selection is not configured for capability",
        });
  }
  const auto provider_id =
      selections.at(capability).get<std::string>();
  if (!valid_file_id(provider_id)) {
    return foundation::Result<std::string>::failure(
        invalid_argument("selected Provider id is invalid"));
  }
  return foundation::Result<std::string>::success(provider_id);
}

foundation::Result<TerminalAttempt> AttemptStore::inspect(
    foundation::AttemptId attempt_id) const {
  if (!valid_file_id(attempt_id.value())) {
    return foundation::Result<TerminalAttempt>::failure(
        invalid_argument("attempt id is not safe for inspection"));
  }
  const auto attempts = existing_attempts_root(workspace_root_);
  if (!attempts.has_value()) {
    return foundation::Result<TerminalAttempt>::failure(attempts.error());
  }
  const auto loaded = read_canonical_file(
      attempts.value() / (attempt_id.value() + ".json"));
  if (!loaded.has_value()) {
    return foundation::Result<TerminalAttempt>::failure(loaded.error());
  }
  try {
    const auto encoded = parse_bounded_or_throw(loaded.value());
    if (loaded.value() != foundation::canonical_json(encoded) + "\n" ||
        !exact_keys(
            encoded,
            {
                "artifacts",
                "attempt_id",
                "candidate_ids",
                "candidate_outputs",
                "capability",
                "ended_at",
                "error",
                "format",
                "minted_outputs",
                "provider",
                "request",
                "started_at",
                "status",
            }) ||
        encoded.at("format") != "terminal-attempt-v2" ||
        encoded.at("attempt_id") != attempt_id.value() ||
        !exact_keys(
            encoded.at("capability"),
            {"contract", "id", "version"}) ||
        encoded.at("capability").at("contract") !=
            "lmdj.capability.v2" ||
        !exact_keys(
            encoded.at("provider"),
            {
                "artifact_sha256",
                "id",
                "model_identity",
                "version",
            }) ||
        !exact_keys(
            encoded.at("request"),
            {
                "capability",
                "data_classification",
                "inputs",
                "parameters_sha256",
                "platform",
                "region",
                "required_permissions",
            }) ||
        !encoded.at("artifacts").is_array() ||
        !encoded.at("candidate_ids").is_array() ||
        !encoded.at("candidate_outputs").is_array() ||
        !encoded.at("minted_outputs").is_array() ||
        !encoded.at("request").at("inputs").is_array() ||
        !encoded.at("request").at("required_permissions").is_array() ||
        !all_exact_shapes(
            encoded.at("artifacts"), exact_artifact_shape) ||
        !all_exact_shapes(
            encoded.at("candidate_outputs"), exact_binding_shape) ||
        !all_exact_shapes(
            encoded.at("minted_outputs"), exact_binding_shape) ||
        !all_exact_shapes(
            encoded.at("request").at("inputs"), exact_binding_shape)) {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("terminal Attempt has an invalid private shape"));
    }

    const auto status_name = encoded.at("status").get<std::string>();
    AttemptStatus status;
    if (status_name == "succeeded") {
      status = AttemptStatus::succeeded;
    } else if (status_name == "failed") {
      status = AttemptStatus::failed;
    } else {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("Attempt record is not terminal"));
    }

    const auto provider_id =
        encoded.at("provider").at("id").get<std::string>();
    const auto provider_version =
        encoded.at("provider").at("version").get<std::string>();
    const auto provider_sha =
        encoded.at("provider").at("artifact_sha256").get<std::string>();
    std::optional<ModelIdentity> model_identity;
    const auto& encoded_model_identity =
        encoded.at("provider").at("model_identity");
    if (!encoded_model_identity.is_null()) {
      if (!exact_keys(
              encoded_model_identity,
              {"artifact_sha256", "id", "version"}) ||
          !encoded_model_identity.at("id").is_string() ||
          !encoded_model_identity.at("version").is_string() ||
          !encoded_model_identity.at("artifact_sha256").is_string()) {
        return foundation::Result<TerminalAttempt>::failure(
            invalid_argument(
                "terminal Attempt model identity is invalid"));
      }
      model_identity = ModelIdentity{
          encoded_model_identity.at("id").get<std::string>(),
          encoded_model_identity.at("version").get<std::string>(),
          encoded_model_identity.at("artifact_sha256").get<std::string>(),
      };
      if (!valid_file_id(model_identity->id) ||
          model_identity->version.empty() ||
          !valid_sha256(model_identity->artifact_sha256)) {
        return foundation::Result<TerminalAttempt>::failure(
            invalid_argument(
                "terminal Attempt model identity is invalid"));
      }
    }
    const auto capability_id =
        encoded.at("capability").at("id").get<std::string>();
    const auto capability_version =
        encoded.at("capability").at("version").get<std::string>();
    const auto parameters_sha =
        encoded.at("request")
            .at("parameters_sha256")
            .get<std::string>();
    const auto request_capability =
        encoded.at("request").at("capability").get<std::string>();
    const auto data_classification =
        encoded.at("request")
            .at("data_classification")
            .get<std::string>();
    const auto platform =
        encoded.at("request").at("platform").get<std::string>();
    const auto region =
        encoded.at("request").at("region").get<std::string>();
    const auto started_at =
        encoded.at("started_at").get<std::string>();
    const auto ended_at =
        encoded.at("ended_at").get<std::string>();
    if (!valid_file_id(provider_id) ||
        !valid_semver(provider_version) ||
        !valid_sha256(provider_sha) ||
        !valid_file_id(capability_id) ||
        !valid_semver(capability_version) ||
        !valid_sha256(parameters_sha) ||
        request_capability != capability_id ||
        data_classification.empty() || platform.empty() || region.empty() ||
        started_at.empty() || ended_at.empty()) {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("terminal Attempt identity is invalid"));
    }

    auto artifacts = decode_artifacts(encoded.at("artifacts"));
    auto inputs =
        decode_bindings(encoded.at("request").at("inputs"));
    auto minted_outputs =
        decode_bindings(encoded.at("minted_outputs"));
    auto candidate_outputs =
        decode_bindings(encoded.at("candidate_outputs"));
    if (!std::all_of(
            artifacts.begin(), artifacts.end(), valid_artifact) ||
        !std::all_of(
            inputs.begin(), inputs.end(), [](const auto& binding) {
              return valid_port_name(binding.port) &&
                     valid_artifact(binding.artifact);
            }) ||
        !std::all_of(
            minted_outputs.begin(),
            minted_outputs.end(),
            [](const auto& binding) {
              return valid_port_name(binding.port) &&
                     valid_artifact(binding.artifact);
            }) ||
        !std::all_of(
            candidate_outputs.begin(),
            candidate_outputs.end(),
            [](const auto& binding) {
              return valid_port_name(binding.port) &&
                     valid_artifact(binding.artifact);
            }) ||
        !std::is_sorted(inputs.begin(), inputs.end(), binding_less) ||
        !std::is_sorted(
            minted_outputs.begin(), minted_outputs.end(), binding_less) ||
        !std::is_sorted(
            candidate_outputs.begin(),
            candidate_outputs.end(),
            binding_less)) {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("terminal Attempt artifacts are invalid"));
    }
    auto candidate_ids =
        std::vector<foundation::CandidateId>{};
    for (const auto& candidate :
         encoded.at("candidate_ids")) {
      const auto value = candidate.get<std::string>();
      if (!valid_file_id(value)) {
        return foundation::Result<TerminalAttempt>::failure(
            invalid_argument("terminal Candidate id is invalid"));
      }
      candidate_ids.emplace_back(value);
    }
    auto permissions = encoded.at("request")
                           .at("required_permissions")
                           .get<std::vector<std::string>>();
    if (!unique_nonempty(permissions)) {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("terminal Attempt permissions are invalid"));
    }

    std::optional<Error> error;
    if (!encoded.at("error").is_null()) {
      const auto& encoded_error = encoded.at("error");
      if (!exact_keys(encoded_error, {"code", "details", "message"}) ||
          !encoded_error.at("details").is_object()) {
        return foundation::Result<TerminalAttempt>::failure(
            invalid_argument("terminal Attempt error is invalid"));
      }
      const auto code = parse_error_code(
          encoded_error.at("code").get<std::string>());
      const auto message =
          encoded_error.at("message").get<std::string>();
      if (!code.has_value() || message.empty()) {
        return foundation::Result<TerminalAttempt>::failure(
            invalid_argument("terminal Attempt error is invalid"));
      }
      error = Error{
          *code,
          message,
          encoded_error.at("details"),
      };
    }
    if ((status == AttemptStatus::succeeded &&
         (candidate_ids.empty() || error.has_value() ||
          !same_bindings(candidate_outputs, minted_outputs))) ||
        (status == AttemptStatus::failed &&
         (!candidate_ids.empty() || !error.has_value() ||
          !candidate_outputs.empty() || !minted_outputs.empty()))) {
      return foundation::Result<TerminalAttempt>::failure(
          invalid_argument("terminal Attempt outcome is inconsistent"));
    }

    return foundation::Result<TerminalAttempt>::success(
        TerminalAttempt{
            attempt_id,
            status,
            started_at,
            ended_at,
            AttemptProviderIdentity{
                provider_id,
                provider_version,
                provider_sha,
                std::move(model_identity),
            },
            AttemptCapabilityIdentity{
                capability_id,
                "lmdj.capability.v2",
                capability_version,
            },
            AttemptRequestMetadata{
                request_capability,
                std::move(inputs),
                parameters_sha,
                data_classification,
                platform,
                region,
                std::move(permissions),
            },
            std::move(candidate_ids),
            std::move(minted_outputs),
            std::move(candidate_outputs),
            std::move(artifacts),
            std::move(error),
        });
  } catch (const nlohmann::json::exception&) {
    return foundation::Result<TerminalAttempt>::failure(
        invalid_argument("terminal Attempt is not valid canonical JSON"));
  }
}

foundation::Result<AttemptResult> AttemptStore::execute(
    foundation::AttemptId attempt_id,
    const CapabilityRequest& request,
    const Registry& registry) {
  if (!valid_file_id(attempt_id.value())) {
    return foundation::Result<AttemptResult>::failure(
        invalid_argument("attempt id is not safe for persistence"));
  }
  const auto workspace = prepare_workspace(workspace_root_);
  if (!workspace.has_value()) {
    return foundation::Result<AttemptResult>::failure(workspace.error());
  }
  const auto attempts_root = workspace.value() / "attempts";
  const auto settings =
      read_host_settings(workspace.value() / "host-settings.json", false);
  if (!settings.has_value()) {
    return foundation::Result<AttemptResult>::failure(settings.error());
  }
  const auto& selections = settings.value().at("provider_selections");
  if (!selections.contains(request.capability) ||
      !selections.at(request.capability).is_string()) {
    return foundation::Result<AttemptResult>::failure(
        Error{
            ErrorCode::provider_not_found,
            "provider selection is not configured for capability",
        });
  }
  const auto provider_id =
      selections.at(request.capability).get<std::string>();
  const auto selected =
      registry.select(provider_id, request.capability);
  if (!selected.has_value()) {
    return foundation::Result<AttemptResult>::failure(selected.error());
  }
  const auto capability = selected_capability(
      selected.value().descriptor, request.capability);
  const auto parameters_hash = hash_parameters(request.parameters);
  if (!parameters_hash.has_value()) {
    return foundation::Result<AttemptResult>::failure(
        parameters_hash.error());
  }
  if (!timestamp_source_) {
    return foundation::Result<AttemptResult>::failure(
        invalid_argument("timestamp source is required"));
  }
  const auto started_at = timestamp_source_();

  std::vector<ArtifactBinding> minted;
  const auto request_error =
      validate_request(request, capability, policy_);
  const auto reservation =
      reserve_attempt(attempts_root, attempt_id);
  if (!reservation.has_value()) {
    return foundation::Result<AttemptResult>::failure(
        reservation.error());
  }
  const auto& attempt_root = reservation.value();
  AttemptResult terminal{
      attempt_id,
      std::nullopt,
      std::nullopt,
  };
  bool provider_invoked = false;
  if (!validation_passed(request_error)) {
    terminal.error = request_error;
  } else {
    const auto output = [
                            &attempt_root,
                            &capability,
                            &minted](
                            std::string port_name,
                            std::span<const std::byte> bytes,
                            std::string media_type)
        -> foundation::Result<ArtifactRef> {
      const auto* port = find_port(
          capability.output_artifacts, port_name);
      if (port == nullptr) {
        return foundation::Result<ArtifactRef>::failure(
            invalid_argument("output port is not declared by capability"));
      }
      if (!valid_media_type(media_type)) {
        return foundation::Result<ArtifactRef>::failure(
            invalid_argument("output media type is invalid"));
      }
      if (!media_type_allowed(*port, media_type)) {
        return foundation::Result<ArtifactRef>::failure(
            invalid_argument(
                "output media type is not declared by capability"));
      }
      if (bytes.size() > capability.max_output_bytes ||
          bytes.size() >
              static_cast<std::size_t>(
                  std::numeric_limits<std::streamsize>::max())) {
        return foundation::Result<ArtifactRef>::failure(
            invalid_argument("output exceeds capability limit"));
      }
      for (const auto& directory :
           {
               attempt_root / "staging",
               attempt_root / "staging/artifacts",
           }) {
        const auto ensured = ensure_directory(directory);
        if (!ensured.has_value()) {
          return foundation::Result<ArtifactRef>::failure(ensured.error());
        }
      }
      const auto temp_path =
          temporary_sibling(
              attempt_root / "staging/artifacts/output");
      const std::string_view payload{
          reinterpret_cast<const char*>(bytes.data()),
          bytes.size(),
      };
      const auto written =
          detail::write_bytes_durable(temp_path, payload);
      if (!written.has_value()) {
        return foundation::Result<ArtifactRef>::failure(written.error());
      }
      const auto described =
          foundation::describe_artifact(temp_path, std::move(media_type));
      if (!described.has_value()) {
        std::error_code cleanup_error;
        std::filesystem::remove(temp_path, cleanup_error);
        return foundation::Result<ArtifactRef>::failure(
            described.error());
      }
      if (std::any_of(
              minted.begin(),
              minted.end(),
              [&described](const auto& binding) {
                return binding.artifact.sha256 == described.value().sha256;
              })) {
        std::error_code cleanup_error;
        std::filesystem::remove(temp_path, cleanup_error);
        return foundation::Result<ArtifactRef>::failure(
            invalid_argument("output Artifact was already minted"));
      }
      const auto final_path =
          attempt_root / "staging/artifacts" /
          described.value().sha256;
      std::error_code final_status_error;
      const auto final_status =
          std::filesystem::symlink_status(final_path, final_status_error);
      if (final_status_error &&
          final_status_error !=
              std::make_error_code(
                  std::errc::no_such_file_or_directory)) {
        std::error_code cleanup_error;
        std::filesystem::remove(temp_path, cleanup_error);
        return foundation::Result<ArtifactRef>::failure(
            io_error(
                "output artifact destination could not be inspected",
                final_path,
                final_status_error));
      }
      if (!final_status_error &&
          final_status.type() !=
              std::filesystem::file_type::not_found) {
        if (std::filesystem::is_symlink(final_status) ||
            !std::filesystem::is_regular_file(final_status)) {
          std::error_code cleanup_error;
          std::filesystem::remove(temp_path, cleanup_error);
          return foundation::Result<ArtifactRef>::failure(
              io_error("output artifact destination is unsafe", final_path));
        }
        const auto existing = foundation::describe_artifact(
            final_path, described.value().media_type);
        if (!existing.has_value() ||
            existing.value() != described.value()) {
          std::error_code cleanup_error;
          std::filesystem::remove(temp_path, cleanup_error);
          return foundation::Result<ArtifactRef>::failure(
              io_error(
                  "existing output artifact does not match its hash",
                  final_path));
        }
        std::error_code cleanup_error;
        std::filesystem::remove(temp_path, cleanup_error);
      } else {
        const auto published =
            detail::publish_replace(temp_path, final_path);
        if (!published.has_value()) {
          return foundation::Result<ArtifactRef>::failure(published.error());
        }
      }
      minted.push_back(ArtifactBinding{
          std::move(port_name),
          described.value(),
      });
      return foundation::Result<ArtifactRef>::success(described.value());
    };

    try {
      provider_invoked = true;
      terminal = selected.value().implementation->run(
          attempt_id, request, output);
    } catch (...) {
      terminal = AttemptResult{
          attempt_id,
          std::nullopt,
          Error{
              ErrorCode::provider_failed,
              "provider execution failed",
          },
      };
    }

    const bool exactly_one =
        terminal.candidate.has_value() != terminal.error.has_value();
    bool valid = exactly_one && terminal.attempt_id == attempt_id;
    if (valid && terminal.error.has_value()) {
      valid =
          terminal.error->code == ErrorCode::provider_failed &&
          minted.empty();
    }
    if (valid && terminal.candidate.has_value()) {
      valid =
          valid_file_id(terminal.candidate->id.value()) &&
          valid_output_bindings(
              terminal.candidate->outputs,
              capability.output_artifacts) &&
          same_bindings(terminal.candidate->outputs, minted);
    }
    if (!valid) {
      terminal = AttemptResult{
          attempt_id,
          std::nullopt,
          invalid_provider_outcome(),
      };
    } else if (terminal.candidate.has_value()) {
      terminal.candidate->provenance = {
          {"capability", capability.id},
          {"contract", "lmdj.capability.v2"},
          {"contract_version", capability.contract_version},
          {"model_identity",
           model_identity_json(
               selected.value().descriptor.model_identity)},
          {"provider",
           {
               {"artifact_sha256",
                selected.value().descriptor.artifact_sha256},
               {"id", selected.value().descriptor.id},
               {"version", selected.value().descriptor.version},
           }},
      };
    }
  }

  if (terminal.candidate.has_value()) {
    if (minted.empty()) {
      const auto cleaned = cleanup_attempt_outputs(attempt_root);
      if (!cleaned.has_value()) {
        return foundation::Result<AttemptResult>::failure(
            cleaned.error());
      }
    } else {
      const auto published = publish_attempt_outputs(attempt_root);
      if (!published.has_value()) {
        const auto cleaned = remove_tree(
            attempt_root, "Attempt reservation cleanup failed");
        if (!cleaned.has_value()) {
          return foundation::Result<AttemptResult>::failure(
              cleaned.error());
        }
        return foundation::Result<AttemptResult>::failure(
            published.error());
      }
    }
  } else {
    const auto cleaned = cleanup_attempt_outputs(attempt_root);
    if (!cleaned.has_value()) {
      return foundation::Result<AttemptResult>::failure(
          cleaned.error());
    }
    minted.clear();
  }

  terminal.attempt_id = attempt_id;
  const auto ended_at = timestamp_source_();
  const auto persisted = persist_attempt(
      attempts_root,
      selected.value().descriptor,
      capability,
      request,
      terminal,
      parameters_hash.value(),
      started_at,
      ended_at,
      minted,
      provider_invoked);
  if (!persisted.has_value()) {
    const auto cleaned = remove_tree(
        attempt_root, "Attempt reservation cleanup failed");
    if (!cleaned.has_value()) {
      return foundation::Result<AttemptResult>::failure(
          cleaned.error());
    }
    return foundation::Result<AttemptResult>::failure(persisted.error());
  }
  if (!terminal.candidate.has_value()) {
    const auto released = remove_tree(
        attempt_root, "Attempt reservation cleanup failed");
    if (!released.has_value()) {
      return foundation::Result<AttemptResult>::failure(
          released.error());
    }
  }
  return foundation::Result<AttemptResult>::success(std::move(terminal));
}

}  // namespace lmdj::provider
