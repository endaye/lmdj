#include "capture_writer.hpp"

#include <array>
#include <chrono>
#include <cstddef>
#include <utility>
#include <vector>

#include <lmdj/domain/project.hpp>

namespace lmdj::native_host {

CaptureWriter::CaptureWriter(
    audio::RealtimeEngine& engine,
    facade::Application& application,
    std::mutex& facade_mutex,
    std::filesystem::path project_path,
    foundation::SequenceSessionId session_id)
    : engine_(engine),
      application_(application),
      facade_mutex_(facade_mutex),
      project_path_(std::move(project_path)),
      session_id_(std::move(session_id)) {}

CaptureWriter::~CaptureWriter() {
  request_stop();
  if (thread_.joinable()) {
    thread_.join();
  }
}

void CaptureWriter::start() {
  thread_ = std::jthread([this] { run(); });
}

void CaptureWriter::request_stop() noexcept {
  stop_requested_.store(true, std::memory_order_release);
}

void CaptureWriter::join() {
  if (thread_.joinable()) {
    thread_.join();
  }
}

std::uint64_t CaptureWriter::persisted_events() const noexcept {
  return persisted_events_.load(std::memory_order_relaxed);
}

std::uint64_t CaptureWriter::failure_count() const noexcept {
  return failure_count_.load(std::memory_order_acquire);
}

const std::optional<foundation::Error>&
CaptureWriter::failure_after_join() const noexcept {
  return failure_;
}

void CaptureWriter::run() {
  std::array<audio::CapturedTriggerEvent, 64> captured{};
  while (true) {
    const auto count = engine_.drain_capture(captured);
    if (count == 0) {
      const auto state = engine_.capture_telemetry().state;
      if (stop_requested_.load(std::memory_order_acquire) &&
          (state == audio::CaptureState::idle ||
           state == audio::CaptureState::corrupted)) {
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
      continue;
    }

    const auto origin = engine_.capture_telemetry().capture_origin_frame;
    std::vector<facade::SequenceEventRequest> events;
    events.reserve(count * 2U);
    for (std::size_t index = 0; index < count; ++index) {
      const auto& event = captured.at(index);
      const domain::PadSlotId slot{
          static_cast<std::uint8_t>(event.slot / 16U),
          static_cast<std::uint8_t>(event.slot % 16U),
      };
      const auto runtime_frame = origin + event.frame_offset;
      events.push_back(facade::SequenceEventRequest{
          project_path_, session_id_,
          facade::SequencePadEvent{
              slot, event.velocity, runtime_frame, event.sequence * 2U, true}});
      events.push_back(facade::SequenceEventRequest{
          project_path_, session_id_,
          facade::SequencePadEvent{
              slot, 0, runtime_frame, event.sequence * 2U + 1U, false}});
    }

    std::lock_guard lock(facade_mutex_);
    for (const auto& event : events) {
      const auto recorded = application_.record_sequence_event(event);
      if (!recorded.has_value()) {
        failure_ = recorded.error();
        failure_count_.store(1, std::memory_order_release);
        return;
      }
    }
    persisted_events_.fetch_add(count, std::memory_order_relaxed);
  }
}

}  // namespace lmdj::native_host
