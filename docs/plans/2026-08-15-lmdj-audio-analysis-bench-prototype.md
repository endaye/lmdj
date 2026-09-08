# Audio Analysis Bench Prototype Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained prototype under `tools/analysis-bench/` that proves the Core Provider mechanism (Registry, Capability v2 port bindings, AttemptStore) can host multiple pluggable audio-analysis tools, and benchmarks/compares them against independent ground truth.

**Architecture:** Three analysis Providers (waveform peaks, loudness, onset detection) are plain static libraries constructed with a Host-injected `ArtifactByteResolver`, because the Capability Contract delivers `ArtifactRef` inputs without bytes and the SDK has no input-bytes resolver yet (recorded as an open architecture issue in `docs/architecture/2026-08-01-provider-multi-port-contract-decision.md`). A bench CLI Host wires them into `provider::Registry` + `provider::AttemptStore` (the production execute path: selection, port validation, staging, attempt evidence), times repeated attempts, checks output determinism, and emits a JSON report. A Python script computes ground truth with numpy/scipy and diffs provider outputs with tolerances.

**Tech Stack:** C++20, existing `lmdj::provider` SDK, nlohmann-json (vendored), CTest via `lmdj_add_test`; Python 3 venv with numpy + scipy for ground truth only.

**Explicitly out of scope (do not implement):**
- No changes to `packages/`, `contracts/`, `products/`, `apps/`, or `providers/` — the prototype lives entirely in `tools/analysis-bench/` plus one `add_subdirectory` line in the root `CMakeLists.txt`.
- No Project Truth interaction, no Candidate adoption, no `Application` facade ops.
- No MP3/compressed decoding, no resampling. Fixtures are PCM16 WAV.
- No module.json / source-package manifests: prototype Providers carry no release identity (that is what keeps Version impact at none).

## Global Constraints

- C++ standard is C++20 (`CMakeLists.txt:4`); every target uses `lmdj_target_warnings(...)` and `lmdj_target_sanitizers(...)`.
- Tests register via `lmdj_add_test(NAME ... TIER unit|component ...)` from `cmake/LmdjTesting.cmake`; `fast` runs unit+component, so all prototype tests must be in those two tiers.
- Providers return only `foundation::ErrorCode::provider_failed`; each Capability descriptor declares `error_codes {"PROVIDER_FAILED"}` exactly.
- Provider `run` must be deterministic: identical input Artifact + parameters must produce byte-identical output Artifacts (the bench Host verifies this).
- Port names match `^[a-z][a-z0-9_]*$` (`provider::valid_port_name`).
- Python third-party packages install only into `tools/analysis-bench/.venv` (never system Python).
- Commit rule (AGENTS.md): one Conventional Commit per Task; verify branch is not `main`; stage only the Task's declared files; `git diff --cached --check` before committing.

## Version Management

Version impact: none

Reason: the prototype adds no Product, Module, Host, Provider, or Contract identity. Nothing under `products/`, `packages/`, `providers/`, `apps/`, or `contracts/` changes; `tools/analysis-bench/` carries no `module.json`, and `products/lmdj/version.json` is untouched.

## Documentation Impact

Documentation impact: none

Reason: the architecture portal derives Product/Module/Host/Provider/Contract identities from active manifests; this prototype adds no manifest anywhere the portal or release tooling scans (`tools/` is not scanned; `tools/release/target_validation.py` globs only `providers/*/module.json`). The prototype is disposable validation tooling, not an active source boundary.

## Success criteria and evidence write-back

This prototype exists to answer specific questions; completing the six Tasks
alone is not success. After Task 6, judge each item explicitly:

1. **Mechanism fit** — `provider::Registry` + Capability v2 port bindings +
   `AttemptStore::execute` host all three analysis Providers through the
   production execute path (selection, port validation, staging, attempt
   evidence on disk) with no SDK modifications.
2. **Attempt/Candidate semantics** — do Attempt/Candidate semantics fit
   analysis tools, whose output is a report rather than adoptable material?
   Record a verdict: fits as-is / needs a lighter-weight result channel /
   unresolved.
3. **Input-bytes resolver gap** — does the prototype confirm the SDK needs a
   first-class input-Artifact byte resolver, and what shape should it take?
   The Host-injected `analysis::ArtifactByteResolver` is the temporary
   bridge; the conclusion must be recorded, not just the workaround.
4. **Accuracy and determinism** — every Provider is byte-identical across
   iterations, and the comparison table passes on all rows under the Task 6
   comparison rules (including the empty-reference onset rule).

Benchmark timings are informational only; this prototype sets no performance
acceptance threshold. If the numbers are later used for tool selection,
define thresholds in that effort, not here.

Write-back: paste the comparison table and the four verdicts into the PR
description (see "Prototype report"), and record the resolver conclusion
(item 3) in `docs/prd/decision-log.md` or the open issue in
`docs/architecture/2026-08-01-provider-multi-port-contract-decision.md`
rather than only in the PR thread. Do not silently settle the
Candidate-adoption Contract question inside this prototype.

---

### Task 1: Shared support library (WAV parser + resolver alias)

**Files:**
- Create: `tools/analysis-bench/shared/include/lmdj/analysis/artifact_bytes.hpp`
- Create: `tools/analysis-bench/shared/include/lmdj/analysis/wav_pcm16.hpp`
- Create: `tools/analysis-bench/shared/src/wav_pcm16.cpp`
- Create: `tools/analysis-bench/CMakeLists.txt`
- Create: `tools/analysis-bench/tests/wav_pcm16_test.cpp`
- Create: `tools/analysis-bench/tests/support.hpp`
- Modify: `CMakeLists.txt` (append one `add_subdirectory` after line 54)

**Interfaces:**
- Consumes: `lmdj::foundation::{Result, Error, ErrorCode}` from `lmdj::foundation` (target `lmdj_foundation`).
- Produces:
  - `lmdj::analysis::ArtifactByteResolver` = `std::function<foundation::Result<std::vector<std::byte>>(const foundation::ArtifactRef&)>`
  - `lmdj::analysis::WavPcm16 { std::uint32_t sample_rate; std::uint16_t channels; std::vector<std::int16_t> interleaved; }` with `std::uint64_t frame_count() const`
  - `foundation::Result<WavPcm16> lmdj::analysis::parse_wav_pcm16(std::span<const std::byte>)`
  - `std::vector<float> lmdj::analysis::mix_to_mono(const WavPcm16&)` (float samples in [-1, 1], channels averaged)
  - CMake target `lmdj_analysis_bench_shared` (static lib, links `lmdj_foundation`)
  - Test helpers in `tests/support.hpp`: `analysis_bench_test::make_resolver(std::map<std::string, std::vector<std::byte>>)`, `analysis_bench_test::CaptureSink`

- [ ] **Step 1: Write the failing test**

`tools/analysis-bench/tests/support.hpp`:

```cpp
#pragma once

#include <cstddef>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <vector>

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/provider.hpp>

namespace analysis_bench_test {

inline std::vector<std::byte> read_bytes(const std::string& path) {
  std::ifstream stream(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream),
          std::istreambuf_iterator<char>()};
}

inline lmdj::analysis::ArtifactByteResolver make_resolver(
    std::map<std::string, std::vector<std::byte>> bytes_by_sha256) {
  return [bytes = std::move(bytes_by_sha256)](
             const lmdj::foundation::ArtifactRef& artifact)
             -> lmdj::foundation::Result<std::vector<std::byte>> {
    const auto found = bytes.find(artifact.sha256);
    if (found == bytes.end()) {
      return lmdj::foundation::Result<std::vector<std::byte>>::failure(
          lmdj::foundation::Error{
              lmdj::foundation::ErrorCode::not_found,
              "resolver has no bytes for artifact",
              {{"sha256", artifact.sha256}},
          });
    }
    return lmdj::foundation::Result<std::vector<std::byte>>::success(
        found->second);
  };
}

struct CaptureSink {
  std::map<std::string, std::vector<std::byte>> written;

  lmdj::provider::ArtifactSink sink() {
    return [this](std::string port,
                  std::span<const std::byte> bytes,
                  std::string media_type)
               -> lmdj::foundation::Result<lmdj::foundation::ArtifactRef> {
      written[port] = {bytes.begin(), bytes.end()};
      return lmdj::foundation::Result<
          lmdj::foundation::ArtifactRef>::success(lmdj::foundation::
                                                      ArtifactRef{
                                                          "placeholder",
                                                          std::move(media_type),
                                                          bytes.size(),
                                                      });
    };
  }
};

}  // namespace analysis_bench_test
```

`tools/analysis-bench/tests/wav_pcm16_test.cpp`:

