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
    foundation::TakeId take_id)
    : engine_(engine),
      application_(application),
      facade_mutex_(facade_mutex),
      project_path_(std::move(project_path)),
      take_id_(std::move(take_id)) {}

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

    std::vector<domain::RawTakeEvent> events;
    events.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
      const auto& event = captured.at(index);
      events.push_back(domain::RawTakeEvent{
          domain::PadSlotId{
              static_cast<std::uint8_t>(event.slot / 16U),
              static_cast<std::uint8_t>(event.slot % 16U),
          },
          event.frame_offset,
          event.velocity,
      });
    }

    std::lock_guard lock(facade_mutex_);
    const auto appended = application_.append_realtime_take_events(
        project_path_, take_id_, events);
    if (!appended.has_value()) {
      failure_ = appended.error();
      failure_count_.store(1, std::memory_order_release);
      return;
    }
    persisted_events_.fetch_add(count, std::memory_order_relaxed);
  }
}

}  // namespace lmdj::native_host
