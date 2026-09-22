// S3 observation harness. Only AttemptStore::execute is inside the timer.
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/providers/local_sample_slice/factory.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>

using namespace lmdj::foundation;
using namespace lmdj::provider;
using namespace lmdj::providers;
using Json = nlohmann::json;

void require(bool ok, const char* why) {
  if (!ok) throw std::runtime_error(why);
}
std::string read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  require(file.good(), "cannot read evidence/input");
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
auto bytes(std::string_view value) { return std::as_bytes(std::span{value.data(), value.size()}); }

int main(int argc, char** argv) {
  try {
    require(argc == 5, "usage: slice-evaluation REPO MANIFEST NEW_WORKSPACE UTC");
    const std::filesystem::path repo = argv[1], manifest_path = argv[2], workspace = argv[3];
    require(!std::filesystem::exists(workspace), "workspace exists; retain it and choose a new path");
    std::filesystem::create_directories(workspace);
    const auto manifest = Json::parse(read(manifest_path));
    auto make_store = [&] {
      return AttemptStore{workspace, {{"local"}, {"public"}, {"sample.slice.execute"}},
                          [&] { return std::string(argv[4]); }};
    };
    auto store = make_store();
    Registry registry;
    auto registration = local_sample_slice_registration();
    Json result{{"provider_id", registration.implementation->id()}, {"version", registration.version},
                {"artifact_sha256", registration.artifact_sha256}, {"parameters", Json::object()},
                {"manifest_sha256", describe_artifact(manifest_path, "application/json").value().sha256},
                {"cases", Json::array()}};
    const auto provider_id = registration.implementation->id();
    require(registry.add(std::move(registration)).has_value(), "registry registration failed");
    require(store.set_provider_selection("sample.slice.v1", provider_id, registry).has_value(), "selection failed");
    unsigned sequence = 0;
    for (const auto& item : manifest.at("scenarios")) {
      const bool present = item.contains("path");
      std::string original;
      ArtifactRef ref{std::string(64, 'a'), "audio/wav", 44};
      if (present) {
        const auto file = repo / item.at("path").get<std::string>();
        original = read(file);
        const auto described = describe_artifact(file, "audio/wav");
        require(described.has_value(), "input identity unavailable");
        ref = described.value();
        require(ref.sha256 == item.at("sha256").get<std::string>() &&
                ref.byte_length == item.at("byte_length").get<std::uint64_t>(), "fixture identity mismatch");
      }
      const auto owner = std::make_shared<const std::vector<std::byte>>(bytes(original).begin(), bytes(original).end());
      CapabilityRequest request{"sample.slice.v1", {{"source_audio", ref}}, Json::object(),
                                "public", "test", "local", {"sample.slice.execute"}};
      Json row{{"fixture_id", item.at("id")}, {"runs", Json::array()}};
      for (unsigned repeat = 0; repeat < 2; ++repeat) {
        ExecutionOptions options{
            [&](const ArtifactRef& wanted) -> Result<std::shared_ptr<const std::vector<std::byte>>> {
              if (!present || wanted != ref) return Result<std::shared_ptr<const std::vector<std::byte>>>::failure(
                  {ErrorCode::not_found, "owner has no bytes"});
              return Result<std::shared_ptr<const std::vector<std::byte>>>::success(owner);
            }, 16777216, 262144, std::make_shared<StagingBudget>(67108864)};
        const AttemptId id{"evaluation-" + std::to_string(++sequence)};
        const auto before = std::chrono::steady_clock::now();
        const auto executed = store.execute(id, request, registry, options);
        const auto after = std::chrono::steady_clock::now();
        require(executed.has_value(), "execute failed without AttemptResult");
        const auto& attempt = executed.value();
        require(options.staging_budget->used_bytes() == 0, "staging budget leaked");
        const auto persisted = make_store().inspect(id);
        require(persisted.has_value(), "AttemptStore reopen failed");
        Json run{{"attempt_id", id.value()},
                 {"elapsed_seconds", std::chrono::duration<double>(after - before).count()}};
        if (attempt.error) {
          require(!attempt.candidate && persisted.value().status == AttemptStatus::failed &&
                  persisted.value().candidate_ids.empty() && persisted.value().minted_outputs.empty(), "failed Attempt retained outputs");
          require(persisted.value().error && persisted.value().error->details == attempt.error->details,
                  "failure changed after reopen");
          run["error_reason"] = attempt.error->details.at("reason");
          run["persisted_status"] = "failed";
        } else {
          require(attempt.candidate && attempt.candidate->outputs.size() == 1, "expected one slice_points output");
          const auto& binding = attempt.candidate->outputs.front();
          require(binding.port == "slice_points", "wrong output port");
          const auto file = workspace / ".lmdj-workspace/attempts" / id.value() / "artifacts" / binding.artifact.sha256;
          const auto raw = read(file);
          require(describe_artifact(file, "application/json").value() == binding.artifact, "persisted output identity differs");
          require(persisted.value().status == AttemptStatus::succeeded &&
                  persisted.value().candidate_outputs == attempt.candidate->outputs, "reopened output differs");
          const auto audio = sample_slice::inspect_pcm16_wav(bytes(original));
          require(audio.has_value(), "successful source is not supported WAV");
          require(sample_slice::validate_slice_points(bytes(raw), ref, audio.value().frame_rate,
                  audio.value().frame_count).has_value(), "emitted output schema invalid");
          run.update({{"output_bytes", raw}, {"output_sha256", binding.artifact.sha256},
                      {"output_byte_length", binding.artifact.byte_length}, {"persisted_status", "succeeded"},
                      {"frame_count", audio.value().frame_count}, {"sample_rate", audio.value().frame_rate}});
        }
        row["runs"].push_back(run);
      }
      if (present) require(read(repo / item.at("path").get<std::string>()) == original, "source bytes changed");
      result["cases"].push_back(row);
    }
    std::cout << canonical_json(result) << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
  }
}
