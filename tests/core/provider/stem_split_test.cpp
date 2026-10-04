#include <algorithm>
#include <array>
#include <cfenv>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>

#include <lmdj/foundation/json.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/providers/local_proof_stem/factory.hpp>
#include <lmdj/providers/local_proof_stem/validation.hpp>
#include <lmdj/providers/local_sample_slice/validation.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj::foundation;
using namespace lmdj::provider;
using namespace lmdj::providers;
using Json = nlohmann::json;
using Bytes = std::vector<std::byte>;

std::string read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary); LMDJ_CHECK(file.good());
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
void write(const std::filesystem::path& path, std::span<const std::byte> bytes) {
  std::ofstream file(path, std::ios::binary);
  file.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
  LMDJ_CHECK(file.good());
}
Bytes wav(std::vector<double> samples = {0, 0, 0, 0}, std::uint32_t rate = 44100,
          std::uint16_t channels = 2) {
  const auto result = stem::encode_pcm16_wav({rate, channels, samples.size() / channels}, samples);
  LMDJ_CHECK(result.has_value()); return result.value();
}
void set(Bytes& bytes, std::size_t offset, std::uint32_t value, unsigned width) {
  for (unsigned i = 0; i < width; ++i) bytes[offset + i] = static_cast<std::byte>((value >> (8 * i)) & 255);
}
Bytes with_metadata(Bytes bytes) {
  const Bytes chunk{std::byte{'J'}, std::byte{'U'}, std::byte{'N'}, std::byte{'K'},
      std::byte{4}, std::byte{0}, std::byte{0}, std::byte{0},
      std::byte{0}, std::byte{0}, std::byte{0}, std::byte{0}};
  bytes.insert(bytes.begin() + 12, chunk.begin(), chunk.end());
  set(bytes, 4, static_cast<std::uint32_t>(bytes.size() - 8), 4); return bytes;
}
using Run = std::function<AttemptResult(ProviderRunContext)>;
class Injected final : public Provider {
 public:
  explicit Injected(Run run) : run_(std::move(run)) {}
  std::string id() const override { return "local.proof.stem"; }
  std::vector<std::string> capabilities() const override { return {"stem.split.v1"}; }
  AttemptResult run(ProviderRunContext context) override { return run_(std::move(context)); }
 private:
  Run run_;
};
ProviderRegistration inject(Run run) {
  auto registration = local_proof_stem_registration();
  registration.implementation = std::make_shared<Injected>(std::move(run));
  return registration;
}

