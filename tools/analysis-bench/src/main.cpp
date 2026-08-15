#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis_bench/loudness/factory.hpp>
#include <lmdj/analysis_bench/onsets/factory.hpp>
#include <lmdj/analysis_bench/peaks/factory.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace {

constexpr std::string_view kUsage =
    "usage: lmdj_analysis_bench --workspace DIR --fixture WAV "
    "--capability CAP --iterations N [--parameters JSON]\n";

struct Invocation {
  std::filesystem::path workspace;
  std::filesystem::path fixture;
  std::string capability;
  std::uint32_t iterations = 0;
  nlohmann::json parameters = nlohmann::json::object();
};

std::optional<Invocation> parse_invocation(int argc, char** argv) {
  Invocation invocation;
  bool have_workspace = false;
  bool have_fixture = false;
  bool have_capability = false;
  for (int index = 1; index + 1 < argc; index += 2) {
    const std::string_view flag(argv[index]);
    const std::string_view value(argv[index + 1]);
    if (flag == "--workspace") {
      invocation.workspace = std::filesystem::path(value);
      have_workspace = true;
    } else if (flag == "--fixture") {
      invocation.fixture = std::filesystem::path(value);
      have_fixture = true;
    } else if (flag == "--capability") {
      invocation.capability = std::string(value);
      have_capability = true;
    } else if (flag == "--iterations") {
      invocation.iterations =
          static_cast<std::uint32_t>(std::stoul(std::string(value)));
    } else if (flag == "--parameters") {
      invocation.parameters = nlohmann::json::parse(value);
    } else {
      return std::nullopt;
    }
  }
  if (!have_workspace || !have_fixture || !have_capability ||
      invocation.iterations == 0 ||
      !invocation.workspace.is_absolute() ||
      !invocation.parameters.is_object()) {
    return std::nullopt;
  }
  return invocation;
}

std::vector<std::byte> read_file(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  const std::vector<char> bytes{std::istreambuf_iterator<char>(stream),
                                std::istreambuf_iterator<char>()};
  std::vector<std::byte> output;
  output.reserve(bytes.size());
  std::transform(bytes.begin(), bytes.end(), std::back_inserter(output),
                 [](char value) {
                   return static_cast<std::byte>(
                       static_cast<unsigned char>(value));
                 });
  return output;
}

double median(std::vector<double> values) {
  std::sort(values.begin(), values.end());
  const auto middle = values.size() / 2;
  if (values.size() % 2 == 1) {
    return values[middle];
  }
  return (values[middle - 1] + values[middle]) / 2.0;
}

