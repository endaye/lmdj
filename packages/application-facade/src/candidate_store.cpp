#include <lmdj/facade/candidate_store.hpp>

#include <algorithm>
#include <limits>
#include <map>
#include <random>
#include <set>
#include <span>
#include <stdexcept>
#include <string_view>

#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/json.hpp>

namespace lmdj::facade::detail {
namespace {
using Json = nlohmann::json;
using foundation::Error;
using foundation::ErrorCode;
template <class T> using Result = foundation::Result<T>;
constexpr std::uint64_t kMaximumStateBytes = 64 * 1024 * 1024;

Error invalid(std::string message) {
  return {ErrorCode::invalid_argument, std::move(message),
          {{"reason", "candidate_state_invalid"}}};
}
Error busy() {
  return {ErrorCode::invalid_argument, "Workspace Candidate mutation is busy",
          {{"reason", "job_busy"}}};
}
void check(bool condition) {
  if (!condition) throw std::invalid_argument("Invalid Workspace Candidate state");
}
Json parse_unique(std::string_view bytes) {
  std::map<int, std::set<std::string>> objects;
  bool valid = true;
  auto parsed = Json::parse(bytes.begin(), bytes.end(),
      [&](int depth, Json::parse_event_t event, Json& value) {
        if ((event == Json::parse_event_t::object_start ||
             event == Json::parse_event_t::array_start) &&
            depth >= foundation::kMaximumJsonContainerDepth) {
          valid = false; return false;
        }
        if (event == Json::parse_event_t::object_start) objects[depth + 1].clear();
        if (event == Json::parse_event_t::key &&
            !objects[depth].insert(value.get<std::string>()).second) valid = false;
        return true;
      }, false);
  check(valid && !parsed.is_discarded());
  return parsed;
}
bool keys(const Json& value, std::initializer_list<std::string_view> names) {
  return value.is_object() && value.size() == names.size() &&
      std::all_of(names.begin(), names.end(), [&](auto name) { return value.contains(std::string(name)); });
}
bool id(const std::string& value) {
  return !value.empty() && value.size() <= 128 &&
      std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
      }) && value != "." && value != "..";
}
bool digest(const Json& value) {
  if (!value.is_string()) return false;
  const auto& text = value.get_ref<const std::string&>();
  return text.size() == 64 && std::all_of(text.begin(), text.end(), [](char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
  });
}
bool integer(const Json& value) {
  return value.is_number_unsigned() || (value.is_number_integer() && value.get<std::int64_t>() >= 0);
}
void validate_artifact(const Json& value) {
  check(keys(value, {"sha256", "media_type", "byte_length"}));
  check(digest(value.at("sha256")) && value.at("media_type").is_string() &&
        !value.at("media_type").get_ref<const std::string&>().empty() && integer(value.at("byte_length")));
}
void validate_source(const Json& source) {
  check(keys(source, {"project_path", "project_id", "asset_id", "project_revision",
                      "artifact", "frame_rate", "frame_count"}));
  const auto path = std::filesystem::path(source.at("project_path").get<std::string>());
  check(path.is_absolute() && path.lexically_normal() == path);
  check(domain::is_valid_uuid(source.at("project_id").get<std::string>()) &&
        domain::is_valid_uuid(source.at("asset_id").get<std::string>()));
  check(integer(source.at("project_revision")) && integer(source.at("frame_rate")) &&
        integer(source.at("frame_count")));
  check(source.at("frame_rate") == 44100 || source.at("frame_rate") == 48000);
  check(source.at("frame_count").get<std::uint64_t>() > 0 &&
        source.at("frame_count").get<std::uint64_t>() <= 8388608);
  validate_artifact(source.at("artifact"));
  check(source.at("artifact").at("media_type") == "audio/wav" &&
        source.at("artifact").at("byte_length").get<std::uint64_t>() <= 16777216);
}
void validate_intent(const Json& intent) {
  check(keys(intent, {"attempt_id", "source", "parameters_sha256", "data_classification",
                      "platform", "region", "required_permissions"}));
  check(id(intent.at("attempt_id").get<std::string>()));
  validate_source(intent.at("source"));
  check(digest(intent.at("parameters_sha256")));
  for (const auto* field : {"data_classification", "platform", "region"})
    check(id(intent.at(field).get<std::string>()));
  check(intent.at("required_permissions").is_array());
  std::set<std::string> permissions;
  for (const auto& permission : intent.at("required_permissions"))
    check(id(permission.get<std::string>()) && permissions.insert(permission.get<std::string>()).second);
}
std::string allocate_id() {
  std::random_device source;
  constexpr char hex[] = "0123456789abcdef";
  std::string value(32, '0');
  for (auto& c : value) c = hex[source() & 15U];
  return value;
}
std::shared_ptr<std::mutex> process_mutex(const std::filesystem::path& path) {
  static std::mutex guard;
  static std::map<std::string, std::weak_ptr<std::mutex>> locks;
  std::lock_guard lock(guard);
  auto& weak = locks[path.generic_string()];
  auto shared = weak.lock();
  if (!shared) { shared = std::make_shared<std::mutex>(); weak = shared; }
  return shared;
}