class Fixture {
 public:
  Fixture() : root(std::filesystem::temp_directory_path() /
      ("lmdj-stem-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))),
      store(reopen()) {
    std::filesystem::create_directories(root);
    const std::array sentinel{std::byte{'a'}}; write(root / "project-sentinel", sentinel);
  }
  ~Fixture() { std::error_code error; std::filesystem::remove_all(root, error); }
  AttemptStore reopen() const {
    return {root, {{"local"}, {"public", "private"}, {"stem.split.execute"}},
            [] { return std::string("2026-10-03T00:00:00.000Z"); }};
  }
  void install(ProviderRegistration registration = local_proof_stem_registration()) {
    LMDJ_CHECK(registry.add(std::move(registration)).has_value());
    LMDJ_CHECK(store.set_provider_selection("stem.split.v1", "local.proof.stem", registry).has_value());
  }
  ArtifactRef supply(Bytes bytes) {
    write(root / "source.wav", bytes);
    const auto ref = describe_artifact(root / "source.wav", "audio/wav"); LMDJ_CHECK(ref.has_value());
    owners[ref.value().sha256] = std::make_shared<const Bytes>(std::move(bytes)); return ref.value();
  }
  CapabilityRequest request(ArtifactRef ref, Json parameters = Json::object()) const {
    return {"stem.split.v1", {{"source_audio", std::move(ref)}}, std::move(parameters),
            "private", "test", "local", {"stem.split.execute"}};
  }
  AttemptResult execute(const CapabilityRequest& request, std::uint64_t output_limit = 67108864,
                        std::uint64_t staging_limit = 83886080,
                        std::uint64_t input_limit = stem::maximum_wav_bytes) {
    auto budget = std::make_shared<StagingBudget>(staging_limit);
    const ExecutionOptions options{
        [&](const ArtifactRef& ref) -> Result<std::shared_ptr<const Bytes>> {
          const auto found = owners.find(ref.sha256); LMDJ_CHECK(found != owners.end());
          return Result<std::shared_ptr<const Bytes>>::success(found->second);
        }, input_limit, output_limit, budget};
    const auto result = store.execute(AttemptId{"stem-" + std::to_string(++sequence)}, request, registry, options);
    LMDJ_CHECK(result.has_value()); LMDJ_CHECK(budget->used_bytes() == 0);
    LMDJ_CHECK(read(root / "project-sentinel") == "a"); return result.value();
  }
  TerminalAttempt success(const AttemptResult& result, const Bytes& expected) const {
    LMDJ_CHECK(result.candidate.has_value() && !result.error.has_value());
    const auto reopened = reopen().inspect(result.attempt_id); LMDJ_CHECK(reopened.has_value());
    const auto& record = reopened.value(); LMDJ_CHECK(record.status == AttemptStatus::succeeded);
    auto returned_outputs = result.candidate->outputs;
    std::sort(returned_outputs.begin(), returned_outputs.end(),
        [](const auto& a, const auto& b) { return a.port < b.port; });
    LMDJ_CHECK(record.candidate_outputs == returned_outputs);
    LMDJ_CHECK(record.provider.id == "local.proof.stem" && record.provider.version == "1.0.0");
    LMDJ_CHECK(record.provider.artifact_sha256 == local_proof_stem_registration().artifact_sha256);
    LMDJ_CHECK(!record.provider.model_identity.has_value());
    LMDJ_CHECK(record.capability.id == "stem.split.v1" && record.capability.version == "1.0.0");
    LMDJ_CHECK(record.candidate_outputs.size() == 4 && record.minted_outputs.size() == 4);
    for (auto role : stem::roles) {
      const auto it = std::find_if(record.candidate_outputs.begin(), record.candidate_outputs.end(),
          [&](const auto& output) { return output.port == role; });
      LMDJ_CHECK(it != record.candidate_outputs.end());
      LMDJ_CHECK(it->artifact == record.candidate_outputs[0].artifact);
      const auto& ref = it->artifact;
      LMDJ_CHECK(ref.media_type == "audio/wav" && ref.byte_length == expected.size());
      const auto actual = reopen().read_candidate_artifact(result.attempt_id, ref, expected.size());
      LMDJ_CHECK(actual.has_value() && actual.value() == expected);
      LMDJ_CHECK(describe_artifact(root / ".lmdj-workspace/attempts" / result.attempt_id.value() /
          "artifacts" / ref.sha256, "audio/wav").value() == ref);
    }
    const auto directory = root / ".lmdj-workspace/attempts" / result.attempt_id.value() / "artifacts";
    LMDJ_CHECK(std::distance(std::filesystem::directory_iterator(directory),
                           std::filesystem::directory_iterator{}) == 1);
    return record;
  }
  TerminalAttempt failure(const AttemptResult& result) const {
    LMDJ_CHECK(!result.candidate.has_value() && result.error.has_value());
    const auto record = reopen().inspect(result.attempt_id); LMDJ_CHECK(record.has_value());
    LMDJ_CHECK(record.value().status == AttemptStatus::failed);
    LMDJ_CHECK(record.value().error->code == result.error->code);
    LMDJ_CHECK(record.value().error->details == result.error->details);
    LMDJ_CHECK(record.value().candidate_outputs.empty() && record.value().minted_outputs.empty());
    const auto attempt = root / ".lmdj-workspace/attempts" / result.attempt_id.value();
    LMDJ_CHECK(!std::filesystem::exists(attempt / "staging"));
    LMDJ_CHECK(!std::filesystem::exists(attempt / "artifacts")); return record.value();
  }
  std::filesystem::path root;
  AttemptStore store;
  Registry registry;
  std::map<std::string, std::shared_ptr<const Bytes>> owners;
  unsigned sequence = 0;
};

void descriptor_and_parameters() {
  auto registration = local_proof_stem_registration();
  LMDJ_CHECK(capability_contract_json(registration.capabilities[0]) ==
             Json::parse(read("contracts/capability/stem.split.v1.json")));
  LMDJ_CHECK(registration.capabilities[0].determinism == Determinism::nondeterministic);
  LMDJ_CHECK(registration.capabilities[0].platforms == std::vector<std::string>{"test"});
  LMDJ_CHECK(registration.model_identity == std::nullopt);
  LMDJ_CHECK(describe_artifact(LMDJ_STEM_SOURCE_PACKAGE_MANIFEST, "application/json").value().sha256 ==
             registration.artifact_sha256);
  const auto vectors = Json::parse(read("tests/fixtures/contracts/stem/parameters.json"));
  for (const auto& value : vectors["valid"]) LMDJ_CHECK(stem::validate_parameters(value).has_value());
  for (const auto& value : vectors["invalid"]) LMDJ_CHECK(!stem::validate_parameters(value).has_value());
  Registry registry; LMDJ_CHECK(registry.add(std::move(registration)).has_value());
  Fixture f; const auto request = f.request(f.supply(wav()));
  AttemptStore denied{f.root, {{"local"}, {"private"}, {"proof.execute"}}, [] { return "now"; }};
  LMDJ_CHECK(denied.set_provider_selection("stem.split.v1", "local.proof.stem", registry).has_value());
  LMDJ_CHECK(!denied.validate_execution_policy(request, registry).has_value());
}

void quantization() {
  const int saved = std::fegetround();
  const std::array pairs{std::pair{-32768.0, -32768}, std::pair{32767.0, 32767},
      std::pair{0.5, 0}, std::pair{1.5, 2}, std::pair{2.5, 2},
      std::pair{-0.5, 0}, std::pair{-1.5, -2}, std::pair{-2.5, -2}, std::pair{-32768.5, -32768}};
  for (int mode : {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO}) {
    LMDJ_CHECK(std::fesetround(mode) == 0);
    for (auto [sample, expected] : pairs) {
      const auto encoded = stem::quantize_pcm16(sample / 32768.0);
      LMDJ_CHECK(encoded.has_value() && encoded.value() == expected);
    }
  }
  LMDJ_CHECK(std::fesetround(saved) == 0);
  for (double value : {std::numeric_limits<double>::quiet_NaN(),
      std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()}) {
    const auto result = stem::quantize_pcm16(value);
    LMDJ_CHECK(!result.has_value() && result.error().details.at("reason") == "stem_output_nonfinite");
  }
  for (double value : {1.0, -2.0, 32767.5 / 32768.0, -32768.75 / 32768.0,
                       std::numeric_limits<double>::max()}) {
    const auto result = stem::quantize_pcm16(value);
    LMDJ_CHECK(!result.has_value() && result.error().details.at("reason") == "stem_output_out_of_range");
  }
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 2, 1}, std::array{0.0}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 2, std::numeric_limits<std::uint64_t>::max()}, {}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({32000, 1, 1}, std::array{0.0}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 3, 1}, std::array{0.0, 0.0, 0.0}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 1, 0}, {}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 1, 1}, std::array{1.0}).has_value());
  LMDJ_CHECK(!stem::encode_pcm16_wav({44100, 1, 1},
      std::array{std::numeric_limits<double>::quiet_NaN()}).has_value());
  const auto encoded = wav({-1, 32767.0 / 32768, 1.5 / 32768, -2.5 / 32768}, 48000, 1);
  LMDJ_CHECK((Bytes(encoded.begin() + 44, encoded.end()) == Bytes{
      std::byte{0}, std::byte{128}, std::byte{255}, std::byte{127},
      std::byte{2}, std::byte{0}, std::byte{254}, std::byte{255}}));
}

