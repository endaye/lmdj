#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <variant>

#include <nlohmann/json.hpp>

#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/json.hpp>

#include "tests/core/support/deterministic_rng.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::domain::AssignPad;
using lmdj::domain::Command;
using lmdj::domain::CommandMeta;
using lmdj::domain::CommandReceipt;
using lmdj::domain::CreatePattern;
using lmdj::domain::ImportAsset;
using lmdj::domain::PadSlotId;
using lmdj::domain::Pattern;
using lmdj::domain::PatternEvent;
using lmdj::domain::ProjectState;
using lmdj::domain::RawTake;
using lmdj::domain::RawTakeEvent;
using lmdj::domain::RecordTake;
using lmdj::foundation::ArtifactRef;
using lmdj::foundation::AssetId;
using lmdj::foundation::CommandId;
using lmdj::foundation::ErrorCode;
using lmdj::foundation::PatternId;
using lmdj::foundation::ProjectId;
using lmdj::foundation::TakeId;
using lmdj::test::DeterministicRng;

constexpr std::array<std::uint64_t, 5> kSeedOneValues{
    0x47e4ce4b896cdd1dULL,
    0xabcfa6a8e079651dULL,
    0xb9d10d8feb731f57ULL,
    0x4db418a0bb1b019dULL,
    0x0e6199b04d5aa600ULL,
};
constexpr std::array<std::uint8_t, 4> kBarChoices{1, 2, 4, 8};

std::string generated_uuid(char family, std::uint64_t seed,
                           std::uint64_t ordinal) {
  std::ostringstream value;
  value << family << "0000000-0000-4000-8000-"
        << std::hex << std::nouppercase << std::setfill('0')
        << std::setw(4) << seed
        << std::setw(8) << ordinal;
  return value.str();
}

std::string generated_sha(std::uint64_t seed, std::uint64_t ordinal) {
  constexpr std::string_view kHex = "0123456789abcdef";
  std::string sha(64, '0');
  auto value = (seed << 32U) ^ ordinal ^ 0xa5a5a5a55a5a5a5aULL;
  for (std::size_t index = 0; index < sha.size(); ++index) {
    sha.at(index) = kHex.at(value & 0x0fU);
    value = (value >> 4U) ^ (value << 7U) ^
            static_cast<std::uint64_t>(index + 1U);
  }
  return sha;
}

ProjectState new_project(std::uint64_t seed) {
  const auto created = lmdj::domain::create_project(
      ProjectId{generated_uuid('0', seed, 1)},
      static_cast<std::uint16_t>(40U + (seed % 201U)));
  LMDJ_CHECK(created.has_value());
  return created.value();
}

nlohmann::json canonical_state_value(const ProjectState& state) {
  auto banks = nlohmann::json::array();
  for (const auto& bank : state.banks) {
    for (const auto& pad : bank) {
      banks.push_back(nlohmann::json::array({
          pad.id.bank,
          pad.id.pad,
          pad.asset_id.has_value()
              ? nlohmann::json(pad.asset_id->value())
              : nlohmann::json(nullptr),
      }));
    }
  }

  auto assets = nlohmann::json::array();
  for (const auto& [id, asset] : state.assets) {
    assets.push_back(nlohmann::json::array({
        id.value(),
        asset.id.value(),
        asset.artifact.sha256,
        asset.artifact.media_type,
        asset.artifact.byte_length,
    }));
  }

  auto takes = nlohmann::json::array();
  for (const auto& [id, take] : state.takes) {
    auto events = nlohmann::json::array();
    for (const auto& event : take.events) {
      events.push_back(nlohmann::json::array({
          event.slot.bank,
          event.slot.pad,
          event.frame_offset,
          event.velocity,
      }));
    }
    takes.push_back(nlohmann::json::array({
        id.value(),
        take.id.value(),
        take.sample_rate,
        std::move(events),
    }));
  }

  auto patterns = nlohmann::json::array();
  for (const auto& [id, pattern] : state.patterns) {
    auto events = nlohmann::json::array();
    for (const auto& event : pattern.events) {
      events.push_back(nlohmann::json::array({
          event.slot.bank,
          event.slot.pad,
          event.step,
          event.velocity,
      }));
    }
    patterns.push_back(nlohmann::json::array({
        id.value(),
        pattern.id.value(),
        pattern.bars,
        std::move(events),
    }));
  }

  return nlohmann::json::array({
      state.id.value(),
      state.revision,
      state.bpm,
      std::move(banks),
      std::move(assets),
      std::move(takes),
      std::move(patterns),
  });
}

