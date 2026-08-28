#include <lmdj/project_io/sequence_journal.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <utility>

#include <nlohmann/json.hpp>
#include <picosha2.h>

#include <lmdj/foundation/json.hpp>

#include "testing_hooks.hpp"

namespace lmdj::project_io {
namespace {

using foundation::Error;
using foundation::ErrorCode;

constexpr std::string_view kJournalContract = "lmdj.sequence.journal.v1";
constexpr std::string_view kRecoveryContract = "lmdj.sequence.recovery.v1";

struct JournalDocument {
  ActiveSequenceJournal journal;
  std::uint64_t valid_prefix_length{};
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

std::filesystem::path active_path(const std::filesystem::path& bundle) {
  return bundle / "recovery/active/sequence.jsonl";
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
            slot.at("bank").get<std::uint8_t>(),
            slot.at("pad").get<std::uint8_t>(),
        },
        input.at("onset_tick").get<std::uint32_t>(),
        input.at("duration_tick").get<std::uint32_t>(),
        input.at("velocity").get<std::uint8_t>(),
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

foundation::Result<nlohmann::json> checked_payload(
    const nlohmann::json& record,
    const std::filesystem::path& path) {
  try {
    if (!record.is_object() || record.size() != 2 ||
        !record.contains("checksum") || !record.contains("payload")) {
      throw std::runtime_error("record envelope is invalid");
    }
    const auto checksum = record.at("checksum").get<std::string>();
    const auto encoded = foundation::canonical_json(record.at("payload"));
    if (!lowercase_sha256(checksum) || sha256(encoded) != checksum) {
      throw std::runtime_error("record checksum does not match payload");
    }
    return foundation::Result<nlohmann::json>::success(record.at("payload"));
  } catch (const std::exception& exception) {
    return foundation::Result<nlohmann::json>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence Journal checksum record is invalid",
            {{"path", path.generic_string()}, {"detail", exception.what()}},
        });
  }
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
      {"pattern_id", flush.pattern_id.value()},
  };
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
    flushes.push_back(std::move(encoded));
  }
  return {
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
      {"next_flush_seq", journal.next_flush_seq},
      {"pattern_fingerprint", journal.pattern_fingerprint},
      {"pattern_id", journal.pattern_id.value()},
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
        input.at("bars").get<std::uint8_t>(),
        input.at("pattern_fingerprint").get<std::string>(),
        input.at("expected_revision").get<std::uint64_t>(),
        input.at("next_flush_seq").get<std::uint64_t>(),
        parse_state(input.at("state").get<std::string>()),
        {},
        std::nullopt,
        std::nullopt,
    };
    journal.armed_capture_slot = optional_slot(input, "armed_capture_slot");
    const auto capture = input.find("capture_commit");
    if (capture != input.end() && !capture->is_null()) {
      journal.capture_commit = parse_capture(*capture, path);
    }
    if (!domain::is_valid_uuid(journal.session_id.value()) ||
        !domain::is_valid_uuid(journal.pattern_id.value()) ||
        !valid_bars(journal.bars) ||
        !lowercase_sha256(journal.pattern_fingerprint)) {
      throw std::runtime_error("recovery metadata is invalid");
    }
    const auto loop_length = domain::pattern_length_ticks(journal.bars);
    for (const auto& encoded : input.at("flushes")) {
      SequenceFlushRecord flush{
          encoded.at("flush_seq").get<std::uint64_t>(),
          foundation::CommandId{encoded.at("command_id").get<std::string>()},
          foundation::PatternId{encoded.at("pattern_id").get<std::string>()},
          encoded.at("expected_revision").get<std::uint64_t>(),
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
      journal.flushes.push_back(std::move(flush));
    }
    return foundation::Result<ActiveSequenceJournal>::success(
        std::move(journal));
  } catch (const std::exception& exception) {
    return foundation::Result<ActiveSequenceJournal>::failure(
        Error{
            ErrorCode::invalid_project,
            "Sequence recovery document is invalid",
            {{"path", path.generic_string()}, {"detail", exception.what()}},
        });
  }
}

