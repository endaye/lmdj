#include <lmdj/audio/apple/coreaudio_output.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/json.hpp>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

using lmdj::audio::EnqueueResult;
using lmdj::audio::PreparedSampleBank;
using lmdj::audio::PublishResult;
using lmdj::audio::RealtimeEngine;
using lmdj::audio::RealtimeState;
using lmdj::audio::TriggerEvent;
using lmdj::audio::apple::CoreAudioOutput;
using lmdj::audio::apple::CoreAudioState;
using lmdj::foundation::ProjectId;
using nlohmann::json;

constexpr int kOperationalFailure = 2;
constexpr int kUsageFailure = 64;
constexpr std::uint32_t kRenderFrames = 128;
constexpr std::size_t kRenderBlocks = 10;
constexpr auto kProbeProjectId = "00000000-0000-4000-8000-000000000005";

std::string_view realtime_state_name(RealtimeState state) noexcept {
  return state == RealtimeState::running ? "running" : "stopped";
}

std::string_view coreaudio_state_name(CoreAudioState state) noexcept {
  switch (state) {
    case CoreAudioState::stopped:
      return "stopped";
    case CoreAudioState::running:
      return "running";
    case CoreAudioState::failed:
      return "failed";
  }
  return "failed";
}

std::string_view enqueue_result_name(EnqueueResult result) noexcept {
  switch (result) {
    case EnqueueResult::accepted:
      return "accepted";
    case EnqueueResult::invalid_slot:
      return "invalid_slot";
    case EnqueueResult::invalid_velocity:
      return "invalid_velocity";
    case EnqueueResult::sample_unavailable:
      return "sample_unavailable";
    case EnqueueResult::not_running:
      return "not_running";
    case EnqueueResult::bank_transition:
      return "bank_transition";
    case EnqueueResult::queue_full:
      return "queue_full";
  }
  return "unknown";
}

std::string_view publish_result_name(PublishResult result) noexcept {
  switch (result) {
    case PublishResult::accepted:
      return "accepted";
    case PublishResult::events_pending:
      return "events_pending";
    case PublishResult::bank_slots_full:
      return "bank_slots_full";
    case PublishResult::publish_queue_full:
      return "publish_queue_full";
  }
  return "unknown";
}

void write_response(const json& response) {
  std::cout << lmdj::foundation::canonical_json(response) << '\n';
  std::cout.flush();
}

json success(std::string_view command, json result) {
  return {
      {"command", command},
      {"ok", true},
      {"result", std::move(result)},
  };
}

json command_error(std::string_view command, std::string_view code) {
  return {
      {"command", command},
      {"error", {{"code", code}}},
      {"ok", false},
  };
}

json operation_error(
    std::string_view command, const lmdj::foundation::Error& error) {
  return {
      {"command", command},
      {"error",
       {
           {"code", lmdj::foundation::error_code_name(error.code)},
           {"message", error.message},
       }},
      {"ok", false},
  };
}

[[noreturn]] void terminal_adapter_failure(
    std::string_view command, const lmdj::foundation::Error& error) {
  write_response(operation_error(command, error));
  std::_Exit(kOperationalFailure);
}

class NativeAudioProbe final {
 public:
  explicit NativeAudioProbe(bool no_device) : no_device_(no_device) {}

