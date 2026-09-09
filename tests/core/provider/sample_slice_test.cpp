#include <algorithm>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>

#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/providers/local_sample_slice/factory.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj::foundation;
using namespace lmdj::provider;
using namespace lmdj::providers;
using Json = nlohmann::json;

std::string read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  LMDJ_CHECK(file.good());
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
void write(const std::filesystem::path& path, std::string_view bytes) {
  std::ofstream file(path, std::ios::binary);
  file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
  LMDJ_CHECK(file.good());
}
auto bytes(std::string_view value) {
  return std::as_bytes(std::span{value.data(), value.size()});
}
void le(std::string& value, std::uint32_t number, unsigned width) {
  for (unsigned i = 0; i < width; ++i) value.push_back(static_cast<char>((number >> (i * 8)) & 255));
}
void set(std::string& value, std::size_t offset, std::uint32_t number, unsigned width) {
  std::string replacement; le(replacement, number, width); value.replace(offset, width, replacement);
}
std::string fmt(std::uint32_t rate = 48000, std::uint16_t channels = 1) {
  std::string result;
  le(result, 1, 2); le(result, channels, 2); le(result, rate, 4);
  le(result, rate * channels * 2, 4); le(result, channels * 2, 2); le(result, 16, 2);
  return result;
}
std::string pcm(const std::vector<int>& values) {
  std::string result;
  for (int value : values) le(result, static_cast<std::uint16_t>(value), 2);
  return result;
}
std::string riff(const std::vector<std::pair<std::string, std::string>>& chunks) {
  std::string body = "WAVE";
  for (const auto& [name, contents] : chunks) {
    body += name; le(body, static_cast<std::uint32_t>(contents.size()), 4); body += contents;
    if (contents.size() % 2) body.push_back('\0');
  }
  std::string result = "RIFF"; le(result, static_cast<std::uint32_t>(body.size()), 4);
  return result + body;
}
std::string wav(const std::vector<int>& samples, std::uint32_t rate = 48000, std::uint16_t channels = 1) {
  return riff({{"fmt ", fmt(rate, channels)}, {"data", pcm(samples)}});
}