std::string canonical_state(const ProjectState& state) {
  return lmdj::foundation::canonical_json(canonical_state_value(state));
}

void check_pattern_slots(const ProjectState& state) {
  for (const auto& [id, pattern] : state.patterns) {
    LMDJ_CHECK(id == pattern.id);
    for (const auto& event : pattern.events) {
      LMDJ_CHECK(lmdj::domain::is_valid_slot(event.slot));
    }
  }
}

void check_receipt_identity(
    const std::map<CommandId, CommandReceipt>& receipts) {
  for (const auto& [command_id, receipt] : receipts) {
    LMDJ_CHECK(
        receipt.event.at("command_id") == command_id.value());
    LMDJ_CHECK(
        receipt.event.at("revision") == receipt.committed_revision);
  }
}

const CommandMeta& command_meta(const Command& command) {
  return std::visit(
      [](const auto& value) -> const CommandMeta& { return value.meta; },
      command);
}

PadSlotId generated_slot(DeterministicRng& rng) {
  return PadSlotId{
      static_cast<std::uint8_t>(rng.bounded(4)),
      static_cast<std::uint8_t>(rng.bounded(16)),
  };
}

std::vector<PatternEvent> generated_pattern_events(
    DeterministicRng& rng,
    std::uint8_t bars) {
  std::vector<PatternEvent> events;
  const auto count = 1U + static_cast<std::size_t>(rng.bounded(4));
  events.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    events.push_back(PatternEvent{
        generated_slot(rng),
        static_cast<std::uint32_t>(rng.bounded(
            static_cast<std::uint64_t>(bars) * 16U)),
        static_cast<std::uint8_t>(1U + rng.bounded(127)),
    });
  }
  return events;
}

std::vector<RawTakeEvent> generated_take_events(DeterministicRng& rng) {
  std::vector<RawTakeEvent> events;
  const auto count = 1U + static_cast<std::size_t>(rng.bounded(4));
  events.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    events.push_back(RawTakeEvent{
        generated_slot(rng),
        static_cast<std::uint32_t>(rng.bounded(192000)),
        static_cast<std::uint8_t>(1U + rng.bounded(127)),
    });
  }
  return events;
}

AssetId select_asset(const ProjectState& state, DeterministicRng& rng) {
  LMDJ_CHECK(!state.assets.empty());
  auto selected = state.assets.begin();
  std::advance(
      selected,
      static_cast<std::ptrdiff_t>(rng.bounded(state.assets.size())));
  return selected->first;
}

