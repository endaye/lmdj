#include <lmdj/project_io/sequence_journal.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <charconv>
#include <iterator>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/json.hpp>

#include "sequence_admission_codec.hpp"
#include "testing_hooks.hpp"

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

struct RecordingProtocol {
  std::string_view name;
  std::string_view journal_contract;
  std::string_view recovery_contract;
  std::string_view active_filename;
  std::string_view sealed_name_marker;
  std::string_view torn_reason;
  std::string_view torn_message;
  std::string_view torn_remedy;
  bool tail_while_switching;
  bool tail_while_flush_pending;
  bool cumulative_flushes;
  std::uint64_t completion_revision_step;
};

constexpr RecordingProtocol kSequenceProtocol{
    "Sequence",
    "lmdj.sequence.journal.v3",
    "lmdj.sequence.recovery.v3",
    "sequence.jsonl",
    "",
    "sequence_journal_torn_tail",
    "active Sequence Journal has a torn trailing record",
    "retain the journal; repair the invalid suffix or discard the recovery "
    "journal explicitly",
    true,
    true,
    true,
    1,
};

constexpr RecordingProtocol kPerformanceProtocol{
    "Performance",
    "lmdj.performance.journal.v1",
    "lmdj.performance.recovery.v1",
    "performance.jsonl",
    "-performance",
    "performance_journal_torn_tail",
    "active Performance Journal has a torn trailing record",
    "retain the journal; repair the invalid record or discard the recovery "
    "journal explicitly",
    false,
    false,
    false,
    1,
};

constexpr const RecordingProtocol& recording_protocol(SessionKind kind) {
  return kind == SessionKind::sequence ? kSequenceProtocol
                                       : kPerformanceProtocol;
}

constexpr SessionKind other_session_kind(SessionKind kind) {
  return kind == SessionKind::sequence ? SessionKind::performance
                                       : SessionKind::sequence;
}

constexpr std::string_view session_kind_string(SessionKind kind) {
  return kind == SessionKind::sequence ? "sequence" : "performance";
}

bool recording_accepts_tail_state(
    SessionKind kind,
    SequenceSessionState state) {
  return state == SequenceSessionState::active ||
         (recording_protocol(kind).tail_while_switching &&
          state == SequenceSessionState::switching);
}

template <typename FlushRange>
bool recording_accepts_tail(
    SessionKind kind,
    SequenceSessionState state,
    const FlushRange& flushes) {
  return recording_accepts_tail_state(kind, state) &&
         (recording_protocol(kind).tail_while_flush_pending ||
          std::ranges::none_of(
              flushes,
              [](const auto& flush) { return !flush.completed; }));
}

template <typename FlushRange>
bool recording_accepts_flush(
    SessionKind kind,
    SequenceSessionState state,
    const FlushRange& flushes) {
  return state == SequenceSessionState::active &&
         (recording_protocol(kind).cumulative_flushes ||
          std::ranges::none_of(
              flushes,
              [](const auto& flush) { return !flush.completed; }));
}

bool recording_completion_revision_is_valid(
    SessionKind kind,
    std::uint64_t expected_revision,
    std::uint64_t committed_revision) {
  return committed_revision ==
         expected_revision +
             recording_protocol(kind).completion_revision_step;
}

template <typename FlushRange>
bool recording_command_is_new(
    const FlushRange& flushes,
    const foundation::CommandId& command_id) {
  return std::ranges::none_of(
      flushes,
      [&command_id](const auto& flush) {
        return flush.command_id == command_id;
      });
}

template <typename Journal>
struct RecordingJournalDocument {
  Journal journal;
  std::uint64_t valid_prefix_length{};
};

// Sequence-only parse metadata; never a durability or ACK receipt.
struct JournalDocument {
  ActiveSequenceJournal journal;
  std::uint64_t valid_prefix_length{};
  std::size_t admission_candidate_bytes{};
};
using PerformanceJournalDocument =
    RecordingJournalDocument<ActivePerformanceJournal>;

// This is a parsing checkpoint, never a write, durability or ACK receipt.
// Every reuse compares a fresh complete read byte-for-byte with this exact
// validated prefix. One private entry per reader thread keeps ownership local
// and leaves the public Journal layout and storage contract unchanged.
constexpr std::size_t kSequenceParsePrefixBytes = 1024U * 1024U;
// Whole Project bytes and the facts checked by validate_admission_project.
// These share the existing raw-byte bound with the Sequence parsing prefix.
struct SequenceProjectParsePrefix {
  std::string manifest_bytes;
  std::string checkpoint_bytes;
  std::string checkpoint_path;
  std::string project_id;
};
struct SequenceParsePrefix {
  const ProjectStoragePlatform* platform;
  std::filesystem::path path;
  std::string bytes;
  JournalDocument document;
  std::size_t admission_candidate_bytes{};
  std::shared_ptr<const SequenceProjectParsePrefix> project_parse_prefix;
};
thread_local std::shared_ptr<const SequenceParsePrefix> sequence_parse_prefix;

struct SequenceParseRead {
  bool enabled;
  bool successful{};
  ~SequenceParseRead() {
    if (enabled && !successful) {
      sequence_parse_prefix.reset();
    }
  }
};

template <typename Source>
nlohmann::json parse_bounded_or_throw(Source&& source) {
  auto parsed = foundation::parse_bounded_json(std::forward<Source>(source));
  if (!parsed.has_value()) {
    throw std::runtime_error(
        "JSON is malformed or exceeds the maximum container depth");
  }
  return std::move(*parsed);
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

foundation::Result<std::string> read_complete_text(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& path, bool use_text_reader = true) {
  const auto* reader = use_text_reader
      ? dynamic_cast<const ProjectStorageTextReader*>(&platform) : nullptr;
  if (reader != nullptr) {
    return reader->read_complete_text(path);
  }
  auto bytes = platform.read_complete(path);
  if (!bytes.has_value()) {
    return foundation::Result<std::string>::failure(bytes.error());
  }
  return foundation::Result<std::string>::success(byte_string(bytes.value()));
}

std::string sha256(std::string_view bytes) {
  picosha2::hash256_one_by_one hasher;
  hasher.process(bytes.begin(), bytes.end());
  hasher.finish();
  return picosha2::get_hash_hex_string(hasher);
}

bool lowercase_sha256(std::string_view value) {
  return value.size() == 64 &&
         std::all_of(
             value.begin(), value.end(), [](unsigned char character) {
               return (character >= '0' && character <= '9') ||
                      (character >= 'a' && character <= 'f');
             });
}

bool valid_bars(std::uint8_t bars) {
  return bars == 1 || bars == 2 || bars == 4 || bars == 8;
}

template <typename T> T sequence_integer(const nlohmann::json& input) {
  if (!(input.is_number_unsigned() ||
        (input.is_number_integer() && input.get<std::int64_t>() >= 0)) ||
      input.get<std::uint64_t>() > std::numeric_limits<T>::max()) {
    throw std::runtime_error("Sequence integer is negative, fractional or out of range");
  }
  return static_cast<T>(input.get<std::uint64_t>());
}

std::filesystem::path recording_active_path(
    const std::filesystem::path& bundle,
    SessionKind kind) {
  return bundle / "recovery/active" /
         recording_protocol(kind).active_filename;
}

std::filesystem::path performance_owner_lock_path(
    const std::filesystem::path& bundle) {
  return bundle / "recovery/active/performance.lock";
}

foundation::Result<void> remove_performance_owner_lock(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle) {
  const auto path = performance_owner_lock_path(bundle);
  auto exists = platform->exists(path);
  if (!exists.has_value()) {
    return foundation::Result<void>::failure(exists.error());
  }
  if (!exists.value()) {
    return foundation::Result<void>::success();
  }
  auto removed = platform->remove(path);
  if (!removed.has_value() && removed.error().details.is_object() &&
      removed.error().details.value("storage_condition", std::string{}) ==
          kStorageConditionProjectBusy) {
    // OPFS cannot unlink a lock file while the current process still has its
    // access handle open. The path is reusable runtime metadata: after the
    // terminal Journal transition, its advisory lock remains the authority
    // until the owning ProjectStore releases that handle.
    return foundation::Result<void>::success();
  }
  return removed;
}

foundation::Result<void> validate_journal_tree(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto validated = platform.validate_managed_tree(bundle);
  if (!validated.has_value()) {
    return validated;
  }
  const std::array required{
      bundle,
      bundle / "assets",
      bundle / "history",
      bundle / "history/checkpoints",
      bundle / "history/transactions",
      bundle / "recovery",
      bundle / "recovery/active",
      bundle / "recovery/sealed",
  };
  for (const auto& directory : required) {
    const auto present = platform.directory_exists(directory);
    if (!present.has_value() || !present.value()) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_project,
              "Sequence Journal managed directory is missing or invalid",
              {{"path", directory.generic_string()}},
          });
    }
  }
  const auto manifest = platform.byte_length(bundle / "manifest.json");
  if (!manifest.has_value()) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence Journal Project manifest is missing or invalid",
            {{"path", (bundle / "manifest.json").generic_string()}},
        });
  }
  return foundation::Result<void>::success();
}

nlohmann::json slot_json(domain::PadSlotId slot) {
  return {{"bank", slot.bank}, {"pad", slot.pad}};
}

std::optional<domain::PadSlotId> optional_slot(
    const nlohmann::json& input,
    std::string_view key) {
  const auto found = input.find(std::string{key});
  if (found == input.end() || found->is_null()) {
    return std::nullopt;
  }
  if (!found->is_object() || found->size() != 2 ||
      !found->contains("bank") || !found->contains("pad") ||
      !found->at("bank").is_number_unsigned() ||
      !found->at("pad").is_number_unsigned()) {
    throw std::runtime_error("armed Capture slot shape is invalid");
  }
  const auto bank = found->at("bank").get<std::uint64_t>();
  const auto pad = found->at("pad").get<std::uint64_t>();
  if (bank > 255 || pad > 255) {
    throw std::runtime_error("armed Capture slot is invalid");
  }
  const domain::PadSlotId slot{
      static_cast<std::uint8_t>(bank),
      static_cast<std::uint8_t>(pad),
  };
  if (!domain::is_valid_slot(slot)) {
    throw std::runtime_error("armed Capture slot is invalid");
  }
  return slot;
}

nlohmann::json event_json(const domain::PatternEvent& event) {
  return {
      {"duration_tick", event.duration_tick},
      {"onset_tick", event.onset_tick},
      {"slot", slot_json(event.slot)},
      {"velocity", event.velocity},
  };
}

foundation::Result<domain::PatternEvent> parse_event(
    const nlohmann::json& input,
    std::uint32_t loop_length,
    const std::filesystem::path& path) {
  try {
    if (!input.is_object() || input.size() != 4 ||
        !input.contains("slot") || !input.contains("onset_tick") ||
        !input.contains("duration_tick") || !input.contains("velocity")) {
      throw std::runtime_error("event shape is invalid");
    }
    const auto& slot = input.at("slot");
    domain::PatternEvent event{
        domain::PadSlotId{
            sequence_integer<std::uint8_t>(slot.at("bank")),
            sequence_integer<std::uint8_t>(slot.at("pad")),
        },
        sequence_integer<std::uint32_t>(input.at("onset_tick")),
        sequence_integer<std::uint32_t>(input.at("duration_tick")),
        sequence_integer<std::uint8_t>(input.at("velocity")),
    };
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 || event.onset_tick >= loop_length ||
        event.duration_tick < 1 ||
        event.duration_tick > loop_length - event.onset_tick) {
      throw std::runtime_error("event value is outside Project v3 bounds");
    }
    return foundation::Result<domain::PatternEvent>::success(event);
  } catch (const std::exception& exception) {
    return foundation::Result<domain::PatternEvent>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence Journal event is invalid",
            {{"path", path.generic_string()}, {"detail", exception.what()}},
        });
  }
}

std::string state_string(SequenceSessionState state) {
  switch (state) {
    case SequenceSessionState::active:
      return "active";
    case SequenceSessionState::switching:
      return "switching";
    case SequenceSessionState::stopped:
      return "stopped";
    case SequenceSessionState::recovery_required:
      return "recovery_required";
    case SequenceSessionState::owner_lost:
      return "owner_lost";
    case SequenceSessionState::abandoned:
      return "abandoned";
  }
  throw std::logic_error("unhandled Sequence session state");
}

SequenceSessionState parse_state(std::string_view value) {
  if (value == "active") {
    return SequenceSessionState::active;
  }
  if (value == "switching") {
    return SequenceSessionState::switching;
  }
  if (value == "stopped") {
    return SequenceSessionState::stopped;
  }
  if (value == "recovery_required") {
    return SequenceSessionState::recovery_required;
  }
  if (value == "owner_lost") {
    return SequenceSessionState::owner_lost;
  }
  if (value == "abandoned") {
    return SequenceSessionState::abandoned;
  }
  throw std::runtime_error("Sequence session state is invalid");
}

nlohmann::json checked_record(nlohmann::json payload) {
  const auto encoded = foundation::canonical_json(payload);
  return {
      {"checksum", sha256(encoded)},
      {"payload", std::move(payload)},
  };
}

Error corrupt_record_error(
    const std::filesystem::path& path,
    std::size_t record_offset,
    std::size_t observed_length,
    std::string_view reason,
    std::string message) {
  return Error{
      ErrorCode::invalid_project,
      std::move(message),
      {
          {"durable_prefix_length", record_offset},
          {"journal_retained", true},
          {"observed_length", observed_length},
          {"path", path.generic_string()},
          {"reason", reason},
          {"record_offset", record_offset},
          {"remedy",
           "retain the journal; repair the invalid record or discard the "
           "recovery journal explicitly"},
      },
  };
}

foundation::Result<nlohmann::json> checked_payload(
    const nlohmann::json& record,
    const std::filesystem::path& path,
    std::size_t record_offset,
    std::size_t observed_length) {
  try {
    if (!record.is_object() || record.size() != 2 ||
        !record.contains("checksum") || !record.contains("payload")) {
      return foundation::Result<nlohmann::json>::failure(
          corrupt_record_error(
              path,
              record_offset,
              observed_length,
              "sequence_journal_record_envelope_invalid",
              "Sequence Journal record envelope is invalid"));
    }
    const auto checksum = record.at("checksum").get<std::string>();
    const auto encoded = foundation::canonical_json(record.at("payload"));
    if (!lowercase_sha256(checksum) || sha256(encoded) != checksum) {
      return foundation::Result<nlohmann::json>::failure(
          corrupt_record_error(
              path,
              record_offset,
              observed_length,
              "sequence_journal_checksum_mismatch",
              "Sequence Journal checksum does not match its canonical payload"));
    }
    return foundation::Result<nlohmann::json>::success(record.at("payload"));
  } catch (const std::exception& exception) {
    (void)exception;
    return foundation::Result<nlohmann::json>::failure(
        corrupt_record_error(
            path,
            record_offset,
            observed_length,
            "sequence_journal_record_envelope_invalid",
            "Sequence Journal record envelope is invalid"));
  }
}

struct CheckedJournalRecord {
  nlohmann::json payload;
  std::size_t offset{};
};

struct CheckedJournalRecords {
  std::vector<CheckedJournalRecord> records;
  std::uint64_t valid_prefix_length{};
  std::size_t observed_length{};
  std::shared_ptr<const SequenceParsePrefix> reused_sequence_prefix;
  std::string sequence_bytes;
};

foundation::Result<CheckedJournalRecords> read_checked_journal_records(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    SessionKind session_kind) {
  SequenceParseRead prefix_read{session_kind == SessionKind::sequence};
  const auto* layout = session_kind == SessionKind::sequence
                           ? dynamic_cast<const ProjectJournalLayoutValidator*>(
                                 &platform)
                           : nullptr;
  auto tree = layout != nullptr ? layout->validate_journal_layout(bundle)
                                : validate_journal_tree(platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<CheckedJournalRecords>::failure(tree.error());
  }
  const auto& protocol = recording_protocol(session_kind);
  const auto path = recording_active_path(bundle, session_kind);
  auto exists = platform.exists(path);
  if (!exists.has_value()) {
    return foundation::Result<CheckedJournalRecords>::failure(exists.error());
  }
  if (!exists.value()) {
    return foundation::Result<CheckedJournalRecords>::failure(Error{
        ErrorCode::not_found,
        "active " + std::string{protocol.name} + " Journal does not exist",
        {{"path", path.generic_string()}},
    });
  }
  // Performance retains its original byte-vector read path.
  auto read = read_complete_text(platform, path, session_kind == SessionKind::sequence);
  if (!read.has_value()) {
    return foundation::Result<CheckedJournalRecords>::failure(read.error());
  }
  auto bytes = std::move(read.value());
  CheckedJournalRecords checked{{}, 0, bytes.size(), {}, {}};
  std::size_t cursor = 0;
  if (session_kind == SessionKind::sequence && sequence_parse_prefix) {
    const auto prefix = sequence_parse_prefix;
    if (prefix->platform == &platform && prefix->path == path &&
        bytes.size() >= prefix->bytes.size() &&
        std::equal(prefix->bytes.begin(), prefix->bytes.end(), bytes.begin())) {
      checked.reused_sequence_prefix = prefix;
      cursor = prefix->bytes.size();
      checked.valid_prefix_length = cursor;
    } else {
      // Truncation, a rewritten prefix or a different owner/path requires the
      // original full checker. A same-length edit is not an append.
      sequence_parse_prefix.reset();
    }
  }
  while (cursor < bytes.size()) {
    const auto record_offset = cursor;
    const auto line_end = bytes.find('\n', cursor);
    if (line_end == std::string::npos) {
      return foundation::Result<CheckedJournalRecords>::failure(
          Error{
              ErrorCode::invalid_project,
              std::string{protocol.torn_message},
              {{"durable_prefix_length", cursor},
               {"journal_retained", true},
               {"observed_length", bytes.size()},
               {"path", path.generic_string()},
               {"reason", protocol.torn_reason},
               {"record_offset", cursor},
               {"remedy", protocol.torn_remedy}},
          });
    }
    const auto line = bytes.substr(cursor, line_end - cursor);
    cursor = line_end + 1;
    checked.valid_prefix_length = cursor;
    if (line.empty()) {
      continue;
    }
    try {
      if (session_kind == SessionKind::sequence) admission_codec::preflight(line);
      const auto envelope = parse_bounded_or_throw(line);
      auto payload = checked_payload(
          envelope, path, record_offset, bytes.size());
      if (!payload.has_value()) {
        return foundation::Result<CheckedJournalRecords>::failure(
            payload.error());
      }
      checked.records.push_back(
          {std::move(payload.value()), record_offset});
    } catch (const std::exception& exception) {
      (void)exception;
      return foundation::Result<CheckedJournalRecords>::failure(
          corrupt_record_error(
              path,
              record_offset,
              bytes.size(),
              session_kind == SessionKind::sequence
                  ? "sequence_journal_record_invalid"
                  : "performance_journal_record_invalid",
              "active " + std::string{protocol.name} +
                  " Journal record is invalid"));
    }
  }
  if (session_kind == SessionKind::sequence &&
      bytes.size() <= kSequenceParsePrefixBytes) {
    checked.sequence_bytes = std::move(bytes);
  }
  prefix_read.successful = true;
  return foundation::Result<CheckedJournalRecords>::success(
      std::move(checked));
}

nlohmann::json flush_json(const SequenceFlushRecord& flush) {
  auto events = nlohmann::json::array();
  for (const auto& event : flush.canonical_events) {
    events.push_back(event_json(event));
  }
  return {
      {"command_id", flush.command_id.value()},
      {"events", std::move(events)},
      {"expected_revision", flush.expected_revision},
      {"flush_seq", flush.flush_seq},
      {"kind", "flush"},
      {"payload_version", 2},
      {"pattern_id", flush.pattern_id.value()},
  };
}

nlohmann::json events_json(std::span<const domain::PatternEvent> events) {
  auto encoded = nlohmann::json::array();
  for (const auto& event : events) {
    encoded.push_back(event_json(event));
  }
  return encoded;
}

nlohmann::json tail_json(
    const ActiveSequenceJournal& journal,
    std::uint64_t input_sequence,
    std::span<const domain::PatternEvent> events) {
  return {
      {"events", events_json(events)},
      {"expected_revision", journal.expected_revision},
      {"input_sequence", input_sequence},
      {"kind", "tail"},
      {"pattern_id", journal.pattern_id.value()},
      {"tail_seq", journal.next_tail_seq},
  };
}

std::vector<domain::PatternEvent> unresolved_batch(
    const ActiveSequenceJournal& journal) {
  std::vector<domain::PatternEvent> result;
  for (const auto& flush : journal.flushes) {
    if (!flush.completed) {
      result = domain::merge_pattern_events(result, flush.recovery_events);
    }
  }
  return domain::merge_pattern_events(result, journal.pending_events);
}

bool same_event_key(
    const domain::PatternEvent& left,
    const domain::PatternEvent& right) noexcept {
  return left.slot == right.slot && left.onset_tick == right.onset_tick;
}

bool covers_event_keys(
    std::span<const domain::PatternEvent> committed,
    std::span<const domain::PatternEvent> candidate) {
  return std::ranges::all_of(candidate, [committed](const auto& event) {
    return std::ranges::any_of(committed, [&event](const auto& visible) {
      return same_event_key(visible, event);
    });
  });
}

std::vector<domain::PatternEvent> uncommitted_residual(
    std::span<const domain::PatternEvent> committed,
    std::span<const domain::PatternEvent> candidate) {
  std::vector<domain::PatternEvent> residual;
  std::ranges::copy_if(
      candidate,
      std::back_inserter(residual),
      [committed](const auto& event) {
        return std::ranges::find(committed, event) == committed.end();
      });
  return residual;
}

nlohmann::json capture_json(const SequenceCaptureCommit& capture) {
  return {
      {"artifact", capture.artifact},
      {"asset_id", capture.asset_id.value()},
      {"command_id", capture.command_id.value()},
      {"expected_revision", capture.expected_revision},
      {"kind", "capture-prepare"},
      {"slot", slot_json(capture.slot)},
  };
}

SequenceCaptureCommit parse_capture(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  if (!input.is_object()) {
    throw std::runtime_error("armed Capture commit shape is invalid");
  }
  const auto slot = optional_slot(input, "slot");
  SequenceCaptureCommit capture{
      foundation::CommandId{input.at("command_id").get<std::string>()},
      foundation::AssetId{input.at("asset_id").get<std::string>()},
      slot.value_or(domain::PadSlotId{}),
      input.at("artifact").get<foundation::ArtifactRef>(),
      input.at("expected_revision").get<std::uint64_t>(),
  };
  if (!slot.has_value() ||
      !domain::is_valid_uuid(capture.command_id.value()) ||
      !domain::is_valid_uuid(capture.asset_id.value()) ||
      !domain::is_valid_slot(capture.slot) ||
      !lowercase_sha256(capture.artifact.sha256) ||
      capture.artifact.media_type.empty()) {
    throw std::runtime_error(
        "armed Capture commit identity is invalid at " +
        path.generic_string());
  }
  return capture;
}

nlohmann::json journal_json(const ActiveSequenceJournal& journal) {
  auto flushes = nlohmann::json::array();
  for (const auto& flush : journal.flushes) {
    auto encoded = flush_json(flush);
    encoded["completed"] = flush.completed;
    encoded["recovery_events"] = events_json(flush.recovery_events);
    flushes.push_back(std::move(encoded));
  }
  return {
      {"admission", journal.admission
          ? admission_codec::encode(*journal.admission) : nlohmann::json(nullptr)},
      {"armed_capture_slot",
       journal.armed_capture_slot.has_value()
           ? nlohmann::json(slot_json(*journal.armed_capture_slot))
           : nlohmann::json(nullptr)},
      {"bars", journal.bars},
      {"capture_commit",
       journal.capture_commit.has_value()
           ? nlohmann::json(capture_json(*journal.capture_commit))
           : nlohmann::json(nullptr)},
      {"expected_revision", journal.expected_revision},
      {"flushes", std::move(flushes)},
      {"last_input_sequence",
       journal.last_input_sequence.has_value()
           ? nlohmann::json(*journal.last_input_sequence)
           : nlohmann::json(nullptr)},
      {"next_flush_seq", journal.next_flush_seq},
      {"next_tail_seq", journal.next_tail_seq},
      {"pattern_fingerprint", journal.pattern_fingerprint},
      {"pattern_id", journal.pattern_id.value()},
      {"pending_events", events_json(journal.pending_events)},
      {"session_id", journal.session_id.value()},
      {"state", state_string(journal.state)},
  };
}