Json expand(const Json& entry, const provider::TerminalAttempt& terminal,
            const std::vector<std::byte>& bytes) {
  const auto& intent = entry.at("intent");
  const auto& source = intent.at("source");
  const auto artifact = source.at("artifact").get<foundation::ArtifactRef>();
  check(terminal.capability.id == "sample.slice.v1" &&
        terminal.capability.contract == "lmdj.capability.v2" && terminal.capability.version == "1.0.0");
  check(terminal.request.capability == "sample.slice.v1" && terminal.request.inputs.size() == 1 &&
        terminal.request.inputs[0].port == "source_audio" && terminal.request.inputs[0].artifact == artifact);
  check(terminal.attempt_id.value() == intent.at("attempt_id").get<std::string>() &&
        terminal.request.parameters_sha256 == intent.at("parameters_sha256").get<std::string>() &&
        terminal.request.data_classification == intent.at("data_classification").get<std::string>() &&
        terminal.request.platform == intent.at("platform").get<std::string>() && terminal.request.region == intent.at("region").get<std::string>());
  auto permissions = terminal.request.required_permissions;
  auto expected = intent.at("required_permissions").get<std::vector<std::string>>();
  std::sort(permissions.begin(), permissions.end()); std::sort(expected.begin(), expected.end());
  check(permissions == expected);
  check(terminal.candidate_ids.size() == 1 && terminal.candidate_outputs.size() == 1 &&
        terminal.candidate_outputs[0].port == "slice_points" &&
        terminal.candidate_outputs[0].artifact.media_type == "application/json");
  const auto output = parse_unique(
      std::string_view(reinterpret_cast<const char*>(bytes.data()), bytes.size()));
  check(keys(output, {"contract", "source_sha256", "frame_rate", "points"}));
  check(output.at("contract") == "lmdj.slice-points.v1" &&
        output.at("source_sha256") == artifact.sha256 &&
        integer(output.at("frame_rate")) && output.at("frame_rate") == source.at("frame_rate") &&
        output.at("points").is_array() && output.at("points").size() <= 4096);
  std::vector<std::uint64_t> boundaries{0};
  const auto frames = source.at("frame_count").get<std::uint64_t>();
  std::optional<std::uint64_t> prior;
  for (const auto& point : output.at("points")) {
    check(point.is_object() && point.contains("frame") && integer(point.at("frame")));
    for (const auto& [key, value] : point.items()) {
      check(key == "frame" || key == "confidence" || key == "label");
      if (key == "confidence") check(value.is_number() && value >= 0 && value <= 1);
      if (key == "label") check(value.is_string() && !value.get_ref<const std::string&>().empty() &&
          value.get_ref<const std::string&>().size() <= 128 && foundation::valid_utf8(value.get_ref<const std::string&>()));
    }
    const auto frame = point.at("frame").get<std::uint64_t>();
    check(frame < frames && (!prior || frame > *prior));
    prior = frame;
    if (frame != 0) boundaries.push_back(frame);
  }
  Json recipes = Json::array();
  if (!output.at("points").empty()) {
    boundaries.push_back(frames);
    for (std::size_t i = 1; i < boundaries.size(); ++i) {
      recipes.push_back({{"candidate_id", entry.at("set_id").get<std::string>() + "." + std::to_string(i - 1)},
          {"kind", "slice_interval_v1"}, {"start_frame", boundaries[i - 1]},
          {"end_frame", boundaries[i]}, {"frame_rate", source.at("frame_rate")}});
    }
  }
  Json model = nullptr;
  if (terminal.provider.model_identity) {
    const auto& identity = *terminal.provider.model_identity;
    model = {{"id", identity.id}, {"version", identity.version}, {"artifact_sha256", identity.artifact_sha256}};
  }
  return {{"set_id", entry.at("set_id")}, {"status", "active"},
      {"attempt_id", terminal.attempt_id.value()}, {"sdk_candidate_id", terminal.candidate_ids[0].value()},
      {"source", source}, {"output_artifact", terminal.candidate_outputs[0].artifact},
      {"capability", {{"id", terminal.capability.id}, {"contract", terminal.capability.contract},
                       {"version", terminal.capability.version}}},
      {"provider", {{"id", terminal.provider.id}, {"version", terminal.provider.version},
                     {"artifact_sha256", terminal.provider.artifact_sha256}}},
      {"model_identity", model}, {"parameters_sha256", terminal.request.parameters_sha256},
      {"recipes", std::move(recipes)}};
}
}  // namespace