  int run() {
    std::vector<float> sample(1'200);
    for (std::size_t frame = 0; frame < sample.size(); ++frame) {
      constexpr double kPi = 3.14159265358979323846;
      sample[frame] = static_cast<float>(
          std::sin(
              2.0 * kPi * 880.0 * static_cast<double>(frame) / 48'000.0) *
          0.12);
    }

    auto bank = PreparedSampleBank::empty(ProjectId{kProbeProjectId}, 0);
    const auto prepared = bank.set_sample(0, sample);
    if (!prepared.has_value()) {
      write_response(operation_error("startup", prepared.error()));
      return kOperationalFailure;
    }
    const auto published = engine_.publish_sample_bank(std::move(bank));
    if (published != PublishResult::accepted) {
      write_response(
          command_error("startup", publish_result_name(published)));
      return kOperationalFailure;
    }

    if (!no_device_) {
      output_ = std::make_unique<CoreAudioOutput>(engine_);
    }
    if (const auto exit_code = start("startup"); exit_code != 0) {
      return exit_code;
    }
    write_response(success("startup", {{"state", state_name()}}));

    std::string command;
    while (std::getline(std::cin, command)) {
      if (command == "trigger") {
        trigger();
      } else if (command == "status") {
        write_response(success("status", status()));
      } else if (command == "stop") {
        if (const auto exit_code = stop("stop"); exit_code != 0) {
          return exit_code;
        }
        write_response(success("stop", {{"state", state_name()}}));
      } else if (command == "start") {
        if (const auto exit_code = start("start"); exit_code != 0) {
          return exit_code;
        }
        write_response(success("start", {{"state", state_name()}}));
      } else if (command == "quit") {
        return quit();
      } else {
        write_response(command_error(command, "unknown_command"));
      }
    }
    return quit();
  }

 private:
  int start(std::string_view command) {
    const auto started = no_device_ ? engine_.start() : output_->start();
    if (started.has_value()) {
      return 0;
    }
    if (!no_device_ && output_->state() == CoreAudioState::failed) {
      terminal_adapter_failure(command, started.error());
    }
    write_response(operation_error(command, started.error()));
    return kOperationalFailure;
  }

  int stop(std::string_view command) {
    if (no_device_) {
      engine_.stop();
      return 0;
    }
    const auto stopped = output_->stop();
    if (stopped.has_value()) {
      return 0;
    }
    if (output_->state() == CoreAudioState::failed) {
      terminal_adapter_failure(command, stopped.error());
    }
    write_response(operation_error(command, stopped.error()));
    return kOperationalFailure;
  }

  int quit() {
    if (const auto exit_code = stop("quit"); exit_code != 0) {
      return exit_code;
    }
    write_response(success("quit", {{"state", state_name()}}));
    return 0;
  }

  void trigger() {
    const auto sequence = next_sequence_;
    const auto result = engine_.enqueue(TriggerEvent{sequence, 0, 100});
    if (result != EnqueueResult::accepted) {
      write_response(command_error("trigger", enqueue_result_name(result)));
      return;
    }

    ++next_sequence_;
    if (no_device_) {
      for (std::size_t block = 0; block < kRenderBlocks; ++block) {
        std::array<float, kRenderFrames> left{};
        std::array<float, kRenderFrames> right{};
        engine_.render(left.data(), right.data(), kRenderFrames);
      }
    }
    write_response(
        success("trigger", {{"sequence", sequence}, {"status", "accepted"}}));
  }

  std::string_view state_name() const noexcept {
    if (no_device_) {
      return realtime_state_name(engine_.telemetry().state);
    }
    return coreaudio_state_name(output_->state());
  }

  json status() const {
    const auto engine = engine_.telemetry();
    std::uint64_t device_overloads = 0;
    std::uint64_t callback_failures = 0;
    std::uint64_t deadline_overruns = 0;
    if (!no_device_) {
      const auto coreaudio = output_->telemetry();
      device_overloads = coreaudio.device_overloads;
      callback_failures = coreaudio.callback_failures;
      deadline_overruns = coreaudio.deadline_overruns;
    }

    return {
        {"active_voices", engine.active_voices},
        {"callback_count", engine.callback_count},
        {"callback_failures", callback_failures},
        {"cancelled_events", engine.cancelled_events},
        {"cancelled_voices", engine.cancelled_voices},
        {"channels", lmdj::audio::kRealtimeChannels},
        {"completed_voices", engine.completed_voices},
        {"deadline_overruns", deadline_overruns},
        {"dequeued_events", engine.dequeued_events},
        {"device_overloads", device_overloads},
        {"enqueued_events", engine.enqueued_events},
        {"invalid_events", engine.invalid_events},
        {"max_callback_frames", engine.max_callback_frames},
        {"queue_capacity", lmdj::audio::kRealtimeQueueCapacity},
        {"queue_drops", engine.queue_drops},
        {"queued_events", engine.queued_events},
        {"rendered_frames", engine.rendered_frames},
        {"sample_rate", lmdj::audio::kRealtimeSampleRate},
        {"started_voices", engine.started_voices},
        {"state", state_name()},
        {"stopped_rejections", engine.stopped_rejections},
        {"voice_capacity", lmdj::audio::kRealtimeVoiceCapacity},
        {"voice_drops", engine.voice_drops},
    };
  }

  bool no_device_;
  RealtimeEngine engine_;
  std::unique_ptr<CoreAudioOutput> output_;
  std::uint64_t next_sequence_ = 1;
};

void usage(const char* executable) {
  std::cerr << "usage: " << executable << " [--no-device]\n";
}

}  // namespace

int main(int argc, char* argv[]) {
  bool no_device = false;
  if (argc == 2 && std::string_view(argv[1]) == "--no-device") {
    no_device = true;
  } else if (argc != 1) {
    usage(argv[0]);
    return kUsageFailure;
  }

  NativeAudioProbe probe(no_device);
  return probe.run();
}