```cpp
#include <cassert>
#include <cstdint>
#include <iostream>
#include <span>

#include <lmdj/analysis/wav_pcm16.hpp>

#include "support.hpp"

int main() {
  const auto kick = analysis_bench_test::read_bytes(
      "tests/fixtures/audio/kick.wav");
  assert(!kick.empty());
  const auto parsed =
      lmdj::analysis::parse_wav_pcm16(std::span<const std::byte>(kick));
  assert(parsed.has_value());
  assert(parsed.value().sample_rate == 48000);
  assert(parsed.value().channels == 1);
  assert(parsed.value().frame_count() > 0);
  assert(parsed.value().frame_count() == parsed.value().interleaved.size());

  const auto stereo = analysis_bench_test::read_bytes(
      "tests/fixtures/audio/stereo.wav");
  const auto parsed_stereo =
      lmdj::analysis::parse_wav_pcm16(std::span<const std::byte>(stereo));
  assert(parsed_stereo.has_value());
  assert(parsed_stereo.value().channels == 2);
  assert(
      parsed_stereo.value().frame_count() * 2 ==
      parsed_stereo.value().interleaved.size());
  const auto mono = lmdj::analysis::mix_to_mono(parsed_stereo.value());
  assert(mono.size() == parsed_stereo.value().frame_count());
  for (const float sample : mono) {
    assert(sample >= -1.0F && sample <= 1.0F);
  }

  const std::byte garbage[16] = {};
  const auto rejected = lmdj::analysis::parse_wav_pcm16(
      std::span<const std::byte>(garbage, sizeof(garbage)));
  assert(!rejected.has_value());
  assert(
      rejected.error().code == lmdj::foundation::ErrorCode::invalid_argument);

  std::cout << "wav_pcm16_test passed\n";
  return 0;
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench.wav
```

Expected: FAIL — target does not exist yet (`No tests were found` or build error for missing headers).

- [ ] **Step 3: Write the implementation**

`tools/analysis-bench/shared/include/lmdj/analysis/artifact_bytes.hpp`:

```cpp
#pragma once

#include <cstddef>
#include <functional>
#include <vector>

#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::analysis {

// Prototype-only bridge: the Capability Contract delivers ArtifactRef inputs
// without bytes and the SDK has no input-bytes resolver yet (open issue in
// docs/architecture/2026-08-01-provider-multi-port-contract-decision.md), so
// the bench Host injects byte access at composition time.
using ArtifactByteResolver =
    std::function<foundation::Result<std::vector<std::byte>>(
        const foundation::ArtifactRef&)>;

}  // namespace lmdj::analysis
```

`tools/analysis-bench/shared/include/lmdj/analysis/wav_pcm16.hpp`:

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

#include <lmdj/foundation/error.hpp>

namespace lmdj::analysis {

struct WavPcm16 {
  std::uint32_t sample_rate = 0;
  std::uint16_t channels = 0;
  std::vector<std::int16_t> interleaved;

  std::uint64_t frame_count() const {
    return channels == 0 ? 0
                         : interleaved.size() /
                               static_cast<std::size_t>(channels);
  }
};

// Strict RIFF/WAVE PCM16 parser. Any sample rate, mono or stereo.
foundation::Result<WavPcm16> parse_wav_pcm16(
    std::span<const std::byte> bytes);

// Mono mixdown to float samples in [-1, 1].
std::vector<float> mix_to_mono(const WavPcm16& wav);

}  // namespace lmdj::analysis
```

`tools/analysis-bench/shared/src/wav_pcm16.cpp`:

```cpp
#include <lmdj/analysis/wav_pcm16.hpp>

#include <cstring>
#include <utility>

namespace lmdj::analysis {
namespace {

foundation::Error invalid_wav(const char* message) {
  return foundation::Error{
      foundation::ErrorCode::invalid_argument,
      message,
      {{"media_type", "audio/wav"}},
  };
}

std::uint16_t read_u16le(const std::byte* p) {
  return static_cast<std::uint16_t>(
      static_cast<std::uint16_t>(p[0]) |
      static_cast<std::uint16_t>(static_cast<std::uint16_t>(p[1]) << 8U));
}

std::uint32_t read_u32le(const std::byte* p) {
  return static_cast<std::uint32_t>(p[0]) |
         (static_cast<std::uint32_t>(p[1]) << 8U) |
         (static_cast<std::uint32_t>(p[2]) << 16U) |
         (static_cast<std::uint32_t>(p[3]) << 24U);
}

bool tag_equals(const std::byte* p, const char (&tag)[5]) {
  return std::memcmp(p, tag, 4) == 0;
}

}  // namespace

foundation::Result<WavPcm16> parse_wav_pcm16(
    std::span<const std::byte> bytes) {
  using ParseResult = foundation::Result<WavPcm16>;
  if (bytes.size() < 12 || !tag_equals(bytes.data(), "RIFF") ||
      !tag_equals(bytes.data() + 8, "WAVE")) {
    return ParseResult::failure(invalid_wav("input is not RIFF/WAVE"));
  }
  bool have_fmt = false;
  bool have_data = false;
  std::uint16_t audio_format = 0;
  std::uint16_t channels = 0;
  std::uint32_t sample_rate = 0;
  std::uint16_t bits_per_sample = 0;
  const std::byte* data = nullptr;
  std::uint32_t data_size = 0;
  std::size_t offset = 12;
  while (offset + 8 <= bytes.size()) {
    const std::byte* chunk = bytes.data() + offset;
    const std::uint32_t chunk_size = read_u32le(chunk + 4);
    if (chunk_size > bytes.size() - offset - 8) {
      return ParseResult::failure(invalid_wav("WAVE chunk is truncated"));
    }
    const std::byte* body = chunk + 8;
    if (tag_equals(chunk, "fmt ")) {
      if (chunk_size < 16) {
        return ParseResult::failure(
            invalid_wav("WAVE fmt chunk is too small"));
      }
      audio_format = read_u16le(body);
      channels = read_u16le(body + 2);
      sample_rate = read_u32le(body + 4);
      bits_per_sample = read_u16le(body + 14);
      have_fmt = true;
    } else if (tag_equals(chunk, "data")) {
      data = body;
      data_size = chunk_size;
      have_data = true;
    }
    offset += 8 + chunk_size + (chunk_size & 1U);
  }
  if (!have_fmt || !have_data) {
    return ParseResult::failure(
        invalid_wav("WAVE fmt or data chunk is missing"));
  }
  if (audio_format != 1 || bits_per_sample != 16 ||
      (channels != 1 && channels != 2)) {
    return ParseResult::failure(
        invalid_wav("WAVE must be PCM16 mono or stereo"));
  }
  if (data_size % 2 != 0) {
    return ParseResult::failure(invalid_wav("WAVE data is misaligned"));
  }
  WavPcm16 wav;
  wav.sample_rate = sample_rate;
  wav.channels = channels;
  wav.interleaved.resize(data_size / 2);
  for (std::size_t index = 0; index < wav.interleaved.size(); ++index) {
    wav.interleaved[index] =
        static_cast<std::int16_t>(read_u16le(data + index * 2));
  }
  return ParseResult::success(std::move(wav));
}

std::vector<float> mix_to_mono(const WavPcm16& wav) {
  std::vector<float> mono;
  const auto frames = wav.frame_count();
  mono.reserve(frames);
  for (std::uint64_t frame = 0; frame < frames; ++frame) {
    float sum = 0.0F;
    for (std::uint16_t channel = 0; channel < wav.channels; ++channel) {
      sum += static_cast<float>(
                 wav.interleaved[static_cast<std::size_t>(frame) *
                                     wav.channels +
                                 channel]) /
             32768.0F;
    }
    mono.push_back(sum / static_cast<float>(wav.channels));
  }
  return mono;
}

}  // namespace lmdj::analysis
```

`tools/analysis-bench/CMakeLists.txt`:

```cmake
add_library(
  lmdj_analysis_bench_shared
  STATIC
    shared/src/wav_pcm16.cpp
)
target_include_directories(
  lmdj_analysis_bench_shared
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/shared/include"
)
target_link_libraries(
  lmdj_analysis_bench_shared
  PUBLIC
    lmdj_foundation
)
lmdj_target_warnings(lmdj_analysis_bench_shared)
lmdj_target_sanitizers(lmdj_analysis_bench_shared)

