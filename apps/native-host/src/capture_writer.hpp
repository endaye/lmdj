#pragma once

#include <atomic>
#include <cstdint>
#include <filesystem>
#include <mutex>
#include <optional>
#include <thread>

#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/facade/application.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/foundation/ids.hpp>

namespace lmdj::native_host {

class CaptureWriter final {
 public:
  CaptureWriter(
      audio::RealtimeEngine& engine,
      facade::Application& application,
      std::mutex& facade_mutex,
      std::filesystem::path project_path,
      foundation::SequenceSessionId session_id);
  ~CaptureWriter();

  CaptureWriter(const CaptureWriter&) = delete;
  CaptureWriter& operator=(const CaptureWriter&) = delete;

  void start();
  void request_stop() noexcept;
  void join();
  std::uint64_t persisted_events() const noexcept;
  std::uint64_t failure_count() const noexcept;
  const std::optional<foundation::Error>& failure_after_join() const noexcept;

 private:
  void run();

  audio::RealtimeEngine& engine_;
  facade::Application& application_;
  std::mutex& facade_mutex_;
  std::filesystem::path project_path_;
  foundation::SequenceSessionId session_id_;
  std::jthread thread_;
  std::atomic<bool> stop_requested_{false};
  std::atomic<std::uint64_t> persisted_events_{0};
  std::atomic<std::uint64_t> failure_count_{0};
  std::optional<foundation::Error> failure_;
};

}  // namespace lmdj::native_host