void replay(bool silence, bool reverse) {
  Fixture f; auto registration = local_proof_stem_registration();
  std::array<unsigned, 4> calls{};
  for (std::size_t i = 0; i < 4; ++i) {
    const auto validate = registration.output_validation[i].validate;
    registration.output_validation[i].validate = [&, i, validate](const auto& request, auto inputs,
        const auto& output, auto bytes, auto scratch) {
      ++calls[i]; return validate(request, inputs, output, bytes, scratch);
    };
  }
  if (reverse) {
    const auto implementation = registration.implementation;
    registration.implementation = std::make_shared<Injected>([implementation](auto context) {
      auto result = implementation->run(std::move(context));
      LMDJ_CHECK(result.candidate.has_value());
      std::reverse(result.candidate->outputs.begin(), result.candidate->outputs.end()); return result;
    });
  }
  f.install(std::move(registration));
  const auto original = silence ? wav() : wav({-1, 0.5, 32767.0 / 32768, -0.25}, 48000, 1);
  const auto ref = f.supply(original); const auto request = f.request(ref);
  const auto result = f.execute(request, original.size() * 4, original.size() * 5);
  const auto record = f.success(result, original);
  LMDJ_CHECK((calls == std::array<unsigned, 4>{1, 1, 1, 1}));
  LMDJ_CHECK(record.request.inputs == request.inputs);
  const std::string empty = canonical_json(Json::object());
  write(f.root / "parameters", std::as_bytes(std::span{empty.data(), empty.size()}));
  LMDJ_CHECK(record.request.parameters_sha256 == describe_artifact(f.root / "parameters", "application/json").value().sha256);
  LMDJ_CHECK(read(f.root / "source.wav") == std::string(reinterpret_cast<const char*>(original.data()), original.size()));
  auto forged = record.candidate_outputs[0].artifact; ++forged.byte_length;
  LMDJ_CHECK(!f.reopen().read_candidate_artifact(result.attempt_id, forged, original.size() + 1).has_value());
  // Logical roles and retained SDK buffers remain charged, even for one blob.
  f.failure(f.execute(request, original.size() * 4 - 1));
  f.failure(f.execute(request, original.size() * 4, original.size() * 5 - 1));
  f.success(result, original);
}