Command generated_valid_command(
    const ProjectState& state,
    DeterministicRng& rng,
    std::uint64_t seed,
    std::uint64_t ordinal,
    std::optional<std::uint64_t> expected_revision = std::nullopt,
    std::optional<std::uint64_t> forced_variant = std::nullopt) {
  const CommandMeta meta{
      CommandId{generated_uuid('1', seed, ordinal + 1U)},
      expected_revision.value_or(state.revision),
  };
  auto variant = forced_variant.value_or(ordinal % 4U);
  if (variant == 1U && state.assets.empty()) {
    variant = 0U;
  }
  switch (variant) {
    case 0:
      return Command{ImportAsset{
          meta,
          {
              AssetId{generated_uuid('2', seed, ordinal + 1U)},
              ArtifactRef{
                  generated_sha(seed, ordinal),
                  "audio/wav",
                  44U + rng.bounded(4096),
              },
          },
      }};
    case 1:
      return Command{AssignPad{
          meta,
          generated_slot(rng),
          select_asset(state, rng),
      }};
    case 2: {
      const auto bars = kBarChoices.at(rng.bounded(kBarChoices.size()));
      return Command{CreatePattern{
          meta,
          Pattern{
              PatternId{generated_uuid('3', seed, ordinal + 1U)},
              bars,
              generated_pattern_events(rng, bars),
          },
      }};
    }
    default: {
      const auto bars = kBarChoices.at(rng.bounded(kBarChoices.size()));
      return Command{RecordTake{
          meta,
          RawTake{
              TakeId{generated_uuid('4', seed, ordinal + 1U)},
              48000,
              generated_take_events(rng),
          },
          Pattern{
              PatternId{generated_uuid('3', seed, ordinal + 1U)},
              bars,
              generated_pattern_events(rng, bars),
          },
      }};
    }
  }
}

void check_applied_effect(
    const ProjectState& state,
    const Command& command) {
  std::visit(
      [&state](const auto& value) {
        using Value = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Value, ImportAsset>) {
          LMDJ_CHECK(state.assets.at(value.asset.id) == value.asset);
        } else if constexpr (std::is_same_v<Value, AssignPad>) {
          LMDJ_CHECK(
              state.banks.at(value.slot.bank).at(value.slot.pad).asset_id ==
              value.asset_id);
        } else if constexpr (std::is_same_v<Value, CreatePattern>) {
          LMDJ_CHECK(state.patterns.at(value.pattern.id) == value.pattern);
        } else {
          LMDJ_CHECK(state.takes.at(value.take.id) == value.take);
          LMDJ_CHECK(state.patterns.at(value.pattern.id) == value.pattern);
        }
      },
      command);
}

void apply_success(
    ProjectState& state,
    const Command& command,
    std::map<CommandId, CommandReceipt>& receipts) {
  const auto revision = state.revision;
  const auto applied = lmdj::domain::apply(state, command, receipts);
  LMDJ_CHECK(applied.has_value());
  LMDJ_CHECK(!applied.value().replayed);
  LMDJ_CHECK(applied.value().state.revision == revision + 1U);
  LMDJ_CHECK(
      applied.value().event.at("command_id") ==
      command_meta(command).command_id.value());
  LMDJ_CHECK(applied.value().event.at("revision") == revision + 1U);

  const auto inserted = receipts.emplace(
      command_meta(command).command_id,
      CommandReceipt{
          applied.value().state.revision,
          applied.value().event,
      });
  LMDJ_CHECK(inserted.second);
  LMDJ_CHECK(
      inserted.first->second.committed_revision ==
      applied.value().state.revision);
  LMDJ_CHECK(inserted.first->second.event == applied.value().event);

  state = applied.value().state;
  check_applied_effect(state, command);
  check_pattern_slots(state);
}

void check_failed_without_state_change(
    const ProjectState& state,
    const Command& command,
    const std::map<CommandId, CommandReceipt>& receipts,
    ErrorCode expected_error,
    std::string_view expected_canonical) {
  const auto result = lmdj::domain::apply(state, command, receipts);
  LMDJ_CHECK(!result.has_value());
  LMDJ_CHECK(result.error().code == expected_error);
  LMDJ_CHECK(canonical_state(state) == expected_canonical);
  check_pattern_slots(state);
}

template <typename Scenario>
void for_each_seed(Scenario&& scenario) {
  for (std::uint64_t seed = 0; seed <= 255; ++seed) {
    try {
      scenario(seed);
    } catch (const std::exception& error) {
      throw std::runtime_error(
          "seed " + std::to_string(seed) + ": " + error.what());
    }
  }
}

void set_expected_revision(Command& command, std::uint64_t revision) {
  std::visit(
      [revision](auto& value) {
        value.meta.expected_revision = revision;
      },
      command);
}

