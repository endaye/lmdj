#pragma once

#include <cstddef>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

#include <lmdj/facade/performance_recording_metadata.hpp>

namespace lmdj::web_runtime::detail {

// Control owns this bounded ledger. Each worker owns only a detached public
// Facade reader, immutable selector and heap result; it never borrows Runtime.
class RecordingMetadataQueries final {
 public:
  static constexpr std::size_t capacity = 16;
  enum class Start { accepted, duplicate, full, worker_failed };
  using Read = foundation::Result<facade::PerformanceRecordingRead>;

  RecordingMetadataQueries();
  ~RecordingMetadataQueries();
  RecordingMetadataQueries(const RecordingMetadataQueries&) = delete;
  RecordingMetadataQueries& operator=(const RecordingMetadataQueries&) = delete;

  Start start(std::string id, facade::PerformanceRecordingMetadataRequest request,
              std::unique_ptr<facade::PerformanceRecordingMetadataReader> reader);
  bool contains(std::string_view id) const;
  // Cancellation consumes only the observer. An unfinished worker retains its
  // place and custody until service observes its real return and joins it.
  std::optional<Read> inspect(std::string_view id, bool consume, bool cancel);
  void retire() noexcept;
  void service();
  bool workers_stopped() const noexcept;
  bool pending() const noexcept { return !jobs_.empty(); }

 private:
  struct Job;
  std::map<std::string, std::unique_ptr<Job>, std::less<>> jobs_;
};

}  // namespace lmdj::web_runtime::detail