if(BUILD_TESTING)
  add_executable(
    lmdj_analysis_bench_wav_tests
    tests/wav_pcm16_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_wav_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_wav_tests
    PRIVATE
      lmdj_analysis_bench_shared
      lmdj_provider_sdk
  )
  lmdj_target_warnings(lmdj_analysis_bench_wav_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_wav_tests)
  lmdj_add_test(
    NAME analysis_bench.wav
    TIER unit
    COMMAND lmdj_analysis_bench_wav_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
endif()
```

Modify root `CMakeLists.txt`: after the line `add_subdirectory(products/lmdj)` add:

```cmake
add_subdirectory(tools/analysis-bench)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench.wav --output-on-failure
```

Expected: `1/1 Test ... analysis_bench.wav ... Passed`

- [ ] **Step 5: Commit**

```bash
git add tools/analysis-bench CMakeLists.txt
git diff --cached --check
git commit -m "feat(tools): add analysis-bench shared WAV PCM16 support"
```

---

### Task 2: Waveform peaks Provider

**Files:**
- Create: `tools/analysis-bench/providers/peaks/include/lmdj/analysis_bench/peaks/factory.hpp`
- Create: `tools/analysis-bench/providers/peaks/src/provider.cpp`
- Create: `tools/analysis-bench/tests/peaks_test.cpp`
- Modify: `tools/analysis-bench/CMakeLists.txt` (append peaks lib + test)

**Interfaces:**
- Consumes: Task 1 `lmdj::analysis::{ArtifactByteResolver, parse_wav_pcm16, mix_to_mono, WavPcm16}`; `lmdj::provider::{Provider, ProviderRegistration, CapabilityDescriptor, ArtifactSink}` from `lmdj_provider_sdk`; test helpers from `tests/support.hpp`.
- Produces:
  - `lmdj::analysis_bench::peaks_registration(analysis::ArtifactByteResolver) -> provider::ProviderRegistration`; Provider id `local.analysis-bench.peaks`, version `0.1.0`
  - Capability `analysis.waveform-peaks.v1` (contract version `2.0.0`): input port `sample` (`audio/wav`, required, max 1), output port `peaks` (`application/json`, required, max 1)
  - Output JSON: `{"contract":"lmdj.analysis-bench.peaks.v1","sample_rate":u32,"channels":u16,"frame_count":u64,"samples_per_bucket":u32,"bucket_count":u64,"min":[i16...],"max":[i16...]}` — min/max over the mono mixdown per bucket, scaled by `lrint(value * 32767)` clamped to int16
  - Parameter: `samples_per_bucket` (integer, default 256, valid range 2..65536)
  - CMake target `lmdj_analysis_bench_peaks`

- [ ] **Step 1: Write the failing test**

`tools/analysis-bench/tests/peaks_test.cpp`:

```cpp
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis_bench/peaks/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

namespace {

std::vector<std::byte> make_wav_bytes(
    const std::vector<std::int16_t>& samples,
    std::uint32_t sample_rate = 48000) {
  const std::uint32_t data_size =
      static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> bytes(44 + data_size);
  auto* p = reinterpret_cast<char*>(bytes.data());
  std::memcpy(p, "RIFF", 4);
  const std::uint32_t riff_size = 36 + data_size;
  std::memcpy(p + 4, &riff_size, 4);
  std::memcpy(p + 8, "WAVEfmt ", 8);
  const std::uint32_t fmt_size = 16;
  std::memcpy(p + 16, &fmt_size, 4);
  const std::uint16_t format = 1;
  const std::uint16_t channels = 1;
  const std::uint32_t byte_rate = sample_rate * 2;
  const std::uint16_t block_align = 2;
  const std::uint16_t bits = 16;
  std::memcpy(p + 20, &format, 2);
  std::memcpy(p + 22, &channels, 2);
  std::memcpy(p + 24, &sample_rate, 4);
  std::memcpy(p + 28, &byte_rate, 4);
  std::memcpy(p + 32, &block_align, 2);
  std::memcpy(p + 34, &bits, 2);
  std::memcpy(p + 36, "data", 4);
  std::memcpy(p + 40, &data_size, 4);
  std::memcpy(p + 44, samples.data(), data_size);
  return bytes;
}

}  // namespace

int main() {
  // 4 samples, bucket size 2 -> 2 buckets.
  const auto wav = make_wav_bytes({16384, -8192, -32768, 0});
  auto registration = lmdj::analysis_bench::peaks_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  assert(registration.implementation->id() ==
         "local.analysis-bench.peaks");
  assert(registration.capabilities.size() == 1);
  assert(
      registration.capabilities.front().id == "analysis.waveform-peaks.v1");

  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.waveform-peaks.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = {{"samples_per_bucket", 2}};

  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  assert(result.candidate.has_value());
  const auto& written = capture.written.at("peaks");
  const auto output = nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
  assert(output.at("contract") == "lmdj.analysis-bench.peaks.v1");
  assert(output.at("sample_rate") == 48000);
  assert(output.at("frame_count") == 4);
  assert(output.at("samples_per_bucket") == 2);
  assert(output.at("bucket_count") == 2);
  // bucket 0: max(16384, -8192): 16384/32768=0.5 -> lrint(0.5*32767)
  //         = lrint(16383.5) = 16384 (round-half-to-even);
  //         min = -8192 -> lrint(-8191.75) = -8192
  // bucket 1: min(-32768, 0) = -32768 -> -32767, max = 0
  assert(output.at("max") == std::vector<int>({16384, 0}));
  assert(output.at("min") == std::vector<int>({-8192, -32767}));

  // Bad input: unresolvable artifact -> provider_failed.
  lmdj::provider::CapabilityRequest bad = request;
  bad.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"missing", "audio/wav", 4},
  }};
  const auto failed = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt-2"}, bad, capture.sink());
  assert(failed.error.has_value());
  assert(
      failed.error->code == lmdj::foundation::ErrorCode::provider_failed);

  std::cout << "peaks_test passed\n";
  return 0;
}
```

Note the scaling rule: `lrint(value * 32767.0F)` where value is `sample / 32768.0F` — so 16384 maps to `lrint(16383.5) = 16384` (round-half-to-even), -8192 maps to `lrint(-8191.75) = -8192`, and -32768 maps to -32767. The Python ground truth uses the identical formula (`np.rint` is also round-half-to-even).

- [ ] **Step 2: Run test to verify it fails**

```bash
scripts/core.sh build dev
```

Expected: FAIL — `lmdj/analysis_bench/peaks/factory.hpp` not found.

- [ ] **Step 3: Write the implementation**

`tools/analysis-bench/providers/peaks/include/lmdj/analysis_bench/peaks/factory.hpp`:

```cpp
#pragma once

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::analysis_bench {

provider::ProviderRegistration peaks_registration(
    analysis::ArtifactByteResolver resolver);

}  // namespace lmdj::analysis_bench
```

`tools/analysis-bench/providers/peaks/src/provider.cpp`:

```cpp
#include <lmdj/analysis_bench/peaks/factory.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/wav_pcm16.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::analysis_bench {
namespace {

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

std::int16_t scale_peak(float value) {
  const auto scaled = std::lrint(value * 32767.0F);
  return static_cast<std::int16_t>(
      std::clamp<long>(scaled, -32767, 32767));
}

class PeaksProvider final : public provider::Provider {
 public:
  explicit PeaksProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override { return "local.analysis-bench.peaks"; }

  std::vector<std::string> capabilities() const override {
    return {"analysis.waveform-peaks.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
    std::uint32_t samples_per_bucket = 256;
    if (request.parameters.contains("samples_per_bucket")) {
      // nlohmann stores C++ integer literals as signed number_integer and
      // text-parsed non-negative integers as number_unsigned; accept any
      // integer representation and validate the value range instead.
      const auto& encoded = request.parameters.at("samples_per_bucket");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 2 ||
          encoded.get<std::int64_t>() > 65536) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("samples_per_bucket must be 2..65536")};
      }
      samples_per_bucket = encoded.get<std::uint32_t>();
    }
    const auto binding = std::find_if(
        request.inputs.begin(),
        request.inputs.end(),
        [](const provider::ArtifactBinding& input) {
          return input.port == "sample";
        });
    if (binding == request.inputs.end()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("missing sample input binding")};
    }
    const auto bytes = resolver_(binding->artifact);
    if (!bytes.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(bytes.error().message)};
    }
    const auto wav = analysis::parse_wav_pcm16(bytes.value());
    if (!wav.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(wav.error().message)};
    }
    const auto mono = analysis::mix_to_mono(wav.value());

    const std::size_t bucket_count =
        mono.empty()
            ? 0
            : (mono.size() + samples_per_bucket - 1) / samples_per_bucket;
    std::vector<std::int16_t> minima;
    std::vector<std::int16_t> maxima;
    minima.reserve(bucket_count);
    maxima.reserve(bucket_count);
    for (std::size_t bucket = 0; bucket < bucket_count; ++bucket) {
      const std::size_t begin = bucket * samples_per_bucket;
      const std::size_t end =
          std::min(begin + samples_per_bucket, mono.size());
      const auto [low, high] =
          std::minmax_element(mono.begin() + static_cast<std::ptrdiff_t>(begin),
                              mono.begin() + static_cast<std::ptrdiff_t>(end));
      minima.push_back(scale_peak(*low));
      maxima.push_back(scale_peak(*high));
    }

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.peaks.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"channels", wav.value().channels},
        {"frame_count", wav.value().frame_count()},
        {"samples_per_bucket", samples_per_bucket},
        {"bucket_count", bucket_count},
        {"min", std::move(minima)},
        {"max", std::move(maxima)},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "peaks",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("peaks artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"peaks", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor peaks_capability() {
  return provider::CapabilityDescriptor{
      "analysis.waveform-peaks.v1",
      "2.0.0",
      {{
          "sample",
          {"audio/wav"},
          "lmdj.artifact.audio-pcm.v1",
          "1.0.0",
          true,
          1,
      }},
      {{
          "peaks",
          {"application/json"},
          "lmdj.artifact.analysis-bench-peaks.v1",
          "1.0.0",
          true,
          1,
      }},
      provider::Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      provider::ResourceRequirements{
          provider::ResourceClass::cpu,
          64,
      },
      provider::ExecutionPolicy{5000, 1},
      provider::CapabilityPolicy{
          {"public"},
          {"local"},
          {"analysis-bench.execute"},
      },
      {"test"},
      4194304,
  };
}

}  // namespace