foundation::Result<ActiveSequenceJournal> parse_journal_snapshot(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    ActiveSequenceJournal journal{
        foundation::SequenceSessionId{
            input.at("session_id").get<std::string>()},
        foundation::PatternId{input.at("pattern_id").get<std::string>()},
        sequence_integer<std::uint8_t>(input.at("bars")),
        input.at("pattern_fingerprint").get<std::string>(),
        sequence_integer<std::uint64_t>(input.at("expected_revision")),
        sequence_integer<std::uint64_t>(input.at("next_flush_seq")),
        parse_state(input.at("state").get<std::string>()),
        {},
        std::nullopt,
        std::nullopt,
        0,
        std::nullopt,
        {},
    };
    (void)input.at("armed_capture_slot");
    journal.armed_capture_slot = optional_slot(input, "armed_capture_slot");
    const auto& capture = input.at("capture_commit");
    if (!capture.is_null()) {
      journal.capture_commit = parse_capture(capture, path);
    }
    if (!domain::is_valid_uuid(journal.session_id.value()) ||
        !domain::is_valid_uuid(journal.pattern_id.value()) ||
        !valid_bars(journal.bars) ||
        !lowercase_sha256(journal.pattern_fingerprint)) {
      throw std::runtime_error("recovery metadata is invalid");
    }
    const auto loop_length = domain::pattern_length_ticks(journal.bars);
    journal.next_tail_seq = sequence_integer<std::uint64_t>(input.at("next_tail_seq"));
    if (!input.at("last_input_sequence").is_null()) {
      journal.last_input_sequence =
          sequence_integer<std::uint64_t>(input.at("last_input_sequence"));
    }
    if (!input.at("pending_events").is_array() || !input.at("flushes").is_array()) {
      throw std::runtime_error("recovery event and flush fields must be arrays");
    }
    {
      for (const auto& encoded : input.at("pending_events")) {
        auto parsed = parse_event(encoded, loop_length, path);
        if (!parsed.has_value()) {
          return foundation::Result<ActiveSequenceJournal>::failure(
              parsed.error());
        }
        journal.pending_events.push_back(parsed.value());
      }
      if (domain::merge_pattern_events({}, journal.pending_events) !=
          journal.pending_events) {
        throw std::runtime_error("recovery tail is not canonical");
      }
    }
    for (const auto& encoded : input.at("flushes")) {
      if (!encoded.is_object() || encoded.size() != 9 ||
          encoded.at("kind") != "flush" || !encoded.at("events").is_array() ||
          !encoded.at("recovery_events").is_array()) {
        throw std::runtime_error("recovery flush record grammar is invalid");
      }
      SequenceFlushRecord flush{
          sequence_integer<std::uint64_t>(encoded.at("flush_seq")),
          foundation::CommandId{encoded.at("command_id").get<std::string>()},
          foundation::PatternId{encoded.at("pattern_id").get<std::string>()},
          sequence_integer<std::uint64_t>(encoded.at("expected_revision")),
          {},
          {},
          encoded.at("completed").get<bool>(),
      };
      if (!domain::is_valid_uuid(flush.command_id.value()) ||
          !domain::is_valid_uuid(flush.pattern_id.value())) {
        throw std::runtime_error("recovery flush identity is invalid");
      }
      for (const auto& event : encoded.at("events")) {
        auto parsed = parse_event(event, loop_length, path);
        if (!parsed.has_value()) {
          return foundation::Result<ActiveSequenceJournal>::failure(
              parsed.error());
        }
        flush.canonical_events.push_back(parsed.value());
      }
      const auto payload_version =
          sequence_integer<std::uint64_t>(encoded.at("payload_version"));
      if (payload_version != 2) {
        throw std::runtime_error("recovery flush payload version is invalid");
      }
      if (payload_version == 2 && !encoded.contains("recovery_events")) {
        throw std::runtime_error(
            "recovery flush v2 is missing its effective residual");
      }
      const auto& recovery_events = encoded.at("recovery_events");
      for (const auto& event : recovery_events) {
        auto parsed = parse_event(event, loop_length, path);
        if (!parsed.has_value()) {
          return foundation::Result<ActiveSequenceJournal>::failure(
              parsed.error());
        }
        flush.recovery_events.push_back(parsed.value());
      }
      if (domain::merge_pattern_events({}, flush.canonical_events) !=
              flush.canonical_events ||
          domain::merge_pattern_events({}, flush.recovery_events) !=
              flush.recovery_events ||
          !std::ranges::all_of(
              flush.recovery_events,
              [&flush](const auto& event) {
                return std::ranges::find(flush.canonical_events, event) !=
                       flush.canonical_events.end();
              })) {
        throw std::runtime_error(
            "recovery flush payload or residual is invalid");
      }
      journal.flushes.push_back(std::move(flush));
    }
    if (!input.at("admission").is_null()) {
      journal.admission = admission_codec::snapshot(input.at("admission"), journal);
    }
    return foundation::Result<ActiveSequenceJournal>::success(
        std::move(journal));
  } catch (const std::exception& exception) {
    return foundation::Result<ActiveSequenceJournal>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence recovery payload is invalid and has been retained",
            {
                {"detail", exception.what()},
                {"path", path.generic_string()},
                {"reason", "sequence_recovery_payload_invalid"},
                {"recovery_retained", true},
                {"remedy",
                 "retain the recovery file; repair its versioned payload or "
                 "discard this recovery candidate explicitly"},
            },
        });
  }
}

foundation::Result<void> validate_admission_project(
    const ProjectStoragePlatform& platform, const std::filesystem::path& bundle,
    const foundation::ProjectId& project_id,
    const std::shared_ptr<const SequenceProjectParsePrefix>& parsed_prefix = {},
    std::size_t project_raw_budget = 0,
    std::shared_ptr<const SequenceProjectParsePrefix>* validated_prefix = nullptr) {
  SequenceParseRead project_read{true};
  if (validated_prefix) validated_prefix->reset();
  // A retained Project node must fit beside the actual fresh Journal bytes.
  // The other callers supply no parsing prefix and remain cold.
  const bool can_reuse = parsed_prefix &&
      parsed_prefix->manifest_bytes.size() <= project_raw_budget &&
      parsed_prefix->checkpoint_bytes.size() <=
          project_raw_budget - parsed_prefix->manifest_bytes.size();
  auto read = read_complete_text(platform, bundle / "manifest.json");
  if (!read.has_value()) return foundation::Result<void>::failure(read.error());
  try {
    const std::string_view manifest_bytes{read.value()};
    const bool reused_manifest = can_reuse &&
        manifest_bytes == std::string_view{parsed_prefix->manifest_bytes};
    std::string checkpoint;
    if (reused_manifest) {
      checkpoint = parsed_prefix->checkpoint_path;
    } else {
      const auto manifest = parse_bounded_or_throw(manifest_bytes);
      if (manifest.at("contract") != "lmdj.project.manifest.v1" ||
          !manifest.at("head_revision").is_number_unsigned()) {
        throw std::runtime_error("invalid admission Project manifest");
      }
      checkpoint = std::string{"history/checkpoints/"} +
          std::to_string(manifest.at("head_revision").get<std::uint64_t>()) + ".json";
      if (manifest.at("head_checkpoint") != checkpoint) {
        throw std::runtime_error("invalid admission Project checkpoint path");
      }
    }
    // Always read the currently derived path, even when the manifest matched.
    auto state = read_complete_text(platform, bundle / checkpoint);
    if (!state.has_value()) return foundation::Result<void>::failure(state.error());
    const std::string_view checkpoint_bytes{state.value()};
    const bool reused_checkpoint = can_reuse &&
        checkpoint == parsed_prefix->checkpoint_path &&
        checkpoint_bytes == std::string_view{parsed_prefix->checkpoint_bytes};
    if (reused_checkpoint) {
      // The current caller's Project identity is checked on every read.
      if (parsed_prefix->project_id != project_id.value()) {
        throw std::runtime_error("admission Project identity mismatch");
      }
    } else {
      const auto data = parse_bounded_or_throw(checkpoint_bytes);
      if (data.at("project_id") != project_id.value()) {
        throw std::runtime_error("admission Project identity mismatch");
      }
    }
    if (validated_prefix && manifest_bytes.size() <= project_raw_budget &&
        checkpoint_bytes.size() <= project_raw_budget - manifest_bytes.size()) {
      if (reused_manifest && reused_checkpoint) {
        *validated_prefix = parsed_prefix;
      } else {
        try {
          *validated_prefix = std::make_shared<const SequenceProjectParsePrefix>(
              SequenceProjectParsePrefix{
                  std::string{manifest_bytes}, std::string{checkpoint_bytes},
                  std::move(checkpoint), project_id.value()});
        } catch (...) {
          // Optional parse metadata allocation is not Project validation.
          validated_prefix->reset();
        }
      }
    }
    project_read.successful = true;
    return foundation::Result<void>::success();
  } catch (const std::exception& e) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_project, e.what(), {{"journal_retained", true}}});
  }
}

foundation::Result<JournalDocument> read_journal(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  SequenceParseRead prefix_read{true};
  auto checked = read_checked_journal_records(
      platform, bundle, SessionKind::sequence);
  if (!checked.has_value()) {
    return foundation::Result<JournalDocument>::failure(checked.error());
  }
  const auto path = recording_active_path(bundle, SessionKind::sequence);
  JournalDocument document = checked.value().reused_sequence_prefix
      ? checked.value().reused_sequence_prefix->document
      : JournalDocument{
          ActiveSequenceJournal{
              foundation::SequenceSessionId{""},
              foundation::PatternId{""},
              0,
              {},
              0,
              0,
              SequenceSessionState::active,
              {},
              std::nullopt,
              std::nullopt,
              0,
              std::nullopt,
              {},
          },
          checked.value().valid_prefix_length,
      };
  document.valid_prefix_length = checked.value().valid_prefix_length;
  std::size_t record_offset = 0;
  std::string_view record_reason = "sequence_journal_record_invalid";
  std::string record_message = "active Sequence Journal record is invalid";
  bool saw_begin = checked.value().reused_sequence_prefix != nullptr;
  std::size_t admission_candidate_bytes = saw_begin
      ? checked.value().reused_sequence_prefix->admission_candidate_bytes
      : 0;
  try {
    for (const auto& record : checked.value().records) {
      record_offset = record.offset;
      record_reason = "sequence_journal_record_invalid";
      record_message = "active Sequence Journal record is invalid";
      auto payload = foundation::Result<nlohmann::json>::success(
          record.payload);
      const auto kind = payload.value().at("kind").get<std::string>();
      if (!saw_begin) {
        if (kind != "begin" ||
            payload.value().at("contract") !=
                recording_protocol(SessionKind::sequence).journal_contract) {
          throw std::runtime_error("first record is not a Sequence begin");
        }
        document.journal = ActiveSequenceJournal{
            foundation::SequenceSessionId{
                payload.value().at("session_id").get<std::string>()},
            foundation::PatternId{
                payload.value().at("pattern_id").get<std::string>()},
            sequence_integer<std::uint8_t>(payload.value().at("bars")),
            payload.value().at("pattern_fingerprint").get<std::string>(),
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision")),
            0,
            SequenceSessionState::active,
            {},
            std::nullopt,
            std::nullopt,
            0,
            std::nullopt,
            {},
        };
        document.journal.armed_capture_slot =
            optional_slot(payload.value(), "armed_capture_slot");
        if (!domain::is_valid_uuid(document.journal.session_id.value()) ||
            !domain::is_valid_uuid(document.journal.pattern_id.value()) ||
            !valid_bars(document.journal.bars) ||
            !lowercase_sha256(document.journal.pattern_fingerprint)) {
          throw std::runtime_error("Sequence begin metadata is invalid");
        }
        saw_begin = true;
      } else if (kind.starts_with("admission-")) {
        if (!admission_codec::apply(document.journal, payload.value(), &admission_candidate_bytes)) {
          throw std::runtime_error("duplicate durable admission record");
        }
      } else if (kind == "tail") {
        if (document.journal.admission && !document.journal.admission->completed) {
          throw std::runtime_error("direct tail bypasses admission");
        }
        record_reason = "sequence_journal_tail_identity_invalid";
        record_message =
            "Sequence Journal tail identity is not monotonic or session-bound";
        const auto tail_seq =
            sequence_integer<std::uint64_t>(payload.value().at("tail_seq"));
        const auto input_sequence =
            sequence_integer<std::uint64_t>(payload.value().at("input_sequence"));
        const auto pattern_id = foundation::PatternId{
            payload.value().at("pattern_id").get<std::string>()};
        const auto expected_revision =
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision"));
        if (tail_seq != document.journal.next_tail_seq ||
            (document.journal.last_input_sequence.has_value() &&
             input_sequence <= *document.journal.last_input_sequence) ||
            pattern_id != document.journal.pattern_id ||
            expected_revision != document.journal.expected_revision ||
            !recording_accepts_tail(
                document.journal.kind,
                document.journal.state,
                document.journal.flushes)) {
          throw std::runtime_error("Sequence tail identity is invalid");
        }
        std::vector<domain::PatternEvent> pending_events;
        record_reason = "sequence_journal_tail_not_canonical";
        record_message =
            "Sequence Journal tail event order is not canonical";
        const auto loop_length =
            domain::pattern_length_ticks(document.journal.bars);
        if (!payload.value().at("events").is_array()) {
          throw std::runtime_error("Sequence tail events must be an array");
        }
        for (const auto& encoded : payload.value().at("events")) {
          auto parsed = parse_event(encoded, loop_length, path);
          if (!parsed.has_value()) {
            return foundation::Result<JournalDocument>::failure(parsed.error());
          }
          pending_events.push_back(parsed.value());
        }
        if (pending_events.empty() ||
            domain::merge_pattern_events({}, pending_events) != pending_events) {
          throw std::runtime_error("Sequence tail events are not canonical");
        }
        document.journal.pending_events = std::move(pending_events);
        document.journal.last_input_sequence = input_sequence;
        ++document.journal.next_tail_seq;
      } else if (kind == "flush") {
        const auto payload_version =
            sequence_integer<std::uint64_t>(payload.value().at("payload_version"));
        SequenceFlushRecord flush{
            sequence_integer<std::uint64_t>(payload.value().at("flush_seq")),
            foundation::CommandId{
                payload.value().at("command_id").get<std::string>()},
            foundation::PatternId{
                payload.value().at("pattern_id").get<std::string>()},
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision")),
            {},
            {},
            false,
        };
        if (admission_codec::blocks_flush(document.journal) ||
            document.journal.capture_commit.has_value() ||
            flush.flush_seq != document.journal.next_flush_seq ||
            !recording_accepts_flush(
                document.journal.kind,
                document.journal.state,
                document.journal.flushes) ||
            payload_version != 2 ||
            !domain::is_valid_uuid(flush.command_id.value()) ||
            !recording_command_is_new(
                document.journal.flushes, flush.command_id) ||
            !domain::is_valid_uuid(flush.pattern_id.value()) ||
            flush.pattern_id != document.journal.pattern_id) {
          throw std::runtime_error("Sequence flush identity is invalid");
        }
        const auto loop_length =
            domain::pattern_length_ticks(document.journal.bars);
        if (!payload.value().at("events").is_array()) {
          throw std::runtime_error("Sequence flush events must be an array");
        }
        for (const auto& encoded : payload.value().at("events")) {
          auto parsed = parse_event(encoded, loop_length, path);
          if (!parsed.has_value()) {
            return foundation::Result<JournalDocument>::failure(
                parsed.error());
          }
          flush.canonical_events.push_back(parsed.value());
        }
        flush.recovery_events = flush.canonical_events;
        const auto required = unresolved_batch(document.journal);
        if (!required.empty() && required != flush.canonical_events) {
          record_reason = "sequence_journal_flush_batch_invalid";
          record_message =
              "Sequence Journal flush omits a durable unresolved event";
          throw std::runtime_error(
              "Sequence flush does not resolve the durable pending batch");
        }
        document.journal.pending_events.clear();
        document.journal.flushes.push_back(std::move(flush));
        ++document.journal.next_flush_seq;
      } else if (kind == "complete") {
        const auto sequence =
            sequence_integer<std::uint64_t>(payload.value().at("flush_seq"));
        const auto found = std::find_if(
            document.journal.flushes.begin(),
            document.journal.flushes.end(),
            [sequence](const auto& flush) {
              return flush.flush_seq == sequence;
            });
        if (found == document.journal.flushes.end() || found->completed) {
          throw std::runtime_error("Sequence completion is not pending");
        }
        const auto fingerprint =
            payload.value().at("pattern_fingerprint").get<std::string>();
        if (!lowercase_sha256(fingerprint)) {
          throw std::runtime_error("Sequence completion fingerprint is invalid");
        }
        const auto committed_flush = *found;
        for (auto& flush : document.journal.flushes) {
          if (flush.completed ||
              flush.pattern_id != committed_flush.pattern_id ||
              flush.expected_revision != committed_flush.expected_revision) {
            continue;
          }
          if (flush.flush_seq <= sequence) {
            if (!covers_event_keys(
                    committed_flush.canonical_events,
                    flush.recovery_events)) {
              record_reason = "sequence_journal_completion_coverage_invalid";
              record_message =
                  "Sequence completion does not cover an earlier cumulative "
                  "flush";
              throw std::runtime_error(
                  "Sequence completion does not cover an earlier flush");
            }
            flush.completed = true;
            flush.recovery_events.clear();
            continue;
          }
          auto residual = uncommitted_residual(
              committed_flush.canonical_events,
              flush.recovery_events);
          if (residual.empty()) {
            flush.completed = true;
            flush.recovery_events.clear();
          } else {
            flush.recovery_events = std::move(residual);
          }
        }
        document.journal.pending_events = uncommitted_residual(
            committed_flush.canonical_events,
            document.journal.pending_events);
        document.journal.expected_revision =
            sequence_integer<std::uint64_t>(payload.value().at("committed_revision"));
        document.journal.pattern_fingerprint = fingerprint;
      } else if (kind == "state") {
        if (document.journal.capture_commit.has_value()) {
          throw std::runtime_error(
              "Sequence state cannot change during Capture recovery");
        }
        document.journal.state =
            parse_state(payload.value().at("state").get<std::string>());
      } else if (kind == "rebase") {
        const auto expected_revision =
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision"));
        if (document.journal.capture_commit.has_value() ||
            expected_revision <= document.journal.expected_revision ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching) ||
            std::any_of(
                document.journal.flushes.begin(),
                document.journal.flushes.end(),
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error("Sequence rebase metadata is invalid");
        }
        document.journal.expected_revision = expected_revision;
      } else if (kind == "capture-prepare") {
        auto capture = parse_capture(payload.value(), path);
        if (document.journal.capture_commit.has_value() ||
            document.journal.armed_capture_slot != capture.slot ||
            capture.expected_revision != document.journal.expected_revision ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching) ||
            std::any_of(
                document.journal.flushes.begin(),
                document.journal.flushes.end(),
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error(
              "armed Capture preparation metadata is invalid");
        }
        document.journal.capture_commit = std::move(capture);
      } else if (kind == "capture-complete") {
        const auto slot = optional_slot(payload.value(), "slot");
        const auto command_id = foundation::CommandId{
            payload.value().at("command_id").get<std::string>()};
        const auto committed_revision =
            sequence_integer<std::uint64_t>(payload.value().at("committed_revision"));
        if (!slot.has_value() || !document.journal.capture_commit.has_value() ||
            !domain::is_valid_uuid(command_id.value()) ||
            document.journal.armed_capture_slot != slot ||
            document.journal.capture_commit->slot != slot ||
            document.journal.capture_commit->command_id != command_id ||
            document.journal.capture_commit->expected_revision !=
                document.journal.expected_revision ||
            committed_revision != document.journal.expected_revision + 1 ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching) ||
            std::any_of(
                document.journal.flushes.begin(),
                document.journal.flushes.end(),
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error(
              "armed Capture completion metadata is invalid");
        }
        document.journal.expected_revision = committed_revision;
        document.journal.armed_capture_slot.reset();
        document.journal.capture_commit.reset();
      } else if (kind == "capture-abort") {
        const auto slot = optional_slot(payload.value(), "slot");
        const auto command_id = foundation::CommandId{
            payload.value().at("command_id").get<std::string>()};
        const auto expected_revision =
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision"));
        if (!slot.has_value() || !document.journal.capture_commit.has_value() ||
            !domain::is_valid_uuid(command_id.value()) ||
            document.journal.armed_capture_slot != slot ||
            document.journal.capture_commit->slot != slot ||
            document.journal.capture_commit->command_id != command_id ||
            document.journal.capture_commit->expected_revision !=
                expected_revision ||
            expected_revision != document.journal.expected_revision ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching) ||
            std::any_of(
                document.journal.flushes.begin(),
                document.journal.flushes.end(),
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error("armed Capture abort metadata is invalid");
        }
        document.journal.armed_capture_slot.reset();
        document.journal.capture_commit.reset();
      } else if (kind == "capture-disarm") {
        const auto slot = optional_slot(payload.value(), "slot");
        if (!slot.has_value() ||
            document.journal.armed_capture_slot != slot ||
            document.journal.capture_commit.has_value() ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching)) {
          throw std::runtime_error("armed Capture disarm metadata is invalid");
        }
        document.journal.armed_capture_slot.reset();
      } else if (kind == "switch") {
        const auto pattern_id = foundation::PatternId{
            payload.value().at("pattern_id").get<std::string>()};
        if (admission_codec::blocks_switch(document.journal, pattern_id)) {
          throw std::runtime_error("switch bypasses admission prefix or authority");
        }
        const auto bars = sequence_integer<std::uint8_t>(payload.value().at("bars"));
        const auto fingerprint =
            payload.value().at("pattern_fingerprint").get<std::string>();
        const auto expected_revision =
            sequence_integer<std::uint64_t>(payload.value().at("expected_revision"));
        if (document.journal.capture_commit.has_value() ||
            !domain::is_valid_uuid(pattern_id.value()) || !valid_bars(bars) ||
            !lowercase_sha256(fingerprint) ||
            expected_revision != document.journal.expected_revision ||
            pattern_id == document.journal.pattern_id ||
            (document.journal.state != SequenceSessionState::active &&
             document.journal.state != SequenceSessionState::switching) ||
            std::any_of(
                document.journal.flushes.begin(),
                document.journal.flushes.end(),
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error("Sequence switch metadata is invalid");
        }
        admission_codec::reconcile_switch(document.journal);
        document.journal.pattern_id = pattern_id;
        document.journal.bars = bars;
        document.journal.pattern_fingerprint = fingerprint;
        document.journal.expected_revision = expected_revision;
        document.journal.state = SequenceSessionState::active;
      } else {
        throw std::runtime_error("Sequence Journal record kind is invalid");
      }
    }
    if (!saw_begin) {
      throw std::runtime_error("Sequence Journal has no durable begin record");
    }
    const auto& reused_prefix = checked.value().reused_sequence_prefix;
    std::shared_ptr<const SequenceProjectParsePrefix> project_parse_prefix;
    if (document.journal.admission) {
      const auto project_raw_budget = checked.value().sequence_bytes.empty()
          ? 0 : kSequenceParsePrefixBytes - checked.value().sequence_bytes.size();
      auto project = validate_admission_project(
          platform, bundle, document.journal.admission->preparation.project_id,
          reused_prefix ? reused_prefix->project_parse_prefix : nullptr,
          project_raw_budget, &project_parse_prefix);
      if (!project.has_value()) return foundation::Result<JournalDocument>::failure(project.error());
    }
    document.admission_candidate_bytes = admission_candidate_bytes;
    // Publish only a wholly checked read. In particular, an unknown append
    // may be readable and reusable for parsing, but its original fresh lease
    // and append_durable retry still have to establish durability separately.
    if (!checked.value().sequence_bytes.empty()) {
      if (reused_prefix &&
          checked.value().observed_length == reused_prefix->bytes.size() &&
          checked.value().records.empty() &&
          project_parse_prefix == reused_prefix->project_parse_prefix) {
        // Both the fresh Journal bytes and freshly validated Project parse
        // node matched. A changed Project or smaller budget replaces this node.
        sequence_parse_prefix = reused_prefix;
      } else {
        try {
          sequence_parse_prefix = std::make_shared<const SequenceParsePrefix>(
              SequenceParsePrefix{
                  &platform, path, std::move(checked.value().sequence_bytes),
                  document, admission_candidate_bytes,
                  std::move(project_parse_prefix)});
        } catch (...) {
          // Allocation of an optional parsing checkpoint is not a Journal
          // validation failure. Keep the successful cold result instead.
          sequence_parse_prefix.reset();
        }
      }
    } else {
      // The document must correspond to the entire stored prefix. Never pair
      // a full-file state with bytes truncated to the private cache bound.
      sequence_parse_prefix.reset();
    }
    prefix_read.successful = true;
    return foundation::Result<JournalDocument>::success(std::move(document));
  } catch (const std::exception& exception) {
    (void)exception;
    return foundation::Result<JournalDocument>::failure(
        corrupt_record_error(
            path,
            record_offset,
            checked.value().observed_length,
            record_reason,
            std::move(record_message)));
  }
}