CandidateStore::CandidateStore(std::filesystem::path workspace_root,
    std::shared_ptr<project_io::ProjectStoragePlatform> platform)
    : root_(std::move(workspace_root) / ".lmdj-host/candidates"), platform_(std::move(platform)) {
  if (!root_.is_absolute() || root_ != root_.lexically_normal() || !platform_)
    throw std::invalid_argument("Candidate Workspace requires a normalized absolute root and storage");
}
Result<CandidateStore::Lease> CandidateStore::acquire(const std::filesystem::path& path) const {
  auto mutex = process_mutex(path);
  std::unique_lock lock(*mutex, std::try_to_lock);
  if (!lock.owns_lock()) return Result<Lease>::failure(busy());
  auto acquired = platform_->acquire_writer(path);
  if (!acquired.has_value()) {
    auto error = acquired.error();
    if (error.details.value("storage_condition", "") == project_io::kStorageConditionProjectBusy)
      error = busy();
    return Result<Lease>::failure(std::move(error));
  }
  return Result<Lease>::success(Lease{std::move(mutex), std::move(lock), std::move(acquired.value())});
}
Result<Json> CandidateStore::read_state() const {
  const auto exists = platform_->exists(root_ / "state.json");
  if (!exists.has_value()) return Result<Json>::failure(exists.error());
  if (!exists.value()) return Result<Json>::success({{"format", "slice-candidate-store-v1"},
      {"jobs", Json::object()}, {"sets", Json::object()}});
  const auto length = platform_->byte_length(root_ / "state.json");
  if (!length.has_value()) return Result<Json>::failure(length.error());
  if (length.value() > kMaximumStateBytes) return Result<Json>::failure(invalid("Candidate state exceeds read bound"));
  const auto bytes = platform_->read_complete(root_ / "state.json");
  if (!bytes.has_value()) return Result<Json>::failure(bytes.error());
  try {
    check(bytes.value().size() == length.value() && bytes.value().size() <= kMaximumStateBytes);
    const auto state = parse_unique(std::string_view(
        reinterpret_cast<const char*>(bytes.value().data()), bytes.value().size()));
    check(keys(state, {"format", "jobs", "sets"}) && state.at("format") == "slice-candidate-store-v1" &&
          state.at("jobs").is_object() && state.at("sets").is_object());
    std::set<std::string> attempts, sets;
    for (const auto& [job_id, job] : state.at("jobs").items()) {
      check(id(job_id) && keys(job, {"history", "active_set_id"}) && job.at("history").is_array());
      unsigned pending = 0;
      for (const auto& entry : job.at("history")) {
        check(keys(entry, {"intent", "set_id", "status"}));
        validate_intent(entry.at("intent"));
        check(attempts.insert(entry.at("intent").at("attempt_id").get<std::string>()).second);
        check(id(entry.at("set_id").get<std::string>()) && sets.insert(entry.at("set_id").get<std::string>()).second);
        const auto status = entry.at("status").get<std::string>();
        check(status == "pending" || status == "succeeded" || status == "failed" || status == "interrupted");
        if (status == "pending") ++pending;
        if (status == "succeeded") {
          const auto& set = state.at("sets").at(entry.at("set_id").get<std::string>());
          check(set.at("source") == entry.at("intent").at("source") &&
                set.at("attempt_id") == entry.at("intent").at("attempt_id") &&
                set.at("parameters_sha256") == entry.at("intent").at("parameters_sha256"));
          check((set.at("status") == "active") == (job.at("active_set_id") == entry.at("set_id")));
        }
        else check(!state.at("sets").contains(entry.at("set_id").get<std::string>()));
      }
      check(pending <= 1);
      if (!job.at("active_set_id").is_null()) {
        const auto active = job.at("active_set_id").get<std::string>();
        check(state.at("sets").contains(active) && state.at("sets").at(active).at("status") == "active");
        check(std::any_of(job.at("history").begin(), job.at("history").end(),
                         [&](const auto& e) { return e.at("set_id") == active && e.at("status") == "succeeded"; }));
      }
    }
    for (const auto& [set_id, set] : state.at("sets").items()) {
      check(keys(set, {"set_id", "status", "attempt_id", "sdk_candidate_id", "source",
                       "output_artifact", "capability", "provider", "model_identity",
                       "parameters_sha256", "recipes"}));
      check(sets.contains(set_id) && set.at("set_id") == set_id);
      check(set.at("status") == "active" || set.at("status") == "superseded");
      validate_source(set.at("source")); validate_artifact(set.at("output_artifact"));
      check(set.at("recipes").is_array() && set.at("recipes").size() <= 4097);
    }
    return Result<Json>::success(state);
  } catch (const std::exception&) { return Result<Json>::failure(invalid("Candidate state is malformed or inconsistent")); }
}
Result<void> CandidateStore::write_state(const Json& state) {
  const auto bytes = foundation::canonical_json(state) + "\n";
  if (bytes.size() > kMaximumStateBytes) return Result<void>::failure(invalid("Candidate state exceeds write bound"));
  const auto ensured = platform_->ensure_directory(root_);
  if (!ensured.has_value()) return ensured;
  return platform_->replace_complete(root_ / "state.json", std::as_bytes(std::span{bytes.data(), bytes.size()}));
}
Result<CandidateStore::Run> CandidateStore::begin(const std::string& job_id, const Json& intent) {
  try { check(id(job_id)); validate_intent(intent); }
  catch (const std::exception&) { return Result<Run>::failure(invalid("Candidate Job intent is invalid")); }
  auto execution = acquire(root_ / "jobs" / job_id);
  if (!execution.has_value()) return Result<Run>::failure(execution.error());
  auto mutation = acquire(root_);
  if (!mutation.has_value()) return Result<Run>::failure(mutation.error());
  auto loaded = read_state();
  if (!loaded.has_value()) return Result<Run>::failure(loaded.error());
  auto& state = loaded.value();
  for (const auto& job : state.at("jobs")) for (const auto& entry : job.at("history"))
    if (entry.at("intent").at("attempt_id") == intent.at("attempt_id").get<std::string>())
      return Result<Run>::failure(invalid("Attempt ID already belongs to a Candidate Job"));
  if (!state["jobs"].contains(job_id)) state["jobs"][job_id] = {{"history", Json::array()}, {"active_set_id", nullptr}};
  auto& job = state["jobs"][job_id];
  for (const auto& entry : job.at("history")) if (entry.at("status") == "pending")
    return Result<Run>::failure(busy()); // caller must inspect/recover the old intent first
  std::string set_id;
  do { set_id = allocate_id(); } while (state.at("sets").contains(set_id));
  job["history"].push_back({{"intent", intent}, {"set_id", set_id}, {"status", "pending"}});
  const auto saved = write_state(state);
  if (!saved.has_value()) return Result<Run>::failure(saved.error());
  return Result<Run>::success(Run{std::move(execution.value()), job_id, intent.at("attempt_id").get<std::string>()});
}
Result<void> CandidateStore::reconcile(Json& state, Json& entry, const provider::AttemptStore& attempts) {
  if (entry.at("status") != "pending") return Result<void>::success();
  const auto inspected = attempts.inspect(foundation::AttemptId{entry.at("intent").at("attempt_id").get<std::string>()});
  if (!inspected.has_value()) {
    if (inspected.error().code != ErrorCode::not_found) return Result<void>::failure(inspected.error());
    entry["status"] = "interrupted";
    return Result<void>::success();
  }
  const auto& terminal = inspected.value();
  if (terminal.status == provider::AttemptStatus::failed) {
    entry["status"] = "failed"; return Result<void>::success();
  }
  if (terminal.candidate_outputs.size() != 1) return Result<void>::failure(invalid("Slice terminal output cardinality changed"));
  auto bytes = attempts.read_candidate_artifact(terminal.attempt_id, terminal.candidate_outputs[0].artifact, 262144);
  if (!bytes.has_value()) return Result<void>::failure(bytes.error());
  try {
    auto set = expand(entry, terminal, bytes.value());
    state["sets"][entry.at("set_id").get<std::string>()] = std::move(set);
    entry["status"] = "succeeded";
    return Result<void>::success();
  } catch (const std::exception&) { return Result<void>::failure(invalid("Slice terminal does not match its recorded Job intent")); }
}
Result<void> CandidateStore::verify_sets(const Json& state, const std::string& job_id,
                                         const provider::AttemptStore& attempts) const {
  try {
    for (const auto& entry : state.at("jobs").at(job_id).at("history")) {
      if (entry.at("status") != "succeeded") continue;
      const auto terminal = attempts.inspect(foundation::AttemptId{
          entry.at("intent").at("attempt_id").get<std::string>()});
      if (!terminal.has_value()) return Result<void>::failure(terminal.error());
      check(terminal.value().candidate_outputs.size() == 1);
      const auto bytes = attempts.read_candidate_artifact(terminal.value().attempt_id,
          terminal.value().candidate_outputs[0].artifact, 262144);
      if (!bytes.has_value()) return Result<void>::failure(bytes.error());
      auto expected = expand(entry, terminal.value(), bytes.value());
      const auto& actual = state.at("sets").at(entry.at("set_id").get<std::string>());
      expected["status"] = actual.at("status");
      check(expected == actual);
    }
    return Result<void>::success();
  } catch (const std::exception&) {
    return Result<void>::failure(invalid("Candidate Set differs from its verified terminal output"));
  }
}
Json CandidateStore::view(const Json& state, const std::string& job_id) const {
  const auto& job = state.at("jobs").at(job_id);
  Json sets = Json::array();
  for (const auto& entry : job.at("history")) {
    const auto set_id = entry.at("set_id").get<std::string>();
    if (state.at("sets").contains(set_id)) sets.push_back(state.at("sets").at(set_id));
  }
  return {{"job_id", job_id}, {"history", job.at("history")},
      {"active_set_id", job.at("active_set_id")}, {"sets", std::move(sets)}};
}
Result<Json> CandidateStore::finish(const Run& run, const provider::AttemptStore& attempts) {
  auto mutation = acquire(root_);
  if (!mutation.has_value()) return Result<Json>::failure(mutation.error());
  auto loaded = read_state();
  if (!loaded.has_value()) return loaded;
  auto& state = loaded.value();
  if (!state["jobs"].contains(run.job_id)) return Result<Json>::failure(invalid("Job is missing"));
  auto& job = state["jobs"][run.job_id];
  auto found = std::find_if(job["history"].begin(), job["history"].end(),
      [&](const auto& e) { return e.at("intent").at("attempt_id") == run.attempt_id; });
  if (found == job["history"].end()) return Result<Json>::failure(invalid("Job Attempt is missing"));
  if (found->at("status") == "pending") {
    const auto reconciled = reconcile(state, *found, attempts);
    if (!reconciled.has_value()) return Result<Json>::failure(reconciled.error());
    if (found->at("status") == "succeeded") {
      if (!job.at("active_set_id").is_null())
        state["sets"][job.at("active_set_id").get<std::string>()]["status"] = "superseded";
      job["active_set_id"] = found->at("set_id");
    }
    const auto saved = write_state(state);
    if (!saved.has_value()) return Result<Json>::failure(saved.error());
  }
  return Result<Json>::success(view(state, run.job_id));
}
Result<CandidateStore::Eligibility> CandidateStore::lease_active(
    const std::string& job_id, const std::string& set_id, const provider::AttemptStore& attempts) {
  if (!id(job_id) || !id(set_id)) return Result<Eligibility>::failure(invalid("Job or Set ID is invalid"));
  auto mutation = acquire(root_);
  if (!mutation.has_value()) return Result<Eligibility>::failure(mutation.error());
  auto loaded = read_state();
  if (!loaded.has_value()) return Result<Eligibility>::failure(loaded.error());
  const auto& state = loaded.value();
  if (!state.at("jobs").contains(job_id) ||
      state.at("jobs").at(job_id).at("active_set_id") != set_id)
    return Result<Eligibility>::failure(Error{ErrorCode::not_found,
        "Candidate Set is unavailable", {{"reason", "candidate_unavailable"}}});
  const auto verified = verify_sets(state, job_id, attempts);
  if (!verified.has_value()) return Result<Eligibility>::failure(verified.error());
  return Result<Eligibility>::success(Eligibility{
      std::move(mutation.value()), state.at("sets").at(set_id)});
}
Result<Json> CandidateStore::inspect(const std::string& job_id, const provider::AttemptStore& attempts) {
  if (!id(job_id)) return Result<Json>::failure(invalid("Job ID is invalid"));
  // A live execution retains this same lease across Provider execution. Recovery
  // may inspect its intent but must not mark it interrupted or publish it early.
  auto execution = acquire(root_ / "jobs" / job_id);
  std::optional<std::string> pending;
  {
    auto mutation = acquire(root_);
    if (!mutation.has_value()) return Result<Json>::failure(mutation.error());
    auto loaded = read_state();
    if (!loaded.has_value()) return loaded;
    const auto& state = loaded.value();
    if (!state.at("jobs").contains(job_id)) return Result<Json>::failure(
        Error{ErrorCode::not_found, "Candidate Job does not exist", {{"reason", "job_not_found"}}});
    const auto verified = verify_sets(state, job_id, attempts);
    if (!verified.has_value()) return Result<Json>::failure(verified.error());
    if (!execution.has_value()) {
      if (execution.error().details.value("reason", "") != "job_busy") return Result<Json>::failure(execution.error());
      return Result<Json>::success(view(state, job_id));
    }
    for (const auto& entry : state.at("jobs").at(job_id).at("history"))
      if (entry.at("status") == "pending") pending = entry.at("intent").at("attempt_id").get<std::string>();
    if (!pending) return Result<Json>::success(view(state, job_id));
  }
  Run run{std::move(execution.value()), job_id, *pending};
  return finish(run, attempts);
}
}  // namespace lmdj::facade::detail
