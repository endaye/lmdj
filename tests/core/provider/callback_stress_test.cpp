#include <atomic>
#include <iostream>
#include <thread>
#include "tests/core/provider/byte_harness.hpp"
using namespace byte_fixture;
int main() {
  try {
    for (int iteration = 0; iteration < 300; ++iteration) {
      Fixture f;
      std::thread worker;
      std::atomic<bool> start{false}, rejected{false};
      ArtifactSource saved;
      f.install(f.registration([&](auto context) {
        saved = context.source;
        worker = std::thread([&, callback = context.source] {
          while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
          rejected = !callback("inputs", 0).has_value();
        });
        auto result = success(context);
        start.store(true, std::memory_order_release);
        return result;
      }));
      auto config = options();
      auto result = f.execute(request(), config);
      worker.join();
      LMDJ_CHECK(rejected);
      if (result.error) f.reason(result, ErrorCode::invalid_argument, "input_binding_invalid");
      else LMDJ_CHECK(result.candidate.has_value());
      auto before = f.store.inspect(result.attempt_id);
      LMDJ_CHECK(before.has_value());
      LMDJ_CHECK(!saved("inputs", 0).has_value());
      auto after = f.store.inspect(result.attempt_id);
      LMDJ_CHECK(after.has_value());
      LMDJ_CHECK(before.value().status == after.value().status);
      LMDJ_CHECK(before.value().candidate_outputs == after.value().candidate_outputs);
      LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
    }
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