provider::ProviderRegistration peaks_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<PeaksProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {peaks_capability()},
  };
}

}  // namespace lmdj::analysis_bench
```

Append to `tools/analysis-bench/CMakeLists.txt` (before the `if(BUILD_TESTING)` block):

```cmake
add_library(
  lmdj_analysis_bench_peaks
  STATIC
    providers/peaks/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_peaks
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/peaks/include"
)
target_link_libraries(
  lmdj_analysis_bench_peaks
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_peaks)
lmdj_target_sanitizers(lmdj_analysis_bench_peaks)
```

Append inside `if(BUILD_TESTING)`:

```cmake
  add_executable(
    lmdj_analysis_bench_peaks_tests
    tests/peaks_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_peaks_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_peaks_tests
    PRIVATE
      lmdj_analysis_bench_peaks
  )
  lmdj_target_warnings(lmdj_analysis_bench_peaks_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_peaks_tests)
  lmdj_add_test(
    NAME analysis_bench.peaks
    TIER unit
    COMMAND lmdj_analysis_bench_peaks_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench --output-on-failure
```

Expected: `analysis_bench.wav` and `analysis_bench.peaks` both Passed.

- [ ] **Step 5: Commit**

```bash
git add tools/analysis-bench
git diff --cached --check
git commit -m "feat(tools): add analysis-bench waveform peaks provider"
```

---

### Task 3: Loudness Provider

**Files:**
- Create: `tools/analysis-bench/providers/loudness/include/lmdj/analysis_bench/loudness/factory.hpp`
- Create: `tools/analysis-bench/providers/loudness/src/provider.cpp`
- Create: `tools/analysis-bench/tests/loudness_test.cpp`
- Modify: `tools/analysis-bench/CMakeLists.txt` (append loudness lib + test)

**Interfaces:**
- Consumes: same as Task 2.
- Produces:
  - `lmdj::analysis_bench::loudness_registration(analysis::ArtifactByteResolver) -> provider::ProviderRegistration`; Provider id `local.analysis-bench.loudness`, version `0.1.0`
  - Capability `analysis.loudness.v1` (contract version `2.0.0`): input port `sample` (`audio/wav`, required, max 1), output port `loudness` (`application/json`, required, max 1)
  - Output JSON: `{"contract":"lmdj.analysis-bench.loudness.v1","sample_rate":u32,"channels":u16,"frame_count":u64,"peak_dbfs":f64,"rms_dbfs":f64,"clipping":bool}` — computed on the mono mixdown; `-300.0` for silence (log10 floor); `clipping` is true when any int16 sample equals 32767 or -32768
  - CMake target `lmdj_analysis_bench_loudness`

- [ ] **Step 1: Write the failing test**

`tools/analysis-bench/tests/loudness_test.cpp`:

```cpp
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis_bench/loudness/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

namespace {

std::vector<std::byte> make_wav_bytes(
    const std::vector<std::int16_t>& samples,
    std::uint32_t sample_rate = 48000) {
  const std::uint32_t data_size =
      static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> bytes(44 + data_size);
  auto* p = reinterpret_cast<char*>(bytes.data());
  std::memcpy(p, "RIFF", 4);
  const std::uint32_t riff_size = 36 + data_size;
  std::memcpy(p + 4, &riff_size, 4);
  std::memcpy(p + 8, "WAVEfmt ", 8);
  const std::uint32_t fmt_size = 16;
  std::memcpy(p + 16, &fmt_size, 4);
  const std::uint16_t format = 1;
  const std::uint16_t channels = 1;
  const std::uint32_t byte_rate = sample_rate * 2;
  const std::uint16_t block_align = 2;
  const std::uint16_t bits = 16;
  std::memcpy(p + 20, &format, 2);
  std::memcpy(p + 22, &channels, 2);
  std::memcpy(p + 24, &sample_rate, 4);
  std::memcpy(p + 28, &byte_rate, 4);
  std::memcpy(p + 32, &block_align, 2);
  std::memcpy(p + 34, &bits, 2);
  std::memcpy(p + 36, "data", 4);
  std::memcpy(p + 40, &data_size, 4);
  std::memcpy(p + 44, samples.data(), data_size);
  return bytes;
}

nlohmann::json run_loudness(const std::vector<std::int16_t>& samples) {
  const auto wav = make_wav_bytes(samples);
  auto registration = lmdj::analysis_bench::loudness_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.loudness.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = nlohmann::json::object();
  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  const auto& written = capture.written.at("loudness");
  return nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
}

}  // namespace

int main() {
  // Full-scale constant: peak 0 dBFS-ish, rms == peak, clipping true.
  const auto full = run_loudness({32767, 32767, 32767, 32767});
  assert(full.at("contract") == "lmdj.analysis-bench.loudness.v1");
  assert(full.at("clipping") == true);
  const double full_peak = full.at("peak_dbfs").get<double>();
  // 32767/32768 -> -0.000265 dBFS
  assert(std::fabs(full_peak - (-0.000265)) < 0.001);
  assert(
      std::fabs(full.at("rms_dbfs").get<double>() - full_peak) < 0.001);

  // Half amplitude (16384): peak = 20*log10(0.5) = -6.0206 dBFS.
  const auto half = run_loudness({16384, -16384, 16384, -16384});
  assert(half.at("clipping") == false);
  assert(std::fabs(half.at("peak_dbfs").get<double>() - (-6.0206)) < 0.001);

  // Silence: floored at -300 dBFS.
  const auto silence = run_loudness({0, 0, 0, 0});
  assert(silence.at("peak_dbfs") == -300.0);
  assert(silence.at("rms_dbfs") == -300.0);

  std::cout << "loudness_test passed\n";
  return 0;
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
scripts/core.sh build dev
```

Expected: FAIL — `lmdj/analysis_bench/loudness/factory.hpp` not found.

- [ ] **Step 3: Write the implementation**

`tools/analysis-bench/providers/loudness/include/lmdj/analysis_bench/loudness/factory.hpp`:

```cpp
#pragma once

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::analysis_bench {

provider::ProviderRegistration loudness_registration(
    analysis::ArtifactByteResolver resolver);

}  // namespace lmdj::analysis_bench
```

`tools/analysis-bench/providers/loudness/src/provider.cpp`:

```cpp
#include <lmdj/analysis_bench/loudness/factory.hpp>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/wav_pcm16.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::analysis_bench {
namespace {

constexpr double kSilenceDbfs = -300.0;

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

double to_dbfs(double amplitude) {
  if (amplitude <= 0.0) {
    return kSilenceDbfs;
  }
  return 20.0 * std::log10(amplitude);
}

class LoudnessProvider final : public provider::Provider {
 public:
  explicit LoudnessProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override {
    return "local.analysis-bench.loudness";
  }

  std::vector<std::string> capabilities() const override {
    return {"analysis.loudness.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
    const auto binding = std::find_if(
        request.inputs.begin(),
        request.inputs.end(),
        [](const provider::ArtifactBinding& input) {
          return input.port == "sample";
        });
    if (binding == request.inputs.end()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("missing sample input binding")};
    }
    const auto bytes = resolver_(binding->artifact);
    if (!bytes.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(bytes.error().message)};
    }
    const auto wav = analysis::parse_wav_pcm16(bytes.value());
    if (!wav.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(wav.error().message)};
    }
    const auto mono = analysis::mix_to_mono(wav.value());

    double peak = 0.0;
    double square_sum = 0.0;
    for (const float sample : mono) {
      const double value = sample;
      peak = std::max(peak, std::fabs(value));
      square_sum += value * value;
    }
    const double rms =
        mono.empty() ? 0.0
                     : std::sqrt(square_sum /
                                 static_cast<double>(mono.size()));
    const bool clipping = std::any_of(
        wav.value().interleaved.begin(),
        wav.value().interleaved.end(),
        [](std::int16_t sample) {
          return sample == 32767 || sample == -32768;
        });

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.loudness.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"channels", wav.value().channels},
        {"frame_count", wav.value().frame_count()},
        {"peak_dbfs", to_dbfs(peak)},
        {"rms_dbfs", to_dbfs(rms)},
        {"clipping", clipping},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "loudness",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("loudness artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"loudness", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor loudness_capability() {
  return provider::CapabilityDescriptor{
      "analysis.loudness.v1",
      "2.0.0",
      {{
          "sample",
          {"audio/wav"},
          "lmdj.artifact.audio-pcm.v1",
          "1.0.0",
          true,
          1,
      }},
      {{
          "loudness",
          {"application/json"},
          "lmdj.artifact.analysis-bench-loudness.v1",
          "1.0.0",
          true,
          1,
      }},
      provider::Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      provider::ResourceRequirements{
          provider::ResourceClass::cpu,
          64,
      },
      provider::ExecutionPolicy{5000, 1},
      provider::CapabilityPolicy{
          {"public"},
          {"local"},
          {"analysis-bench.execute"},
      },
      {"test"},
      65536,
  };
}

}  // namespace

provider::ProviderRegistration loudness_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<LoudnessProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {loudness_capability()},
  };
}

}  // namespace lmdj::analysis_bench
```

Append to `tools/analysis-bench/CMakeLists.txt` (before `if(BUILD_TESTING)`):

```cmake
add_library(
  lmdj_analysis_bench_loudness
  STATIC
    providers/loudness/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_loudness
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/loudness/include"
)
target_link_libraries(
  lmdj_analysis_bench_loudness
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_loudness)
lmdj_target_sanitizers(lmdj_analysis_bench_loudness)
```

Append inside `if(BUILD_TESTING)`:

```cmake
  add_executable(
    lmdj_analysis_bench_loudness_tests
    tests/loudness_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_loudness_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_loudness_tests
    PRIVATE
      lmdj_analysis_bench_loudness
  )
  lmdj_target_warnings(lmdj_analysis_bench_loudness_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_loudness_tests)
  lmdj_add_test(
    NAME analysis_bench.loudness
    TIER unit
    COMMAND lmdj_analysis_bench_loudness_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench --output-on-failure
```

Expected: wav, peaks, loudness all Passed.

- [ ] **Step 5: Commit**

```bash
git add tools/analysis-bench
git diff --cached --check
git commit -m "feat(tools): add analysis-bench loudness provider"
```

---

### Task 4: Onset detection Provider (spectral flux + FFT)

**Files:**
- Create: `tools/analysis-bench/shared/include/lmdj/analysis/fft.hpp`
- Create: `tools/analysis-bench/providers/onsets/include/lmdj/analysis_bench/onsets/factory.hpp`
- Create: `tools/analysis-bench/providers/onsets/src/provider.cpp`
- Create: `tools/analysis-bench/tests/onsets_test.cpp`
- Modify: `tools/analysis-bench/CMakeLists.txt` (append onsets lib + test)

**Interfaces:**
- Consumes: same as Task 2.
- Produces:
  - `void lmdj::analysis::fft(std::vector<std::complex<float>>&)` — in-place iterative radix-2 FFT; size must be a power of two
  - `lmdj::analysis_bench::onsets_registration(analysis::ArtifactByteResolver) -> provider::ProviderRegistration`; Provider id `local.analysis-bench.onsets`, version `0.1.0`
  - Capability `analysis.onsets.v1` (contract version `2.0.0`): input port `sample`, output port `onsets` (`application/json`, required, max 1)
  - Output JSON: `{"contract":"lmdj.analysis-bench.onsets.v1","sample_rate":u32,"frame_count":u64,"fft_size":u32,"hop_size":u32,"onsets_seconds":[f64...]}` sorted ascending
  - Algorithm (must match `compare.py` exactly): mono mix; frames at `i*hop_size` (no centering), Hann window; magnitude spectrum over first `fft_size/2+1` bins; spectral flux `sum(max(0, mag[i]-prev[i]))`; onset where flux is a strict local maximum and `flux > mean + 1.5*stddev`; minimum onset spacing 0.05 s
  - Parameters: `fft_size` (default 1024, power of two 256..8192), `hop_size` (default 512, 128..65536)
  - CMake target `lmdj_analysis_bench_onsets`

- [ ] **Step 1: Write the failing test**

`tools/analysis-bench/tests/onsets_test.cpp`:

```cpp
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/fft.hpp>
#include <lmdj/analysis_bench/onsets/factory.hpp>
#include <lmdj/provider/provider.hpp>

#include "support.hpp"

namespace {

std::vector<std::byte> make_wav_bytes(
    const std::vector<std::int16_t>& samples,
    std::uint32_t sample_rate = 48000) {
  const std::uint32_t data_size =
      static_cast<std::uint32_t>(samples.size() * 2);
  std::vector<std::byte> bytes(44 + data_size);
  auto* p = reinterpret_cast<char*>(bytes.data());
  std::memcpy(p, "RIFF", 4);
  const std::uint32_t riff_size = 36 + data_size;
  std::memcpy(p + 4, &riff_size, 4);
  std::memcpy(p + 8, "WAVEfmt ", 8);
  const std::uint32_t fmt_size = 16;
  std::memcpy(p + 16, &fmt_size, 4);
  const std::uint16_t format = 1;
  const std::uint16_t channels = 1;
  const std::uint32_t byte_rate = sample_rate * 2;
  const std::uint16_t block_align = 2;
  const std::uint16_t bits = 16;
  std::memcpy(p + 20, &format, 2);
  std::memcpy(p + 22, &channels, 2);
  std::memcpy(p + 24, &sample_rate, 4);
  std::memcpy(p + 28, &byte_rate, 4);
  std::memcpy(p + 32, &block_align, 2);
  std::memcpy(p + 34, &bits, 2);
  std::memcpy(p + 36, "data", 4);
  std::memcpy(p + 40, &data_size, 4);
  std::memcpy(p + 44, samples.data(), data_size);
  return bytes;
}

}  // namespace

int main() {
  // FFT sanity: impulse at index 0 -> flat magnitude 1 everywhere.
  std::vector<std::complex<float>> impulse(8, {0.0F, 0.0F});
  impulse[0] = {1.0F, 0.0F};
  lmdj::analysis::fft(impulse);
  for (const auto& value : impulse) {
    assert(std::fabs(std::abs(value) - 1.0F) < 1e-5F);
  }

  // 1 s of audio (48000 samples) with 4 broadband clicks at 0.1 s intervals
  // starting at 0.1 s (4800, 9600, 14400, 19200 samples). A click is a short
  // burst of alternating full-scale samples (rich in high frequencies).
  std::vector<std::int16_t> samples(48000, 0);
  for (int click = 1; click <= 4; ++click) {
    const std::size_t start = static_cast<std::size_t>(click) * 4800;
    for (std::size_t i = 0; i < 64; ++i) {
      samples[start + i] = (i % 2 == 0) ? 24000 : -24000;
    }
  }
  const auto wav = make_wav_bytes(samples);
  auto registration = lmdj::analysis_bench::onsets_registration(
      analysis_bench_test::make_resolver({{"wav-sha", wav}}));
  lmdj::provider::CapabilityRequest request;
  request.capability = "analysis.onsets.v1";
  request.inputs = {lmdj::provider::ArtifactBinding{
      "sample",
      lmdj::foundation::ArtifactRef{"wav-sha", "audio/wav", wav.size()},
  }};
  request.parameters = nlohmann::json::object();
  analysis_bench_test::CaptureSink capture;
  const auto result = registration.implementation->run(
      lmdj::foundation::AttemptId{"test-attempt"}, request, capture.sink());
  assert(!result.error.has_value());
  const auto& written = capture.written.at("onsets");
  const auto output = nlohmann::json::parse(
      reinterpret_cast<const char*>(written.data()),
      reinterpret_cast<const char*>(written.data()) + written.size());
  assert(output.at("contract") == "lmdj.analysis-bench.onsets.v1");
  const auto onsets =
      output.at("onsets_seconds").get<std::vector<double>>();
  assert(onsets.size() == 4);
  for (std::size_t click = 0; click < 4; ++click) {
    const double expected = 0.1 * static_cast<double>(click + 1);
    assert(std::fabs(onsets[click] - expected) < 0.03);
  }

  std::cout << "onsets_test passed\n";
  return 0;
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
scripts/core.sh build dev
```

Expected: FAIL — onsets factory header not found.

- [ ] **Step 3: Write the implementation**

`tools/analysis-bench/shared/include/lmdj/analysis/fft.hpp`:

```cpp
#pragma once

#include <cmath>
#include <complex>
#include <cstddef>
#include <numbers>
#include <utility>
#include <vector>

namespace lmdj::analysis {

// In-place iterative radix-2 FFT. values.size() must be a power of two.
inline void fft(std::vector<std::complex<float>>& values) {
  const std::size_t n = values.size();
  for (std::size_t i = 1, j = 0; i < n; ++i) {
    std::size_t bit = n >> 1U;
    for (; (j & bit) != 0U; bit >>= 1U) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      std::swap(values[i], values[j]);
    }
  }
  for (std::size_t length = 2; length <= n; length <<= 1U) {
    const float angle =
        -2.0F * std::numbers::pi_v<float> / static_cast<float>(length);
    const std::complex<float> step(std::cos(angle), std::sin(angle));
    for (std::size_t i = 0; i < n; i += length) {
      std::complex<float> factor(1.0F, 0.0F);
      for (std::size_t j = 0; j < length / 2; ++j) {
        const auto even = values[i + j];
        const auto odd = values[i + j + length / 2] * factor;
        values[i + j] = even + odd;
        values[i + j + length / 2] = even - odd;
        factor *= step;
      }
    }
  }
}

}  // namespace lmdj::analysis
```

`tools/analysis-bench/providers/onsets/include/lmdj/analysis_bench/onsets/factory.hpp`:

```cpp
#pragma once

#include <lmdj/analysis/artifact_bytes.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::analysis_bench {

provider::ProviderRegistration onsets_registration(
    analysis::ArtifactByteResolver resolver);

}  // namespace lmdj::analysis_bench
```

`tools/analysis-bench/providers/onsets/src/provider.cpp`:

```cpp
#include <lmdj/analysis_bench/onsets/factory.hpp>

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <numbers>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/analysis/fft.hpp>
#include <lmdj/analysis/wav_pcm16.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/capability.hpp>
#include <lmdj/provider/provider.hpp>