void set_command_id(Command& command, CommandId id) {
  std::visit(
      [&id](auto& value) {
        value.meta.command_id = id;
      },
      command);
}

struct MatrixEvidence {
  std::uint64_t valid_commands{};
  std::uint64_t stale_failures{};
  std::uint64_t duplicate_replays{};
  std::uint64_t invalid_id_failures{};
  std::uint64_t slot_identity_checks{};
};

MatrixEvidence run_generated_matrix() {
  MatrixEvidence evidence;
  for_each_seed([&evidence](std::uint64_t seed) {
    constexpr std::size_t kCommandCount = 64;
    DeterministicRng rng(seed);
    auto state = new_project(seed);
    std::map<CommandId, CommandReceipt> receipts;
    const PadSlotId observed_slot{
        static_cast<std::uint8_t>(seed % 4U),
        static_cast<std::uint8_t>((seed / 4U) % 16U),
    };
    const PatternId observed_pattern{
        generated_uuid('3', seed, kCommandCount + 1U)};
    std::array<AssetId, 2> assets{
        AssetId{generated_uuid('2', seed, 1)},
        AssetId{generated_uuid('2', seed, 2)},
    };
    auto selected_asset = assets.at(0);
    std::optional<Command> last_successful_command;
    std::optional<std::string> failure_baseline;
    std::uint64_t successful_count = 0;

    for (std::size_t index = 0; index < kCommandCount; ++index) {
      // Preserve the established generated sequence without constructing the
      // forced ImportAsset that every branch immediately replaced.
      static_cast<void>(rng.bounded(4096));
      Command command = [&]() -> Command {
        if (index < 2U) {
          return generated_valid_command(
              state, rng, seed, index, std::nullopt, 0);
        }
        if (index == 2U) {
          return Command{AssignPad{
              CommandMeta{
                  CommandId{generated_uuid('1', seed, index + 1U)},
                  state.revision,
              },
              observed_slot,
              assets.at(0),
          }};
        }
        if (index == 3U) {
          return Command{CreatePattern{
              CommandMeta{
                  CommandId{generated_uuid('1', seed, index + 1U)},
                  state.revision,
              },
              Pattern{
                  observed_pattern,
                  1,
                  {PatternEvent{observed_slot, 0, 127}},
              },
          }};
        }
        if (index == 4U) {
          return generated_valid_command(
              state, rng, seed, index, std::nullopt, 3);
        }
        return Command{AssignPad{
            CommandMeta{
                CommandId{generated_uuid('1', seed, index + 1U)},
                state.revision,
            },
            observed_slot,
            selected_asset,
        }};
      }();

      const auto scenario =
          index < 5U ? 0U : static_cast<unsigned>((index - 5U) % 5U);
      if (scenario == 0U || scenario == 4U) {
        if (scenario == 4U) {
          selected_asset = assets.at((index + seed) % assets.size());
          command = Command{AssignPad{
              CommandMeta{
                  CommandId{generated_uuid('1', seed, index + 1U)},
                  state.revision,
              },
              observed_slot,
              selected_asset,
          }};
        }
        apply_success(state, command, receipts);
        ++successful_count;
        LMDJ_CHECK(state.revision == successful_count);
        LMDJ_CHECK(receipts.size() == successful_count);
        last_successful_command = command;
        failure_baseline.reset();
        ++evidence.valid_commands;
      } else if (scenario == 1U) {
        if (!failure_baseline.has_value()) {
          failure_baseline = canonical_state(state);
        }
        set_expected_revision(command, state.revision + 1U);
        check_failed_without_state_change(
            state,
            command,
            receipts,
            ErrorCode::revision_conflict,
            *failure_baseline);
        ++evidence.stale_failures;
      } else if (scenario == 2U) {
        LMDJ_CHECK(last_successful_command.has_value());
        const auto replay = lmdj::domain::apply(
            state, *last_successful_command, receipts);
        LMDJ_CHECK(replay.has_value());
        LMDJ_CHECK(replay.value().replayed);
        LMDJ_CHECK(replay.value().state == state);
        const auto& receipt =
            receipts.at(command_meta(*last_successful_command).command_id);
        LMDJ_CHECK(
            replay.value().state.revision == receipt.committed_revision);
        LMDJ_CHECK(replay.value().event == receipt.event);
        check_pattern_slots(replay.value().state);
        ++evidence.duplicate_replays;
      } else {
        if (!failure_baseline.has_value()) {
          failure_baseline = canonical_state(state);
        }
        auto invalid_id = command_meta(command).command_id.value();
        invalid_id.back() = 'A';
        set_command_id(command, CommandId{invalid_id});
        const std::map<CommandId, CommandReceipt> invalid_receipt{
            {
                CommandId{invalid_id},
                CommandReceipt{
                    999,
                    {
                        {"command_id", invalid_id},
                        {"revision", 999},
                        {"type", "must.not.replay"},
                    },
                },
            },
        };
        check_failed_without_state_change(
            state,
            command,
            invalid_receipt,
            ErrorCode::invalid_argument,
            *failure_baseline);
        ++evidence.invalid_id_failures;
      }

      if (index >= 3U) {
        const auto& event =
            state.patterns.at(observed_pattern).events.at(0);
        LMDJ_CHECK(event.slot == observed_slot);
        const auto resolved =
            lmdj::domain::resolve_slot_asset(state, event.slot);
        LMDJ_CHECK(resolved.has_value());
        LMDJ_CHECK(resolved->id == selected_asset);
        ++evidence.slot_identity_checks;
      }
      LMDJ_CHECK(state.revision == successful_count);
      LMDJ_CHECK(receipts.size() == successful_count);
      check_receipt_identity(receipts);
      check_pattern_slots(state);
    }
  });
  return evidence;
}

