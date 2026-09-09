#include <iostream>
#include <thread>
#include <future>
#include <type_traits>
#include "tests/core/provider/byte_harness.hpp"
using namespace byte_fixture;

class OldProvider : public Provider {
 public:
  std::string id() const override { return "old"; }
  std::vector<std::string> capabilities() const override { return {}; }
  AttemptResult run(AttemptId, const CapabilityRequest&, const ArtifactSink&);
};
static_assert(std::is_abstract_v<OldProvider>);

void source_ownership() {
  Fixture f;
  auto config = options();
  auto owner = std::make_shared<std::vector<std::byte>>(1, std::byte{'a'});
  config.resolve_input = [owner](const auto&) {
    return Result<std::shared_ptr<const std::vector<std::byte>>>::success(owner);
  };
  ArtifactHandle retained;
  std::optional<ProviderRunContext> saved;
  f.install(f.registration([&](ProviderRunContext context) {
    saved = context;
    auto source = context.source("inputs", 0);
    LMDJ_CHECK(source.has_value());
    retained = source.value();
    (*owner)[0] = std::byte{'z'};
    LMDJ_CHECK(retained->bytes()[0] == std::byte{'a'});
    return success(context);
  }));
  auto result = f.execute(request(), config);
  LMDJ_CHECK(result.candidate.has_value());
  LMDJ_CHECK(config.staging_budget->used_bytes() == 1);
  LMDJ_CHECK(!saved->source("inputs", 0).has_value());
  LMDJ_CHECK(!saved->output("candidate", {}, "application/x-lmdj-proof").has_value());
  LMDJ_CHECK(f.store.inspect(result.attempt_id).value().status == AttemptStatus::succeeded);
  retained.reset();
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
  LMDJ_CHECK(saved->request->inputs[0].artifact.byte_length == 1);
}
void ingress_failure(int mode) {
  Fixture f;
  bool ran = false;
  f.install(f.registration([&](auto context) { ran = true; return success(context); }));
  auto config = options();
  auto input = request();
  ErrorCode code = ErrorCode::io_error;
  std::string reason = "input_artifact_mismatch";
  if (mode == 0) {
    config.resolve_input = {};
    code = ErrorCode::not_found; reason = "input_artifact_unavailable";
  } else if (mode == 1) {
    input.inputs[0].artifact.byte_length = 2;
  } else if (mode == 2) {
    config.resolve_input = [](const auto&) {
      return Result<std::shared_ptr<const std::vector<std::byte>>>::success(
          std::make_shared<const std::vector<std::byte>>(1, std::byte{'z'}));
    };
  } else if (mode == 3) {
    config.maximum_input_bytes = 0;
    code = ErrorCode::invalid_argument; reason = "input_artifact_too_large";
  } else {
    input.inputs[0].port = "undeclared";
    config.resolve_input = [](const auto&) -> Result<std::shared_ptr<const std::vector<std::byte>>> {
      throw std::runtime_error("must not read owner");
    };
    code = ErrorCode::invalid_argument; reason = "input_binding_invalid";
  }
  f.reason(f.execute(input, config), code, reason);
  LMDJ_CHECK(!ran);
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
void wrong_thread(bool sink) {
  Fixture f;
  f.install(f.registration([&](auto context) {
    std::thread worker([&] {
      if (sink) LMDJ_CHECK(!context.output("candidate", {}, "application/x-lmdj-proof").has_value());
      else LMDJ_CHECK(!context.source("inputs", 0).has_value());
    });
    worker.join();
    return success(context);
  }));
  f.reason(f.execute(request(), options()),
      sink ? ErrorCode::provider_failed : ErrorCode::invalid_argument,
      sink ? "output_contract_invalid" : "input_binding_invalid");
}
void retained_budget() {
  Fixture f;
  ArtifactHandle retained;
  f.install(f.registration([&](auto context) {
    retained = context.source("inputs", 0).value();
    return success(context);
  }));
  auto config = options();
  config.staging_budget = std::make_shared<StagingBudget>(1);
  LMDJ_CHECK(f.execute(request(), config, "first").candidate.has_value());
  f.reason(f.execute(request(), config, "second"), ErrorCode::invalid_argument,
           "input_artifact_too_large");
  retained.reset();
  LMDJ_CHECK(f.execute(request(), config, "third").candidate.has_value());
}
void occurrence_order() {
  Fixture f;
  auto input = request();
  input.inputs.insert(input.inputs.begin(),
      {"inputs", {"3b64db95cb55c763391c707108489ae18b4112d783300de38e033b4c98c3deaf", "audio/wav", 2}});
  f.install(f.registration([](auto context) {
    LMDJ_CHECK(context.source("inputs", 0).value()->bytes().size() == 2);
    LMDJ_CHECK(context.source("inputs", 1).value()->bytes()[0] == std::byte{'a'});
    return success(context);
  }));
  LMDJ_CHECK(f.execute(input, options()).candidate.has_value());
}
void aggregate_and_admission(int mode) {
  Fixture f;
  bool read = false, ran = false;
  f.install(f.registration([&](auto context) { ran = true; return success(context); }));
  auto input = request();
  auto config = options();
  const auto resolver = config.resolve_input;
  config.resolve_input = [&](const auto& artifact) { read = true; return resolver(artifact); };
  ErrorCode code = ErrorCode::invalid_argument;
  std::string reason = "input_artifact_too_large";
  if (mode < 2) {
    input.inputs.push_back({"inputs", {"3b64db95cb55c763391c707108489ae18b4112d783300de38e033b4c98c3deaf", "audio/wav", 2}});
    if (mode == 0) config.maximum_input_bytes = 2;
    else {
      input.inputs[0].artifact.byte_length = UINT64_MAX;
      config.maximum_input_bytes = UINT64_MAX;
    }
  } else if (mode == 2) {
    input.inputs.push_back(input.inputs.front());
    reason = "input_binding_invalid";
  } else {
    input.required_permissions.push_back("undeclared.permission");
    code = ErrorCode::permission_denied;
  }
  auto result = f.execute(input, config);
  if (mode == 3) LMDJ_CHECK(result.error->code == code);
  else f.reason(result, code, reason);
  LMDJ_CHECK(!read && !ran);
}
void invalid_occurrence() {
  Fixture f;
  f.install(f.registration([](auto context) {
    LMDJ_CHECK(!context.source("inputs", 1).has_value());
    return success(context);
  }));
  f.reason(f.execute(request(), options()), ErrorCode::invalid_argument, "input_binding_invalid");
}
void overlapping_attempts() {
  Fixture f;
  std::promise<void> entered, release;
  auto released = release.get_future();
  f.install(f.registration([&](auto context) {
    if (context.attempt_id.value() == "first") {
      entered.set_value(); released.wait();
    }
    return success(context);
  }));
  auto config = options();
  config.staging_budget = std::make_shared<StagingBudget>(1);
  std::optional<Result<AttemptResult>> first;
  std::thread worker([&] {
    first = f.store.execute(AttemptId{"first"}, request(), f.registry, config);
  });
  entered.get_future().wait();
  auto second = f.store.execute(AttemptId{"second"}, request(), f.registry, config);
  release.set_value(); worker.join();
  LMDJ_CHECK(first->has_value() && first->value().candidate.has_value());
  LMDJ_CHECK(second.has_value());
  f.reason(second.value(), ErrorCode::invalid_argument, "input_artifact_too_large");
  LMDJ_CHECK(config.staging_budget->used_bytes() == 0);
}
int main() {
  try {
    source_ownership();
    for (int mode = 0; mode < 5; ++mode) ingress_failure(mode);
    wrong_thread(false); wrong_thread(true);
    retained_budget(); occurrence_order();
    for (int mode = 0; mode < 4; ++mode) aggregate_and_admission(mode);
    invalid_occurrence();
    overlapping_attempts();
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