std::shared_ptr<std::mutex> append_mutex(
    const std::shared_ptr<ProjectStoragePlatform>& platform) {
  static std::mutex registry_mutex;
  static std::unordered_map<
      const ProjectStoragePlatform*, std::weak_ptr<std::mutex>> registry;
  std::lock_guard lock(registry_mutex);
  for (auto entry = registry.begin(); entry != registry.end();) {
    if (entry->second.expired()) {
      entry = registry.erase(entry);
    } else {
      ++entry;
    }
  }
  if (const auto found = registry.find(platform.get()); found != registry.end()) {
    if (auto existing = found->second.lock()) {
      return existing;
    }
  }
  auto created = std::make_shared<std::mutex>();
  registry[platform.get()] = created;
  return created;
}

foundation::Result<void> append_recording_record(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    SessionKind session_kind,
    std::uint64_t valid_prefix_length,
    nlohmann::json payload) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_write,
      recording_active_path(bundle, session_kind));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  const auto bytes = foundation::canonical_json(
                         checked_record(std::move(payload))) +
                     "\n";
  return platform->append_durable(
      recording_active_path(bundle, session_kind),
      valid_prefix_length,
      byte_span(bytes));
}

foundation::Result<std::uint64_t> manifest_head_revision(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  const auto path = bundle / "manifest.json";
  auto read = platform.read_complete(path);
  if (!read.has_value()) {
    return foundation::Result<std::uint64_t>::failure(read.error());
  }
  try {
    const auto manifest = parse_bounded_or_throw(
        std::string_view(byte_string(read.value())));
    if (manifest.at("contract") != "lmdj.project.manifest.v1" ||
        !manifest.at("head_revision").is_number_unsigned()) {
      throw std::runtime_error("Project manifest head is invalid");
    }
    return foundation::Result<std::uint64_t>::success(
        manifest.at("head_revision").get<std::uint64_t>());
  } catch (const std::exception& exception) {
    return foundation::Result<std::uint64_t>::failure(Error{
        ErrorCode::invalid_project,
        "recording session could not validate the Project revision",
        {{"detail", exception.what()}, {"path", path.generic_string()}},
    });
  }
}

foundation::Result<std::optional<SessionKind>> active_recording_session(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    SessionKind requested_kind) {
  for (const auto candidate :
       {requested_kind, other_session_kind(requested_kind)}) {
    auto exists = platform.exists(recording_active_path(bundle, candidate));
    if (!exists.has_value()) {
      return foundation::Result<std::optional<SessionKind>>::failure(
          exists.error());
    }
    if (exists.value()) {
      return foundation::Result<std::optional<SessionKind>>::success(
          candidate);
    }
  }
  return foundation::Result<std::optional<SessionKind>>::success(
      std::nullopt);
}

struct CheckedRecoveryDocument {
  nlohmann::json payload;
  std::filesystem::path path;
};

foundation::Result<std::vector<CheckedRecoveryDocument>>
read_checked_recovery_documents(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle,
    SessionKind requested_kind) {
  auto tree = validate_journal_tree(platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<
        std::vector<CheckedRecoveryDocument>>::failure(tree.error());
  }
  auto names = platform.list_names(bundle / "recovery/sealed");
  if (!names.has_value()) {
    return foundation::Result<
        std::vector<CheckedRecoveryDocument>>::failure(names.error());
  }
  const auto& requested = recording_protocol(requested_kind);
  const auto& other = recording_protocol(other_session_kind(requested_kind));
  std::vector<CheckedRecoveryDocument> result;
  for (const auto& name : names.value()) {
    const auto path = bundle / "recovery/sealed" / name;
    if (path.extension() != ".json") {
      continue;
    }
    auto read = platform.read_complete(path);
    if (!read.has_value()) {
      return foundation::Result<
          std::vector<CheckedRecoveryDocument>>::failure(read.error());
    }
    try {
      const auto bytes = byte_string(read.value());
      if (requested_kind == SessionKind::sequence) admission_codec::preflight(bytes);
      const auto envelope = parse_bounded_or_throw(bytes);
      auto payload = checked_payload(envelope, path, 0, bytes.size());
      if (!payload.has_value()) {
        return foundation::Result<
            std::vector<CheckedRecoveryDocument>>::failure(payload.error());
      }
      if (!payload.value().is_object() ||
          !payload.value().contains("contract") ||
          !payload.value().at("contract").is_string() ||
          !payload.value().contains("journal") ||
          !payload.value().contains("reason") ||
          !payload.value().at("reason").is_string()) {
        throw std::runtime_error(
            "recording recovery payload shape is invalid");
      }
      const auto contract =
          payload.value().at("contract").get<std::string>();
      if (contract == other.recovery_contract) {
        continue;
      }
      if (contract != requested.recovery_contract) {
        throw std::runtime_error(
            "recording recovery contract is unknown");
      }
      result.push_back({std::move(payload.value()), path});
    } catch (const std::exception& exception) {
      return foundation::Result<
          std::vector<CheckedRecoveryDocument>>::failure(Error{
          ErrorCode::invalid_project,
          std::string{requested.name} +
              " recovery payload is invalid and has been retained",
          {{"detail", exception.what()},
           {"path", path.generic_string()},
           {"reason",
            requested_kind == SessionKind::sequence
                ? "sequence_recovery_payload_invalid"
                : "performance_recovery_payload_invalid"},
           {"recovery_retained", true},
           {"remedy",
            "retain the recovery file; repair its versioned payload or "
            "discard this recovery candidate explicitly"}},
      });
    }
  }
  std::ranges::sort(result, {}, [](const auto& document) {
    return document.path.generic_string();
  });
  return foundation::Result<
      std::vector<CheckedRecoveryDocument>>::success(std::move(result));
}

std::string file_reason(std::string_view reason) {
  std::string result;
  result.reserve(reason.size());
  for (const unsigned char character : reason) {
    result.push_back(
        std::isalnum(character) != 0 || character == '-' || character == '_'
            ? static_cast<char>(character)
            : '_');
  }
  return result.empty() ? "recovery" : result;
}

foundation::Result<std::filesystem::path> seal_recording_session(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    SessionKind session_kind,
    const foundation::SequenceSessionId& session_id,
    std::string_view reason,
    nlohmann::json journal) {
  const auto& protocol = recording_protocol(session_kind);
  const auto payload = nlohmann::json{
      {"contract", protocol.recovery_contract},
      {"journal", std::move(journal)},
      {"reason", reason},
  };
  const auto bytes = foundation::canonical_json(checked_record(payload)) +
                     "\n";
  const auto directory = bundle / "recovery/sealed";
  const auto stem =
      session_kind == SessionKind::performance
          ? session_id.value() + std::string{protocol.sealed_name_marker} +
                "-owner_lost"
          : session_id.value() + std::string{protocol.sealed_name_marker} +
                "-" + file_reason(reason);
  auto destination = directory / (stem + ".json");
  std::uint64_t suffix = 1;
  auto exists = platform->exists(destination);
  if (!exists.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        exists.error());
  }
  if (session_kind == SessionKind::performance && exists.value()) {
    auto existing = platform->read_complete(destination);
    if (!existing.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          existing.error());
    }
    if (byte_string(existing.value()) != bytes) {
      return foundation::Result<std::filesystem::path>::failure(Error{
          ErrorCode::invalid_project,
          "Performance recovery candidate conflicts with the active Journal",
          {{"active_journal_retained", true},
           {"candidate_retained", true},
           {"path", destination.generic_string()},
           {"reason", "performance_recovery_candidate_conflict"}},
      });
    }
    auto removed = platform->remove(
        recording_active_path(bundle, session_kind));
    if (!removed.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          removed.error());
    }
    auto lock_removed = remove_performance_owner_lock(platform, bundle);
    if (!lock_removed.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          lock_removed.error());
    }
    return foundation::Result<std::filesystem::path>::success(destination);
  }
  while (exists.value()) {
    destination = directory /
                  (stem + "-" + std::to_string(suffix++) + ".json");
    exists = platform->exists(destination);
    if (!exists.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          exists.error());
    }
  }
  auto written = platform->create_immutable(destination, byte_span(bytes));
  if (!written.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        written.error());
  }
  auto removed = platform->remove(
      recording_active_path(bundle, session_kind));
  if (!removed.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        removed.error());
  }
  if (session_kind == SessionKind::performance) {
    auto lock_removed = remove_performance_owner_lock(platform, bundle);
    if (!lock_removed.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(
          lock_removed.error());
    }
  }
  return foundation::Result<std::filesystem::path>::success(
      std::move(destination));
}

foundation::Result<void> append_admission_record(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, std::string_view kind,
    nlohmann::json data) {
  auto mutex = append_mutex(platform);
  std::lock_guard append_operation(*mutex);
  auto lease = platform->acquire_writer(bundle);
  if (!lease.has_value()) return foundation::Result<void>::failure(lease.error());
  auto operation = std::move(lease.value());
  (void)operation;
  // Always reread under the lease, including after an unknown append response.
  auto document = read_journal(*platform, bundle);
  if (!document.has_value()) return foundation::Result<void>::failure(document.error());
  const nlohmann::json record{
      {"kind", kind}, {"session_id", session.value()},
      {"identity", admission_codec::encode(identity)}, {"data", std::move(data)}};
  try {
    auto admission_candidate_bytes = document.value().admission_candidate_bytes;
    auto tentative = std::move(document.value().journal);
    if (!admission_codec::apply(tentative, record, &admission_candidate_bytes)) {
      // An earlier write can be readable even though its sync failed. Finish
      // durability under this same lease, without appending duplicate bytes.
      return platform->append_durable(recording_active_path(bundle, SessionKind::sequence),
                                      document.value().valid_prefix_length, {});
    }
    if (kind == "admission-prepare") {
      auto project = validate_admission_project(*platform, bundle, tentative.admission->preparation.project_id);
      if (!project.has_value()) return project;
    }
    return append_recording_record(platform, bundle, SessionKind::sequence,
                                   document.value().valid_prefix_length, record);
  } catch (const std::exception& e) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument, e.what(), {{"journal_retained", true}}});
  }
}
}  // namespace

foundation::Result<void> SequenceJournal::prepare_admission(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionPreparation& preparation) {
  return append_admission_record(platform_, bundle, session, preparation.identity,
                                 "admission-prepare", admission_codec::encode(preparation));
}
foundation::Result<void> SequenceJournal::append_admission_candidate(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, const SequenceAdmissionCandidate& candidate) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-candidate", admission_codec::encode(candidate));
}
foundation::Result<void> SequenceJournal::retain_admission_fence(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, const SequenceAdmissionFence& fence) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-fence", admission_codec::encode(fence));
}
foundation::Result<void> SequenceJournal::retain_admission_switch(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, const SequencePublicationAuthority& authority) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-switch", admission_codec::encode(authority));
}
foundation::Result<void> SequenceJournal::retain_admission_overlay(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, std::uint64_t publication_generation) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-overlay",
                                 nlohmann::json{{"publication_generation", publication_generation}});
}
foundation::Result<void> SequenceJournal::close_admission(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, const SequenceAdmissionClosure& closure) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-close", admission_codec::encode(closure));
}
foundation::Result<void> SequenceJournal::retain_admission_timing_profile(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity,
    const SequenceAdmissionTimingProfile& profile) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-profile", admission_codec::encode(profile));
}
foundation::Result<void> SequenceJournal::transfer_admission_prefix(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity, const SequenceAdmissionTransfer& transfer) {
  return append_admission_record(platform_, bundle, session, identity,
                                 "admission-transfer", admission_codec::encode(transfer));
}
foundation::Result<void> SequenceJournal::complete_admission(
    const std::filesystem::path& bundle, foundation::SequenceSessionId session,
    const SequenceAdmissionIdentity& identity) {
  return append_admission_record(platform_, bundle, session, identity, "admission-complete", nullptr);
}

SequenceCandidateReceipt sequence_admission_candidate_receipt(
    const SequenceAdmissionCandidate& candidate) {
  return {candidate.watermark,
          sha256(foundation::canonical_json(admission_codec::encode(candidate)))};
}

std::string sequence_admission_candidates_sha256(
    std::span<const SequenceAdmissionCandidate> candidates) {
  auto encoded = nlohmann::json::array();
  for (const auto& candidate : candidates) {
    encoded.push_back(admission_codec::encode(candidate));
  }
  return sha256(foundation::canonical_json(encoded));
}

std::string sequence_pattern_fingerprint(const domain::Pattern& pattern) {
  auto canonical_events = domain::merge_pattern_events({}, pattern.events);
  auto events = nlohmann::json::array();
  for (const auto& event : canonical_events) {
    events.push_back(event_json(event));
  }
  const nlohmann::json preimage = {
      {"bars", pattern.bars},
      {"events", std::move(events)},
  };
  return sha256(foundation::canonical_json(preimage));
}

SequenceJournal::SequenceJournal()
    : SequenceJournal(make_default_project_storage_platform()) {}

SequenceJournal::SequenceJournal(
    std::shared_ptr<ProjectStoragePlatform> platform)
    : platform_(platform != nullptr
                    ? std::move(platform)
                    : make_default_project_storage_platform()) {}

foundation::Result<void> SequenceJournal::begin(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::PatternId pattern_id,
    std::uint8_t bars,
    std::string pattern_fingerprint,
    std::uint64_t expected_revision,
    std::optional<domain::PadSlotId> armed_capture_slot) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(pattern_id.value()) || !valid_bars(bars) ||
      !lowercase_sha256(pattern_fingerprint) ||
      (armed_capture_slot.has_value() &&
       !domain::is_valid_slot(*armed_capture_slot))) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence begin metadata is invalid"});
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  // Validate the tree only under the writer lease: a contender that walked it
  // first could observe the owner's in-flight publication (a journal briefly
  // linked under both its temporary and final names) and report a corrupt
  // Project instead of project_busy.
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto tree = validate_journal_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  auto active_kind = active_recording_session(
      *platform_, bundle, SessionKind::sequence);
  if (!active_kind.has_value()) {
    return foundation::Result<void>::failure(active_kind.error());
  }
  if (active_kind.value().has_value()) {
    const auto kind = *active_kind.value();
    auto details = nlohmann::json{
        {"reason",
         kind == SessionKind::sequence ? "sequence_session_active"
                                       : "recording_session_active"},
        {"session_kind", session_kind_string(kind)},
    };
    if (kind == SessionKind::sequence) {
      auto active = read_journal(*platform_, bundle);
      if (active.has_value()) {
        details["session_id"] = active.value().journal.session_id.value();
      }
    }
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "a " + std::string{recording_protocol(kind).name} +
            " session is already active for this Project",
        std::move(details),
    });
  }
  auto head_revision = manifest_head_revision(*platform_, bundle);
  if (!head_revision.has_value()) {
    return foundation::Result<void>::failure(head_revision.error());
  }
  if (head_revision.value() != expected_revision) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::revision_conflict,
        "Sequence begin expected revision does not match Project Truth",
        {{"actual_revision", head_revision.value()},
         {"expected_revision", expected_revision}},
    });
  }
  const auto path = recording_active_path(bundle, SessionKind::sequence);
  const auto payload = nlohmann::json{
      {"armed_capture_slot",
       armed_capture_slot.has_value()
           ? nlohmann::json(slot_json(*armed_capture_slot))
           : nlohmann::json(nullptr)},
      {"bars", bars},
      {"contract", recording_protocol(SessionKind::sequence).journal_contract},
      {"expected_revision", expected_revision},
      {"kind", "begin"},
      {"pattern_fingerprint", std::move(pattern_fingerprint)},
      {"pattern_id", pattern_id.value()},
      {"session_id", session_id.value()},
  };
  const auto bytes = foundation::canonical_json(checked_record(payload)) + "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_write, path);
  if (!fault.has_value()) {
    return fault;
  }
#endif
  auto created = platform_->create_immutable(path, byte_span(bytes));
  if (!created.has_value()) {
    const auto condition = created.error().details.find("storage_condition");
    if (condition != created.error().details.end() &&
        condition->is_string() &&
        condition->get<std::string>() ==
            std::string{kStorageConditionAlreadyExists}) {
      return foundation::Result<void>::failure(
          Error{
              ErrorCode::invalid_argument,
              "a Sequence session is already active for this Project",
              {{"reason", "sequence_session_active"}},
          });
    }
    return foundation::Result<void>::failure(created.error());
  }
  return foundation::Result<void>::success();
}

foundation::Result<ActiveSequenceJournal> SequenceJournal::read_active(
    const std::filesystem::path& bundle) const {
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<ActiveSequenceJournal>::failure(document.error());
  }
  return foundation::Result<ActiveSequenceJournal>::success(
      std::move(document.value().journal));
}

foundation::Result<void> SequenceJournal::append_tail(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::PatternId pattern_id,
    std::uint64_t expected_revision,
    std::uint64_t input_sequence,
    std::span<const domain::PatternEvent> events) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(pattern_id.value()) || events.empty()) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence tail metadata is invalid"});
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  auto& journal = document.value().journal;
  if ((journal.admission && !journal.admission->completed) ||
      journal.session_id != session_id || journal.pattern_id != pattern_id ||
      journal.expected_revision != expected_revision ||
      (journal.last_input_sequence.has_value() &&
       input_sequence <= *journal.last_input_sequence) ||
      !recording_accepts_tail(
          journal.kind, journal.state, journal.flushes)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence tail does not match the active session",
        });
  }
  const std::vector<domain::PatternEvent> incoming{events.begin(), events.end()};
  const auto canonical = domain::merge_pattern_events({}, incoming);
  const auto loop_length = domain::pattern_length_ticks(journal.bars);
  for (const auto& event : canonical) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 || event.onset_tick >= loop_length ||
        event.duration_tick < 1 ||
        event.duration_tick > loop_length - event.onset_tick) {
      return foundation::Result<void>::failure(
          Error{ErrorCode::invalid_argument, "Sequence tail event is invalid"});
    }
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      tail_json(journal, input_sequence, canonical));
}

foundation::Result<SequenceFlushRecord> SequenceJournal::append_flush(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId command_id,
    foundation::PatternId pattern_id,
    std::uint64_t expected_revision,
    std::span<const domain::PatternEvent> events) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value()) ||
      !domain::is_valid_uuid(pattern_id.value()) || events.empty()) {
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{ErrorCode::invalid_argument, "Sequence flush metadata is invalid"});
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<SequenceFlushRecord>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<SequenceFlushRecord>::failure(document.error());
  }
  auto& journal = document.value().journal;
  if (journal.session_id != session_id) {
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush does not match the active session",
        });
  }
  const std::vector<domain::PatternEvent> incoming{
      events.begin(), events.end()};
  auto canonical = domain::merge_pattern_events({}, incoming);
  const auto repeated = std::find_if(
      journal.flushes.begin(),
      journal.flushes.end(),
      [&command_id](const auto& flush) {
        return flush.command_id == command_id;
      });
  if (repeated != journal.flushes.end()) {
    if (repeated->pattern_id == pattern_id &&
        repeated->expected_revision == expected_revision &&
        repeated->canonical_events == canonical) {
      return foundation::Result<SequenceFlushRecord>::success(*repeated);
    }
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence command id is already bound to a different flush",
            {{"reason", "sequence_command_conflict"}},
        });
  }
  if (admission_codec::blocks_flush(journal) ||
      journal.pattern_id != pattern_id ||
      journal.expected_revision != expected_revision ||
      !recording_accepts_flush(
          journal.kind, journal.state, journal.flushes) ||
      journal.capture_commit.has_value()) {
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush does not match the active session",
        });
  }
  const auto loop_length = domain::pattern_length_ticks(journal.bars);
  for (const auto& event : canonical) {
    if (!domain::is_valid_slot(event.slot) || event.velocity < 1 ||
        event.velocity > 127 || event.onset_tick >= loop_length ||
        event.duration_tick < 1 ||
        event.duration_tick > loop_length - event.onset_tick) {
      return foundation::Result<SequenceFlushRecord>::failure(
          Error{ErrorCode::invalid_argument, "Sequence flush event is invalid"});
    }
  }
  const auto required = unresolved_batch(journal);
  if (!required.empty() && required != canonical) {
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush does not resolve the durable pending batch",
        });
  }
  SequenceFlushRecord flush{
      journal.next_flush_seq,
      std::move(command_id),
      std::move(pattern_id),
      expected_revision,
      canonical,
      std::move(canonical),
      false,
  };
  auto appended = append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length, flush_json(flush));
  if (!appended.has_value()) {
    return foundation::Result<SequenceFlushRecord>::failure(appended.error());
  }
  return foundation::Result<SequenceFlushRecord>::success(std::move(flush));
}

foundation::Result<void> SequenceJournal::complete_flush(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::uint64_t flush_seq,
    std::uint64_t committed_revision,
    std::string pattern_fingerprint) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !lowercase_sha256(pattern_fingerprint)) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence completion is invalid"});
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  if (document.value().journal.session_id != session_id ||
      document.value().journal.capture_commit.has_value()) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence session does not match"});
  }
  const auto found = std::find_if(
      document.value().journal.flushes.begin(),
      document.value().journal.flushes.end(),
      [flush_seq](const auto& flush) { return flush.flush_seq == flush_seq; });
  if (found == document.value().journal.flushes.end()) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::not_found, "Sequence flush does not exist"});
  }
  if (found->completed) {
    return foundation::Result<void>::success();
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_completion,
      recording_active_path(bundle, SessionKind::sequence));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  return append_recording_record(
      platform_,
      bundle,
      document.value().journal.kind,
      document.value().valid_prefix_length,
      {
          {"committed_revision", committed_revision},
          {"flush_seq", flush_seq},
          {"kind", "complete"},
          {"pattern_fingerprint", std::move(pattern_fingerprint)},
      });
}

foundation::Result<void> SequenceJournal::set_state(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    SequenceSessionState state) {
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  if (document.value().journal.session_id != session_id ||
      document.value().journal.capture_commit.has_value()) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence session does not match"});
  }
  if (document.value().journal.state == state) {
    // A previous append may be readable after its sync failed. Reconfirm the
    // exact prefix under this writer lease without growing it on every retry.
    return platform_->append_durable(
        recording_active_path(bundle, document.value().journal.kind),
        document.value().valid_prefix_length, {});
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"kind", "state"}, {"state", state_string(state)}});
}

foundation::Result<void> SequenceJournal::rebase(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::uint64_t expected_revision) {
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      expected_revision <= journal.expected_revision ||
      journal.capture_commit.has_value() ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching) ||
      std::any_of(
          journal.flushes.begin(), journal.flushes.end(),
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Sequence rebase does not match the active session",
    });
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"expected_revision", expected_revision}, {"kind", "rebase"}});
}