const MatrixEvidence& generated_matrix_evidence() {
  static const MatrixEvidence evidence = run_generated_matrix();
  return evidence;
}

void test_deterministic_rng_contract() {
  DeterministicRng rng(1);
  LMDJ_CHECK(rng.seed() == 1);
  for (const auto expected : kSeedOneValues) {
    LMDJ_CHECK(rng.next_u64() == expected);
  }

  DeterministicRng zero_seed(0);
  DeterministicRng documented_state(0x9e3779b97f4a7c15ULL);
  LMDJ_CHECK(zero_seed.seed() == 0);
  for (std::size_t index = 0; index < kSeedOneValues.size(); ++index) {
    LMDJ_CHECK(zero_seed.next_u64() == documented_state.next_u64());
  }
}

void test_generated_valid_sequences_increment_revision_once() {
  LMDJ_CHECK(
      generated_matrix_evidence().valid_commands == 256U * 28U);
}

void test_generated_stale_commands_leave_state_byte_identical() {
  LMDJ_CHECK(
      generated_matrix_evidence().stale_failures == 256U * 12U);
}

void test_generated_duplicate_commands_replay_original_outcome() {
  LMDJ_CHECK(
      generated_matrix_evidence().duplicate_replays == 256U * 12U);
}

void test_generated_invalid_ids_fail_before_receipt_lookup() {
  LMDJ_CHECK(
      generated_matrix_evidence().invalid_id_failures == 256U * 12U);
}

void test_generated_pad_reassignment_keeps_pattern_slot_identity() {
  LMDJ_CHECK(
      generated_matrix_evidence().slot_identity_checks ==
      256U * (64U - 3U));
}

}  // namespace

int main() {
  try {
    test_deterministic_rng_contract();
    test_generated_valid_sequences_increment_revision_once();
    test_generated_stale_commands_leave_state_byte_identical();
    test_generated_duplicate_commands_replay_original_outcome();
    test_generated_invalid_ids_fail_before_receipt_lookup();
    test_generated_pad_reassignment_keeps_pattern_slot_identity();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "domain model sequence tests: PASS\n";
  return 0;
}
