#include <lmdj/facade/pattern_transport_ports.hpp>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <source_location>
#include <stdexcept>
#include <thread>

using namespace lmdj::facade;
namespace {
void check(bool value, const std::source_location location = std::source_location::current()) {
  if (!value) throw std::runtime_error(
      "transport executor assertion failed at line " + std::to_string(location.line()));
}
template<class Predicate> void await(Predicate predicate) {
  const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!predicate()) {
    if (std::chrono::steady_clock::now() >= end)
      throw std::runtime_error("transport executor completion deadline");
    std::this_thread::yield();
  }
}
struct Probe {
  std::mutex mutex;
  std::condition_variable cv;
  bool release{};
  bool entered{};
  bool throws{};
  std::optional<PatternTransportWorkCompletion> result;
  std::atomic<unsigned> executions{};
  std::atomic<bool> destroyed{};
  std::thread::id created_on;
  std::thread::id ran_on;
  std::thread::id destroyed_on;
};
class Worker final : public PatternTransportWorkOwner {
 public:
  explicit Worker(Probe& probe) : probe_(probe) {
    probe_.created_on = std::this_thread::get_id();
  }
  ~Worker() override {
    probe_.destroyed_on = std::this_thread::get_id();
    probe_.destroyed.store(true);
  }
  PatternTransportWorkCompletion execute(
      const PatternTransportWorkRequest& request) override {
    probe_.ran_on = std::this_thread::get_id();
    ++probe_.executions;
    std::unique_lock lock(probe_.mutex);
    probe_.entered = true;
    probe_.cv.notify_all();
    probe_.cv.wait(lock, [&] { return probe_.release; });
    if (probe_.throws) throw std::runtime_error("private implementation detail");
    if (probe_.result) return *probe_.result;
    return {PatternTransportWorkOutcome::success, request.payload, std::nullopt};
  }
 private:
  Probe& probe_;
};
PatternTransportWorkRequest request(std::uint64_t step = 1) {
  return {{7, 1, lmdj::foundation::CommandId{"11111111-1111-4111-8111-111111111111"}, step}, "prepare"};
}
void release(Probe& probe) {
  std::lock_guard lock(probe.mutex);
  probe.release = true;
  probe.cv.notify_all();
}
void ready(PatternTransportExecutor& executor) {
  await([&] { return executor.inspect().ready; });
}
struct ReleaseOnExit {
  Probe& probe;
  ~ReleaseOnExit() { release(probe); }
};
void retained_completion_and_owner_lifetime() {
  Probe probe;
  PatternTransportExecutor executor(7, [&] { return std::make_unique<Worker>(probe); });
  ReleaseOnExit cleanup{probe};
  ready(executor);
  const auto work = request();
  check(executor.submit(work) == PatternTransportWorkSubmit::accepted);
  await([&] { std::lock_guard lock(probe.mutex); return probe.entered; });
  check(!executor.inspect().completion);
  check(executor.submit(work) == PatternTransportWorkSubmit::replayed);
  auto changed = work;
  changed.payload = "flush";
  check(executor.submit(changed) == PatternTransportWorkSubmit::invalid);
  check(executor.submit(request(2)) == PatternTransportWorkSubmit::busy);
  check(!executor.consume(work.identity));
  // Shutdown is nonblocking even while real work is still unresolved.
  executor.request_shutdown();
  check(!executor.inspect().stopped);
  check(!probe.destroyed.load());
  release(probe);
  await([&] { return executor.inspect().stopped; });
  const auto observed = executor.inspect();
  check(observed.completion && observed.completion->payload == "prepare");
  check(observed.completion->outcome == PatternTransportWorkOutcome::success);
  check(probe.executions == 1);
  check(probe.created_on != std::this_thread::get_id());
  check(probe.created_on == probe.ran_on && probe.ran_on == probe.destroyed_on);
  check(executor.consume(work.identity));
  check(!executor.consume(work.identity));
  // A previously obtained immutable receipt remains usable after consumption.
  check(observed.completion->payload == "prepare");
  check(executor.submit(request(2)) == PatternTransportWorkSubmit::unavailable);
}
void stale_generation_and_consumed_step_do_not_reexecute() {
  Probe probe;
  probe.release = true;
  PatternTransportExecutor executor(7, [&] { return std::make_unique<Worker>(probe); });
  ready(executor);
  auto stale = request();
  stale.identity.runtime_generation = 6;
  check(executor.submit(stale) == PatternTransportWorkSubmit::stale);
  auto large = request();
  large.payload.assign(kPatternTransportWorkPayloadBytes + 1, 'x');
  check(executor.submit(large) == PatternTransportWorkSubmit::invalid);
  const auto work = request();
  check(executor.submit(work) == PatternTransportWorkSubmit::accepted);
  await([&] { return executor.inspect().completion != nullptr; });
  check(executor.submit(request(2)) == PatternTransportWorkSubmit::busy);
  auto wrong = work.identity;
  ++wrong.step;
  check(!executor.consume(wrong));
  check(executor.consume(work.identity));
  check(executor.submit(work) == PatternTransportWorkSubmit::stale);
  check(executor.submit(request(2)) == PatternTransportWorkSubmit::accepted);
  await([&] { return executor.inspect().completion != nullptr; });
  check(probe.executions == 2);
}
void exception_is_unknown_not_a_retryable_refusal() {
  Probe probe;
  probe.release = true;
  probe.throws = true;
  PatternTransportExecutor executor(7, [&] { return std::make_unique<Worker>(probe); });
  ready(executor);
  check(executor.submit(request()) == PatternTransportWorkSubmit::accepted);
  await([&] { return executor.inspect().completion != nullptr; });
  const auto receipt = executor.inspect().completion;
  check(receipt->outcome == PatternTransportWorkOutcome::unknown);
  check(receipt->error.has_value());
  check(receipt->error->message.find("private") == std::string::npos);
  check(executor.submit(request()) == PatternTransportWorkSubmit::replayed);
  check(probe.executions == 1);
}
void failed_start_is_terminal() {
  PatternTransportExecutor executor(7, []() -> std::unique_ptr<PatternTransportWorkOwner> {
    throw std::runtime_error("owner initialization failed");
  });
  await([&] { return executor.inspect().stopped; });
  check(executor.inspect().startup_error.has_value());
  check(executor.submit(request()) == PatternTransportWorkSubmit::unavailable);
}
void invalid_worker_result_is_retained_as_unknown() {
  for (const auto& result : {
      PatternTransportWorkCompletion{PatternTransportWorkOutcome::success,
          std::string(kPatternTransportWorkPayloadBytes + 1, 'x'), std::nullopt},
      PatternTransportWorkCompletion{PatternTransportWorkOutcome::refused, {}, std::nullopt}}) {
    Probe probe;
    probe.release = true;
    probe.result = result;
    PatternTransportExecutor executor(7, [&] { return std::make_unique<Worker>(probe); });
    ready(executor);
    check(executor.submit(request()) == PatternTransportWorkSubmit::accepted);
    await([&] { return executor.inspect().completion != nullptr; });
    const auto completion = executor.inspect().completion;
    check(completion->outcome == PatternTransportWorkOutcome::unknown);
    check(completion->payload.empty() && completion->error.has_value());
    check(executor.submit(request()) == PatternTransportWorkSubmit::replayed);
    check(probe.executions == 1);
  }
}
void refusal_and_epoch_watermark_are_preserved() {
  Probe probe;
  probe.release = true;
  probe.result = PatternTransportWorkCompletion{PatternTransportWorkOutcome::refused, {},
      lmdj::foundation::Error{lmdj::foundation::ErrorCode::io_error, "known refusal"}};
  PatternTransportExecutor executor(7, [&] { return std::make_unique<Worker>(probe); });
  ready(executor);
  auto work = request();
  work.identity.transport_epoch = 2;
  check(executor.submit(work) == PatternTransportWorkSubmit::accepted);
  await([&] { return executor.inspect().completion != nullptr; });
  check(executor.inspect().completion->outcome == PatternTransportWorkOutcome::refused);
  check(executor.inspect().completion->error->message == "known refusal");
  check(executor.consume(work.identity));
  check(executor.submit(request(2)) == PatternTransportWorkSubmit::stale);
  check(probe.executions == 1);
}
}  // namespace
int main() {
  try {
    retained_completion_and_owner_lifetime();
    stale_generation_and_consumed_step_do_not_reexecute();
    exception_is_unknown_not_a_retryable_refusal();
    failed_start_is_terminal();
    invalid_worker_result_is_retained_as_unknown();
    refusal_and_epoch_watermark_are_preserved();
    std::cout << "Pattern transport executor: 6 cases passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