foundation::Result<void> SequenceJournal::complete_armed_capture(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId command_id,
    domain::PadSlotId slot,
    std::uint64_t committed_revision) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value()) ||
      !domain::is_valid_slot(slot)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture completion identity is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      !journal.capture_commit.has_value() ||
      journal.capture_commit->command_id != command_id ||
      journal.capture_commit->slot != slot ||
      journal.armed_capture_slot != slot ||
      journal.capture_commit->expected_revision != journal.expected_revision ||
      committed_revision != journal.expected_revision + 1 ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching) ||
      std::any_of(
          journal.flushes.begin(), journal.flushes.end(),
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture completion does not match the active session",
        {{"reason", "armed_capture_target_mismatch"}},
    });
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"command_id", command_id.value()},
       {"committed_revision", committed_revision},
       {"kind", "capture-complete"},
       {"slot", slot_json(slot)}});
}

foundation::Result<void> SequenceJournal::prepare_armed_capture(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId command_id,
    foundation::AssetId asset_id,
    domain::PadSlotId slot,
    foundation::ArtifactRef artifact,
    std::uint64_t expected_revision) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value()) ||
      !domain::is_valid_uuid(asset_id.value()) || !domain::is_valid_slot(slot) ||
      !lowercase_sha256(artifact.sha256) || artifact.media_type.empty()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture preparation identity is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      journal.armed_capture_slot != slot ||
      journal.capture_commit.has_value() ||
      expected_revision != journal.expected_revision ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching) ||
      std::any_of(
          journal.flushes.begin(), journal.flushes.end(),
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture preparation does not match the active session",
        {{"reason", "armed_capture_target_mismatch"}},
    });
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      capture_json(SequenceCaptureCommit{
          std::move(command_id), std::move(asset_id), slot,
          std::move(artifact), expected_revision}));
}

foundation::Result<void> SequenceJournal::disarm_capture(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    domain::PadSlotId slot) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_slot(slot)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture disarm identity is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture disarm does not match the active session",
        {{"reason", "sequence_owner_mismatch"}},
    });
  }
  if (!journal.armed_capture_slot.has_value()) {
    return foundation::Result<void>::success();
  }
  if (journal.armed_capture_slot != slot) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture disarm target does not match",
        {{"reason", "armed_capture_target_mismatch"}},
    });
  }
  if (journal.capture_commit.has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "armed Capture commit must be reconciled before disarm",
        {{"reason", "armed_capture_recovery_pending"},
         {"remedy", "retry or reconcile the durable Capture commit first"}},
    });
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"kind", "capture-disarm"}, {"slot", slot_json(slot)}});
}

foundation::Result<SequenceCaptureDisarmResult>
SequenceJournal::resolve_capture_disarm(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    domain::PadSlotId slot,
    const SequenceCaptureTruthInspector& inspect_truth) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_slot(slot) || !inspect_truth) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(Error{
        ErrorCode::invalid_argument,
        "checked armed Capture disarm identity is invalid",
    });
  }
  // ProjectStore Capture publication holds the writer lease before appending
  // journal completion, so checked abort must take the same lock order.
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(
        document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching)) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(Error{
        ErrorCode::invalid_argument,
        "checked armed Capture disarm does not match the active session",
        {{"reason", "sequence_owner_mismatch"}},
    });
  }
  if (!journal.armed_capture_slot.has_value()) {
    return foundation::Result<SequenceCaptureDisarmResult>::success(
        SequenceCaptureDisarmResult{false, journal.expected_revision});
  }
  if (journal.armed_capture_slot != slot) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(Error{
        ErrorCode::invalid_argument,
        "checked armed Capture disarm target does not match",
        {{"reason", "armed_capture_target_mismatch"}},
    });
  }
  if (!journal.capture_commit.has_value()) {
    auto appended = append_recording_record(
        platform_, bundle, document.value().journal.kind,
        document.value().valid_prefix_length,
        {{"kind", "capture-disarm"}, {"slot", slot_json(slot)}});
    if (!appended.has_value()) {
      return foundation::Result<SequenceCaptureDisarmResult>::failure(
          appended.error());
    }
    return foundation::Result<SequenceCaptureDisarmResult>::success(
        SequenceCaptureDisarmResult{false, journal.expected_revision});
  }

  const auto& capture = *journal.capture_commit;
  auto truth = inspect_truth(capture);
  if (!truth.has_value()) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(
        truth.error());
  }
  if (truth.value().has_value()) {
    const auto committed_revision = *truth.value();
    if (committed_revision != capture.expected_revision + 1) {
      return foundation::Result<SequenceCaptureDisarmResult>::failure(Error{
          ErrorCode::invalid_project,
          "checked armed Capture receipt revision is invalid",
          {{"reason", "armed_capture_recovery_conflict"},
           {"remedy",
            "inspect the committed Capture receipt and Project Truth"}},
      });
    }
    auto completed = append_recording_record(
        platform_, bundle, document.value().journal.kind,
        document.value().valid_prefix_length,
        {{"command_id", capture.command_id.value()},
         {"committed_revision", committed_revision},
         {"kind", "capture-complete"},
         {"slot", slot_json(slot)}});
    if (!completed.has_value()) {
      return foundation::Result<SequenceCaptureDisarmResult>::failure(
          completed.error());
    }
    return foundation::Result<SequenceCaptureDisarmResult>::success(
        SequenceCaptureDisarmResult{true, committed_revision});
  }

  auto aborted = append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"command_id", capture.command_id.value()},
       {"expected_revision", capture.expected_revision},
       {"kind", "capture-abort"},
       {"slot", slot_json(slot)}});
  if (!aborted.has_value()) {
    return foundation::Result<SequenceCaptureDisarmResult>::failure(
        aborted.error());
  }
  return foundation::Result<SequenceCaptureDisarmResult>::success(
      SequenceCaptureDisarmResult{false, capture.expected_revision});
}

foundation::Result<void> SequenceJournal::switch_pattern(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::PatternId pattern_id,
    std::uint8_t bars,
    std::string pattern_fingerprint,
    std::uint64_t expected_revision) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(pattern_id.value()) || !valid_bars(bars) ||
      !lowercase_sha256(pattern_fingerprint)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence switch metadata is invalid",
        });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (admission_codec::blocks_switch(journal, pattern_id) ||
      journal.session_id != session_id || journal.pattern_id == pattern_id ||
      journal.expected_revision != expected_revision ||
      journal.capture_commit.has_value() ||
      (journal.state != SequenceSessionState::active &&
       journal.state != SequenceSessionState::switching) ||
      std::any_of(
          journal.flushes.begin(), journal.flushes.end(),
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Sequence switch does not match the active session",
    });
  }
  return append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length,
      {
          {"bars", bars},
          {"expected_revision", expected_revision},
          {"kind", "switch"},
          {"pattern_fingerprint", std::move(pattern_fingerprint)},
          {"pattern_id", pattern_id.value()},
      });
}

foundation::Result<std::filesystem::path> SequenceJournal::seal(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::string reason) {
  if (reason.empty()) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{ErrorCode::invalid_argument, "Sequence recovery reason is empty"});
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(document.error());
  }
  if (document.value().journal.session_id != session_id) {
    return foundation::Result<std::filesystem::path>::failure(
        Error{ErrorCode::invalid_argument, "Sequence session does not match"});
  }
  document.value().journal.state = SequenceSessionState::owner_lost;
  return seal_recording_session(
      platform_,
      bundle,
      document.value().journal.kind,
      session_id,
      reason,
      journal_json(document.value().journal));
}

foundation::Result<std::vector<SequenceRecoveryCandidate>>
SequenceJournal::list_recoverable(const std::filesystem::path& bundle) const {
  auto documents = read_checked_recovery_documents(
      *platform_, bundle, SessionKind::sequence);
  if (!documents.has_value()) {
    return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
        documents.error());
  }
  std::vector<SequenceRecoveryCandidate> result;
  for (auto& document : documents.value()) {
    auto journal = parse_journal_snapshot(
        document.payload.at("journal"), document.path);
    if (!journal.has_value()) {
      return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
          journal.error());
    }
    if (journal.value().admission) {
      auto project = validate_admission_project(*platform_, bundle,
          journal.value().admission->preparation.project_id);
      if (!project.has_value()) {
        return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(project.error());
      }
    }
    result.push_back(
        {std::move(journal.value()),
         document.payload.at("reason").get<std::string>(),
         std::move(document.path)});
  }
  return foundation::Result<std::vector<SequenceRecoveryCandidate>>::success(
      std::move(result));
}

foundation::Result<void> SequenceJournal::remove_active_if_complete(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id) {
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id) {
    return foundation::Result<void>::failure(
        Error{ErrorCode::invalid_argument, "Sequence session does not match"});
  }
  if (std::any_of(
          journal.flushes.begin(), journal.flushes.end(),
          [](const auto& flush) { return !flush.completed; }) ||
      !journal.pending_events.empty() ||
      (journal.admission && !journal.admission->completed)) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence Journal still contains uncommitted events",
        });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_deletion,
      recording_active_path(bundle, SessionKind::sequence));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  return platform_->remove(
      recording_active_path(bundle, SessionKind::sequence));
}

namespace {

nlohmann::json performance_events_json(
    std::span<const domain::PerformanceEvent> events) {
  auto encoded = nlohmann::json::array();
  for (const auto& event : events) {
    encoded.push_back(domain::performance_event_json(event));
  }
  return encoded;
}

constexpr std::array<std::string_view, 8> kPerformanceFxNames{
    "filter", "delay", "reverb", "stutter",
    "gate", "reverse", "crush", "cutter"};

std::string_view performance_fx_name(domain::PerformanceFx fx) {
  const auto index = static_cast<std::size_t>(fx);
  if (index >= kPerformanceFxNames.size()) {
    throw std::runtime_error("Performance transient FX is invalid");
  }
  return kPerformanceFxNames.at(index);
}

domain::PerformanceFx parse_performance_fx(std::string_view value) {
  const auto found = std::ranges::find(kPerformanceFxNames, value);
  if (found == kPerformanceFxNames.end()) {
    throw std::runtime_error("Performance transient FX is invalid");
  }
  return static_cast<domain::PerformanceFx>(
      std::distance(kPerformanceFxNames.begin(), found));
}

// The headered recording profile (lmdj.project.v5 5.4.1) is selected by an
// explicit discriminator on the Journal begin record; a legacy v1 Journal
// never carries it, so grammar never has to be guessed from stray fields.
constexpr std::string_view kLiveControlProfileHeaderInputSequence =
    "header_input_sequence";

bool is_live_control_profile(const ActivePerformanceJournal& journal) {
  return journal.initial_live_state.has_value();
}

// The ledger writes 64-bit sequences as canonical decimal strings ("0" is
// legal for the Core-issued admission counter; durable event sequences start
// at 1).
std::optional<std::uint64_t> parse_bounded_decimal(
    const nlohmann::json& input,
    std::uint64_t minimum) {
  if (!input.is_string()) {
    return std::nullopt;
  }
  const auto& text = input.get_ref<const std::string&>();
  // Canonical decimal: "0" is the zero counter; longer strings never carry a
  // leading zero.
  if (text.empty() || text.size() > 20 ||
      (text.front() == '0' && text.size() != 1) ||
      !std::ranges::all_of(text, [](char c) {
        return c >= '0' && c <= '9';
      })) {
    return std::nullopt;
  }
  if (text.size() == 20 && text > "18446744073709551615") {
    return std::nullopt;
  }
  std::uint64_t value = 0;
  const auto* last = text.data() + text.size();
  const auto parsed = std::from_chars(text.data(), last, value);
  if (parsed.ec != std::errc{} || parsed.ptr != last ||
      value < minimum) {
    return std::nullopt;
  }
  return value;
}

std::string_view admission_phase_string(PerformanceAdmissionPhase phase) {
  switch (phase) {
    case PerformanceAdmissionPhase::prepared:
      return "prepared";
    case PerformanceAdmissionPhase::completed:
      return "completed";
  }
  throw std::runtime_error("Performance admission phase is invalid");
}

std::optional<PerformanceAdmissionPhase> parse_admission_phase(
    std::string_view value) {
  if (value == "prepared") {
    return PerformanceAdmissionPhase::prepared;
  }
  if (value == "completed") {
    return PerformanceAdmissionPhase::completed;
  }
  return std::nullopt;
}

std::string_view admission_result_string(PerformanceAdmissionResult result) {
  switch (result) {
    case PerformanceAdmissionResult::not_published:
      return "not_published";
    case PerformanceAdmissionResult::published:
      return "published";
    case PerformanceAdmissionResult::no_audio:
      return "no_audio";
  }
  throw std::runtime_error("Performance admission result is invalid");
}

std::optional<PerformanceAdmissionResult> parse_admission_result(
    std::string_view value) {
  if (value == "not_published") {
    return PerformanceAdmissionResult::not_published;
  }
  if (value == "published") {
    return PerformanceAdmissionResult::published;
  }
  if (value == "no_audio") {
    return PerformanceAdmissionResult::no_audio;
  }
  return std::nullopt;
}

nlohmann::json admission_binding_json(
    const PerformanceAdmissionBinding& binding) {
  return {
      {"fx", performance_fx_name(binding.fx)},
      {"recording_gesture_id", binding.recording_gesture_id},
  };
}

nlohmann::json admission_receipt_json(
    const PerformanceAdmissionReceipt& receipt) {
  auto event_sequences = nlohmann::json::array();
  for (const auto sequence : receipt.event_input_sequences) {
    event_sequences.push_back(std::to_string(sequence));
  }
  return {
      {"accepted_tick", receipt.accepted_tick},
      {"binding_result",
       receipt.binding_result.has_value()
           ? admission_binding_json(*receipt.binding_result)
           : nlohmann::json(nullptr)},
      {"event_input_sequences", std::move(event_sequences)},
      {"expected_recording_sequence",
       std::to_string(receipt.expected_recording_sequence)},
      {"input_sequence", std::to_string(receipt.input_sequence)},
      {"phase", admission_phase_string(receipt.phase)},
      {"request_fingerprint", receipt.request_fingerprint},
      {"request_id", receipt.request_id.value()},
      {"result", admission_result_string(receipt.result)},
  };
}

nlohmann::json admission_ledger_json(
    const PerformanceAdmissionLedger& ledger) {
  return {
      {"completed",
       ledger.completed.has_value()
           ? admission_receipt_json(*ledger.completed)
           : nlohmann::json(nullptr)},
      {"next_recording_sequence",
       std::to_string(ledger.next_recording_sequence)},
      {"pending",
       ledger.pending.has_value() ? admission_receipt_json(*ledger.pending)
                                  : nlohmann::json(nullptr)},
  };
}

PerformanceAdmissionReceipt parse_admission_receipt(
    const nlohmann::json& input) {
  if (!input.is_object() || input.size() != 9 ||
      !input.contains("accepted_tick") || !input.contains("binding_result") ||
      !input.contains("event_input_sequences") ||
      !input.contains("expected_recording_sequence") ||
      !input.contains("input_sequence") || !input.contains("phase") ||
      !input.contains("request_fingerprint") ||
      !input.contains("request_id") || !input.contains("result")) {
    throw std::runtime_error("Performance admission receipt shape is invalid");
  }
  PerformanceAdmissionReceipt receipt;
  receipt.request_id = foundation::CommandId{
      input.at("request_id").get<std::string>()};
  receipt.request_fingerprint =
      input.at("request_fingerprint").get<std::string>();
  const auto expected =
      parse_bounded_decimal(input.at("expected_recording_sequence"), 0);
  const auto sequence = parse_bounded_decimal(input.at("input_sequence"), 1);
  if (!input.at("phase").is_string() || !input.at("result").is_string()) {
    throw std::runtime_error("Performance admission receipt shape is invalid");
  }
  const auto phase =
      parse_admission_phase(input.at("phase").get<std::string>());
  const auto result =
      parse_admission_result(input.at("result").get<std::string>());
  if (!domain::is_valid_uuid(receipt.request_id.value()) ||
      !lowercase_sha256(receipt.request_fingerprint) ||
      !expected.has_value() || !sequence.has_value() ||
      !phase.has_value() || !result.has_value()) {
    throw std::runtime_error("Performance admission receipt value is invalid");
  }
  // Phase and result are one closed pairing: prepared is exactly
  // not_published; completed is exactly published or no_audio.
  if ((*phase == PerformanceAdmissionPhase::prepared) !=
          (*result == PerformanceAdmissionResult::not_published)) {
    throw std::runtime_error(
        "Performance admission receipt phase/result pairing is invalid");
  }
  receipt.expected_recording_sequence = *expected;
  receipt.input_sequence = *sequence;
  receipt.phase = *phase;
  receipt.result = *result;
  if (!input.at("accepted_tick").is_number_unsigned()) {
    throw std::runtime_error("Performance admission receipt tick is invalid");
  }
  receipt.accepted_tick = input.at("accepted_tick").get<std::uint64_t>();
  const auto& sequences = input.at("event_input_sequences");
  if (!sequences.is_array()) {
    throw std::runtime_error(
        "Performance admission receipt event sequences are invalid");
  }
  for (const auto& encoded : sequences) {
    const auto event_sequence = parse_bounded_decimal(encoded, 1);
    if (!event_sequence.has_value()) {
      throw std::runtime_error(
          "Performance admission receipt event sequence is invalid");
    }
    receipt.event_input_sequences.push_back(*event_sequence);
  }
  const auto& binding = input.at("binding_result");
  if (!binding.is_null()) {
    if (!binding.is_object() || binding.size() != 2 ||
        !binding.contains("fx") || !binding.contains("recording_gesture_id") ||
        !binding.at("fx").is_string() ||
        !binding.at("recording_gesture_id").is_string()) {
      throw std::runtime_error(
          "Performance admission binding result shape is invalid");
    }
    PerformanceAdmissionBinding parsed_binding{
        parse_performance_fx(binding.at("fx").get<std::string>()),
        binding.at("recording_gesture_id").get<std::string>(),
    };
    if (!domain::is_valid_uuid(parsed_binding.recording_gesture_id)) {
      throw std::runtime_error(
          "Performance admission binding result identity is invalid");
    }
    receipt.binding_result = std::move(parsed_binding);
  }
  return receipt;
}

PerformanceAdmissionLedger parse_admission_ledger(const nlohmann::json& input) {
  if (!input.is_object() || input.size() != 3 ||
      !input.contains("completed") || !input.contains("next_recording_sequence") ||
      !input.contains("pending")) {
    throw std::runtime_error("Performance admission ledger shape is invalid");
  }
  PerformanceAdmissionLedger ledger;
  const auto next =
      parse_bounded_decimal(input.at("next_recording_sequence"), 0);
  if (!next.has_value()) {
    throw std::runtime_error(
        "Performance admission ledger next sequence is invalid");
  }
  ledger.next_recording_sequence = *next;
  if (!input.at("pending").is_null()) {
    ledger.pending = parse_admission_receipt(input.at("pending"));
    // A durable pending receipt is the prepared boundary; a crash may have
    // followed the write, so it is never proof the cell stayed unpublished.
    if (ledger.pending->phase != PerformanceAdmissionPhase::prepared ||
        ledger.pending->expected_recording_sequence !=
            ledger.next_recording_sequence) {
      throw std::runtime_error(
          "Performance admission ledger pending receipt is invalid");
    }
  }
  if (!input.at("completed").is_null()) {
    ledger.completed = parse_admission_receipt(input.at("completed"));
    if (ledger.completed->phase != PerformanceAdmissionPhase::completed ||
        ledger.completed->expected_recording_sequence + 1 >
            ledger.next_recording_sequence) {
      throw std::runtime_error(
          "Performance admission ledger completed receipt is invalid");
    }
  }
  return ledger;
}

// The begin checkpoint derives from the header alone: HOLD seeds it, the
// complete live state is captured, and no gesture is invented — engaged
// controls at the fence need their caller-supplied logical bindings.
PerformanceTransientCheckpoint initial_live_checkpoint(
    const std::optional<domain::PerformanceInitialLiveState>& header) {
  if (!header.has_value()) {
    return PerformanceTransientCheckpoint{{}, {}, false, 0};
  }
  return PerformanceTransientCheckpoint{{}, {}, header->hold, 0,
                                        std::nullopt, *header};
}

nlohmann::json open_filter_json(const PerformanceOpenFilterTransient& filter) {
  return {
      {"cutoff_hz", filter.cutoff_hz},
      {"gesture_id", filter.gesture_id},
      {"resonance_milli", filter.resonance_milli},
      {"type",
       std::string{filter.type == domain::PerformanceFilterType::lp
                       ? "lp"
                       : filter.type == domain::PerformanceFilterType::hp
                             ? "hp"
                             : "bp"}},
  };
}

PerformanceOpenFilterTransient parse_open_filter(const nlohmann::json& input) {
  if (!input.is_object() || input.size() != 4 ||
      !input.contains("cutoff_hz") || !input.contains("gesture_id") ||
      !input.contains("resonance_milli") || !input.contains("type") ||
      !input.at("cutoff_hz").is_number_unsigned() ||
      !input.at("gesture_id").is_string() ||
      !input.at("resonance_milli").is_number_unsigned() ||
      !input.at("type").is_string()) {
    throw std::runtime_error(
        "Performance open Filter checkpoint shape is invalid");
  }
  const auto cutoff = input.at("cutoff_hz").get<std::uint64_t>();
  const auto resonance = input.at("resonance_milli").get<std::uint64_t>();
  const auto type_text = input.at("type").get<std::string>();
  domain::PerformanceFilterType type;
  if (type_text == "lp") {
    type = domain::PerformanceFilterType::lp;
  } else if (type_text == "hp") {
    type = domain::PerformanceFilterType::hp;
  } else if (type_text == "bp") {
    type = domain::PerformanceFilterType::bp;
  } else {
    throw std::runtime_error(
        "Performance open Filter checkpoint type is invalid");
  }
  PerformanceOpenFilterTransient filter{
      input.at("gesture_id").get<std::string>(),
      type,
      0,
      0,
  };
  if (!domain::is_valid_uuid(filter.gesture_id) ||
      cutoff < domain::kFilterCutoffHzMin ||
      cutoff > domain::kFilterCutoffHzMax ||
      resonance > domain::kFilterResonanceMilliMax) {
    throw std::runtime_error(
        "Performance open Filter checkpoint value is invalid");
  }
  filter.cutoff_hz = static_cast<std::uint16_t>(cutoff);
  filter.resonance_milli = static_cast<std::uint16_t>(resonance);
  return filter;
}


foundation::Result<std::uint64_t> performance_temporal_high_water(
    std::span<const domain::PerformanceEvent> events) {
  std::uint64_t result = 0;
  for (const auto& event : events) {
    auto tick = domain::performance_event_tick(event);
    if (const auto* pad = std::get_if<domain::PadHitPerformanceEvent>(
            &event.payload)) {
      if (pad->duration_tick >
          std::numeric_limits<std::uint64_t>::max() - pad->onset_tick) {
        return foundation::Result<std::uint64_t>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance Pad duration overflows the Core tick domain",
            {{"reason", "performance_tick_overflow"}},
        });
      }
      tick = pad->onset_tick + pad->duration_tick;
    }
    result = std::max(result, tick);
  }
  return foundation::Result<std::uint64_t>::success(result);
}

nlohmann::json performance_checkpoint_json(
    const PerformanceTransientCheckpoint& checkpoint) {
  auto pads = nlohmann::json::array();
  for (const auto& pad : checkpoint.open_pads) {
    auto encoded = nlohmann::json{
        {"gesture_id", pad.gesture_id},
        {"onset_tick", pad.onset_tick},
        {"slot", pad.slot},
        {"velocity", pad.velocity},
    };
    if (pad.input_sequence.has_value()) {
      encoded["input_sequence"] = std::to_string(*pad.input_sequence);
    }
    pads.push_back(std::move(encoded));
  }
  auto effects = nlohmann::json::array();
  for (const auto& effect : checkpoint.open_fx) {
    effects.push_back({
        {"effective_value", effect.effective_value},
        {"fx", performance_fx_name(effect.fx)},
        {"gesture_id", effect.gesture_id},
        {"pending_value",
         effect.pending_value.has_value()
             ? nlohmann::json(*effect.pending_value)
             : nlohmann::json(nullptr)},
    });
  }
  auto encoded = nlohmann::json{
      {"hold", checkpoint.hold},
      {"last_accepted_tick", checkpoint.last_accepted_tick},
      {"open_fx", std::move(effects)},
      {"open_pads", std::move(pads)},
  };
  if (checkpoint.open_filter.has_value() || checkpoint.live_state.has_value()) {
    encoded["open_filter"] =
        checkpoint.open_filter.has_value()
            ? open_filter_json(*checkpoint.open_filter)
            : nlohmann::json(nullptr);
    encoded["live_state"] =
        checkpoint.live_state.has_value()
            ? domain::performance_initial_live_state_json(
                  *checkpoint.live_state)
            : nlohmann::json(nullptr);
  }
  return encoded;
}