void provider_domain_failures() {
  Fixture f; f.install(); const auto ref = f.supply(wav());
  const auto result = f.execute(f.request(ref, {{"gain", 1}})); f.failure(result);
  LMDJ_CHECK(result.error->code == ErrorCode::invalid_argument);
  LMDJ_CHECK(result.error->details.at("reason") == "stem_parameters_invalid");
  auto corrupt = wav(); corrupt.pop_back();
  const auto bad = f.execute(f.request(f.supply(corrupt))); f.failure(bad);
  LMDJ_CHECK(bad.error->code == ErrorCode::unsupported_audio);
  LMDJ_CHECK(bad.error->details.at("reason") == "source_audio_unsupported");
}

void conversion_failure(double sample, const std::string& reason) {
  Fixture f;
  f.install(inject([sample](auto context) {
    const auto encoded = stem::encode_pcm16_wav({44100, 2, 2}, std::array{0.0, 0.0, 0.0, sample});
    LMDJ_CHECK(!encoded.has_value());
    return AttemptResult{context.attempt_id, std::nullopt, encoded.error()};
  }));
  const auto result = f.execute(f.request(f.supply(wav()))); f.failure(result);
  LMDJ_CHECK(result.error->code == ErrorCode::provider_failed);
  LMDJ_CHECK(result.error->details.at("reason") == reason);
}

void canonical_replay() {
  Fixture f; f.install(); const auto canonical = wav({0.5, -0.5, 0.25, -0.25});
  const auto source = with_metadata(canonical);
  const auto result = f.execute(f.request(f.supply(source)));
  const auto terminal = f.success(result, canonical);
  LMDJ_CHECK(terminal.request.inputs.front().artifact.sha256 != terminal.candidate_outputs.front().artifact.sha256);
  LMDJ_CHECK(read(f.root / "source.wav") == std::string(reinterpret_cast<const char*>(source.data()), source.size()));
}