namespace lmdj::analysis_bench {
namespace {

constexpr double kMinOnsetSpacingSeconds = 0.05;

foundation::Error failed(std::string message) {
  return foundation::Error{
      foundation::ErrorCode::provider_failed,
      std::move(message),
      nlohmann::json::object(),
  };
}

bool is_power_of_two(std::uint32_t value) {
  return value != 0 && (value & (value - 1)) == 0;
}

// Spectral flux onset times (seconds). Mirrors compare.py exactly:
// frames at i*hop (no centering), Hann window, half-spectrum magnitude,
// flux = sum(max(0, mag-prev)), threshold = mean + 1.5*stddev, strict local
// maximum, minimum spacing 0.05 s.
std::vector<double> detect_onsets(
    const std::vector<float>& mono,
    std::uint32_t sample_rate,
    std::uint32_t fft_size,
    std::uint32_t hop_size) {
  std::vector<float> window(fft_size);
  for (std::uint32_t i = 0; i < fft_size; ++i) {
    window[i] = 0.5F - 0.5F * std::cos(
                              2.0F * std::numbers::pi_v<float> *
                              static_cast<float>(i) /
                              static_cast<float>(fft_size - 1));
  }
  const std::size_t bin_count = fft_size / 2 + 1;
  std::vector<float> previous(bin_count, 0.0F);
  std::vector<double> flux;
  std::vector<double> times;
  for (std::size_t start = 0; start + fft_size <= mono.size();
       start += hop_size) {
    std::vector<std::complex<float>> frame(fft_size);
    for (std::uint32_t i = 0; i < fft_size; ++i) {
      frame[i] = {mono[start + i] * window[i], 0.0F};
    }
    analysis::fft(frame);
    double frame_flux = 0.0;
    for (std::size_t bin = 0; bin < bin_count; ++bin) {
      const float magnitude = std::abs(frame[bin]);
      frame_flux += std::max(0.0F, magnitude - previous[bin]);
      previous[bin] = magnitude;
    }
    flux.push_back(frame_flux);
    times.push_back(static_cast<double>(start) /
                    static_cast<double>(sample_rate));
  }
  if (flux.size() < 3) {
    return {};
  }
  double mean = 0.0;
  for (const double value : flux) {
    mean += value;
  }
  mean /= static_cast<double>(flux.size());
  double variance = 0.0;
  for (const double value : flux) {
    variance += (value - mean) * (value - mean);
  }
  variance /= static_cast<double>(flux.size());
  const double threshold = mean + 1.5 * std::sqrt(variance);

  std::vector<double> onsets;
  for (std::size_t i = 1; i + 1 < flux.size(); ++i) {
    if (flux[i] > threshold && flux[i] > flux[i - 1] &&
        flux[i] >= flux[i + 1]) {
      if (!onsets.empty() &&
          times[i] - onsets.back() < kMinOnsetSpacingSeconds) {
        continue;
      }
      onsets.push_back(times[i]);
    }
  }
  return onsets;
}

class OnsetsProvider final : public provider::Provider {
 public:
  explicit OnsetsProvider(analysis::ArtifactByteResolver resolver)
      : resolver_(std::move(resolver)) {}