nlohmann::json performance_launch_ack_json(
    const PerformanceLaunchAck& ack) {
  return {
      {"effective_tick", ack.effective_tick},
      {"pattern_slot", ack.pattern_slot},
      {"request_id", ack.request_id.value()},
  };
}

foundation::Result<void> validate_performance_launch_ack(
    const PerformanceLaunchAck& ack,
    std::span<const domain::PerformanceEvent> events) {
  const auto matching_event = std::ranges::any_of(
      events, [&ack](const domain::PerformanceEvent& event) {
        const auto* launch =
            std::get_if<domain::PatternLaunchPerformanceEvent>(&event.payload);
        return launch != nullptr && launch->pattern_slot == ack.pattern_slot &&
               launch->effective_tick == ack.effective_tick;
      });
  if (!domain::is_valid_uuid(ack.request_id.value()) ||
      ack.pattern_slot >= domain::kPatternSlotCount || !matching_event) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance launch acknowledgement does not match durable events",
        {{"reason", "performance_launch_ack_invalid"},
         {"remedy",
          "retain the journal and repair the launch acknowledgement to match "
          "its exact durable Pattern launch event"}},
    });
  }
  return foundation::Result<void>::success();
}

std::size_t performance_launch_occurrences(
    std::span<const domain::PerformanceEvent> events,
    const PerformanceLaunchAck& ack) {
  return static_cast<std::size_t>(std::ranges::count_if(
      events, [&ack](const domain::PerformanceEvent& event) {
        const auto* launch =
            std::get_if<domain::PatternLaunchPerformanceEvent>(&event.payload);
        return launch != nullptr && launch->pattern_slot == ack.pattern_slot &&
               launch->effective_tick == ack.effective_tick;
      }));
}

foundation::Result<void> validate_performance_launch_ack_transition(
    std::span<const domain::PerformanceEvent> previous_pending_events,
    std::span<const domain::PerformanceEvent> next_pending_events,
    const std::optional<PerformanceLaunchAck>& previous_ack,
    const std::optional<PerformanceLaunchAck>& next_ack) {
  if (next_ack == previous_ack) {
    return foundation::Result<void>::success();
  }
  const bool added_exact_launch =
      next_ack.has_value() &&
      performance_launch_occurrences(next_pending_events, *next_ack) ==
          performance_launch_occurrences(previous_pending_events, *next_ack) +
              1U;
  if (!added_exact_launch) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance launch acknowledgement is not bound to this tail",
        {{"reason", "performance_launch_ack_invalid"},
         {"remedy",
          "retain the previous acknowledgement, or append exactly one matching "
          "Pattern launch event with the new request identity"}},
    });
  }
  return foundation::Result<void>::success();
}

foundation::Result<PerformanceLaunchAck> parse_performance_launch_ack(
    const nlohmann::json& input,
    std::span<const domain::PerformanceEvent> events,
    const std::filesystem::path& path) {
  try {
    if (!input.is_object() || input.size() != 3 ||
        !input.contains("effective_tick") ||
        !input.contains("pattern_slot") || !input.contains("request_id") ||
        !input.at("effective_tick").is_number_unsigned() ||
        !input.at("pattern_slot").is_number_unsigned() ||
        !input.at("request_id").is_string()) {
      throw std::runtime_error(
          "Performance launch acknowledgement shape is invalid");
    }
    const auto pattern_slot = input.at("pattern_slot").get<std::uint64_t>();
    if (pattern_slot > std::numeric_limits<std::uint8_t>::max()) {
      throw std::runtime_error(
          "Performance launch acknowledgement slot is out of range");
    }
    PerformanceLaunchAck ack{
        foundation::CommandId{input.at("request_id").get<std::string>()},
        static_cast<std::uint8_t>(pattern_slot),
        input.at("effective_tick").get<std::uint64_t>(),
    };
    auto valid = validate_performance_launch_ack(ack, events);
    if (!valid.has_value()) {
      throw std::runtime_error(valid.error().message);
    }
    return foundation::Result<PerformanceLaunchAck>::success(std::move(ack));
  } catch (const std::exception& exception) {
    return foundation::Result<PerformanceLaunchAck>::failure(Error{
        ErrorCode::invalid_project,
        "Performance launch acknowledgement is invalid and has been retained",
        {{"detail", exception.what()},
         {"path", path.generic_string()},
         {"reason", "performance_launch_ack_invalid"},
         {"recovery_retained", true},
         {"remedy",
          "retain the recovery file; repair its launch acknowledgement to "
          "match the exact durable Pattern launch event"}},
    });
  }
}

foundation::Result<void> validate_performance_checkpoint(
    const PerformanceTransientCheckpoint& checkpoint,
    std::span<const domain::PerformanceEvent> events,
    bool live_profile) {
  if (!std::ranges::is_sorted(
          checkpoint.open_pads,
          {},
          [](const auto& pad) {
            return std::pair{pad.slot, pad.gesture_id};
          }) ||
      !std::ranges::is_sorted(
          checkpoint.open_fx,
          {},
          [](const auto& effect) {
            return static_cast<std::uint8_t>(effect.fx);
          })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance transient checkpoint is not canonical",
    });
  }
  std::unordered_set<std::string> gesture_ids;
  for (std::size_t index = 0; index < checkpoint.open_pads.size(); ++index) {
    const auto& pad = checkpoint.open_pads.at(index);
    if (!domain::is_valid_uuid(pad.gesture_id) ||
        pad.slot > domain::kPerformancePadSlotMax || pad.velocity == 0 ||
        pad.velocity > 127 || pad.onset_tick > checkpoint.last_accepted_tick ||
        !gesture_ids.insert(pad.gesture_id).second) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance open Pad checkpoint is invalid",
      });
    }
    if (live_profile != pad.input_sequence.has_value()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance open Pad checkpoint input sequence is invalid",
      });
    }
  }
  for (std::size_t index = 0; index < checkpoint.open_fx.size(); ++index) {
    const auto& effect = checkpoint.open_fx.at(index);
    const auto fx = static_cast<std::size_t>(effect.fx);
    if (fx >= kPerformanceFxNames.size() ||
        !domain::is_valid_uuid(effect.gesture_id) ||
        effect.effective_value > 1'000 ||
        (effect.pending_value.has_value() && *effect.pending_value > 1'000) ||
        (index != 0 && checkpoint.open_fx.at(index - 1).fx == effect.fx) ||
        !gesture_ids.insert(effect.gesture_id).second) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance open FX checkpoint is invalid",
      });
    }
  }
  if (!live_profile) {
    return foundation::Result<void>::success();
  }
  // Headered profile: the checkpoint carries the complete current live state
  // and never two Filter bindings. A legacy-mode Filter gesture stays in
  // open_fx; an engaged independent Filter has the only open_filter gesture;
  // a frozen-only Filter is live state, not an open gesture.
  if (!checkpoint.live_state.has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance live checkpoint is missing the current live state",
    });
  }
  const auto& live_state = *checkpoint.live_state;
  if (live_state.hold != checkpoint.hold) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance live checkpoint HOLD state is inconsistent",
    });
  }
  const auto legacy_filter_open = std::ranges::any_of(
      checkpoint.open_fx,
      [](const auto& effect) {
        return effect.fx == domain::PerformanceFx::filter;
      });
  // The single Filter stage never has two bindings; zero bindings is simply
  // a disengaged Filter.
  if (legacy_filter_open && checkpoint.open_filter.has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance live checkpoint carries two Filter bindings",
    });
  }
  const auto* independent =
      std::get_if<domain::IndependentFilterLiveState>(&live_state.filter);
  const auto* legacy =
      std::get_if<domain::LegacyFilterLiveState>(&live_state.filter);
  if (checkpoint.open_filter.has_value()) {
    if (independent == nullptr || !independent->engaged ||
        !gesture_ids.insert(checkpoint.open_filter->gesture_id).second) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance open Filter checkpoint is invalid",
      });
    }
  } else if (independent != nullptr && independent->engaged) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance engaged independent Filter has no open gesture",
    });
  }
  if (legacy_filter_open && (legacy == nullptr || !legacy->engaged)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance legacy Filter gesture lacks its live state",
    });
  }
  (void)events;
  return foundation::Result<void>::success();
}

foundation::Result<PerformanceTransientCheckpoint>
parse_performance_checkpoint(
    const nlohmann::json& input,
    std::span<const domain::PerformanceEvent> events,
    const std::filesystem::path& path,
    bool live_profile) {
  try {
    const auto expected_keys = live_profile ? 6U : 4U;
    if (!input.is_object() || input.size() != expected_keys ||
        !input.contains("hold") || !input.contains("last_accepted_tick") ||
        !input.contains("open_fx") || !input.contains("open_pads") ||
        !input.at("hold").is_boolean() ||
        !input.at("last_accepted_tick").is_number_unsigned() ||
        !input.at("open_fx").is_array() ||
        !input.at("open_pads").is_array() ||
        (live_profile &&
         (!input.contains("open_filter") || !input.contains("live_state")))) {
      throw std::runtime_error(
          "Performance transient checkpoint shape is invalid");
    }
    PerformanceTransientCheckpoint checkpoint{
        {},
        {},
        input.at("hold").get<bool>(),
        input.at("last_accepted_tick").get<std::uint64_t>(),
    };
    for (const auto& encoded : input.at("open_pads")) {
      const auto pad_keys = live_profile ? 5U : 4U;
      if (!encoded.is_object() || encoded.size() != pad_keys ||
          !encoded.contains("gesture_id") ||
          !encoded.contains("onset_tick") || !encoded.contains("slot") ||
          !encoded.contains("velocity") ||
          !encoded.at("gesture_id").is_string() ||
          !encoded.at("onset_tick").is_number_unsigned() ||
          !encoded.at("slot").is_number_unsigned() ||
          !encoded.at("velocity").is_number_unsigned() ||
          (live_profile && !encoded.contains("input_sequence"))) {
        throw std::runtime_error(
            "Performance open Pad checkpoint shape is invalid");
      }
      const auto slot = encoded.at("slot").get<std::uint64_t>();
      const auto velocity = encoded.at("velocity").get<std::uint64_t>();
      if (slot > std::numeric_limits<std::uint8_t>::max() ||
          velocity > std::numeric_limits<std::uint8_t>::max()) {
        throw std::runtime_error(
            "Performance open Pad checkpoint number is out of range");
      }
      PerformanceOpenPadTransient pad{
          encoded.at("gesture_id").get<std::string>(),
          static_cast<std::uint8_t>(slot),
          encoded.at("onset_tick").get<std::uint64_t>(),
          static_cast<std::uint8_t>(velocity),
      };
      if (live_profile) {
        const auto sequence =
            parse_bounded_decimal(encoded.at("input_sequence"), 1);
        if (!sequence.has_value()) {
          throw std::runtime_error(
              "Performance open Pad checkpoint input sequence is invalid");
        }
        pad.input_sequence = *sequence;
      }
      checkpoint.open_pads.push_back(std::move(pad));
    }
    for (const auto& encoded : input.at("open_fx")) {
      if (!encoded.is_object() || encoded.size() != 4 ||
          !encoded.contains("effective_value") || !encoded.contains("fx") ||
          !encoded.contains("gesture_id") ||
          !encoded.contains("pending_value") ||
          !encoded.at("effective_value").is_number_unsigned() ||
          !encoded.at("fx").is_string() ||
          !encoded.at("gesture_id").is_string() ||
          (!encoded.at("pending_value").is_null() &&
           !encoded.at("pending_value").is_number_unsigned())) {
        throw std::runtime_error(
            "Performance open FX checkpoint shape is invalid");
      }
      const auto effective_value =
          encoded.at("effective_value").get<std::uint64_t>();
      if (effective_value > std::numeric_limits<std::uint16_t>::max()) {
        throw std::runtime_error(
            "Performance open FX checkpoint number is out of range");
      }
      PerformanceOpenFxTransient effect{
          parse_performance_fx(encoded.at("fx").get<std::string>()),
          encoded.at("gesture_id").get<std::string>(),
          static_cast<std::uint16_t>(effective_value),
          std::nullopt,
      };
      if (!encoded.at("pending_value").is_null()) {
        const auto pending_value =
            encoded.at("pending_value").get<std::uint64_t>();
        if (pending_value > std::numeric_limits<std::uint16_t>::max()) {
          throw std::runtime_error(
              "Performance open FX checkpoint number is out of range");
        }
        effect.pending_value = static_cast<std::uint16_t>(pending_value);
      }
      checkpoint.open_fx.push_back(std::move(effect));
    }
    if (live_profile) {
      if (!input.at("open_filter").is_null()) {
        checkpoint.open_filter =
            parse_open_filter(input.at("open_filter"));
      }
      auto live_state = domain::performance_initial_live_state_from_json(
          input.at("live_state"));
      if (!live_state.has_value()) {
        throw std::runtime_error(
            "Performance live checkpoint state is invalid");
      }
      checkpoint.live_state = std::move(live_state.value());
    }
    auto valid =
        validate_performance_checkpoint(checkpoint, events, live_profile);
    if (!valid.has_value()) {
      throw std::runtime_error(valid.error().message);
    }
    return foundation::Result<PerformanceTransientCheckpoint>::success(
        std::move(checkpoint));
  } catch (const std::exception& exception) {
    return foundation::Result<PerformanceTransientCheckpoint>::failure(Error{
        ErrorCode::invalid_project,
        "Performance transient checkpoint is invalid and has been retained",
        {{"detail", exception.what()},
         {"journal_retained", true},
         {"path", path.generic_string()},
         {"reason", "performance_transient_checkpoint_invalid"}},
    });
  }
}

foundation::Result<void> validate_performance_event_structure(
    std::span<const domain::PerformanceEvent> events) {
  for (const auto& event : events) {
    auto parsed = domain::performance_event_from_json(
        domain::performance_event_json(event));
    if (!parsed.has_value() || parsed.value() != event) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance event contains an invalid field value",
      });
    }
  }
  return foundation::Result<void>::success();
}

foundation::Result<std::vector<domain::PerformanceEvent>>
parse_performance_events(
    const nlohmann::json& input,
    const std::filesystem::path& path,
    bool live_profile) {
  if (!input.is_array()) {
    return foundation::Result<
        std::vector<domain::PerformanceEvent>>::failure(Error{
        ErrorCode::invalid_project,
        "Performance Journal events are not an array",
        {{"path", path.generic_string()}},
    });
  }
  std::vector<domain::PerformanceEvent> events;
  for (const auto& encoded : input) {
    auto parsed = domain::performance_event_from_json(encoded);
    if (!parsed.has_value()) {
      auto error = parsed.error();
      error.details["path"] = path.generic_string();
      return foundation::Result<
          std::vector<domain::PerformanceEvent>>::failure(std::move(error));
    }
    if (live_profile != parsed.value().input_sequence.has_value()) {
      return foundation::Result<
          std::vector<domain::PerformanceEvent>>::failure(Error{
          ErrorCode::invalid_project,
          "Performance Journal event profile does not match its Journal",
          {{"path", path.generic_string()}},
      });
    }
    events.push_back(std::move(parsed.value()));
  }
  const auto canonical = domain::canonical_performance_events(
      events,
      live_profile ? domain::PerformanceEventProfile::header_input_sequence
                   : domain::PerformanceEventProfile::legacy);
  if (canonical != events) {
    return foundation::Result<
        std::vector<domain::PerformanceEvent>>::failure(Error{
        ErrorCode::invalid_project,
        "Performance Journal events are not canonical",
        {{"path", path.generic_string()}},
    });
  }
  return foundation::Result<std::vector<domain::PerformanceEvent>>::success(
      std::move(events));
}

nlohmann::json performance_flush_json(const PerformanceFlushRecord& flush) {
  return {
      {"command_id", flush.command_id.value()},
      {"events", performance_events_json(flush.canonical_events)},
      {"expected_revision", flush.expected_revision},
      {"flush_seq", flush.flush_seq},
      {"kind", "flush"},
      {"performance_id", flush.performance_id.value()},
  };
}

nlohmann::json performance_journal_json(
    const ActivePerformanceJournal& journal) {
  auto flushes = nlohmann::json::array();
  for (const auto& flush : journal.flushes) {
    auto encoded = performance_flush_json(flush);
    encoded["completed"] = flush.completed;
    flushes.push_back(std::move(encoded));
  }
  auto rebases = nlohmann::json::array();
  for (const auto& rebase : journal.rebases) {
    rebases.push_back({
        {"bpm_anchor",
         rebase.bpm_anchor.has_value()
             ? nlohmann::json(*rebase.bpm_anchor)
             : nlohmann::json(nullptr)},
        {"command_fingerprint", rebase.command_fingerprint},
        {"command_id", rebase.command_id.value()},
        {"completed", rebase.completed},
        {"from_revision", rebase.from_revision},
        {"to_revision", rebase.to_revision},
    });
  }
  auto encoded = nlohmann::json{
      {"begin_command_id",
       journal.begin_command_id.has_value()
           ? nlohmann::json(journal.begin_command_id->value())
           : nlohmann::json(nullptr)},
      {"expected_revision", journal.expected_revision},
      {"flushes", std::move(flushes)},
      {"last_input_sequence",
       journal.last_input_sequence.has_value()
           ? nlohmann::json(*journal.last_input_sequence)
           : nlohmann::json(nullptr)},
      {"last_launch_ack",
       journal.last_launch_ack.has_value()
           ? performance_launch_ack_json(*journal.last_launch_ack)
           : nlohmann::json(nullptr)},
      {"next_flush_seq", journal.next_flush_seq},
      {"next_tail_seq", journal.next_tail_seq},
      {"pending_events", performance_events_json(journal.pending_events)},
      {"performance_fingerprint", journal.performance_fingerprint},
      {"performance_id", journal.performance_id.value()},
      {"session_id", journal.session_id.value()},
      {"stop_request_id",
       journal.stop_request_id.has_value()
           ? nlohmann::json(journal.stop_request_id->value())
           : nlohmann::json(nullptr)},
      {"rebases", std::move(rebases)},
      {"state", state_string(journal.state)},
      {"transient_checkpoint",
       journal.transient_checkpoint.has_value()
           ? performance_checkpoint_json(*journal.transient_checkpoint)
           : nlohmann::json(nullptr)},
  };
  if (is_live_control_profile(journal)) {
    // The sealed snapshot keeps the profile discriminator, the immutable
    // begin header and the ledger exactly as they stand; a terminal pending
    // admission stays unknown rather than being rewritten.
    encoded["live_control_profile"] =
        std::string{kLiveControlProfileHeaderInputSequence};
    encoded["initial_live_state"] =
        domain::performance_initial_live_state_json(
            *journal.initial_live_state);
    encoded["admission_ledger"] =
        admission_ledger_json(*journal.admission_ledger);
  }
  return encoded;
}

foundation::Result<ActivePerformanceJournal> parse_performance_snapshot(
    const nlohmann::json& input,
    const std::filesystem::path& path) {
  try {
    ActivePerformanceJournal journal{
        foundation::SequenceSessionId{
            input.at("session_id").get<std::string>()},
        domain::PerformanceId{
            input.at("performance_id").get<std::string>()},
        input.at("performance_fingerprint").get<std::string>(),
        input.at("expected_revision").get<std::uint64_t>(),
        input.at("next_flush_seq").get<std::uint64_t>(),
        parse_state(input.at("state").get<std::string>()),
        {},
        input.at("next_tail_seq").get<std::uint64_t>(),
        std::nullopt,
        {},
        SessionKind::performance,
        std::nullopt,
        std::nullopt,
        {},
        std::nullopt,
        std::nullopt,
        std::nullopt,
        std::nullopt,
    };
    if (!domain::is_valid_uuid(journal.session_id.value()) ||
        !domain::is_valid_uuid(journal.performance_id.value()) ||
        !lowercase_sha256(journal.performance_fingerprint)) {
      throw std::runtime_error("Performance recovery metadata is invalid");
    }
    // The discriminator selects the grammar explicitly; a legacy v1 snapshot
    // never carries it, and an unknown value fails closed.
    if (input.contains("live_control_profile")) {
      if (!input.at("live_control_profile").is_string() ||
          input.at("live_control_profile").get<std::string>() !=
              kLiveControlProfileHeaderInputSequence ||
          !input.contains("initial_live_state") ||
          !input.contains("admission_ledger")) {
        throw std::runtime_error(
            "Performance recovery live control profile is invalid");
      }
      auto header = domain::performance_initial_live_state_from_json(
          input.at("initial_live_state"));
      if (!header.has_value()) {
        throw std::runtime_error(
            "Performance recovery initial live state is invalid");
      }
      journal.initial_live_state = std::move(header.value());
      journal.admission_ledger =
          parse_admission_ledger(input.at("admission_ledger"));
    }
    const bool live_profile = journal.initial_live_state.has_value();
    if (!input.at("last_input_sequence").is_null()) {
      journal.last_input_sequence =
          input.at("last_input_sequence").get<std::uint64_t>();
    }
    if (input.contains("begin_command_id") &&
        !input.at("begin_command_id").is_null()) {
      journal.begin_command_id = foundation::CommandId{
          input.at("begin_command_id").get<std::string>()};
    }
    if (input.contains("stop_request_id") &&
        !input.at("stop_request_id").is_null()) {
      journal.stop_request_id = foundation::CommandId{
          input.at("stop_request_id").get<std::string>()};
    }
    if (input.contains("rebases")) {
      for (const auto& encoded : input.at("rebases")) {
        PerformanceRebaseRecord rebase{
            foundation::CommandId{
                encoded.at("command_id").get<std::string>()},
            encoded.at("command_fingerprint").get<std::string>(),
            encoded.at("from_revision").get<std::uint64_t>(),
            encoded.at("to_revision").get<std::uint64_t>(),
            std::nullopt,
            encoded.at("completed").get<bool>(),
        };
        if (!encoded.at("bpm_anchor").is_null()) {
          rebase.bpm_anchor =
              encoded.at("bpm_anchor").get<std::uint16_t>();
        }
        journal.rebases.push_back(std::move(rebase));
      }
    }
    auto pending =
        parse_performance_events(input.at("pending_events"), path, live_profile);
    if (!pending.has_value()) {
      return foundation::Result<ActivePerformanceJournal>::failure(
          pending.error());
    }
    journal.pending_events = std::move(pending.value());
    for (const auto& encoded : input.at("flushes")) {
      auto events =
          parse_performance_events(encoded.at("events"), path, live_profile);
      if (!events.has_value()) {
        return foundation::Result<ActivePerformanceJournal>::failure(
            events.error());
      }
      PerformanceFlushRecord flush{
          encoded.at("flush_seq").get<std::uint64_t>(),
          foundation::CommandId{
              encoded.at("command_id").get<std::string>()},
          domain::PerformanceId{
              encoded.at("performance_id").get<std::string>()},
          encoded.at("expected_revision").get<std::uint64_t>(),
          std::move(events.value()),
          encoded.at("completed").get<bool>(),
      };
      if (!domain::is_valid_uuid(flush.command_id.value()) ||
          !recording_command_is_new(journal.flushes, flush.command_id) ||
          flush.performance_id != journal.performance_id ||
          flush.flush_seq != journal.flushes.size() ||
          flush.canonical_events.empty() ||
          (!recording_protocol(journal.kind).cumulative_flushes &&
           std::ranges::any_of(
               journal.flushes,
               [](const auto& candidate) {
                 return !candidate.completed;
               }))) {
        throw std::runtime_error(
            "Performance recovery flush identity is invalid");
      }
      if (!journal.flushes.empty()) {
        const auto& predecessor = journal.flushes.back();
        const auto next_revision = predecessor.expected_revision + 1;
        if (!predecessor.completed ||
            flush.expected_revision != next_revision) {
          throw std::runtime_error(
              "Performance recovery flush revision is invalid");
        }
      }
      journal.flushes.push_back(std::move(flush));
    }
    if (input.contains("transient_checkpoint") &&
        !input.at("transient_checkpoint").is_null()) {
      std::vector<domain::PerformanceEvent> durable_events =
          journal.pending_events;
      for (const auto& flush : journal.flushes) {
        durable_events.insert(
            durable_events.end(),
            flush.canonical_events.begin(),
            flush.canonical_events.end());
      }
      auto checkpoint = parse_performance_checkpoint(
          input.at("transient_checkpoint"), durable_events, path,
          live_profile);
      if (!checkpoint.has_value()) {
        return foundation::Result<ActivePerformanceJournal>::failure(
            checkpoint.error());
      }
      journal.transient_checkpoint = std::move(checkpoint.value());
    }
    if (input.contains("last_launch_ack") &&
        !input.at("last_launch_ack").is_null()) {
      std::vector<domain::PerformanceEvent> durable_events =
          journal.pending_events;
      for (const auto& flush : journal.flushes) {
        durable_events.insert(
            durable_events.end(), flush.canonical_events.begin(),
            flush.canonical_events.end());
      }
      auto ack = parse_performance_launch_ack(
          input.at("last_launch_ack"), durable_events, path);
      if (!ack.has_value()) {
        return foundation::Result<ActivePerformanceJournal>::failure(
            ack.error());
      }
      journal.last_launch_ack = std::move(ack.value());
    }
    if (journal.next_flush_seq != journal.flushes.size()) {
      throw std::runtime_error(
          "Performance recovery flush sequence is invalid");
    }
    if (!journal.flushes.empty()) {
      const auto& last = journal.flushes.back();
      const auto visible_revision =
          last.expected_revision + (last.completed ? 1 : 0);
      if (journal.expected_revision != visible_revision ||
          (!last.completed && !journal.pending_events.empty())) {
        throw std::runtime_error(
            "Performance recovery revision state is invalid");
      }
    }
    if (!journal.transient_checkpoint.has_value()) {
      if (journal.state != SequenceSessionState::stopped || live_profile) {
        throw std::runtime_error(
            "active legacy Performance recovery has no transient checkpoint");
      }
      std::vector<domain::PerformanceEvent> durable_events =
          journal.pending_events;
      for (const auto& flush : journal.flushes) {
        durable_events.insert(
            durable_events.end(),
            flush.canonical_events.begin(),
            flush.canonical_events.end());
      }
      auto high_water = performance_temporal_high_water(durable_events);
      if (!high_water.has_value()) {
        throw std::runtime_error(high_water.error().message);
      }
      journal.transient_checkpoint = PerformanceTransientCheckpoint{
          {}, {}, false, high_water.value()};
    }
    return foundation::Result<ActivePerformanceJournal>::success(
        std::move(journal));
  } catch (const std::exception& exception) {
    return foundation::Result<ActivePerformanceJournal>::failure(Error{
        ErrorCode::invalid_project,
        "Performance recovery payload is invalid and has been retained",
        {{"detail", exception.what()},
         {"path", path.generic_string()},
         {"reason", "performance_recovery_payload_invalid"},
         {"recovery_retained", true},
         {"remedy",
          "retain the recovery file; repair its versioned payload or discard "
          "this recovery candidate explicitly"}},
    });
  }
}

