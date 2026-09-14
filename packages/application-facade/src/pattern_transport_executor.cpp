#include <lmdj/facade/pattern_transport_ports.hpp>

#include <condition_variable>
#include <mutex>
#include <stdexcept>
#include <thread>

#include <lmdj/domain/project.hpp>

namespace lmdj::facade {
namespace {
foundation::Error failure(const char* reason) {
  return {foundation::ErrorCode::internal_error,
          "Pattern transport work did not provide a known outcome",
          {{"reason", reason},
           {"remedy", "inspect the retained operation before retrying any effect"}}};
}
PatternTransportWorkCompletion unknown(const char* reason) {
  return {PatternTransportWorkOutcome::unknown, {}, failure(reason)};
}
bool valid(const PatternTransportWorkCompletion& result) {
  if (result.payload.size() > kPatternTransportWorkPayloadBytes) return false;
  switch (result.outcome) {
    case PatternTransportWorkOutcome::success: return !result.error;
    case PatternTransportWorkOutcome::refused:
    case PatternTransportWorkOutcome::unknown:
      return result.error &&
          result.error->message.size() <= kPatternTransportWorkPayloadBytes &&
          result.error->details.dump().size() <= kPatternTransportWorkPayloadBytes;
  }
  return false;
}
}  // namespace

struct PatternTransportExecutor::Impl {
  explicit Impl(std::uint64_t generation_value, Factory factory)
      : generation(generation_value), thread([this, factory = std::move(factory)] {
          run(factory);
        }) {}

  void run(const Factory& factory) {
    std::unique_ptr<PatternTransportWorkOwner> owner;
    try {
      owner = factory();
      if (!owner) throw std::runtime_error("missing work owner");
    } catch (...) {
      std::lock_guard lock(mutex);
      startup_error = failure("pattern_transport_worker_start_failed");
      stopped = true;
      return;
    }
    std::unique_lock lock(mutex);
    ready = true;
    for (;;) {
      changed.wait(lock, [&] { return shutdown || (request && !completion); });
      if (request && !completion) {
        // Retain the original payload in the cell for exact duplicate checks.
        const auto work = *request;
        lock.unlock();
        PatternTransportWorkCompletion result;
        try {
          result = owner->execute(work);
          if (!valid(result)) result = unknown("pattern_transport_work_invalid_result");
        } catch (...) {
          // execute may already have committed. Exceptions are unknown, never
          // proof of refusal/absence, and private exception text is not exposed.
          result = unknown("pattern_transport_work_exception");
        }
        auto retained = std::make_shared<const PatternTransportWorkCompletion>(std::move(result));
        lock.lock();
        completion = std::move(retained);
      }
      if (shutdown) break;
    }
    lock.unlock();
    owner.reset();  // OPFS token registry belongs to this thread.
    lock.lock();
    stopped = true;
  }

  const std::uint64_t generation;
  mutable std::mutex mutex;
  std::condition_variable changed;
  bool ready{};
  bool shutdown{};
  bool stopped{};
  std::uint64_t last_step{};
  std::uint64_t last_epoch{};
  std::optional<PatternTransportWorkRequest> request;
  std::shared_ptr<const PatternTransportWorkCompletion> completion;
  std::optional<foundation::Error> startup_error;
  // Last: all state must exist before the worker can access it.
  std::thread thread;
};

PatternTransportExecutor::PatternTransportExecutor(
    std::uint64_t generation, Factory factory) {
  if (generation == 0 || !factory) throw std::invalid_argument("invalid transport executor owner");
  impl_ = std::make_unique<Impl>(generation, std::move(factory));
}
PatternTransportExecutor::~PatternTransportExecutor() {
  request_shutdown();
  impl_->thread.join();
}
PatternTransportWorkSubmit PatternTransportExecutor::submit(
    const PatternTransportWorkRequest& request) {
  const auto& identity = request.identity;
  if (!identity.step || !identity.transport_epoch ||
      !domain::is_valid_uuid(identity.command_id.value()) ||
      request.payload.size() > kPatternTransportWorkPayloadBytes)
    return PatternTransportWorkSubmit::invalid;
  std::lock_guard lock(impl_->mutex);
  if (identity.runtime_generation != impl_->generation)
    return PatternTransportWorkSubmit::stale;
  if (impl_->request && impl_->request->identity == identity)
    return *impl_->request == request ? PatternTransportWorkSubmit::replayed
                                     : PatternTransportWorkSubmit::invalid;
  if (impl_->shutdown || impl_->stopped || !impl_->ready)
    return PatternTransportWorkSubmit::unavailable;
  if (impl_->request) return PatternTransportWorkSubmit::busy;
  if (identity.step <= impl_->last_step || identity.transport_epoch < impl_->last_epoch)
    return PatternTransportWorkSubmit::stale;
  impl_->request = request;
  impl_->last_step = identity.step;
  impl_->last_epoch = identity.transport_epoch;
  impl_->changed.notify_one();
  return PatternTransportWorkSubmit::accepted;
}
PatternTransportExecutorStatus PatternTransportExecutor::inspect() const {
  std::lock_guard lock(impl_->mutex);
  return {impl_->ready, impl_->shutdown, impl_->stopped,
          impl_->request ? std::optional{impl_->request->identity} : std::nullopt,
          impl_->completion, impl_->startup_error};
}
bool PatternTransportExecutor::consume(const PatternTransportWorkIdentity& identity) {
  std::lock_guard lock(impl_->mutex);
  if (!impl_->request || impl_->request->identity != identity || !impl_->completion)
    return false;
  impl_->request.reset();
  impl_->completion.reset();
  return true;
}
void PatternTransportExecutor::request_shutdown() {
  std::lock_guard lock(impl_->mutex);
  impl_->shutdown = true;
  impl_->changed.notify_one();
}
}  // namespace lmdj::facade