class Fixture {
 public:
  Fixture() : root(std::filesystem::temp_directory_path() /
      ("lmdj-slice-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))),
      store(make_store()) {
    std::filesystem::create_directories(root);
    write(root / "project-sentinel", "unchanged authoring bytes");
  }
  ~Fixture() { std::error_code error; std::filesystem::remove_all(root, error); }
  AttemptStore make_store() const {
    return {root, {{"local"}, {"public", "private"}, {"sample.slice.execute"}},
            [] { return std::string("2026-09-09T00:00:00.000Z"); }};
  }
  void install(ProviderRegistration registration = local_sample_slice_registration()) {
    const auto id = registration.implementation->id();
    LMDJ_CHECK(registry.add(std::move(registration)).has_value());
    LMDJ_CHECK(store.set_provider_selection("sample.slice.v1", id, registry).has_value());
  }
  ArtifactRef supply(const std::string& contents) {
    write(root / "source.wav", contents);
    auto reference = describe_artifact(root / "source.wav", "audio/wav");
    LMDJ_CHECK(reference.has_value());
    owners[reference.value().sha256] = std::make_shared<const std::vector<std::byte>>(
        bytes(contents).begin(), bytes(contents).end());
    return reference.value();
  }
  CapabilityRequest request(ArtifactRef source, Json parameters = Json::object()) {
    return {"sample.slice.v1", {{"source_audio", std::move(source)}},
            std::move(parameters), "private", "test", "local", {"sample.slice.execute"}};
  }
  AttemptResult execute(const CapabilityRequest& input) {
    ExecutionOptions options{
        [&](const ArtifactRef& ref) -> Result<std::shared_ptr<const std::vector<std::byte>>> {
          const auto found = owners.find(ref.sha256);
          if (found == owners.end()) return Result<std::shared_ptr<const std::vector<std::byte>>>::failure(
              {ErrorCode::not_found, "owner has no bytes"});
          return Result<std::shared_ptr<const std::vector<std::byte>>>::success(found->second);
        }, 16777216, 262144, std::make_shared<StagingBudget>(67108864)};
    const auto result = store.execute(AttemptId{"slice-" + std::to_string(++sequence)}, input, registry, options);
    LMDJ_CHECK(result.has_value());
    LMDJ_CHECK(options.staging_budget->used_bytes() == 0);
    LMDJ_CHECK(read(root / "project-sentinel") == "unchanged authoring bytes");
    return result.value();
  }
  std::string output(const AttemptResult& result) {
    LMDJ_CHECK(result.candidate.has_value() && !result.error.has_value());
    LMDJ_CHECK(result.candidate->outputs.size() == 1);
    const auto& binding = result.candidate->outputs[0];
    LMDJ_CHECK(binding.port == "slice_points");
    const auto file = root / ".lmdj-workspace/attempts" / result.attempt_id.value() /
        "artifacts" / binding.artifact.sha256;
    LMDJ_CHECK(describe_artifact(file, "application/json").value() == binding.artifact);
    auto reopened = make_store().inspect(result.attempt_id);
    LMDJ_CHECK(reopened.has_value());
    LMDJ_CHECK(reopened.value().status == AttemptStatus::succeeded);
    LMDJ_CHECK(reopened.value().candidate_outputs == result.candidate->outputs);
    return read(file);
  }
  void failure(const AttemptResult& result, ErrorCode code, std::string_view reason) {
    LMDJ_CHECK(!result.candidate.has_value() && result.error.has_value());
    LMDJ_CHECK(result.error->code == code);
    LMDJ_CHECK(result.error->details.at("reason") == reason);
    auto reopened = make_store().inspect(result.attempt_id);
    LMDJ_CHECK(reopened.has_value() && reopened.value().status == AttemptStatus::failed);
    LMDJ_CHECK(reopened.value().error->code == code);
    LMDJ_CHECK(reopened.value().error->details.at("reason") == reason);
    LMDJ_CHECK(reopened.value().candidate_ids.empty() && reopened.value().minted_outputs.empty());
  }
  std::filesystem::path root;
  AttemptStore store;
  Registry registry;
  std::map<std::string, std::shared_ptr<const std::vector<std::byte>>> owners;
  unsigned sequence = 0;
};

void algorithm(const std::vector<int>& samples, std::uint32_t rate, std::uint16_t channels,
               const Json& parameters, const std::vector<std::uint64_t>& expected) {
  Fixture f; f.install();
  const auto original = wav(samples, rate, channels);
  const auto ref = f.supply(original);
  const auto input = f.request(ref, parameters);
  const auto first = f.execute(input), second = f.execute(input);
  const auto encoded = f.output(first);
  LMDJ_CHECK(encoded == f.output(second));
  LMDJ_CHECK(read(f.root / "source.wav") == original);
  Json points = Json::array();
  for (auto frame : expected) points.push_back({{"frame", frame}});
  LMDJ_CHECK(encoded == canonical_json({{"contract", "lmdj.slice-points.v1"},
      {"source_sha256", ref.sha256}, {"frame_rate", rate}, {"points", points}}));
}

void unseen_algorithm() {
  algorithm({0, 4095, 4096, 9000, 0, 5000, 0, -32768, 0}, 48000, 1,
            {{"refractory_frames", 1}}, {2, 5, 7});
  algorithm({-32768, 0, 32767, 0}, 44100, 1,
            {{"threshold_pcm16", 32767}, {"refractory_frames", 1}}, {0, 2});
  algorithm({0, -32768, 0, 0, 5000, 0, 0, 0}, 44100, 2,
            {{"refractory_frames", 1}}, {0, 2});
  algorithm({0, 5000, 0, 5000, 6000, 0, 7000, 0, 8000, 0}, 48000, 1,
            {{"refractory_frames", 5}}, {1, 6});
  algorithm(std::vector<int>(377, 0), 48000, 1, Json::object(), {});
  // A refractory-suppressed rising edge must not become a delayed onset while
  // the envelope remains above threshold (overlapping tails).
  algorithm({5000, 0, 5000, 6000, 7000, 0, 5000}, 48000, 1,
            {{"refractory_frames", 4}}, {0, 6});
  Fixture f; f.install();
  const auto ref = f.supply(wav({0, 5000, 0}));
  const auto omitted = f.execute(f.request(ref));
  const auto explicit_defaults = f.execute(f.request(ref, {{"threshold_pcm16", 4096}, {"refractory_frames", 240}}));
  LMDJ_CHECK(f.output(omitted) == f.output(explicit_defaults));
  LMDJ_CHECK(f.store.inspect(omitted.attempt_id).value().request.parameters_sha256 !=
             f.store.inspect(explicit_defaults.attempt_id).value().request.parameters_sha256);
}

void malformed_audio() {
  const auto good = wav({0, 5000, 0});
  std::vector<std::string> cases{good.substr(0, 9), wav({}),
      riff({{"data", pcm({1})}}), riff({{"fmt ", fmt()}}),
      riff({{"fmt ", fmt()}, {"fmt ", fmt()}, {"data", pcm({1})}}),
      riff({{"fmt ", fmt()}, {"data", pcm({1})}, {"data", pcm({2})}}),
      riff({{"fmt ", fmt() + std::string(1, '\0')}, {"data", pcm({1})}}),
      riff({{"fmt ", fmt() + std::string("\1\0", 2)}, {"data", pcm({1})}}),
      riff({{"fmt ", fmt()}, {"data", "x"}})};
  for (const auto [offset, value, width] : std::vector<std::array<std::uint32_t, 3>>{
      {0, 0, 1}, {4, 0xffffffff, 4}, {20, 3, 2}, {20, 65534, 2},
      {22, 3, 2}, {24, 22050, 4}, {28, 1, 4}, {32, 1, 2}, {34, 8, 2}}) {
    auto bad = good; set(bad, offset, value, width); cases.push_back(bad);
  }
  auto truncated = good.substr(0, good.size() - 1);
  set(truncated, 4, static_cast<std::uint32_t>(truncated.size() - 8), 4); cases.push_back(truncated);
  auto missing_pad = riff({{"fmt ", fmt()}, {"data", pcm({1})}, {"JUNK", "x"}});
  missing_pad.pop_back();
  set(missing_pad, 4, static_cast<std::uint32_t>(missing_pad.size() - 8), 4); cases.push_back(missing_pad);
  auto short_header = good + "RI";
  set(short_header, 4, static_cast<std::uint32_t>(short_header.size() - 8), 4); cases.push_back(short_header);
  for (const auto& contents : cases) {
    Fixture f; f.install();
    f.failure(f.execute(f.request(f.supply(contents))), ErrorCode::unsupported_audio, "source_audio_unsupported");
  }
  for (const auto& contents : {
      riff({{"data", pcm({0, 5000})}, {"JUNK", "abc"}, {"fmt ", fmt()}}),
      riff({{"fmt ", fmt() + std::string("\2\0xy", 4)}, {"LIST", "odd"}, {"data", pcm({0, 5000})}})}) {
    Fixture f; f.install();
    const auto ref = f.supply(contents);
    const auto result = Json::parse(f.output(f.execute(f.request(ref))));
    LMDJ_CHECK(result.at("points") == Json::array({{{"frame", 1}}}));
  }
}

void invalid_parameters() {
  const std::vector<Json> cases{Json::array(), {{"unknown", 1}}, {{"path", "/tmp/input"}},
      {{"threshold_pcm16", true}}, {{"threshold_pcm16", 1.0}}, {{"threshold_pcm16", 0}},
      {{"threshold_pcm16", -1}}, {{"threshold_pcm16", 32768}},
      {{"refractory_frames", 0}}, {{"refractory_frames", 48001}}, {{"refractory_frames", "240"}}};
  for (const auto& parameters : cases) {
    Fixture f; f.install();
    f.failure(f.execute(f.request(f.supply(wav({0, 5000})), parameters)),
              ErrorCode::invalid_argument, "slice_parameters_invalid");
  }
  Fixture f; f.install();
  f.failure(f.execute(f.request({"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "audio/wav", 44})), ErrorCode::not_found, "input_artifact_unavailable");
}

void onset_limit() {
  for (std::size_t count : {4096U, 4097U}) {
    Fixture f; f.install();
    std::vector<int> samples(count * 2);
    for (std::size_t i = 0; i < count; ++i) samples[i * 2] = 5000;
    const auto result = f.execute(f.request(f.supply(wav(samples)), {{"refractory_frames", 1}}));
    if (count == 4096) LMDJ_CHECK(Json::parse(f.output(result)).at("points").size() == count);
    else f.failure(result, ErrorCode::provider_failed, "slice_analysis_failed");
  }
}

class BadOutput final : public Provider {
 public:
  std::string id() const override { return "test.bad.slice"; }
  std::vector<std::string> capabilities() const override { return {"sample.slice.v1"}; }
  std::string payload;
  bool omit = false;
  AttemptResult run(ProviderRunContext context) override {
    std::vector<ArtifactBinding> outputs;
    if (!omit) {
      const auto output = context.output("slice_points", bytes(payload), "application/json");
      LMDJ_CHECK(output.has_value()); outputs.push_back({"slice_points", output.value()});
    }
    return {context.attempt_id, Candidate{CandidateId{context.attempt_id.value()}, outputs, Json::object()}, std::nullopt};
  }
};
void independent_validator() {
  for (unsigned mode = 0; mode < 6; ++mode) {
    Fixture f;
    const auto ref = f.supply(wav({0, 5000, 0}));
    auto provider = std::make_shared<BadOutput>();
    Json output{{"contract", "lmdj.slice-points.v1"}, {"source_sha256", ref.sha256},
                {"frame_rate", 48000}, {"points", Json::array({{{"frame", 1}}})}};
    if (mode == 0) output["source_sha256"] = std::string(64, 'b');
    if (mode == 1) output["frame_rate"] = 44100;
    if (mode == 2) output["points"][0]["frame"] = 3;
    if (mode == 3) output["points"].push_back({{"frame", 1}});
    provider->payload = mode == 4 ? "{\"contract\":1,\"contract\":2}" : canonical_json(output);
    provider->omit = mode == 5;
    auto registration = local_sample_slice_registration(); registration.implementation = provider;
    f.install(std::move(registration));
    f.failure(f.execute(f.request(ref)), ErrorCode::provider_failed,
              mode == 5 ? "output_contract_invalid" : "output_schema_invalid");
  }
}

void vectors() {
  std::size_t total = 0;
  for (const auto* file : {"valid.json", "invalid.json"}) {
    const auto vector_file = Json::parse(read(std::filesystem::path("tests/fixtures/contracts/slice-points") / file));
    for (const auto& item : vector_file.at("cases")) {
      const auto& context = item.at("context");
      std::string raw;
      if (item.contains("raw_json")) raw = item.at("raw_json").get<std::string>();
      else if (item.contains("raw_hex")) {
        const auto hex = item.at("raw_hex").get<std::string>();
        for (std::size_t i = 0; i < hex.size(); i += 2)
          raw.push_back(static_cast<char>(std::stoul(hex.substr(i, 2), nullptr, 16)));
      } else raw = canonical_json(item.at("payload"));
      const bool valid = sample_slice::validate_slice_points(bytes(raw),
          {context.at("source_sha256").get<std::string>(), "audio/wav", 1},
          context.at("frame_rate").get<std::uint32_t>(), context.at("frame_count").get<std::uint64_t>()).has_value();
      if (valid != (item.at("expected_layer") == "valid"))
        throw std::runtime_error("Slice validator disagrees with K1: " + item.at("name").get<std::string>());
      ++total;
    }
  }
  LMDJ_CHECK(total == 40);
}

Json corpus() {
  const std::filesystem::path manifest_path = "tests/fixtures/provider-benchmark/sample-slice/manifest.json";
  const auto manifest = Json::parse(read(manifest_path));
  Json predictions{{"format", "slice-frame-predictions"}, {"format_version", 1},
      {"manifest_sha256", describe_artifact(manifest_path, "application/json").value().sha256}, {"cases", Json::array()}};
  for (const auto& item : manifest.at("scenarios")) {
    Fixture f; f.install();
    if (!item.contains("path")) {
      f.failure(f.execute(f.request({std::string(64, 'a'), "audio/wav", 44})),
                ErrorCode::not_found, "input_artifact_unavailable"); continue;
    }
    const auto original = read(item.at("path").get<std::string>());
    const auto ref = f.supply(original);
    LMDJ_CHECK(ref.sha256 == item.at("sha256").get<std::string>() && ref.byte_length == item.at("byte_length").get<std::uint64_t>());
    const auto first = f.execute(f.request(ref));
    if (item.at("class") != "success") {
      f.failure(first, ErrorCode::unsupported_audio, "source_audio_unsupported"); continue;
    }
    const auto encoded = f.output(first);
    LMDJ_CHECK(encoded == f.output(f.execute(f.request(ref))));
    LMDJ_CHECK(read(item.at("path").get<std::string>()) == original);
    Json frames = Json::array();
    const auto decoded = Json::parse(encoded);
    for (const auto& point : decoded.at("points")) frames.push_back(point.at("frame"));
    predictions["cases"].push_back({{"fixture_id", item.at("id")}, {"source_sha256", ref.sha256}, {"frames", frames}});
  }
  return predictions;
}

void identity() {
  const auto manifest = Json::parse(read(LMDJ_SLICE_SOURCE_PACKAGE_MANIFEST));
  LMDJ_CHECK(manifest.at("files").size() == 5);
  for (const auto& file : manifest.at("files"))
    LMDJ_CHECK(describe_artifact(file.at("path").get<std::string>(), "application/octet-stream").value().sha256 == file.at("sha256").get<std::string>());
  const auto registration = local_sample_slice_registration();
  LMDJ_CHECK(registration.version == "1.0.0");
  LMDJ_CHECK(registration.capabilities.size() == 1);
  const auto& capability = registration.capabilities.front();
  auto expected_contract = Json::parse(read("contracts/capability/sample.slice.v1.json"));
  // These Contract arrays are sets; SDK serialization sorts them.
  std::sort(expected_contract["errors"].begin(), expected_contract["errors"].end());
  auto& classifications = expected_contract["policy"]["data_classifications"];
  std::sort(classifications.begin(), classifications.end());
  LMDJ_CHECK(capability_contract_json(capability) == expected_contract);
  LMDJ_CHECK(capability.platforms == std::vector<std::string>{"test"});
  LMDJ_CHECK(capability.max_output_bytes == 262144);
  LMDJ_CHECK(registration.artifact_sha256 ==
      describe_artifact(LMDJ_SLICE_SOURCE_PACKAGE_MANIFEST, "application/json").value().sha256);
  const auto assembly = Json::parse(read("products/lmdj/assembly.json"));
  LMDJ_CHECK(std::count_if(assembly.at("providers").begin(), assembly.at("providers").end(),
      [](const auto& provider) { return provider.at("id") == "local.sample.slice"; }) == 1);
}
}  // namespace
int main(int argc, char** argv) {
  try {
    identity(); unseen_algorithm(); malformed_audio(); invalid_parameters();
    onset_limit(); independent_validator(); vectors();
    const auto predictions = corpus();
    if (argc == 2) write(argv[1], canonical_json(predictions) + "\n");
    std::cout << "sample.slice: real execution, byte replay, K1 vectors and unchanged corpus passed\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