foundation::Result<PerformanceJournalDocument> read_performance_journal(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  auto checked = read_checked_journal_records(
      platform, bundle, SessionKind::performance);
  if (!checked.has_value()) {
    return foundation::Result<PerformanceJournalDocument>::failure(
        checked.error());
  }
  const auto path = recording_active_path(bundle, SessionKind::performance);
  PerformanceJournalDocument document{
      ActivePerformanceJournal{
          foundation::SequenceSessionId{""},
          domain::PerformanceId{""},
          {},
          0,
          0,
          SequenceSessionState::active,
          {},
          0,
          std::nullopt,
          {},
          SessionKind::performance,
          std::nullopt,
          std::nullopt,
          {},
          std::nullopt,
          std::nullopt,
          std::nullopt,
          std::nullopt,
      },
      checked.value().valid_prefix_length,
  };
  bool saw_begin = false;
  bool saw_transient_checkpoint = false;
  bool saw_launch_ack_field = false;
  try {
    for (const auto& record : checked.value().records) {
      auto payload = foundation::Result<nlohmann::json>::success(
          record.payload);
      const auto kind = payload.value().at("kind").get<std::string>();
      if (!saw_begin) {
        const bool live_profile =
            payload.value().contains("live_control_profile");
        if (kind != "begin" ||
            payload.value().at("contract") !=
                recording_protocol(SessionKind::performance)
                    .journal_contract) {
          throw std::runtime_error(
              "first record is not a Performance begin");
        }
        if (live_profile) {
          // The discriminator is explicit and the grammar closed; a legacy
          // v1 begin never grows these keys.
          const auto& begin_payload = payload.value();
          if ((begin_payload.size() != 10 && begin_payload.size() != 11) ||
              !begin_payload.at("live_control_profile").is_string() ||
              begin_payload.at("live_control_profile").get<std::string>() !=
                  kLiveControlProfileHeaderInputSequence ||
              !begin_payload.contains("initial_live_state") ||
              !begin_payload.contains("admission_ledger") ||
              !begin_payload.contains("transient_checkpoint")) {
            throw std::runtime_error(
                "Performance live-control begin grammar is invalid");
          }
        } else if (
            payload.value().size() != 6 && payload.value().size() != 7 &&
            payload.value().size() != 8) {
          throw std::runtime_error(
              "first record is not a Performance begin");
        }
        document.journal = ActivePerformanceJournal{
            foundation::SequenceSessionId{
                payload.value().at("session_id").get<std::string>()},
            domain::PerformanceId{
                payload.value().at("performance_id").get<std::string>()},
            payload.value().at("performance_fingerprint").get<std::string>(),
            payload.value().at("expected_revision").get<std::uint64_t>(),
            0,
            SequenceSessionState::active,
            {},
            0,
            std::nullopt,
            {},
            SessionKind::performance,
            std::nullopt,
            std::nullopt,
            {},
            std::nullopt,
            std::nullopt,
            std::nullopt,
            std::nullopt,
        };
        if (live_profile) {
          auto header = domain::performance_initial_live_state_from_json(
              payload.value().at("initial_live_state"));
          if (!header.has_value()) {
            throw std::runtime_error(
                "Performance begin initial live state is invalid");
          }
          document.journal.initial_live_state = std::move(header.value());
          document.journal.admission_ledger =
              parse_admission_ledger(payload.value().at("admission_ledger"));
          // Write paths create an empty ledger at begin; a restored stopped
          // Journal carries its terminal one. Both are coherent producers.
        }
        if (payload.value().contains("command_id")) {
          document.journal.begin_command_id = foundation::CommandId{
              payload.value().at("command_id").get<std::string>()};
          document.journal.state =
              SequenceSessionState::recovery_required;
        }
        if (payload.value().contains("transient_checkpoint")) {
          auto checkpoint = parse_performance_checkpoint(
              payload.value().at("transient_checkpoint"), {}, path,
              live_profile);
          if (!checkpoint.has_value()) {
            return foundation::Result<PerformanceJournalDocument>::failure(
                checkpoint.error());
          }
          document.journal.transient_checkpoint =
              std::move(checkpoint.value());
          saw_transient_checkpoint = true;
        }
        if (!domain::is_valid_uuid(document.journal.session_id.value()) ||
            !domain::is_valid_uuid(document.journal.performance_id.value()) ||
            !lowercase_sha256(
                document.journal.performance_fingerprint)) {
          throw std::runtime_error("Performance begin metadata is invalid");
        }
        saw_begin = true;
      } else if (kind == "begin-complete") {
        const auto committed_revision =
            payload.value().at("committed_revision").get<std::uint64_t>();
        const auto fingerprint = payload.value()
                                     .at("performance_fingerprint")
                                     .get<std::string>();
        if (!document.journal.begin_command_id.has_value() ||
            committed_revision != document.journal.expected_revision + 1 ||
            !lowercase_sha256(fingerprint)) {
          throw std::runtime_error(
              "Performance draft begin completion is invalid");
        }
        document.journal.expected_revision = committed_revision;
        document.journal.performance_fingerprint = fingerprint;
        document.journal.state = SequenceSessionState::active;
      } else if (kind == "tail") {
        const bool live_profile = is_live_control_profile(document.journal);
        const bool has_checkpoint =
            payload.value().contains("transient_checkpoint");
        const bool has_launch_ack =
            payload.value().contains("last_launch_ack");
        const bool has_ledger = payload.value().contains("admission_ledger");
        const auto expected_size =
            (live_profile ? std::size_t{8} : std::size_t{6}) +
            (live_profile ? 0U : (has_checkpoint ? 1U : 0U)) +
            (has_launch_ack ? 1U : 0U);
        // The headered profile fixes its tail shape: extended checkpoint and
        // admission ledger are always present. A legacy Journal rejects them.
        if (live_profile != has_ledger ||
            (live_profile && !has_checkpoint) ||
            payload.value().size() != expected_size ||
            (has_launch_ack && !has_checkpoint) ||
            (saw_transient_checkpoint && !has_checkpoint) ||
            (saw_launch_ack_field && !has_launch_ack)) {
          throw std::runtime_error("Performance tail shape is invalid");
        }
        const auto tail_seq =
            payload.value().at("tail_seq").get<std::uint64_t>();
        const auto input_sequence =
            payload.value().at("input_sequence").get<std::uint64_t>();
        const auto performance_id = domain::PerformanceId{
            payload.value().at("performance_id").get<std::string>()};
        const auto expected_revision =
            payload.value().at("expected_revision").get<std::uint64_t>();
        if (tail_seq != document.journal.next_tail_seq ||
            input_sequence == 0 ||
            performance_id != document.journal.performance_id ||
            expected_revision != document.journal.expected_revision ||
            (document.journal.last_input_sequence.has_value() &&
             input_sequence <= *document.journal.last_input_sequence) ||
            !recording_accepts_tail(
                document.journal.kind,
                document.journal.state,
                document.journal.flushes)) {
          throw std::runtime_error(
              "Performance tail identity is invalid");
        }
        auto events = parse_performance_events(
            payload.value().at("events"), path, live_profile);
        if (!events.has_value() ||
            (events.value().empty() && !has_checkpoint)) {
          throw std::runtime_error("Performance tail events are invalid");
        }
        std::optional<PerformanceTransientCheckpoint> checkpoint;
        std::vector<domain::PerformanceEvent> durable_events = events.value();
        for (const auto& flush : document.journal.flushes) {
          durable_events.insert(
              durable_events.end(), flush.canonical_events.begin(),
              flush.canonical_events.end());
        }
        if (has_checkpoint) {
          auto parsed = parse_performance_checkpoint(
              payload.value().at("transient_checkpoint"), durable_events, path,
              live_profile);
          if (!parsed.has_value()) {
            return foundation::Result<PerformanceJournalDocument>::failure(
                parsed.error());
          }
          checkpoint = std::move(parsed.value());
          if (document.journal.transient_checkpoint.has_value() &&
              checkpoint->last_accepted_tick <
                  document.journal.transient_checkpoint->last_accepted_tick) {
            throw std::runtime_error(
                "Performance checkpoint tick is not monotone");
          }
        }
        std::optional<PerformanceAdmissionLedger> ledger;
        if (live_profile) {
          // The high-water covers every sequence this admission allocated,
          // including internal ones that never became durable events.
          ledger = parse_admission_ledger(payload.value().at("admission_ledger"));
          const auto& previous = *document.journal.admission_ledger;
          const auto receipt_within_window = [&]() {
            if (!ledger->pending.has_value()) {
              return true;
            }
            const auto& pending = *ledger->pending;
            if (pending.expected_recording_sequence !=
                    previous.next_recording_sequence ||
                pending.input_sequence > input_sequence) {
              return false;
            }
            return std::ranges::all_of(
                pending.event_input_sequences,
                [input_sequence](std::uint64_t sequence) {
                  return sequence <= input_sequence;
                });
          };
          const bool carries_new_pending =
              ledger->pending.has_value() && !previous.pending.has_value() &&
              ledger->next_recording_sequence ==
                  previous.next_recording_sequence &&
              ledger->completed == previous.completed;
          const bool carries_existing =
              ledger->pending == previous.pending &&
              ledger->next_recording_sequence ==
                  previous.next_recording_sequence &&
              ledger->completed == previous.completed;
          // Every durable event sequence stays under the tail's high-water.
          const auto events_within_window = std::ranges::all_of(
              events.value(), [input_sequence](const auto& event) {
                return *event.input_sequence <= input_sequence;
              });
          if ((!carries_new_pending && !carries_existing) ||
              !receipt_within_window() || !events_within_window) {
            throw std::runtime_error(
                "Performance tail admission ledger transition is invalid");
          }
        }
        std::optional<PerformanceLaunchAck> launch_ack;
        if (has_launch_ack && !payload.value().at("last_launch_ack").is_null()) {
          auto parsed = parse_performance_launch_ack(
              payload.value().at("last_launch_ack"), durable_events, path);
          if (!parsed.has_value()) {
            return foundation::Result<PerformanceJournalDocument>::failure(
                parsed.error());
          }
          launch_ack = std::move(parsed.value());
        }
        if (has_launch_ack) {
          auto transition = validate_performance_launch_ack_transition(
              document.journal.pending_events, events.value(),
              document.journal.last_launch_ack, launch_ack);
          if (!transition.has_value()) {
            throw std::runtime_error(transition.error().message);
          }
        }
        if (events.value().empty() &&
            events.value() == document.journal.pending_events &&
            document.journal.transient_checkpoint.has_value() &&
            checkpoint.has_value() &&
            *checkpoint == *document.journal.transient_checkpoint &&
            (!has_launch_ack ||
             launch_ack == document.journal.last_launch_ack) &&
            (!live_profile ||
             *ledger == *document.journal.admission_ledger)) {
          throw std::runtime_error("Performance tail is a no-op");
        }
        document.journal.pending_events = std::move(events.value());
        if (checkpoint.has_value()) {
          document.journal.transient_checkpoint = std::move(checkpoint);
          saw_transient_checkpoint = true;
        }
        if (has_launch_ack) {
          document.journal.last_launch_ack = std::move(launch_ack);
          saw_launch_ack_field = true;
        }
        if (live_profile) {
          document.journal.admission_ledger = std::move(*ledger);
        }
        document.journal.last_input_sequence = input_sequence;
        ++document.journal.next_tail_seq;
      } else if (kind == "admission_complete") {
        // The metadata record binds to the unique pending admission; it
        // advances the admission counter and never allocates a musical
        // sequence or rewrites events.
        if (!is_live_control_profile(document.journal)) {
          throw std::runtime_error(
              "Performance admission completion requires the live-control "
              "profile");
        }
        const auto& record = payload.value();
        if (record.size() != 5 || !record.contains("expected_revision") ||
            !record.contains("performance_id") || !record.contains("receipt") ||
            !record.contains("tail_seq")) {
          throw std::runtime_error(
              "Performance admission completion shape is invalid");
        }
        const auto tail_seq = record.at("tail_seq").get<std::uint64_t>();
        const auto expected_revision =
            record.at("expected_revision").get<std::uint64_t>();
        const auto performance_id = domain::PerformanceId{
            record.at("performance_id").get<std::string>()};
        auto receipt = parse_admission_receipt(record.at("receipt"));
        auto& ledger = *document.journal.admission_ledger;
        const auto identity_matches =
            ledger.pending.has_value() &&
            ledger.pending->request_id == receipt.request_id &&
            ledger.pending->expected_recording_sequence ==
                receipt.expected_recording_sequence &&
            ledger.pending->request_fingerprint ==
                receipt.request_fingerprint &&
            ledger.pending->accepted_tick == receipt.accepted_tick &&
            ledger.pending->input_sequence == receipt.input_sequence &&
            ledger.pending->event_input_sequences ==
                receipt.event_input_sequences &&
            ledger.pending->binding_result == receipt.binding_result;
        if (receipt.phase != PerformanceAdmissionPhase::completed ||
            tail_seq + 1 != document.journal.next_tail_seq ||
            expected_revision != document.journal.expected_revision ||
            performance_id != document.journal.performance_id ||
            !identity_matches) {
          throw std::runtime_error(
              "Performance admission completion does not match the pending "
              "admission");
        }
        ledger.next_recording_sequence += 1;
        ledger.completed = std::move(receipt);
        ledger.pending.reset();
      } else if (kind == "flush") {
        const bool live_profile = is_live_control_profile(document.journal);
        auto events = parse_performance_events(
            payload.value().at("events"), path, live_profile);
        if (!events.has_value() || events.value().empty()) {
          throw std::runtime_error("Performance flush events are invalid");
        }
        PerformanceFlushRecord flush{
            payload.value().at("flush_seq").get<std::uint64_t>(),
            foundation::CommandId{
                payload.value().at("command_id").get<std::string>()},
            domain::PerformanceId{
                payload.value().at("performance_id").get<std::string>()},
            payload.value().at("expected_revision").get<std::uint64_t>(),
            std::move(events.value()),
            false,
        };
        if (!domain::is_valid_uuid(flush.command_id.value()) ||
            !recording_command_is_new(
                document.journal.flushes, flush.command_id) ||
            flush.flush_seq != document.journal.next_flush_seq ||
            flush.performance_id != document.journal.performance_id ||
            flush.expected_revision != document.journal.expected_revision ||
            !recording_accepts_flush(
                document.journal.kind,
                document.journal.state,
                document.journal.flushes) ||
            // A prepared admission owns its pending events until its
            // completion metadata is durable; flush does not advance past it.
            (live_profile &&
             document.journal.admission_ledger->pending.has_value()) ||
            (!document.journal.pending_events.empty() &&
             flush.canonical_events != document.journal.pending_events)) {
          throw std::runtime_error(
              "Performance flush identity is invalid");
        }
        document.journal.pending_events.clear();
        document.journal.flushes.push_back(std::move(flush));
        ++document.journal.next_flush_seq;
      } else if (kind == "complete") {
        const auto flush_seq =
            payload.value().at("flush_seq").get<std::uint64_t>();
        const auto found = std::find_if(
            document.journal.flushes.begin(),
            document.journal.flushes.end(),
            [flush_seq](const auto& flush) {
              return flush.flush_seq == flush_seq;
            });
        const auto fingerprint = payload.value()
                                     .at("performance_fingerprint")
                                     .get<std::string>();
        const auto committed_revision = payload.value()
                                            .at("committed_revision")
                                            .get<std::uint64_t>();
        if (found == document.journal.flushes.end() || found->completed ||
            !lowercase_sha256(fingerprint) ||
            !recording_completion_revision_is_valid(
                document.journal.kind,
                found->expected_revision,
                committed_revision)) {
          throw std::runtime_error(
              "Performance completion is invalid");
        }
        found->completed = true;
        document.journal.expected_revision = committed_revision;
        document.journal.performance_fingerprint = fingerprint;
      } else if (kind == "stop") {
        const auto request_id = foundation::CommandId{
            payload.value().at("request_id").get<std::string>()};
        if (!domain::is_valid_uuid(request_id.value()) ||
            document.journal.stop_request_id.has_value() ||
            document.journal.state != SequenceSessionState::active ||
            std::ranges::any_of(
                document.journal.flushes,
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error("Performance stop record is invalid");
        }
        document.journal.stop_request_id = request_id;
        document.journal.state = SequenceSessionState::stopped;
      } else if (kind == "rebase_prepare") {
        PerformanceRebaseRecord rebase{
            foundation::CommandId{
                payload.value().at("command_id").get<std::string>()},
            payload.value().at("command_fingerprint").get<std::string>(),
            payload.value().at("from_revision").get<std::uint64_t>(),
            payload.value().at("to_revision").get<std::uint64_t>(),
            std::nullopt,
            false,
        };
        if (!domain::is_valid_uuid(rebase.command_id.value()) ||
            !lowercase_sha256(rebase.command_fingerprint) ||
            rebase.from_revision != document.journal.expected_revision ||
            rebase.to_revision != rebase.from_revision + 1 ||
            document.journal.state != SequenceSessionState::active ||
            std::ranges::any_of(
                document.journal.rebases,
                [&rebase](const auto& existing) {
                  return existing.command_id == rebase.command_id;
                }) ||
            std::ranges::any_of(
                document.journal.flushes,
                [](const auto& flush) { return !flush.completed; })) {
          throw std::runtime_error(
              "Performance rebase preparation is invalid");
        }
        document.journal.rebases.push_back(std::move(rebase));
        document.journal.state = SequenceSessionState::recovery_required;
      } else if (kind == "rebase_complete") {
        const auto command_id = foundation::CommandId{
            payload.value().at("command_id").get<std::string>()};
        const auto committed_revision =
            payload.value().at("committed_revision").get<std::uint64_t>();
        const auto fingerprint = payload.value()
                                     .at("performance_fingerprint")
                                     .get<std::string>();
        const auto found = std::find_if(
            document.journal.rebases.begin(),
            document.journal.rebases.end(),
            [&command_id](const auto& rebase) {
              return rebase.command_id == command_id;
            });
        if (found == document.journal.rebases.end() || found->completed ||
            committed_revision != found->to_revision ||
            document.journal.state !=
                SequenceSessionState::recovery_required ||
            !lowercase_sha256(fingerprint)) {
          throw std::runtime_error("Performance rebase completion is invalid");
        }
        if (!payload.value().at("bpm_anchor").is_null()) {
          found->bpm_anchor =
              payload.value().at("bpm_anchor").get<std::uint16_t>();
        }
        found->completed = true;
        document.journal.expected_revision = committed_revision;
        document.journal.performance_fingerprint = fingerprint;
        document.journal.state = SequenceSessionState::active;
      } else {
        throw std::runtime_error(
            "Performance Journal record kind is invalid");
      }
    }
    if (!saw_begin) {
      throw std::runtime_error(
          "Performance Journal has no durable begin record");
    }
    if (!document.journal.transient_checkpoint.has_value()) {
      if (document.journal.state != SequenceSessionState::stopped ||
          is_live_control_profile(document.journal)) {
        throw std::runtime_error(
            "active legacy Performance Journal has no transient checkpoint");
      }
      std::vector<domain::PerformanceEvent> durable_events =
          document.journal.pending_events;
      for (const auto& flush : document.journal.flushes) {
        durable_events.insert(
            durable_events.end(),
            flush.canonical_events.begin(),
            flush.canonical_events.end());
      }
      auto high_water = performance_temporal_high_water(durable_events);
      if (!high_water.has_value()) {
        throw std::runtime_error(high_water.error().message);
      }
      document.journal.transient_checkpoint =
          PerformanceTransientCheckpoint{{}, {}, false, high_water.value()};
    }
    return foundation::Result<PerformanceJournalDocument>::success(
        std::move(document));
  } catch (const std::exception& exception) {
    return foundation::Result<PerformanceJournalDocument>::failure(Error{
        ErrorCode::invalid_project,
        "Performance Journal is invalid and has been retained",
        {{"detail", exception.what()},
         {"path", path.generic_string()},
         {"reason", "performance_journal_record_invalid"},
         {"journal_retained", true},
         {"remedy",
          "retain the journal; repair the invalid record or discard the "
          "recovery journal explicitly"}},
    });
  }
}

}  // namespace