  std::string id() const override { return "local.analysis-bench.onsets"; }

  std::vector<std::string> capabilities() const override {
    return {"analysis.onsets.v1"};
  }

  provider::AttemptResult run(
      foundation::AttemptId attempt_id,
      const provider::CapabilityRequest& request,
      provider::ArtifactSink output) override {
    std::uint32_t fft_size = 1024;
    std::uint32_t hop_size = 512;
    if (request.parameters.contains("fft_size")) {
      // Accept both signed and unsigned JSON integer representations
      // (nlohmann stores C++ literals as signed, parsed non-negative text as
      // unsigned); bound-check as int64 before the narrowing get.
      const auto& encoded = request.parameters.at("fft_size");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 0 ||
          encoded.get<std::int64_t>() > 8192) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("fft_size must be an integer in 256..8192")};
      }
      fft_size = encoded.get<std::uint32_t>();
    }
    if (!is_power_of_two(fft_size) || fft_size < 256 || fft_size > 8192) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("fft_size must be a power of two in 256..8192")};
    }
    if (request.parameters.contains("hop_size")) {
      const auto& encoded = request.parameters.at("hop_size");
      if (!encoded.is_number_integer() ||
          encoded.get<std::int64_t>() < 0 ||
          encoded.get<std::int64_t>() > 65536) {
        return {std::move(attempt_id),
                std::nullopt,
                failed("hop_size must be an integer in 128..65536")};
      }
      hop_size = encoded.get<std::uint32_t>();
    }
    if (hop_size < 128) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("hop_size must be at least 128")};
    }
    const auto binding = std::find_if(
        request.inputs.begin(),
        request.inputs.end(),
        [](const provider::ArtifactBinding& input) {
          return input.port == "sample";
        });
    if (binding == request.inputs.end()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("missing sample input binding")};
    }
    const auto bytes = resolver_(binding->artifact);
    if (!bytes.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(bytes.error().message)};
    }
    const auto wav = analysis::parse_wav_pcm16(bytes.value());
    if (!wav.has_value()) {
      return {std::move(attempt_id), std::nullopt, failed(wav.error().message)};
    }
    const auto mono = analysis::mix_to_mono(wav.value());
    const auto onsets = detect_onsets(
        mono, wav.value().sample_rate, fft_size, hop_size);

    const nlohmann::json result{
        {"contract", "lmdj.analysis-bench.onsets.v1"},
        {"sample_rate", wav.value().sample_rate},
        {"frame_count", wav.value().frame_count()},
        {"fft_size", fft_size},
        {"hop_size", hop_size},
        {"onsets_seconds", onsets},
    };
    const auto encoded = result.dump();
    const auto artifact = output(
        "onsets",
        std::span<const std::byte>(
            reinterpret_cast<const std::byte*>(encoded.data()),
            encoded.size()),
        "application/json");
    if (!artifact.has_value()) {
      return {std::move(attempt_id),
              std::nullopt,
              failed("onsets artifact sink failed")};
    }
    return provider::AttemptResult{
        attempt_id,
        provider::Candidate{
            foundation::CandidateId{attempt_id.value()},
            {{"onsets", artifact.value()}},
            nlohmann::json::object(),
        },
        std::nullopt,
    };
  }

 private:
  analysis::ArtifactByteResolver resolver_;
};

provider::CapabilityDescriptor onsets_capability() {
  return provider::CapabilityDescriptor{
      "analysis.onsets.v1",
      "2.0.0",
      {{
          "sample",
          {"audio/wav"},
          "lmdj.artifact.audio-pcm.v1",
          "1.0.0",
          true,
          1,
      }},
      {{
          "onsets",
          {"application/json"},
          "lmdj.artifact.analysis-bench-onsets.v1",
          "1.0.0",
          true,
          1,
      }},
      provider::Determinism::deterministic,
      {},
      {"PROVIDER_FAILED"},
      provider::ResourceRequirements{
          provider::ResourceClass::cpu,
          64,
      },
      provider::ExecutionPolicy{5000, 1},
      provider::CapabilityPolicy{
          {"public"},
          {"local"},
          {"analysis-bench.execute"},
      },
      {"test"},
      1048576,
  };
}

}  // namespace

