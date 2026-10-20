#include "recording_metadata_queries.hpp"

#include <atomic>
#include <stop_token>
#include <thread>
#include <utility>

namespace lmdj::web_runtime::detail {

struct RecordingMetadataQueries::Job {
  struct State {
    std::atomic<bool> returned{false};
    std::optional<Read> result;
  };
  std::shared_ptr<State> state = std::make_shared<State>();
  std::stop_source stop;
  std::thread worker;
  bool retired = false;
  bool consumed = false;

  ~Job() {
    stop.request_stop();
    if (worker.joinable()) {
      // Native direct destruction is not a physical-release witness. All
      // unfinished inputs are heap-owned; formal bridge disposal must first
      // observe workers_stopped() after actual service/join.
      worker.detach();
    }
  }
};

RecordingMetadataQueries::RecordingMetadataQueries() = default;
RecordingMetadataQueries::~RecordingMetadataQueries() = default;

RecordingMetadataQueries::Start RecordingMetadataQueries::start(
    std::string id, facade::PerformanceRecordingMetadataRequest request,
    std::unique_ptr<facade::PerformanceRecordingMetadataReader> reader) {
  service();
  if (jobs_.contains(id)) return Start::duplicate;
  if (jobs_.size() == capacity) return Start::full;
  auto job = std::make_unique<Job>();
  const auto state = job->state;
  const auto token = job->stop.get_token();
  // Own the ledger entry before starting the worker, including allocation
  // failures. A failed thread creation cannot leave an untracked worker.
  auto [entry, inserted] = jobs_.emplace(std::move(id), std::move(job));
  static_cast<void>(inserted);
  try {
    entry->second->worker = std::thread(
        [state, token, request = std::move(request), reader = std::move(reader)]() mutable {
          try { state->result.emplace(reader->inspect(request, token)); }
          catch (...) { /* The control boundary reports a generic failure. */ }
          reader.reset();
          state->returned.store(true, std::memory_order_release);
        });
  } catch (...) {
    jobs_.erase(entry);
    return Start::worker_failed;
  }
  return Start::accepted;
}

bool RecordingMetadataQueries::contains(std::string_view id) const {
  const auto found = jobs_.find(id);
  return found != jobs_.end() && !found->second->consumed;
}

void RecordingMetadataQueries::service() {
  for (auto i = jobs_.begin(); i != jobs_.end();) {
    auto& job = *i->second;
    if (job.state->returned.load(std::memory_order_acquire) && job.worker.joinable())
      job.worker.join(); // No outstanding reader or I/O; reclaim the actual thread.
    if (job.consumed && !job.worker.joinable()) i = jobs_.erase(i);
    else ++i;
  }
}

std::optional<RecordingMetadataQueries::Read> RecordingMetadataQueries::inspect(
    std::string_view id, bool consume, bool cancel) {
  service();
  const auto found = jobs_.find(id);
  if (found == jobs_.end() || found->second->consumed) return std::nullopt;
  auto& job = *found->second;
  if (cancel) { job.retired = true; job.stop.request_stop(); }
  std::optional<Read> result;
  if (job.retired) {
    result.emplace(Read::success(facade::PerformanceRecordingRead{
        facade::PerformanceRecordingReadCancelled{}}));
  } else if (!job.worker.joinable()) {
    if (job.state->result) result = *job.state->result;
    else result.emplace(Read::failure({foundation::ErrorCode::internal_error,
                                       "Recording metadata worker failed"}));
  }
  if (result && consume) { job.consumed = true; service(); }
  return result;
}

void RecordingMetadataQueries::retire() noexcept {
  for (auto& [id, job] : jobs_) {
    static_cast<void>(id);
    job->retired = true;
    job->stop.request_stop();
  }
}

bool RecordingMetadataQueries::workers_stopped() const noexcept {
  for (const auto& [id, job] : jobs_) {
    static_cast<void>(id);
    if (job->worker.joinable()) return false;
  }
  return true;
}

}  // namespace lmdj::web_runtime::detail