std::string performance_fingerprint(const domain::Performance& performance) {
  const auto profile =
      domain::performance_event_profile(performance);
  auto preimage = nlohmann::json{
      {"created_bpm", performance.created_bpm},
      {"events",
       performance_events_json(
           domain::canonical_performance_events(performance.events, profile))},
      {"name", performance.name},
      {"recording_revision", performance.recording_revision},
      {"recording_artifact",
       performance.recording_artifact.has_value()
           ? nlohmann::json(*performance.recording_artifact)
           : nlohmann::json(nullptr)},
  };
  // The header binds only when present, so a legacy Performance keeps its
  // exact historical preimage bytes.
  if (performance.initial_live_state.has_value()) {
    preimage["initial_live_state"] =
        domain::performance_initial_live_state_json(
            *performance.initial_live_state);
  }
  return sha256(foundation::canonical_json(preimage));
}

// The verified durable high-water for the headered profile: the recorded
// tail high-water plus every sequence already durable in pending or flushed
// events and in open Pad press references. Owner-loss closure derives its
// fresh sequences only from this value, so they can never collide with or
// fall below an already-durable sequence.
std::uint64_t durable_sequence_high_water(
    const ActivePerformanceJournal& journal) {
  std::uint64_t result = journal.last_input_sequence.value_or(0);
  const auto raise = [&result](std::optional<std::uint64_t> sequence) {
    if (sequence.has_value()) {
      result = std::max(result, *sequence);
    }
  };
  for (const auto& event : journal.pending_events) {
    raise(event.input_sequence);
  }
  for (const auto& flush : journal.flushes) {
    for (const auto& event : flush.canonical_events) {
      raise(event.input_sequence);
    }
  }
  if (journal.transient_checkpoint.has_value()) {
    for (const auto& pad : journal.transient_checkpoint->open_pads) {
      raise(pad.input_sequence);
    }
  }
  return result;
}

foundation::Result<PerformanceTransientClosurePreview>
preview_performance_owner_loss(const ActivePerformanceJournal& journal) {
  if (!journal.transient_checkpoint.has_value()) {
    return foundation::Result<PerformanceTransientClosurePreview>::failure(
        Error{
            ErrorCode::invalid_project,
            "Performance owner-loss closure requires a durable transient checkpoint",
            {{"journal_retained", true},
             {"reason", "performance_transient_checkpoint_missing"}},
        });
  }
  const auto& checkpoint = *journal.transient_checkpoint;
  const bool live_profile = is_live_control_profile(journal);
  PerformanceTransientClosurePreview preview{
      journal.pending_events, 0, checkpoint.last_accepted_tick};
  if (checkpoint.open_pads.empty() && checkpoint.open_fx.empty() &&
      !checkpoint.hold && !checkpoint.open_filter.has_value()) {
    auto high_water = performance_temporal_high_water(preview.canonical_events);
    if (!high_water.has_value()) {
      return foundation::Result<PerformanceTransientClosurePreview>::failure(
          high_water.error());
    }
    preview.closure_tick =
        std::max(preview.closure_tick, high_water.value());
    return foundation::Result<PerformanceTransientClosurePreview>::success(
        std::move(preview));
  }

  std::vector<domain::PerformanceEvent> durable_events =
      journal.pending_events;
  for (const auto& flush : journal.flushes) {
    durable_events.insert(
        durable_events.end(),
        flush.canonical_events.begin(),
        flush.canonical_events.end());
  }
  auto high_water = performance_temporal_high_water(durable_events);
  if (!high_water.has_value()) {
    return foundation::Result<PerformanceTransientClosurePreview>::failure(
        high_water.error());
  }
  const auto maximum_tick =
      std::max(checkpoint.last_accepted_tick, high_water.value());
  if (maximum_tick == std::numeric_limits<std::uint64_t>::max()) {
    return foundation::Result<PerformanceTransientClosurePreview>::failure(
        Error{
            ErrorCode::invalid_project,
            "Performance owner-loss closure tick overflows",
            {{"journal_retained", true},
             {"reason", "performance_tick_overflow"}},
        });
  }
  preview.closure_tick = maximum_tick + 1;
  // Closure event sequences derive uniquely from the verified durable
  // high-water: a closed PadHit keeps its press's sequence, while the
  // internally generated releases and HoldOff each take one fresh value.
  std::uint64_t next_closure_sequence =
      durable_sequence_high_water(journal);
  const auto fresh_sequence = [&next_closure_sequence]() {
    if (next_closure_sequence == std::numeric_limits<std::uint64_t>::max()) {
      throw std::runtime_error("performance_input_sequence_overflow");
    }
    ++next_closure_sequence;
    return next_closure_sequence;
  };
  try {
  for (const auto& pad : checkpoint.open_pads) {
    if (preview.closure_tick <= pad.onset_tick) {
      return foundation::Result<PerformanceTransientClosurePreview>::failure(
          Error{
              ErrorCode::invalid_project,
              "Performance owner-loss Pad closure is not positive",
              {{"journal_retained", true},
               {"reason", "performance_tick_overflow"}},
          });
    }
    preview.canonical_events.push_back(domain::PerformanceEvent{
        domain::PadHitPerformanceEvent{
            pad.slot,
            pad.onset_tick,
            preview.closure_tick - pad.onset_tick,
            pad.velocity,
        },
        live_profile ? pad.input_sequence : std::nullopt});
    ++preview.appended_event_count;
  }
  for (const auto& effect : checkpoint.open_fx) {
    preview.canonical_events.push_back(domain::PerformanceEvent{
        domain::FxReleasePerformanceEvent{
            effect.fx, preview.closure_tick},
        live_profile
            ? std::optional<std::uint64_t>{fresh_sequence()}
            : std::nullopt});
    ++preview.appended_event_count;
  }
  if (checkpoint.open_filter.has_value()) {
    // The independent Filter gesture closes with its retained parameter
    // tuple; it never degrades into the legacy scalar.
    preview.canonical_events.push_back(domain::PerformanceEvent{
        domain::FilterChangePerformanceEvent{
            domain::PerformanceFilterPhase::release,
            checkpoint.open_filter->type,
            checkpoint.open_filter->cutoff_hz,
            checkpoint.open_filter->resonance_milli,
            preview.closure_tick},
        live_profile
            ? std::optional<std::uint64_t>{fresh_sequence()}
            : std::nullopt});
    ++preview.appended_event_count;
  }
  if (checkpoint.hold) {
    preview.canonical_events.push_back(domain::PerformanceEvent{
        domain::HoldOffPerformanceEvent{preview.closure_tick},
        live_profile
            ? std::optional<std::uint64_t>{fresh_sequence()}
            : std::nullopt});
    ++preview.appended_event_count;
  }
  } catch (const std::runtime_error& overflow) {
    return foundation::Result<PerformanceTransientClosurePreview>::failure(
        Error{
            ErrorCode::invalid_project,
            "Performance owner-loss input sequence overflows",
            {{"journal_retained", true},
             {"reason", overflow.what()}},
        });
  }
  preview.canonical_events = domain::canonical_performance_events(
      preview.canonical_events,
      live_profile ? domain::PerformanceEventProfile::header_input_sequence
                   : domain::PerformanceEventProfile::legacy);
  std::vector<domain::PerformanceEvent> validation_events;
  for (const auto& flush : journal.flushes) {
    validation_events.insert(
        validation_events.end(),
        flush.canonical_events.begin(),
        flush.canonical_events.end());
  }
  validation_events.insert(
      validation_events.end(),
      preview.canonical_events.begin(),
      preview.canonical_events.end());
  // The headered stream validates from the begin header's seed, so a release
  // pairs with the gesture the fence recorded even when its engage predates
  // the durable event list.
  auto valid = live_profile
                   ? domain::validate_performance_events(
                         validation_events, *journal.initial_live_state)
                   : domain::validate_performance_events(validation_events);
  if (!valid.has_value()) {
    auto error = valid.error();
    error.code = ErrorCode::invalid_project;
    error.details["journal_retained"] = true;
    error.details["reason"] = "performance_transient_closure_invalid";
    return foundation::Result<PerformanceTransientClosurePreview>::failure(
        std::move(error));
  }
  return foundation::Result<PerformanceTransientClosurePreview>::success(
      std::move(preview));
}

foundation::Result<void> SequenceJournal::begin_performance_draft_locked(
    const std::filesystem::path& bundle,
    foundation::CommandId command_id,
    foundation::SequenceSessionId session_id,
    domain::PerformanceId performance_id,
    std::string fingerprint,
    std::uint64_t from_revision,
    std::optional<domain::PerformanceInitialLiveState> initial_live_state,
    std::optional<PerformanceTransientCheckpoint> initial_checkpoint) {
  if (!domain::is_valid_uuid(command_id.value()) ||
      !domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(performance_id.value()) ||
      !lowercase_sha256(fingerprint)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance draft begin metadata is invalid",
    });
  }
  auto active_kind = active_recording_session(
      *platform_, bundle, SessionKind::performance);
  if (!active_kind.has_value()) {
    return foundation::Result<void>::failure(active_kind.error());
  }
  if (active_kind.value().has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "a recording session is already active for this Project",
        {{"reason", "recording_session_active"},
         {"session_kind", session_kind_string(*active_kind.value())},
         {"remedy",
          "finish or reconcile the active recording session before beginning a Performance draft"}},
    });
  }
  auto checkpoint = initial_checkpoint.has_value()
                        ? std::move(*initial_checkpoint)
                        : initial_live_checkpoint(initial_live_state);
  if (initial_checkpoint.has_value() != initial_live_state.has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance draft begin profile is inconsistent",
    });
  }
  if (initial_live_state.has_value()) {
    auto valid = validate_performance_checkpoint(
        checkpoint, {}, true);
    if (!valid.has_value()) {
      return valid;
    }
  }
  const auto path = recording_active_path(bundle, SessionKind::performance);
  auto payload = nlohmann::json{
      {"command_id", command_id.value()},
      {"contract",
       recording_protocol(SessionKind::performance).journal_contract},
      {"expected_revision", from_revision},
      {"kind", "begin"},
      {"performance_fingerprint", std::move(fingerprint)},
      {"performance_id", performance_id.value()},
      {"session_id", session_id.value()},
      {"transient_checkpoint", performance_checkpoint_json(checkpoint)},
  };
  if (initial_live_state.has_value()) {
    payload["live_control_profile"] =
        std::string{kLiveControlProfileHeaderInputSequence};
    payload["initial_live_state"] =
        domain::performance_initial_live_state_json(*initial_live_state);
    payload["admission_ledger"] =
        admission_ledger_json(PerformanceAdmissionLedger{});
  }
  const auto bytes = foundation::canonical_json(checked_record(payload)) +
                     "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_write, path);
  if (!fault.has_value()) {
    return fault;
  }
#endif
  auto created = platform_->create_immutable(path, byte_span(bytes));
  return created.has_value()
             ? foundation::Result<void>::success()
             : foundation::Result<void>::failure(created.error());
}

foundation::Result<void> SequenceJournal::complete_performance_begin_locked(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::uint64_t committed_revision,
    std::string fingerprint) {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  if (document.value().journal.session_id != session_id ||
      !document.value().journal.begin_command_id.has_value() ||
      document.value().journal.expected_revision + 1 != committed_revision ||
      !lowercase_sha256(fingerprint)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance draft begin completion does not match the Journal",
    });
  }
  return append_recording_record(
      platform_, bundle, SessionKind::performance,
      document.value().valid_prefix_length,
      {{"committed_revision", committed_revision},
       {"kind", "begin-complete"},
       {"performance_fingerprint", std::move(fingerprint)}});
}

foundation::Result<void> SequenceJournal::stop_performance_locked(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId request_id) {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id ||
      !domain::is_valid_uuid(request_id.value())) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance stop identity does not match the active Journal",
    });
  }
  if (journal.stop_request_id.has_value()) {
    if (*journal.stop_request_id == request_id &&
        journal.state == SequenceSessionState::stopped) {
      return foundation::Result<void>::success();
    }
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance stop request id is bound to another request",
        {{"reason", "performance_stop_request_conflict"},
         {"remedy",
          "retry the exact original stop request id or start a new session before issuing a different request"}},
    });
  }
  if (journal.state == SequenceSessionState::recovery_required) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance stop is blocked until durable rebase reconciliation completes",
        {{"reason", "performance_rebase_recovery_required"},
         {"remedy",
          "reopen the Project and retry the exact prepared command before stopping the session"}},
    });
  }
  if (journal.state != SequenceSessionState::active ||
      std::ranges::any_of(
          journal.flushes,
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance session cannot stop in its current state",
    });
  }
  if (!journal.transient_checkpoint.has_value() ||
      !journal.transient_checkpoint->open_pads.empty() ||
      !journal.transient_checkpoint->open_fx.empty() ||
      journal.transient_checkpoint->hold) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance session cannot stop with open transients",
        {{"reason", "performance_transient_closure_required"}},
    });
  }
  return append_recording_record(
      platform_, bundle, SessionKind::performance,
      document.value().valid_prefix_length,
      {{"kind", "stop"}, {"request_id", request_id.value()}});
}

foundation::Result<void> SequenceJournal::prepare_performance_rebase_locked(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    PerformanceRebaseRecord record) {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  const auto existing = std::find_if(
      journal.rebases.begin(), journal.rebases.end(),
      [&record](const auto& candidate) {
        return candidate.command_id == record.command_id;
      });
  if (existing != journal.rebases.end()) {
    if (existing->command_fingerprint == record.command_fingerprint &&
        existing->from_revision == record.from_revision &&
        existing->to_revision == record.to_revision) {
      return foundation::Result<void>::success();
    }
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance rebase command id is bound to another command",
        {{"reason", "performance_rebase_command_conflict"},
         {"remedy",
          "retry the exact prepared command payload or issue a new command id before preparation"}},
    });
  }
  if (journal.session_id != session_id ||
      journal.state != SequenceSessionState::active ||
      journal.expected_revision != record.from_revision ||
      record.to_revision != record.from_revision + 1 ||
      !domain::is_valid_uuid(record.command_id.value()) ||
      !lowercase_sha256(record.command_fingerprint) ||
      std::ranges::any_of(
          journal.flushes,
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance rebase cannot be prepared in the current state",
    });
  }
  return append_recording_record(
      platform_, bundle, SessionKind::performance,
      document.value().valid_prefix_length,
      {{"command_fingerprint", std::move(record.command_fingerprint)},
       {"command_id", record.command_id.value()},
       {"from_revision", record.from_revision},
       {"kind", "rebase_prepare"},
       {"to_revision", record.to_revision}});
}

foundation::Result<void> SequenceJournal::complete_performance_rebase_locked(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId command_id,
    std::uint64_t committed_revision,
    std::optional<std::uint16_t> bpm_anchor,
    std::string fingerprint) {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  const auto found = std::find_if(
      journal.rebases.begin(), journal.rebases.end(),
      [&command_id](const auto& rebase) {
        return rebase.command_id == command_id;
      });
  if (journal.session_id != session_id || found == journal.rebases.end() ||
      found->completed || found->to_revision != committed_revision ||
      journal.state != SequenceSessionState::recovery_required ||
      !lowercase_sha256(fingerprint)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance rebase completion does not match the Journal",
    });
  }
  return append_recording_record(
      platform_, bundle, SessionKind::performance,
      document.value().valid_prefix_length,
      {{"bpm_anchor",
        bpm_anchor.has_value() ? nlohmann::json(*bpm_anchor)
                               : nlohmann::json(nullptr)},
       {"command_id", command_id.value()},
       {"committed_revision", committed_revision},
       {"kind", "rebase_complete"},
       {"performance_fingerprint", std::move(fingerprint)}});
}

foundation::Result<void> SequenceJournal::remove_active_performance_locked(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    bool require_stopped) {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  if (document.value().journal.session_id != session_id ||
      (require_stopped &&
       document.value().journal.state != SequenceSessionState::stopped)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance Journal cleanup precondition failed",
    });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_deletion,
      recording_active_path(bundle, SessionKind::performance));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  auto removed = platform_->remove(
      recording_active_path(bundle, SessionKind::performance));
  if (!removed.has_value()) {
    return removed;
  }
  return remove_performance_owner_lock(platform_, bundle);
}

foundation::Result<void> SequenceJournal::restore_stopped_performance_locked(
    const std::filesystem::path& bundle,
    const PerformanceRecoveryCandidate& candidate,
    std::uint64_t expected_revision,
    std::string fingerprint,
    foundation::CommandId request_id) {
  const auto active_path =
      recording_active_path(bundle, SessionKind::performance);
  auto active_exists = platform_->exists(active_path);
  if (!active_exists.has_value()) {
    return foundation::Result<void>::failure(active_exists.error());
  }
  if (active_exists.value()) {
    auto active = read_performance_journal(*platform_, bundle);
    if (!active.has_value()) {
      return foundation::Result<void>::failure(active.error());
    }
    if (active.value().journal.session_id != candidate.journal.session_id ||
        active.value().journal.performance_id !=
            candidate.journal.performance_id ||
        active.value().journal.state != SequenceSessionState::stopped ||
        active.value().journal.stop_request_id != request_id) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "another recording session blocks Performance recovery",
          {{"reason", "recording_session_active"}},
      });
    }
  } else {
    auto begin_payload = nlohmann::json{
        {"contract",
         recording_protocol(SessionKind::performance)
             .journal_contract},
        {"expected_revision", expected_revision},
        {"kind", "begin"},
        {"performance_fingerprint", fingerprint},
        {"performance_id",
         candidate.journal.performance_id.value()},
        {"session_id",
         candidate.journal.session_id.value()},
        {"transient_checkpoint",
         performance_checkpoint_json(
             candidate.journal.transient_checkpoint.has_value()
                 ? *candidate.journal.transient_checkpoint
                 : PerformanceTransientCheckpoint{{}, {}, false, 0})},
    };
    // The restored stopped Journal keeps the profile's unknown facts: the
    // discriminator, the immutable header and the terminal ledger survive
    // recovery verbatim rather than being rewritten or completed.
    if (is_live_control_profile(candidate.journal)) {
      begin_payload["live_control_profile"] =
          std::string{kLiveControlProfileHeaderInputSequence};
      begin_payload["initial_live_state"] =
          domain::performance_initial_live_state_json(
              *candidate.journal.initial_live_state);
      begin_payload["admission_ledger"] =
          admission_ledger_json(*candidate.journal.admission_ledger);
    }
    const auto begin =
        foundation::canonical_json(checked_record(begin_payload)) + "\n";
    const auto stop = foundation::canonical_json(checked_record({
                          {"kind", "stop"},
                          {"request_id", request_id.value()},
                      })) +
                      "\n";
    const auto bytes = begin + stop;
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
    const auto fault = testing::detail::invoke_fault(
        testing::FaultPoint::sequence_journal_write, active_path);
    if (!fault.has_value()) {
      return fault;
    }
#endif
    auto created = platform_->create_immutable(active_path, byte_span(bytes));
    if (!created.has_value()) {
      return foundation::Result<void>::failure(created.error());
    }
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto cleanup_fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_deletion, candidate.path);
  if (!cleanup_fault.has_value()) {
    return cleanup_fault;
  }
#endif
  auto candidate_exists = platform_->exists(candidate.path);
  if (!candidate_exists.has_value()) {
    return foundation::Result<void>::failure(candidate_exists.error());
  }
  return candidate_exists.value()
             ? platform_->remove(candidate.path)
             : foundation::Result<void>::success();
}

foundation::Result<void> SequenceJournal::begin_performance(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    domain::PerformanceId performance_id,
    std::string fingerprint,
    std::uint64_t expected_revision,
    std::optional<domain::PerformanceInitialLiveState> initial_live_state,
    std::optional<PerformanceTransientCheckpoint> initial_checkpoint) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(performance_id.value()) ||
      !lowercase_sha256(fingerprint)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance begin metadata is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  // As in begin(), validate the tree only under the writer lease.
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto tree = validate_journal_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  auto active_kind = active_recording_session(
      *platform_, bundle, SessionKind::performance);
  if (!active_kind.has_value()) {
    return foundation::Result<void>::failure(active_kind.error());
  }
  if (active_kind.value().has_value()) {
    const auto kind = *active_kind.value();
    auto details = nlohmann::json{
        {"reason", "recording_session_active"},
        {"session_kind", session_kind_string(kind)},
        {"remedy",
         "finish or reconcile the active recording session before beginning another Performance session"},
    };
    if (kind == SessionKind::performance) {
      auto active = read_performance_journal(*platform_, bundle);
      if (active.has_value()) {
        details["session_id"] = active.value().journal.session_id.value();
      }
    }
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "a " + std::string{recording_protocol(kind).name} +
            " session is already active for this Project",
        std::move(details),
    });
  }
  auto head_revision = manifest_head_revision(*platform_, bundle);
  if (!head_revision.has_value()) {
    return foundation::Result<void>::failure(head_revision.error());
  }
  if (head_revision.value() != expected_revision) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::revision_conflict,
        "Performance begin expected revision does not match Project Truth",
        {{"actual_revision", head_revision.value()},
         {"expected_revision", expected_revision}},
    });
  }
  if (initial_checkpoint.has_value() != initial_live_state.has_value()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance begin profile is inconsistent",
    });
  }
  auto checkpoint = initial_checkpoint.has_value()
                        ? std::move(*initial_checkpoint)
                        : initial_live_checkpoint(initial_live_state);
  if (initial_live_state.has_value()) {
    auto valid = validate_performance_checkpoint(checkpoint, {}, true);
    if (!valid.has_value()) {
      return valid;
    }
  }
  const auto path = recording_active_path(bundle, SessionKind::performance);
  auto payload = nlohmann::json{
      {"contract",
       recording_protocol(SessionKind::performance).journal_contract},
      {"expected_revision", expected_revision},
      {"kind", "begin"},
      {"performance_fingerprint", std::move(fingerprint)},
      {"performance_id", performance_id.value()},
      {"session_id", session_id.value()},
      {"transient_checkpoint", performance_checkpoint_json(checkpoint)},
  };
  if (initial_live_state.has_value()) {
    payload["live_control_profile"] =
        std::string{kLiveControlProfileHeaderInputSequence};
    payload["initial_live_state"] =
        domain::performance_initial_live_state_json(*initial_live_state);
    payload["admission_ledger"] =
        admission_ledger_json(PerformanceAdmissionLedger{});
  }
  const auto bytes = foundation::canonical_json(checked_record(payload)) +
                     "\n";
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_write, path);
  if (!fault.has_value()) {
    return fault;
  }
#endif
  auto created = platform_->create_immutable(path, byte_span(bytes));
  if (!created.has_value()) {
    return foundation::Result<void>::failure(created.error());
  }
  return foundation::Result<void>::success();
}

foundation::Result<ActivePerformanceJournal>
SequenceJournal::read_active_performance(
    const std::filesystem::path& bundle) const {
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<ActivePerformanceJournal>::failure(
        document.error());
  }
  return foundation::Result<ActivePerformanceJournal>::success(
      std::move(document.value().journal));
}

foundation::Result<void> SequenceJournal::append_performance_tail(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    domain::PerformanceId performance_id,
    std::uint64_t expected_revision,
    std::uint64_t input_sequence,
    std::span<const domain::PerformanceEvent> events,
    std::optional<PerformanceTransientCheckpoint> transient_checkpoint,
    std::optional<PerformanceLaunchAck> last_launch_ack,
    std::optional<PerformanceAdmissionReceipt> pending_receipt) {
  return append_performance_tail_internal(
      bundle,
      session_id,
      performance_id,
      expected_revision,
      input_sequence,
      events,
      std::move(transient_checkpoint),
      std::move(last_launch_ack),
      std::move(pending_receipt),
      false);
}