provider::ProviderRegistration onsets_registration(
    analysis::ArtifactByteResolver resolver) {
  return provider::ProviderRegistration{
      std::make_shared<OnsetsProvider>(std::move(resolver)),
      "0.1.0",
      std::string(64, '0'),
      std::nullopt,
      {onsets_capability()},
  };
}

}  // namespace lmdj::analysis_bench
```

Append to `tools/analysis-bench/CMakeLists.txt` (before `if(BUILD_TESTING)`):

```cmake
add_library(
  lmdj_analysis_bench_onsets
  STATIC
    providers/onsets/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_onsets
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/onsets/include"
)
target_link_libraries(
  lmdj_analysis_bench_onsets
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_onsets)
lmdj_target_sanitizers(lmdj_analysis_bench_onsets)
```

Append inside `if(BUILD_TESTING)`:

```cmake
  add_executable(
    lmdj_analysis_bench_onsets_tests
    tests/onsets_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_onsets_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_onsets_tests
    PRIVATE
      lmdj_analysis_bench_onsets
  )
  lmdj_target_warnings(lmdj_analysis_bench_onsets_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_onsets_tests)
  lmdj_add_test(
    NAME analysis_bench.onsets
    TIER unit
    COMMAND lmdj_analysis_bench_onsets_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench --output-on-failure
```

Expected: wav, peaks, loudness, onsets all Passed.

- [ ] **Step 5: Commit**

```bash
git add tools/analysis-bench
git diff --cached --check
git commit -m "feat(tools): add analysis-bench onset detection provider"
```

---

### Task 5: Bench CLI Host

**Files:**
- Create: `tools/analysis-bench/src/main.cpp`
- Create: `tools/analysis-bench/tests/bench_smoke_test.py`
- Modify: `tools/analysis-bench/CMakeLists.txt` (append CLI target + smoke test)

**Interfaces:**
- Consumes: `peaks_registration`, `loudness_registration`, `onsets_registration` (Tasks 2-4); `provider::{Registry, AttemptStore, ProviderPolicy}`; `foundation::describe_artifact`.
- Produces:
  - Executable `lmdj_analysis_bench`:
    `lmdj_analysis_bench --workspace DIR --fixture WAV --capability CAP --iterations N [--parameters JSON]`
  - For every registered Provider serving `--capability`: selects it via `AttemptStore::set_provider_selection`, runs N attempts through `AttemptStore::execute` (the production path), times each attempt, reads the output Artifact bytes back from `<workspace>/attempts/<attempt_id>/artifacts/<sha256>`, and verifies all iterations produce the identical output sha256.
  - Stdout report JSON: `{"fixture":path,"fixture_sha256":str,"capability":str,"iterations":N,"runs":[{"provider_id":str,"deterministic":bool,"output_sha256":str,"ms_min":f64,"ms_median":f64,"ms_max":f64,"result":<parsed output artifact JSON>}]}`. Exit 0 on success, 2 on any failure (message on stderr).

- [ ] **Step 1: Write the failing test**

`tools/analysis-bench/tests/bench_smoke_test.py`:

```python
"""Smoke test: run the bench CLI on a fixture and validate the report."""

import json
import subprocess
import sys
import tempfile


def main() -> int:
    bench_binary = sys.argv[1]
    fixture = sys.argv[2]
    with tempfile.TemporaryDirectory() as workspace:
        completed = subprocess.run(
            [
                bench_binary,
                "--workspace", workspace,
                "--fixture", fixture,
                "--capability", "analysis.loudness.v1",
                "--iterations", "3",
            ],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        report = json.loads(completed.stdout)
        assert report["capability"] == "analysis.loudness.v1"
        assert report["iterations"] == 3
        assert len(report["runs"]) == 1
        run = report["runs"][0]
        assert run["provider_id"] == "local.analysis-bench.loudness"
        assert run["deterministic"] is True
        assert len(run["output_sha256"]) == 64
        assert run["ms_min"] <= run["ms_median"] <= run["ms_max"]
        result = run["result"]
        assert result["contract"] == "lmdj.analysis-bench.loudness.v1"
        assert result["sample_rate"] == 48000
        assert result["peak_dbfs"] <= 0.0
        assert result["rms_dbfs"] <= result["peak_dbfs"]
    print("bench_smoke_test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
scripts/core.sh build dev
```

Expected: FAIL — no `lmdj_analysis_bench` target yet.

- [ ] **Step 3: Write the implementation**

`tools/analysis-bench/src/main.cpp`:

```cpp
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
  return {std::istreambuf_iterator<char>(stream),
          std::istreambuf_iterator<char>()};
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
        const auto output_path = invocation.workspace / "attempts" /
                                 attempt_id / "artifacts" /
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
```

Append to `tools/analysis-bench/CMakeLists.txt` (before `if(BUILD_TESTING)`):

```cmake
add_executable(
  lmdj_analysis_bench
  src/main.cpp
)
target_link_libraries(
  lmdj_analysis_bench
  PRIVATE
    lmdj_analysis_bench_peaks
    lmdj_analysis_bench_loudness
    lmdj_analysis_bench_onsets
)
lmdj_target_warnings(lmdj_analysis_bench)
lmdj_target_sanitizers(lmdj_analysis_bench)
```

Append inside `if(BUILD_TESTING)`:

```cmake
  lmdj_add_test(
    NAME analysis_bench.smoke
    TIER component
    COMMAND
      python3
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/bench_smoke_test.py"
      $<TARGET_FILE:lmdj_analysis_bench>
      "${CMAKE_SOURCE_DIR}/tests/fixtures/audio/kick.wav"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
ctest --test-dir build/core/dev -R analysis_bench --output-on-failure
```

Expected: 5 tests (wav, peaks, loudness, onsets, smoke) all Passed.

Also run the full fast suite to prove nothing regressed:

```bash
scripts/core.sh test dev fast
```

Expected: `100% tests passed` (baseline 25 + 5 new = 30).

- [ ] **Step 5: Commit**

```bash
git add tools/analysis-bench
git diff --cached --check
git commit -m "feat(tools): add analysis-bench CLI host"
```

---

### Task 6: Ground-truth comparison (numpy/scipy) + README

**Files:**
- Create: `tools/analysis-bench/compare/requirements.txt`
- Create: `tools/analysis-bench/compare/compare.py`
- Create: `tools/analysis-bench/README.md`
- Modify: `tools/analysis-bench/CMakeLists.txt` (venv-gated compare test)

**Interfaces:**
- Consumes: `lmdj_analysis_bench` binary (Task 5) and its report JSON; fixtures `tests/fixtures/audio/{kick,snare,stereo}.wav`.
- Produces:
  - `compare.py --bench BINARY --fixtures-dir DIR --report PATH` — runs every capability on the three declared fixtures (`kick.wav`, `snare.wav`, `stereo.wav`; an explicit list, never a directory glob, because the fixtures directory also holds WAVs owned by other suites) plus a generated click train, computes numpy/scipy ground truth with the identical algorithms, prints and writes a Markdown comparison table, exit 1 on mismatch.
  - Comparison rules: peaks min/max arrays exact (±1 LSB); loudness peak/rms within 0.01 dB and equal `clipping`; onsets on the click train: equal count and each within 30 ms; onsets on real fixtures: matched-within-30 ms fraction ≥ 0.5 (reported, borderline spectral-flux peaks may flip between float32/float64); when the reference finds no onsets (fixture shorter than `fft_size`), the provider must also report none.
  - CTest `analysis_bench.compare` (component tier), registered only when `tools/analysis-bench/.venv/bin/python3` exists.

- [ ] **Step 1: Create the venv and requirements**

`tools/analysis-bench/compare/requirements.txt`:

```text
numpy>=1.26
scipy>=1.11
```

```bash
python3 -m venv tools/analysis-bench/.venv
tools/analysis-bench/.venv/bin/pip install -r tools/analysis-bench/compare/requirements.txt
```

Add `.venv` to `.gitignore` (append one line `.venv` if not already covered — check with `git check-ignore tools/analysis-bench/.venv`).

- [ ] **Step 2: Write compare.py**

`tools/analysis-bench/compare/compare.py`:

```python
"""Ground-truth comparison for the analysis-bench prototype.

Runs the lmdj_analysis_bench CLI on every fixture x capability, computes
reference values with numpy/scipy using the identical algorithms documented
in docs/plans/2026-08-15-lmdj-audio-analysis-bench-prototype.md,
and emits a Markdown comparison table.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

ONSET_TOLERANCE_SECONDS = 0.03
CLICK_TRAIN_TIMES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
# Explicit fixture list: the fixtures directory also holds WAV files owned by
# other suites (e.g. web-runtime-host-short.wav), which this comparison must
# not pick up.
FIXTURE_NAMES = ("kick.wav", "snare.wav", "stereo.wav")


def read_mono(path: Path) -> tuple[int, np.ndarray]:
    sample_rate, data = wavfile.read(path)
    assert data.dtype == np.int16, f"{path} must be PCM16"
    mono = data.astype(np.float64) / 32768.0
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    return sample_rate, mono


def reference_peaks(mono: np.ndarray, samples_per_bucket: int = 256):
    bucket_count = (mono.size + samples_per_bucket - 1) // samples_per_bucket
    padded = np.zeros(bucket_count * samples_per_bucket)
    padded[: mono.size] = mono
    buckets = padded.reshape(bucket_count, samples_per_bucket)
    if mono.size % samples_per_bucket:
        # Ignore padding in the final partial bucket.
        buckets[-1, mono.size % samples_per_bucket :] = buckets[
            -1, mono.size % samples_per_bucket - 1
        ]
    scale = lambda v: np.clip(np.rint(v * 32767.0), -32767, 32767).astype(int)
    return scale(buckets.min(axis=1)), scale(buckets.max(axis=1))


def reference_loudness(mono: np.ndarray):
    if mono.size == 0:
        return -300.0, -300.0
    peak = float(np.abs(mono).max())
    rms = float(np.sqrt(np.mean(mono * mono)))
    to_dbfs = lambda a: -300.0 if a <= 0.0 else 20.0 * np.log10(a)
    return to_dbfs(peak), to_dbfs(rms)


def reference_onsets(
    mono: np.ndarray,
    sample_rate: int,
    fft_size: int = 1024,
    hop_size: int = 512,
):
    if mono.size < fft_size:
        return []
    window = np.hanning(fft_size)
    frames = [
        mono[start : start + fft_size] * window
        for start in range(0, mono.size - fft_size + 1, hop_size)
    ]
    magnitudes = np.abs(np.fft.rfft(np.array(frames), axis=1))
    flux = np.maximum(0.0, np.diff(magnitudes, axis=0, prepend=0)).sum(axis=1)
    threshold = flux.mean() + 1.5 * flux.std()
    times = np.arange(flux.size) * hop_size / sample_rate
    onsets = []
    for i in range(1, flux.size - 1):
        if (
            flux[i] > threshold
            and flux[i] > flux[i - 1]
            and flux[i] >= flux[i + 1]
        ):
            if onsets and times[i] - onsets[-1] < 0.05:
                continue
            onsets.append(float(times[i]))
    return onsets


def match_onsets(expected, actual, tolerance=ONSET_TOLERANCE_SECONDS):
    matched = sum(
        any(abs(found - want) <= tolerance for found in actual)
        for want in expected
    )
    return matched


def make_click_train(path: Path, sample_rate: int = 48000) -> None:
    samples = np.zeros(sample_rate * 2, dtype=np.int16)
    for at in CLICK_TRAIN_TIMES:
        start = int(at * sample_rate)
        burst = np.where(
            np.arange(64) % 2 == 0, 24000, -24000
        ).astype(np.int16)
        samples[start : start + 64] = burst
    wavfile.write(path, sample_rate, samples)


def run_bench(bench, workspace, fixture, capability, parameters=None):
    command = [
        str(bench),
        "--workspace", str(workspace),
        "--fixture", str(fixture),
        "--capability", capability,
        "--iterations", "5",
    ]
    if parameters:
        command += ["--parameters", json.dumps(parameters)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"bench failed for {fixture}: {completed.stderr}")
    report = json.loads(completed.stdout)
    assert len(report["runs"]) == 1
    return report["runs"][0]


def compare_fixture(bench, workspace_root, fixture, rows, failures):
    sample_rate, mono = read_mono(fixture)
    is_click_train = fixture.name == "click_train.wav"

    run = run_bench(
        bench, workspace_root / "peaks", fixture, "analysis.waveform-peaks.v1"
    )
    result = run["result"]
    ref_min, ref_max = reference_peaks(mono)
    peaks_ok = (
        np.array_equal(np.array(result["min"]), ref_min)
        and np.array_equal(np.array(result["max"]), ref_max)
    ) or (
        np.abs(np.array(result["min"]) - ref_min).max() <= 1
        and np.abs(np.array(result["max"]) - ref_max).max() <= 1
    )
    rows.append(
        f"| {fixture.name} | peaks | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | buckets={result['bucket_count']} | "
        f"{'PASS' if peaks_ok else 'FAIL'} |"
    )
    if not peaks_ok:
        failures.append(f"{fixture.name} peaks mismatch")

    run = run_bench(
        bench, workspace_root / "loudness", fixture, "analysis.loudness.v1"
    )
    result = run["result"]
    ref_peak, ref_rms = reference_loudness(mono)
    loudness_ok = (
        abs(result["peak_dbfs"] - ref_peak) <= 0.01
        and abs(result["rms_dbfs"] - ref_rms) <= 0.01
    )
    rows.append(
        f"| {fixture.name} | loudness | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | peak={result['peak_dbfs']:.2f} dBFS "
        f"rms={result['rms_dbfs']:.2f} dBFS | "
        f"{'PASS' if loudness_ok else 'FAIL'} |"
    )
    if not loudness_ok:
        failures.append(f"{fixture.name} loudness mismatch")

    run = run_bench(
        bench, workspace_root / "onsets", fixture, "analysis.onsets.v1"
    )
    result = run["result"]
    actual = result["onsets_seconds"]
    if is_click_train:
        matched = match_onsets(CLICK_TRAIN_TIMES, actual)
        onsets_ok = matched == len(CLICK_TRAIN_TIMES) and len(actual) == len(
            CLICK_TRAIN_TIMES
        )
        detail = f"{matched}/{len(CLICK_TRAIN_TIMES)} clicks matched"
    else:
        expected = reference_onsets(mono, sample_rate)
        if not expected:
            # Short fixtures (fewer samples than fft_size) legitimately have
            # no reference onsets; agreement means the provider found none.
            onsets_ok = not actual
            detail = (
                "no reference onsets; provider agrees"
                if onsets_ok
                else f"no reference onsets but provider found {len(actual)}"
            )
        else:
            matched = match_onsets(expected, actual)
            fraction = matched / len(expected)
            onsets_ok = fraction >= 0.5
            detail = (
                f"{matched}/{len(expected)} reference onsets matched "
                f"({fraction:.0%})"
            )
    rows.append(
        f"| {fixture.name} | onsets | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | {detail} | "
        f"{'PASS' if onsets_ok else 'FAIL'} |"
    )
    if not onsets_ok:
        failures.append(f"{fixture.name} onsets mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--fixtures-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    fixtures = [Path(args.fixtures_dir) / name for name in FIXTURE_NAMES]
    missing = [fixture.name for fixture in fixtures if not fixture.is_file()]
    assert not missing, f"missing fixtures: {missing}"
    rows = [
        "| fixture | capability | provider | median time | result | verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp:
        workspace_root = Path(temp)
        click_train = workspace_root / "click_train.wav"
        make_click_train(click_train)
        for fixture in [*fixtures, click_train]:
            compare_fixture(
                Path(args.bench), workspace_root, fixture, rows, failures
            )

    table = "# analysis-bench comparison\n\n" + "\n".join(rows) + "\n"
    print(table)
    Path(args.report).write_text(table)
    if failures:
        print("FAILURES:", *failures, sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run compare manually to verify it passes**

```bash
tools/analysis-bench/.venv/bin/python3 tools/analysis-bench/compare/compare.py \
  --bench build/core/dev/tools/analysis-bench/lmdj_analysis_bench \
  --fixtures-dir tests/fixtures/audio \
  --report build/core/dev/analysis-bench-report.md
```

Expected: table printed, all rows PASS, exit 0. (Bench binary path: confirm with `find build/core/dev -name lmdj_analysis_bench`.)

- [ ] **Step 4: Register the venv-gated CTest**

Append inside `if(BUILD_TESTING)` in `tools/analysis-bench/CMakeLists.txt`:

```cmake
  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python3")
    lmdj_add_test(
      NAME analysis_bench.compare
      TIER component
      COMMAND
        "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python3"
        "${CMAKE_CURRENT_SOURCE_DIR}/compare/compare.py"
        --bench $<TARGET_FILE:lmdj_analysis_bench>
        --fixtures-dir "${CMAKE_SOURCE_DIR}/tests/fixtures/audio"
        --report "${CMAKE_BINARY_DIR}/analysis-bench-report.md"
      WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
      LABELS analysis-bench
    )
  endif()
```

Re-run:

```bash
scripts/core.sh configure dev && ctest --test-dir build/core/dev -R analysis_bench --output-on-failure
```

Expected: 6 tests, all Passed (compare included once the venv exists).

- [ ] **Step 5: Write the README**

`tools/analysis-bench/README.md`:

```markdown
# analysis-bench (prototype)

Disposable prototype validating that the Core Provider mechanism
(`provider::Registry` + Capability v2 port bindings + `AttemptStore`) can
host multiple pluggable audio-analysis tools. It is independent of
`web-runtime-host` and `creator-web`, touches no Project Truth, and carries
no Product/Module/Provider identity (no `module.json`).

## What it validates / does not validate

Validates: multi-Provider registration, per-Capability selection, the
Attempt execute path (port validation, staging, evidence), deterministic
analysis output, and accuracy/performance against numpy/scipy ground truth.

Does not validate: Candidate adoption into Project Truth (open Contract
question), SDK-level input-Artifact byte resolution (the bench Host injects
`analysis::ArtifactByteResolver` at composition time instead), out-of-process
Provider Hosts, or real-time constraints.

## Layout

- `shared/` — strict WAV PCM16 parser, mono mixdown, radix-2 FFT, resolver alias
- `providers/peaks` — `analysis.waveform-peaks.v1` (mirrored peak envelope)
- `providers/loudness` — `analysis.loudness.v1` (peak/RMS dBFS, clipping)
- `providers/onsets` — `analysis.onsets.v1` (spectral-flux onset times)
- `src/main.cpp` — bench CLI: registers all Providers, runs N attempts per
  Provider through `AttemptStore`, times them, checks determinism, prints a
  JSON report
- `compare/` — numpy/scipy ground-truth diff (Markdown table)
- `tests/` — C++ unit tests + CLI smoke test

## Usage

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
build/core/dev/tools/analysis-bench/lmdj_analysis_bench \
  --workspace /tmp/analysis-bench \
  --fixture tests/fixtures/audio/kick.wav \
  --capability analysis.waveform-peaks.v1 \
  --iterations 10 --parameters '{"samples_per_bucket": 512}'

python3 -m venv .venv && .venv/bin/pip install -r compare/requirements.txt
.venv/bin/python3 compare/compare.py \
  --bench ../../build/core/dev/tools/analysis-bench/lmdj_analysis_bench \
  --fixtures-dir ../../tests/fixtures/audio \
  --report ../../build/core/dev/analysis-bench-report.md
```

## Graduation path (not part of this prototype)

If the validation succeeds, production analysis Providers move to
`providers/` with real `module.json` identities, the SDK grows a first-class
input-Artifact byte resolver, and display rendering lives in `creator-web`.
```

- [ ] **Step 6: Run the full fast suite, then commit**

```bash
scripts/core.sh test dev fast
bash scripts/architecture-portal.sh check
```

Expected: `100% tests passed` (30 without the venv test, 31 with it); portal check passes (no manifest changes).

```bash
git add tools/analysis-bench .gitignore
git diff --cached --check
git commit -m "feat(tools): add analysis-bench ground-truth comparison"
```

---

## Prototype report

After Task 6, paste the generated `build/core/dev/analysis-bench-report.md` table
plus explicit verdicts on the four items in "Success criteria and evidence
write-back" into the PR description — that is the evidence this prototype
exists to produce. Record the input-bytes resolver conclusion in
`docs/prd/decision-log.md` or the open issue in
`docs/architecture/2026-08-01-provider-multi-port-contract-decision.md`, not
only in the PR thread.