foundation::Result<JournalDocument> read_journal(
    const ProjectStoragePlatform& platform,
    const std::filesystem::path& bundle) {
  auto tree = validate_journal_tree(platform, bundle);
  if (!tree.has_value()) {
    return foundation::Result<JournalDocument>::failure(tree.error());
  }
  const auto path = active_path(bundle);
  auto exists = platform.exists(path);
  if (!exists.has_value()) {
    return foundation::Result<JournalDocument>::failure(exists.error());
  }
  if (!exists.value()) {
    return foundation::Result<JournalDocument>::failure(
        Error{
            ErrorCode::not_found,
            "active Sequence Journal does not exist",
            {{"path", path.generic_string()}},
        });
  }
  auto read = platform.read_complete(path);
  if (!read.has_value()) {
    return foundation::Result<JournalDocument>::failure(read.error());
  }
  const auto bytes = byte_string(read.value());
  JournalDocument document{
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
      },
      0,
  };
  std::size_t cursor = 0;
  bool saw_begin = false;
  try {
    while (cursor < bytes.size()) {
      const auto line_end = bytes.find('\n', cursor);
      if (line_end == std::string::npos) {
        break;
      }
      const auto line = bytes.substr(cursor, line_end - cursor);
      cursor = line_end + 1;
      if (line.empty()) {
        document.valid_prefix_length = cursor;
        continue;
      }
      const auto envelope = parse_bounded_or_throw(line);
      auto payload = checked_payload(envelope, path);
      if (!payload.has_value()) {
        return foundation::Result<JournalDocument>::failure(payload.error());
      }
      const auto kind = payload.value().at("kind").get<std::string>();
      if (!saw_begin) {
        if (kind != "begin" ||
            payload.value().at("contract") != kJournalContract) {
          throw std::runtime_error("first record is not a Sequence begin");
        }
        document.journal = ActiveSequenceJournal{
            foundation::SequenceSessionId{
                payload.value().at("session_id").get<std::string>()},
            foundation::PatternId{
                payload.value().at("pattern_id").get<std::string>()},
            payload.value().at("bars").get<std::uint8_t>(),
            payload.value().at("pattern_fingerprint").get<std::string>(),
            payload.value().at("expected_revision").get<std::uint64_t>(),
            0,
            SequenceSessionState::active,
            {},
            std::nullopt,
            std::nullopt,
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
      } else if (kind == "flush") {
        SequenceFlushRecord flush{
            payload.value().at("flush_seq").get<std::uint64_t>(),
            foundation::CommandId{
                payload.value().at("command_id").get<std::string>()},
            foundation::PatternId{
                payload.value().at("pattern_id").get<std::string>()},
            payload.value().at("expected_revision").get<std::uint64_t>(),
            {},
            false,
        };
        if (document.journal.capture_commit.has_value() ||
            flush.flush_seq != document.journal.next_flush_seq ||
            !domain::is_valid_uuid(flush.command_id.value()) ||
            !domain::is_valid_uuid(flush.pattern_id.value()) ||
            flush.pattern_id != document.journal.pattern_id) {
          throw std::runtime_error("Sequence flush identity is invalid");
        }
        const auto loop_length =
            domain::pattern_length_ticks(document.journal.bars);
        for (const auto& encoded : payload.value().at("events")) {
          auto parsed = parse_event(encoded, loop_length, path);
          if (!parsed.has_value()) {
            return foundation::Result<JournalDocument>::failure(
                parsed.error());
          }
          flush.canonical_events.push_back(parsed.value());
        }
        document.journal.flushes.push_back(std::move(flush));
        ++document.journal.next_flush_seq;
      } else if (kind == "complete") {
        const auto sequence =
            payload.value().at("flush_seq").get<std::uint64_t>();
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
        found->completed = true;
        document.journal.expected_revision =
            payload.value().at("committed_revision").get<std::uint64_t>();
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
            payload.value().at("expected_revision").get<std::uint64_t>();
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
            payload.value().at("committed_revision").get<std::uint64_t>();
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
        const auto bars = payload.value().at("bars").get<std::uint8_t>();
        const auto fingerprint =
            payload.value().at("pattern_fingerprint").get<std::string>();
        const auto expected_revision =
            payload.value().at("expected_revision").get<std::uint64_t>();
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
        document.journal.pattern_id = pattern_id;
        document.journal.bars = bars;
        document.journal.pattern_fingerprint = fingerprint;
        document.journal.expected_revision = expected_revision;
        document.journal.state = SequenceSessionState::active;
      } else {
        throw std::runtime_error("Sequence Journal record kind is invalid");
      }
      document.valid_prefix_length = cursor;
    }
    if (!saw_begin) {
      throw std::runtime_error("Sequence Journal has no durable begin record");
    }
    return foundation::Result<JournalDocument>::success(std::move(document));
  } catch (const std::exception& exception) {
    return foundation::Result<JournalDocument>::failure(
        Error{
            ErrorCode::invalid_project,
            "active Sequence Journal could not be parsed",
            {{"path", path.generic_string()}, {"detail", exception.what()}},
        });
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

foundation::Result<void> append_record(
    const std::shared_ptr<ProjectStoragePlatform>& platform,
    const std::filesystem::path& bundle,
    const JournalDocument& document,
    nlohmann::json payload) {
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_write, active_path(bundle));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  const auto bytes = foundation::canonical_json(
                         checked_record(std::move(payload))) +
                     "\n";
  return platform->append_durable(
      active_path(bundle), document.valid_prefix_length, byte_span(bytes));
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

}  // namespace

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
  auto tree = validate_journal_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return tree;
  }
  auto lease = platform_->acquire_writer(bundle);
  if (!lease.has_value()) {
    return foundation::Result<void>::failure(lease.error());
  }
  auto operation = std::move(lease.value());
  (void)operation;
  const auto path = active_path(bundle);
  auto exists = platform_->exists(path);
  if (!exists.has_value()) {
    return foundation::Result<void>::failure(exists.error());
  }
  if (exists.value()) {
    auto active = read_journal(*platform_, bundle);
    auto details = nlohmann::json{{"reason", "sequence_session_active"}};
    if (active.has_value()) {
      details["session_id"] = active.value().journal.session_id.value();
    }
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "a Sequence session is already active for this Project",
            std::move(details),
        });
  }
  const auto payload = nlohmann::json{
      {"armed_capture_slot",
       armed_capture_slot.has_value()
           ? nlohmann::json(slot_json(*armed_capture_slot))
           : nlohmann::json(nullptr)},
      {"bars", bars},
      {"contract", kJournalContract},
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
  if (journal.session_id != session_id || journal.pattern_id != pattern_id ||
      journal.expected_revision != expected_revision ||
      journal.state != SequenceSessionState::active ||
      journal.capture_commit.has_value()) {
    return foundation::Result<SequenceFlushRecord>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence flush does not match the active session",
        });
  }
  const std::vector<domain::PatternEvent> incoming{
      events.begin(), events.end()};
  auto canonical = domain::merge_pattern_events({}, incoming);
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
  SequenceFlushRecord flush{
      journal.next_flush_seq,
      std::move(command_id),
      std::move(pattern_id),
      expected_revision,
      std::move(canonical),
      false,
  };
  auto appended = append_record(platform_, bundle, document.value(), flush_json(flush));
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
      testing::FaultPoint::sequence_journal_completion, active_path(bundle));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  return append_record(
      platform_,
      bundle,
      document.value(),
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
  return append_record(
      platform_, bundle, document.value(),
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
  return append_record(
      platform_, bundle, document.value(),
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
  return append_record(
      platform_, bundle, document.value(),
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
  return append_record(
      platform_, bundle, document.value(),
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
  return append_record(
      platform_, bundle, document.value(),
      {{"kind", "capture-disarm"}, {"slot", slot_json(slot)}});
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
  if (journal.session_id != session_id || journal.pattern_id == pattern_id ||
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
  return append_record(
      platform_, bundle, document.value(),
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
  const auto payload = nlohmann::json{
      {"contract", kRecoveryContract},
      {"journal", journal_json(document.value().journal)},
      {"reason", reason},
  };
  const auto bytes = foundation::canonical_json(checked_record(payload)) + "\n";
  const auto directory = bundle / "recovery/sealed";
  auto destination = directory /
                     (session_id.value() + "-" + file_reason(reason) + ".json");
  std::uint64_t suffix = 1;
  auto exists = platform_->exists(destination);
  if (!exists.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(exists.error());
  }
  while (exists.value()) {
    destination = directory /
                  (session_id.value() + "-" + file_reason(reason) + "-" +
                   std::to_string(suffix++) + ".json");
    exists = platform_->exists(destination);
    if (!exists.has_value()) {
      return foundation::Result<std::filesystem::path>::failure(exists.error());
    }
  }
  auto written = platform_->create_immutable(destination, byte_span(bytes));
  if (!written.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(written.error());
  }
  auto removed = platform_->remove(active_path(bundle));
  if (!removed.has_value()) {
    return foundation::Result<std::filesystem::path>::failure(removed.error());
  }
  return foundation::Result<std::filesystem::path>::success(
      std::move(destination));
}

foundation::Result<std::vector<SequenceRecoveryCandidate>>
SequenceJournal::list_recoverable(const std::filesystem::path& bundle) const {
  auto tree = validate_journal_tree(*platform_, bundle);
  if (!tree.has_value()) {
    return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
        tree.error());
  }
  auto names = platform_->list_names(bundle / "recovery/sealed");
  if (!names.has_value()) {
    return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
        names.error());
  }
  std::vector<SequenceRecoveryCandidate> result;
  for (const auto& name : names.value()) {
    const auto path = bundle / "recovery/sealed" / name;
    if (path.extension() != ".json") {
      continue;
    }
    auto read = platform_->read_complete(path);
    if (!read.has_value()) {
      return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
          read.error());
    }
    try {
      const auto envelope = parse_bounded_or_throw(byte_string(read.value()));
      auto payload = checked_payload(envelope, path);
      if (!payload.has_value()) {
        return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
            payload.error());
      }
      if (payload.value().at("contract") != kRecoveryContract) {
        throw std::runtime_error("Sequence recovery contract is invalid");
      }
      auto journal = parse_journal_snapshot(payload.value().at("journal"), path);
      if (!journal.has_value()) {
        return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
            journal.error());
      }
      result.push_back(
          {std::move(journal.value()),
           payload.value().at("reason").get<std::string>(), path});
    } catch (const std::exception& exception) {
      return foundation::Result<std::vector<SequenceRecoveryCandidate>>::failure(
          Error{
              ErrorCode::invalid_project,
              "Sequence recovery file could not be parsed",
              {{"path", path.generic_string()}, {"detail", exception.what()}},
          });
    }
  }
  std::sort(
      result.begin(), result.end(), [](const auto& left, const auto& right) {
        return left.path.generic_string() < right.path.generic_string();
      });
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
          [](const auto& flush) { return !flush.completed; })) {
    return foundation::Result<void>::failure(
        Error{
            ErrorCode::invalid_argument,
            "Sequence Journal still contains an incomplete flush",
        });
  }
#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING
  const auto fault = testing::detail::invoke_fault(
      testing::FaultPoint::sequence_journal_deletion, active_path(bundle));
  if (!fault.has_value()) {
    return fault;
  }
#endif
  return platform_->remove(active_path(bundle));
}

}  // namespace lmdj::project_io