foundation::Result<void> SequenceJournal::append_performance_tail_internal(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    domain::PerformanceId performance_id,
    std::uint64_t expected_revision,
    std::uint64_t input_sequence,
    std::span<const domain::PerformanceEvent> events,
    std::optional<PerformanceTransientCheckpoint> transient_checkpoint,
    std::optional<PerformanceLaunchAck> last_launch_ack,
    std::optional<PerformanceAdmissionReceipt> pending_receipt,
    bool allow_ledger_carryover) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(performance_id.value()) || input_sequence == 0) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance tail metadata is invalid",
    });
  }
  auto validated = validate_performance_event_structure(events);
  if (!validated.has_value()) {
    return validated;
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  const bool live_profile = is_live_control_profile(journal);
  // The legacy grammar never grows the new fields: a legacy Journal rejects
  // a receipt, and a headered Journal never silently drops into it.
  if (live_profile != pending_receipt.has_value() &&
      !allow_ledger_carryover) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance tail admission receipt does not match the Journal "
        "profile",
        {{"reason", "performance_admission_ledger_profile_mismatch"}},
    });
  }
  if (journal.state == SequenceSessionState::recovery_required) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance admission is blocked until durable rebase reconciliation completes",
        {{"reason", "performance_rebase_recovery_required"},
         {"remedy",
          "retry the exact prepared command after reopening the Project; do not submit new events or flushes"}},
    });
  }
  if (journal.session_id != session_id ||
      journal.performance_id != performance_id ||
      journal.expected_revision != expected_revision ||
      (journal.last_input_sequence.has_value() &&
       input_sequence <= *journal.last_input_sequence) ||
      !recording_accepts_tail(
          journal.kind, journal.state, journal.flushes)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance tail does not match the active session",
    });
  }
  const auto event_profile =
      live_profile ? domain::PerformanceEventProfile::header_input_sequence
                   : domain::PerformanceEventProfile::legacy;
  for (const auto& event : events) {
    if (live_profile != event.input_sequence.has_value()) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance tail event profile does not match the Journal",
      });
    }
  }
  if (live_profile) {
    std::unordered_set<std::uint64_t> sequences;
    for (const auto& event : events) {
      if (!sequences.insert(*event.input_sequence).second ||
          *event.input_sequence > input_sequence) {
        return foundation::Result<void>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance tail event input sequence is invalid",
        });
      }
    }
  }
  auto canonical = domain::canonical_performance_events(
      std::vector<domain::PerformanceEvent>{events.begin(), events.end()},
      event_profile);
  std::vector<domain::PerformanceEvent> durable_events = canonical;
  for (const auto& flush : journal.flushes) {
    durable_events.insert(
        durable_events.end(),
        flush.canonical_events.begin(),
        flush.canonical_events.end());
  }
  if (!transient_checkpoint.has_value()) {
    if (live_profile) {
      return foundation::Result<void>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance live-control tail requires its live checkpoint",
      });
    }
    auto high_water = performance_temporal_high_water(durable_events);
    if (!high_water.has_value()) {
      return foundation::Result<void>::failure(high_water.error());
    }
    transient_checkpoint =
        PerformanceTransientCheckpoint{{}, {}, false, high_water.value()};
  }
  if (live_profile) {
    // Open Pad transients reference their press's durable sequence, which is
    // always under this tail's high-water.
    for (const auto& pad : transient_checkpoint->open_pads) {
      if (*pad.input_sequence > input_sequence) {
        return foundation::Result<void>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance open Pad press sequence exceeds the high-water",
        });
      }
    }
  }
  auto checkpoint_valid = validate_performance_checkpoint(
      *transient_checkpoint, durable_events, live_profile);
  if (!checkpoint_valid.has_value()) {
    return checkpoint_valid;
  }
  if (last_launch_ack.has_value()) {
    auto ack_valid =
        validate_performance_launch_ack(*last_launch_ack, durable_events);
    if (!ack_valid.has_value()) {
      return ack_valid;
    }
  }
  auto ack_transition = validate_performance_launch_ack_transition(
      journal.pending_events, canonical, journal.last_launch_ack,
      last_launch_ack);
  if (!ack_transition.has_value()) {
    return ack_transition;
  }
  if (journal.transient_checkpoint.has_value() &&
      transient_checkpoint->last_accepted_tick <
          journal.transient_checkpoint->last_accepted_tick) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance checkpoint tick is not monotone",
    });
  }
  std::optional<PerformanceAdmissionLedger> next_ledger;
  if (live_profile) {
    next_ledger = journal.admission_ledger;
    if (pending_receipt.has_value()) {
      const auto& receipt = *pending_receipt;
      // One pending admission per session window: the receipt binds the
      // original request identity, its raw-payload fingerprint and the
      // frozen tick/sequence; queue rejection happens before this point.
      if (!domain::is_valid_uuid(receipt.request_id.value()) ||
          !lowercase_sha256(receipt.request_fingerprint) ||
          receipt.phase != PerformanceAdmissionPhase::prepared ||
          receipt.result != PerformanceAdmissionResult::not_published ||
          receipt.input_sequence == 0 ||
          receipt.input_sequence > input_sequence ||
          receipt.expected_recording_sequence !=
              next_ledger->next_recording_sequence ||
          next_ledger->pending.has_value() ||
          (receipt.binding_result.has_value() &&
           !domain::is_valid_uuid(
               receipt.binding_result->recording_gesture_id)) ||
          !std::ranges::all_of(
              receipt.event_input_sequences,
              [input_sequence](std::uint64_t sequence) {
                return sequence >= 1 && sequence <= input_sequence;
              })) {
        return foundation::Result<void>::failure(Error{
            ErrorCode::invalid_argument,
            "Performance admission receipt does not fit the durable window",
            {{"reason", "performance_admission_receipt_invalid"}},
        });
      }
      next_ledger->pending = receipt;
    }
  }
  if (canonical.empty() && canonical == journal.pending_events &&
      journal.transient_checkpoint.has_value() &&
      *transient_checkpoint == *journal.transient_checkpoint &&
      last_launch_ack == journal.last_launch_ack &&
      (!live_profile || *next_ledger == *journal.admission_ledger)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance tail must contain a state transition",
    });
  }
  auto payload = nlohmann::json{
      {"events", performance_events_json(canonical)},
      {"expected_revision", expected_revision},
      {"input_sequence", input_sequence},
      {"kind", "tail"},
      {"last_launch_ack",
       last_launch_ack.has_value()
           ? performance_launch_ack_json(*last_launch_ack)
           : nlohmann::json(nullptr)},
      {"performance_id", performance_id.value()},
      {"tail_seq", journal.next_tail_seq},
      {"transient_checkpoint",
       performance_checkpoint_json(*transient_checkpoint)},
  };
  if (live_profile) {
    payload["admission_ledger"] = admission_ledger_json(*next_ledger);
  }
  const auto append_once = [&]() {
    return append_recording_record(
        platform_,
        bundle,
        document.value().journal.kind,
        document.value().valid_prefix_length,
        payload);
  };
  auto appended = append_once();
  if (appended.has_value()) {
    return appended;
  }

  const auto is_exact_appended_state = [&](const ActivePerformanceJournal& value) {
    return value.session_id == session_id &&
           value.performance_id == performance_id &&
           value.expected_revision == expected_revision &&
           value.next_tail_seq == journal.next_tail_seq + 1 &&
           value.last_input_sequence == input_sequence &&
           value.pending_events == canonical &&
           value.transient_checkpoint == transient_checkpoint &&
           value.last_launch_ack == last_launch_ack &&
           value.admission_ledger == next_ledger;
  };
  auto first_observed = read_performance_journal(*platform_, bundle);
  if (first_observed.has_value() &&
      first_observed.value().journal != journal &&
      !is_exact_appended_state(first_observed.value().journal)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::io_error,
        "Performance tail outcome is unknown after durable append",
        {{"journal_retained", true},
         {"reason", "performance_tail_outcome_unknown"},
         {"remedy",
          "freeze the in-memory session and reconcile the retained Journal before accepting more input"}},
    });
  }

  // A failed append may have written the record before its sync failed.
  // Rewriting from the same validated prefix is the sole bounded retry and
  // cannot duplicate the logical transition.
  auto retried = append_once();
  if (retried.has_value()) {
    return retried;
  }
  auto observed = read_performance_journal(*platform_, bundle);
  if (observed.has_value() && observed.value().journal == journal) {
    return foundation::Result<void>::failure(retried.error());
  }
  return foundation::Result<void>::failure(Error{
      ErrorCode::io_error,
      "Performance tail outcome is unknown after durable append retry",
      {{"journal_retained", true},
       {"reason", "performance_tail_outcome_unknown"},
       {"remedy",
        "freeze the in-memory session and reconcile the retained Journal before accepting more input"}},
  });
}

foundation::Result<void>
SequenceJournal::close_performance_transients_for_owner_loss(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id) {
  auto active = read_active_performance(bundle);
  if (!active.has_value()) {
    return foundation::Result<void>::failure(active.error());
  }
  if (active.value().session_id != session_id) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance owner-loss closure does not match the active session",
    });
  }
  auto preview = preview_performance_owner_loss(active.value());
  if (!preview.has_value()) {
    return foundation::Result<void>::failure(preview.error());
  }
  if (preview.value().appended_event_count == 0) {
    return foundation::Result<void>::success();
  }
  if (active.value().last_input_sequence.has_value() &&
      *active.value().last_input_sequence ==
          std::numeric_limits<std::uint64_t>::max()) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_project,
        "Performance owner-loss input sequence overflows",
        {{"journal_retained", true},
         {"reason", "performance_input_sequence_overflow"}},
    });
  }
  const auto next_input_sequence =
      active.value().last_input_sequence.value_or(0) + 1;
  if (!is_live_control_profile(active.value())) {
    return append_performance_tail(
        bundle,
        active.value().session_id,
        active.value().performance_id,
        active.value().expected_revision,
        next_input_sequence,
        preview.value().canonical_events,
        PerformanceTransientCheckpoint{
            {}, {}, false, preview.value().closure_tick},
        active.value().last_launch_ack);
  }
  // Headered profile: the closure is metadata-only. Its tail carries the
  // admission ledger unchanged — a pending prepared admission stays pending
  // and unknown — and the checkpoint records the neutralized live state. The
  // tail's high-water covers every durable sequence, not only the closure's
  // own events.
  std::uint64_t closure_high_water = std::max(
      next_input_sequence, durable_sequence_high_water(active.value()));
  for (const auto& event : preview.value().canonical_events) {
    closure_high_water =
        std::max(closure_high_water, event.input_sequence.value_or(0));
  }
  auto closed_state = *active.value().transient_checkpoint->live_state;
  closed_state.hold = false;
  for (auto& gate : closed_state.other_fx) {
    gate.engaged = false;
    gate.frozen = false;
  }
  if (auto* independent =
          std::get_if<domain::IndependentFilterLiveState>(
              &closed_state.filter)) {
    // A released Filter keeps its parameter tuple for readback.
    independent->engaged = false;
    independent->frozen = false;
  } else {
    auto& legacy = std::get<domain::LegacyFilterLiveState>(closed_state.filter);
    legacy.engaged = false;
    legacy.frozen = false;
  }
  return append_performance_tail_internal(
      bundle,
      active.value().session_id,
      active.value().performance_id,
      active.value().expected_revision,
      closure_high_water,
      preview.value().canonical_events,
      PerformanceTransientCheckpoint{
          {},
          {},
          false,
          preview.value().closure_tick,
          std::nullopt,
          std::move(closed_state)},
      active.value().last_launch_ack,
      std::nullopt,
      true);
}

foundation::Result<PerformanceFlushRecord>
SequenceJournal::append_performance_flush(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    foundation::CommandId command_id,
    domain::PerformanceId performance_id,
    std::uint64_t expected_revision,
    std::span<const domain::PerformanceEvent> events) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(command_id.value()) ||
      !domain::is_valid_uuid(performance_id.value()) || events.empty()) {
    return foundation::Result<PerformanceFlushRecord>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush metadata is invalid",
    });
  }
  auto validated = validate_performance_event_structure(events);
  if (!validated.has_value()) {
    return foundation::Result<PerformanceFlushRecord>::failure(
        validated.error());
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<PerformanceFlushRecord>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<PerformanceFlushRecord>::failure(
        document.error());
  }
  const auto& journal = document.value().journal;
  const bool live_profile = is_live_control_profile(journal);
  for (const auto& event : events) {
    if (live_profile != event.input_sequence.has_value()) {
      return foundation::Result<PerformanceFlushRecord>::failure(Error{
          ErrorCode::invalid_argument,
          "Performance flush event profile does not match the Journal",
      });
    }
  }
  auto canonical = domain::canonical_performance_events(
      std::vector<domain::PerformanceEvent>{events.begin(), events.end()},
      live_profile ? domain::PerformanceEventProfile::header_input_sequence
                   : domain::PerformanceEventProfile::legacy);
  if (journal.state == SequenceSessionState::recovery_required) {
    return foundation::Result<PerformanceFlushRecord>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush is blocked until durable rebase reconciliation completes",
        {{"reason", "performance_rebase_recovery_required"},
         {"remedy",
          "retry the exact prepared command after reopening the Project; do not submit new events or flushes"}},
    });
  }
  const auto repeated = std::find_if(
      journal.flushes.begin(), journal.flushes.end(),
      [&command_id](const auto& flush) {
        return flush.command_id == command_id;
      });
  if (repeated != journal.flushes.end()) {
    if (repeated->performance_id == performance_id &&
        repeated->expected_revision == expected_revision &&
        repeated->canonical_events == canonical) {
      return foundation::Result<PerformanceFlushRecord>::success(*repeated);
    }
    return foundation::Result<PerformanceFlushRecord>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance command id is bound to a different flush",
        {{"reason", "performance_command_conflict"},
         {"remedy",
          "retry the exact original flush payload or issue a new command id"}},
    });
  }
  if (journal.session_id != session_id ||
      journal.performance_id != performance_id ||
      journal.expected_revision != expected_revision ||
      !recording_accepts_flush(
          journal.kind, journal.state, journal.flushes) ||
      // A prepared admission owns its pending events until its completion
      // metadata is durable; flush does not advance past it.
      (live_profile &&
       journal.admission_ledger->pending.has_value()) ||
      (!journal.pending_events.empty() &&
       journal.pending_events != canonical)) {
    return foundation::Result<PerformanceFlushRecord>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance flush does not match the active session",
    });
  }
  PerformanceFlushRecord flush{
      journal.next_flush_seq,
      std::move(command_id),
      std::move(performance_id),
      expected_revision,
      std::move(canonical),
      false,
  };
  auto appended = append_recording_record(
      platform_, bundle, document.value().journal.kind,
      document.value().valid_prefix_length, performance_flush_json(flush));
  if (!appended.has_value()) {
    return foundation::Result<PerformanceFlushRecord>::failure(
        appended.error());
  }
  return foundation::Result<PerformanceFlushRecord>::success(
      std::move(flush));
}

foundation::Result<void> SequenceJournal::complete_performance_flush(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::uint64_t flush_seq,
    std::uint64_t committed_revision,
    std::string fingerprint) {
  if (!lowercase_sha256(fingerprint)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance completion fingerprint is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  const auto found = std::find_if(
      journal.flushes.begin(), journal.flushes.end(),
      [flush_seq](const auto& flush) {
        return flush.flush_seq == flush_seq;
      });
  if (journal.session_id != session_id ||
      found == journal.flushes.end() || found->completed ||
      !recording_completion_revision_is_valid(
          journal.kind, found->expected_revision, committed_revision)) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance completion does not match the active session",
    });
  }
  return append_recording_record(
      platform_,
      bundle,
      document.value().journal.kind,
      document.value().valid_prefix_length,
      {{"committed_revision", committed_revision},
       {"flush_seq", flush_seq},
       {"kind", "complete"},
       {"performance_fingerprint", std::move(fingerprint)}});
}

foundation::Result<std::filesystem::path>
SequenceJournal::seal_performance(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    std::string reason) {
  if (reason.empty()) {
    return foundation::Result<std::filesystem::path>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recovery reason is empty",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(
        document.error());
  }
  if (document.value().journal.session_id != session_id) {
    return foundation::Result<std::filesystem::path>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance session does not match",
    });
  }
  const auto& checkpoint = document.value().journal.transient_checkpoint;
  if (!checkpoint.has_value() || !checkpoint->open_pads.empty() ||
      !checkpoint->open_fx.empty() || checkpoint->hold) {
    return foundation::Result<std::filesystem::path>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance recovery cannot seal open transients",
        {{"journal_retained", true},
         {"reason", "performance_transient_closure_required"}},
    });
  }
  document.value().journal.state = SequenceSessionState::owner_lost;
  return seal_recording_session(
      platform_,
      bundle,
      document.value().journal.kind,
      session_id,
      reason,
      performance_journal_json(document.value().journal));
}

foundation::Result<std::vector<PerformanceRecoveryCandidate>>
SequenceJournal::list_performance_recoverable(
    const std::filesystem::path& bundle) const {
  auto documents = read_checked_recovery_documents(
      *platform_, bundle, SessionKind::performance);
  if (!documents.has_value()) {
    return foundation::Result<
        std::vector<PerformanceRecoveryCandidate>>::failure(
        documents.error());
  }
  std::vector<PerformanceRecoveryCandidate> result;
  for (auto& document : documents.value()) {
    auto journal = parse_performance_snapshot(
        document.payload.at("journal"), document.path);
    if (!journal.has_value()) {
      return foundation::Result<
          std::vector<PerformanceRecoveryCandidate>>::failure(
          journal.error());
    }
    result.push_back(
        {std::move(journal.value()),
         document.payload.at("reason").get<std::string>(),
         std::move(document.path)});
  }
  return foundation::Result<
      std::vector<PerformanceRecoveryCandidate>>::success(std::move(result));
}

foundation::Result<void>
SequenceJournal::remove_active_performance_if_complete(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id) {
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (journal.session_id != session_id) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance session does not match",
    });
  }
  if (!journal.pending_events.empty() ||
      std::ranges::any_of(
          journal.flushes,
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance Journal still contains uncommitted events",
    });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_deletion,
      recording_active_path(bundle, SessionKind::performance));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  auto removed = platform_->remove(
      recording_active_path(bundle, SessionKind::performance));
  if (!removed.has_value()) {
    return removed;
  }
  return remove_performance_owner_lock(platform_, bundle);
}

foundation::Result<void> SequenceJournal::complete_performance_admission(
    const std::filesystem::path& bundle,
    foundation::SequenceSessionId session_id,
    const PerformanceAdmissionReceipt& receipt) {
  if (!domain::is_valid_uuid(session_id.value()) ||
      !domain::is_valid_uuid(receipt.request_id.value()) ||
      !lowercase_sha256(receipt.request_fingerprint) ||
      receipt.phase != PerformanceAdmissionPhase::completed ||
      receipt.result == PerformanceAdmissionResult::not_published) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance admission completion identity is invalid",
    });
  }
  auto mutex = append_mutex(platform_);
  std::lock_guard append_operation(*mutex);
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  auto document = read_performance_journal(*platform_, bundle);
  if (!document.has_value()) {
    return foundation::Result<void>::failure(document.error());
  }
  const auto& journal = document.value().journal;
  if (!is_live_control_profile(journal) ||
      journal.session_id != session_id) {
    return foundation::Result<void>::failure(Error{
        ErrorCode::invalid_argument,
        "Performance admission completion does not match the active session",
    });
  }
  const auto& ledger = *journal.admission_ledger;
  // The completion matches the unique pending admission by identity and
  // fingerprint; anything else is a collision or an expired retry, never a
  // second application.
  const auto matches_pending = [&]() {
    return ledger.pending.has_value() &&
           ledger.pending->request_id == receipt.request_id &&
           ledger.pending->expected_recording_sequence ==
               receipt.expected_recording_sequence &&
           ledger.pending->request_fingerprint ==
               receipt.request_fingerprint &&
           ledger.pending->accepted_tick == receipt.accepted_tick &&
           ledger.pending->input_sequence == receipt.input_sequence &&
           ledger.pending->event_input_sequences ==
               receipt.event_input_sequences &&
           ledger.pending->binding_result == receipt.binding_result;
  };
  if (matches_pending()) {
    const auto payload = nlohmann::json{
        {"expected_revision", journal.expected_revision},
        {"kind", "admission_complete"},
        {"performance_id", journal.performance_id.value()},
        {"receipt", admission_receipt_json(receipt)},
        {"tail_seq", journal.next_tail_seq - 1},
    };
    auto appended = append_recording_record(
        platform_,
        bundle,
        document.value().journal.kind,
        document.value().valid_prefix_length,
        payload);
    if (appended.has_value()) {
      return appended;
    }
    // The metadata write may have persisted before its sync failed: re-read,
    // then either accept the exact present record or rewrite the identical
    // bytes once from the validated prefix. Never a second logical write.
    auto observed = read_performance_journal(*platform_, bundle);
    const auto completed_matches = [&]() {
      return observed.has_value() &&
             observed.value().journal.admission_ledger.has_value() &&
             !observed.value().journal.admission_ledger->pending.has_value() &&
             observed.value().journal.admission_ledger->completed ==
                 receipt &&
             observed.value().journal.admission_ledger
                     ->next_recording_sequence ==
                 ledger.next_recording_sequence + 1;
    };
    if (completed_matches()) {
      return foundation::Result<void>::success();
    }
    if (observed.has_value() && observed.value().journal == journal) {
      auto retried = append_recording_record(
          platform_,
          bundle,
          document.value().journal.kind,
          document.value().valid_prefix_length,
          payload);
      if (retried.has_value()) {
        return retried;
      }
      auto after_retry = read_performance_journal(*platform_, bundle);
      if (after_retry.has_value() &&
          after_retry.value().journal == journal) {
        return foundation::Result<void>::failure(retried.error());
      }
    }
    return foundation::Result<void>::failure(Error{
        ErrorCode::io_error,
        "Performance admission completion outcome is unknown after durable "
        "append",
        {{"journal_retained", true},
         {"reason", "performance_admission_complete_outcome_unknown"},
         {"remedy",
          "freeze the in-memory session and reconcile the retained Journal "
          "before accepting more input"}},
    });
  }
  // Exact reattach of an already-completed admission returns its durable
  // receipt without another write.
  if (ledger.completed.has_value() &&
      ledger.completed->request_id == receipt.request_id &&
      ledger.completed->expected_recording_sequence ==
          receipt.expected_recording_sequence &&
      ledger.completed->request_fingerprint ==
          receipt.request_fingerprint &&
      ledger.completed->accepted_tick == receipt.accepted_tick &&
      ledger.completed->input_sequence == receipt.input_sequence &&
      ledger.completed->event_input_sequences ==
          receipt.event_input_sequences &&
      ledger.completed->binding_result == receipt.binding_result &&
      ledger.completed->phase == receipt.phase &&
      ledger.completed->result == receipt.result) {
    return foundation::Result<void>::success();
  }
  return foundation::Result<void>::failure(Error{
      ErrorCode::invalid_argument,
      "Performance admission completion does not match the durable window",
      {{"reason", "performance_admission_receipt_invalid"},
       {"remedy",
        "query the durable ledger for the original identity before "
        "completing; an expired or foreign admission is never rewritten"}},
  });
}

PerformanceAdmissionLookup lookup_performance_admission(
    const ActivePerformanceJournal& journal,
    const foundation::CommandId& request_id,
    std::uint64_t expected_recording_sequence,
    std::string_view request_fingerprint) {
  using Status = PerformanceAdmissionLookupStatus;
  if (!journal.admission_ledger.has_value()) {
    return {Status::unavailable, std::nullopt};
  }
  const auto& ledger = *journal.admission_ledger;
  const auto window_hit =
      [&](const PerformanceAdmissionReceipt& receipt)
      -> PerformanceAdmissionLookup {
    if (receipt.request_id == request_id &&
        receipt.expected_recording_sequence == expected_recording_sequence) {
      return {receipt.request_fingerprint == request_fingerprint
                  ? Status::exact
                  : Status::collision,
              receipt};
    }
    return {Status::occupied, std::nullopt};
  };
  if (ledger.pending.has_value() &&
      (ledger.pending->request_id == request_id ||
       ledger.pending->expected_recording_sequence ==
           expected_recording_sequence)) {
    return window_hit(*ledger.pending);
  }
  if (ledger.completed.has_value() &&
      (ledger.completed->request_id == request_id ||
       ledger.completed->expected_recording_sequence ==
           expected_recording_sequence)) {
    return window_hit(*ledger.completed);
  }
  if (expected_recording_sequence < ledger.next_recording_sequence) {
    return {Status::retry_expired, std::nullopt};
  }
  if (expected_recording_sequence > ledger.next_recording_sequence) {
    return {Status::out_of_order, std::nullopt};
  }
  return {Status::fresh, std::nullopt};
}

}  // namespace lmdj::project_io