void oversized_source() {
  Fixture f; f.install(); auto source = wav({0}, 44100, 1);
  source.resize(stem::maximum_wav_bytes + 2);
  set(source, 4, static_cast<std::uint32_t>(source.size() - 8), 4);
  set(source, 40, static_cast<std::uint32_t>(source.size() - 44), 4);
  LMDJ_CHECK(sample_slice::inspect_pcm16_wav(source).has_value());
  const auto result = f.execute(f.request(f.supply(source)), 67108864, 83886080, source.size());
  f.failure(result);
  LMDJ_CHECK(result.error->code == ErrorCode::unsupported_audio);
  LMDJ_CHECK(result.error->details.at("reason") == "source_audio_unsupported");
}

void substituted_input() {
  Fixture f; unsigned calls = 0;
  const auto implementation = local_proof_stem_registration().implementation;
  f.install(inject([&](auto context) { ++calls; return implementation->run(std::move(context)); }));
  const auto original = wav(); const auto ref = f.supply(original);
  f.owners[ref.sha256] = std::make_shared<const Bytes>(wav({0.5, -0.5, 0.25, -0.25}));
  const auto result = f.execute(f.request(ref)); f.failure(result);
  LMDJ_CHECK(calls == 0 && result.error->code == ErrorCode::io_error);
  LMDJ_CHECK(result.error->details.at("reason") == "input_artifact_mismatch");
  LMDJ_CHECK(read(f.root / "source.wav") == std::string(reinterpret_cast<const char*>(original.data()), original.size()));
}

void invalid_role_set(int mutation) {
  Fixture f;
  const auto implementation = local_proof_stem_registration().implementation;
  f.install(inject([implementation, mutation](auto context) {
    auto result = implementation->run(std::move(context)); LMDJ_CHECK(result.candidate.has_value());
    auto& outputs = result.candidate->outputs;
    if (mutation == 0) outputs.pop_back();
    if (mutation == 1) outputs.push_back(outputs[0]);
    if (mutation == 2) outputs[3].port = "piano";
    if (mutation == 3) ++outputs[3].artifact.byte_length;
    if (mutation == 4) outputs[3].artifact.media_type = "application/json";
    return result;
  }));
  f.failure(f.execute(f.request(f.supply(wav()))));
}

void invalid_audio_on_role(std::size_t role, int mutation) {
  Fixture f;
  f.install(inject([role, mutation](auto context) {
    Bytes valid = wav(), invalid = valid;
    if (mutation == 0) { set(invalid, 24, 48000, 4); set(invalid, 28, 48000 * 4, 4); }
    if (mutation == 1) { set(invalid, 22, 1, 2); set(invalid, 28, 44100 * 2, 4); set(invalid, 32, 2, 2); }
    if (mutation == 2) invalid = wav({0, 0, 0, 0, 0, 0});
    if (mutation == 3) invalid.pop_back();
    if (mutation == 4) invalid = with_metadata(valid);
    std::vector<ArtifactBinding> outputs;
    for (std::size_t i = 0; i < 4; ++i) {
      const auto ref = context.output(std::string(stem::roles[i]), i == role ? invalid : valid, "audio/wav");
      LMDJ_CHECK(ref.has_value()); outputs.push_back({std::string(stem::roles[i]), ref.value()});
    }
    return AttemptResult{context.attempt_id, Candidate{CandidateId{context.attempt_id.value()},
        std::move(outputs), Json::object()}, std::nullopt};
  }));
  const auto result = f.execute(f.request(f.supply(wav()))); f.failure(result);
  LMDJ_CHECK(result.error->details.at("reason") == "output_schema_invalid");
}
}  // namespace

int main() {
  try {
    descriptor_and_parameters(); quantization(); replay(true, false); replay(false, true);
    provider_domain_failures();
    canonical_replay();
    oversized_source(); substituted_input();
    conversion_failure(std::numeric_limits<double>::quiet_NaN(), "stem_output_nonfinite");
    conversion_failure(std::numeric_limits<double>::infinity(), "stem_output_nonfinite");
    conversion_failure(1.0, "stem_output_out_of_range");
    for (int i = 0; i < 5; ++i) invalid_role_set(i);
    for (std::size_t role = 0; role < 4; ++role)
      for (int mutation = 0; mutation < 5; ++mutation) invalid_audio_on_role(role, mutation);
    std::cout << "Stem descriptor, PCM16 conversion, per-role validation and durable SDK Proof: PASS\n";
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