int fail(std::string_view message) {
  std::cerr << "analysis-bench: " << message << '\n';
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  const auto parsed = parse_invocation(argc, argv);
  if (!parsed.has_value()) {
    std::cerr << kUsage;
    return 64;
  }
  const auto& invocation = *parsed;
  std::error_code directory_error;
  std::filesystem::create_directories(
      invocation.workspace, directory_error);
  if (directory_error) {
    return fail("workspace directory cannot be created");
  }

  const auto described = lmdj::foundation::describe_artifact(
      invocation.fixture, "audio/wav");
  if (!described.has_value()) {
    return fail(described.error().message);
  }
  const auto fixture_artifact = described.value();
  const auto fixture_bytes = read_file(invocation.fixture);
  if (fixture_bytes.empty()) {
    return fail("fixture is empty or unreadable");
  }

  lmdj::analysis::ArtifactByteResolver resolver =
      [fixture_artifact, fixture_bytes](
          const lmdj::foundation::ArtifactRef& artifact)
      -> lmdj::foundation::Result<std::vector<std::byte>> {
    if (artifact.sha256 != fixture_artifact.sha256) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::not_found,
              "bench resolver only serves the fixture artifact",
              {{"sha256", artifact.sha256}},
          });
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        fixture_bytes);
  };

  lmdj::provider::Registry registry;
  for (auto registration :
       {lmdj::analysis_bench::peaks_registration(resolver),
        lmdj::analysis_bench::loudness_registration(resolver),
        lmdj::analysis_bench::onsets_registration(resolver)}) {
    const auto added = registry.add(std::move(registration));
    if (!added.has_value()) {
      return fail(added.error().message);
    }
  }

  lmdj::provider::AttemptStore attempts(
      invocation.workspace,
      lmdj::provider::ProviderPolicy{
          {"local"},
          {"public"},
          {"analysis-bench.execute"},
      },
      [] { return std::string("2026-01-01T00:00:00Z"); });

  nlohmann::json report{
      {"fixture", invocation.fixture.generic_string()},
      {"fixture_sha256", fixture_artifact.sha256},
      {"capability", invocation.capability},
      {"iterations", invocation.iterations},
      {"runs", nlohmann::json::array()},
  };

  std::uint32_t provider_index = 0;
  for (const auto& descriptor : registry.list()) {
    const auto serves = std::any_of(
        descriptor.capabilities.begin(),
        descriptor.capabilities.end(),
        [&](const lmdj::provider::CapabilityDescriptor& capability) {
          return capability.id == invocation.capability;
        });
    if (!serves) {
      continue;
    }
    const auto selected = attempts.set_provider_selection(
        invocation.capability, descriptor.id, registry);
    if (!selected.has_value()) {
      return fail(selected.error().message);
    }

    std::vector<double> timings_ms;
    std::string output_sha256;
    nlohmann::json output_json;
    for (std::uint32_t iteration = 0;
         iteration < invocation.iterations;
         ++iteration) {
      const std::string attempt_id =
          "bench-" + std::to_string(provider_index) + "-" +
          std::to_string(iteration);
      lmdj::provider::CapabilityRequest request;
      request.capability = invocation.capability;
      request.inputs = {lmdj::provider::ArtifactBinding{
          "sample",
          fixture_artifact,
      }};
      request.parameters = invocation.parameters;
      request.data_classification = "public";
      request.platform = "test";
      request.region = "local";
      request.required_permissions = {"analysis-bench.execute"};

      const auto started = std::chrono::steady_clock::now();
      auto executed = attempts.execute(
          lmdj::foundation::AttemptId{attempt_id},
          std::move(request),
          registry);
      const auto stopped = std::chrono::steady_clock::now();
      if (!executed.has_value()) {
        return fail(executed.error().message);
      }
      if (executed.value().error.has_value()) {
        return fail(executed.value().error->message);
      }
      timings_ms.push_back(
          std::chrono::duration<double, std::milli>(stopped - started)
              .count());

      const auto& candidate = executed.value().candidate;
      if (!candidate.has_value() || candidate->outputs.size() != 1) {
        return fail("candidate must carry exactly one output binding");
      }
      const auto& output_ref = candidate->outputs.front().artifact;
      if (iteration == 0) {
        output_sha256 = output_ref.sha256;
        const auto output_path = invocation.workspace / ".lmdj-workspace" /
                                 "attempts" / attempt_id / "artifacts" /
                                 output_ref.sha256;
        const auto output_bytes = read_file(output_path);
        if (output_bytes.empty()) {
          return fail("output artifact bytes are unreadable");
        }
        output_json = nlohmann::json::parse(
            reinterpret_cast<const char*>(output_bytes.data()),
            reinterpret_cast<const char*>(output_bytes.data()) +
                output_bytes.size());
      } else if (output_ref.sha256 != output_sha256) {
        return fail("provider output is not deterministic");
      }
    }

    report["runs"].push_back({
        {"provider_id", descriptor.id},
        {"deterministic", true},
        {"output_sha256", output_sha256},
        {"ms_min",
         *std::min_element(timings_ms.begin(), timings_ms.end())},
        {"ms_median", median(timings_ms)},
        {"ms_max",
         *std::max_element(timings_ms.begin(), timings_ms.end())},
        {"result", std::move(output_json)},
    });
    ++provider_index;
  }

  if (report["runs"].empty()) {
    return fail("no registered provider serves the capability");
  }
  std::cout << report.dump(2) << '\n';
  return 0;
}
