#include <lmdj/cooker/project_cooker.hpp>

#include <array>
#include <cstdint>
#include <limits>
#include <map>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/cooker/wav_reader.hpp>

namespace lmdj::cooker {
namespace {

constexpr std::array<std::uint32_t, 64> kSha256Constants{
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
    0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
    0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
    0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
    0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
    0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
};

std::uint32_t rotate_right(std::uint32_t value, std::uint32_t amount) {
  return (value >> amount) | (value << (32U - amount));
}

void sha256_block(
    std::array<std::uint32_t, 8>& state,
    const std::array<std::uint8_t, 64>& block) {
  std::array<std::uint32_t, 64> words{};
  for (std::size_t index = 0; index < 16; ++index) {
    const auto offset = index * 4;
    words.at(index) =
        (static_cast<std::uint32_t>(block.at(offset)) << 24) |
        (static_cast<std::uint32_t>(block.at(offset + 1)) << 16) |
        (static_cast<std::uint32_t>(block.at(offset + 2)) << 8) |
        static_cast<std::uint32_t>(block.at(offset + 3));
  }
  for (std::size_t index = 16; index < words.size(); ++index) {
    const auto sigma0 = rotate_right(words.at(index - 15), 7) ^
                        rotate_right(words.at(index - 15), 18) ^
                        (words.at(index - 15) >> 3);
    const auto sigma1 = rotate_right(words.at(index - 2), 17) ^
                        rotate_right(words.at(index - 2), 19) ^
                        (words.at(index - 2) >> 10);
    words.at(index) = words.at(index - 16) + sigma0 +
                      words.at(index - 7) + sigma1;
  }

  auto a = state.at(0);
  auto b = state.at(1);
  auto c = state.at(2);
  auto d = state.at(3);
  auto e = state.at(4);
  auto f = state.at(5);
  auto g = state.at(6);
  auto h = state.at(7);
  for (std::size_t index = 0; index < words.size(); ++index) {
    const auto sigma1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^
                        rotate_right(e, 25);
    const auto choice = (e & f) ^ (~e & g);
    const auto temp1 = h + sigma1 + choice + kSha256Constants.at(index) +
                       words.at(index);
    const auto sigma0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^
                        rotate_right(a, 22);
    const auto majority = (a & b) ^ (a & c) ^ (b & c);
    const auto temp2 = sigma0 + majority;
    h = g;
    g = f;
    f = e;
    e = d + temp1;
    d = c;
    c = b;
    b = a;
    a = temp1 + temp2;
  }
  state.at(0) += a;
  state.at(1) += b;
  state.at(2) += c;
  state.at(3) += d;
  state.at(4) += e;
  state.at(5) += f;
  state.at(6) += g;
  state.at(7) += h;
}

std::string sha256_hex(const std::vector<std::byte>& bytes) {
  constexpr std::array<char, 16> kHex{
      '0', '1', '2', '3', '4', '5', '6', '7',
      '8', '9', 'a', 'b', 'c', 'd', 'e', 'f',
  };
  std::array<std::uint32_t, 8> state{
      0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
      0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
  };
  std::vector<std::uint8_t> padded;
  padded.reserve(bytes.size() + 72);
  for (const auto byte : bytes) {
    padded.push_back(std::to_integer<std::uint8_t>(byte));
  }
  const auto bit_length = static_cast<std::uint64_t>(bytes.size()) * 8U;
  padded.push_back(0x80U);
  while (padded.size() % 64 != 56) {
    padded.push_back(0U);
  }
  for (std::uint32_t shift = 56; shift > 0; shift -= 8) {
    padded.push_back(static_cast<std::uint8_t>(bit_length >> shift));
  }
  padded.push_back(static_cast<std::uint8_t>(bit_length));

  for (std::size_t offset = 0; offset < padded.size(); offset += 64) {
    std::array<std::uint8_t, 64> block{};
    for (std::size_t index = 0; index < block.size(); ++index) {
      block.at(index) = padded.at(offset + index);
    }
    sha256_block(state, block);
  }

  std::string result;
  result.reserve(64);
  for (const auto word : state) {
    for (std::uint32_t shift = 24;; shift -= 8) {
      const auto byte = static_cast<std::uint8_t>(word >> shift);
      result.push_back(kHex.at(byte >> 4));
      result.push_back(kHex.at(byte & 0x0fU));
      if (shift == 0) {
        break;
      }
    }
  }
  return result;
}

bool valid_sha256(std::string_view value) {
  if (value.size() != 64) {
    return false;
  }
  for (const char character : value) {
    if (!((character >= '0' && character <= '9') ||
          (character >= 'a' && character <= 'f'))) {
      return false;
    }
  }
  return true;
}

bool valid_pattern(const domain::Pattern& pattern) {
  if (!domain::is_valid_uuid(pattern.id.value()) ||
      !(pattern.bars == 1 || pattern.bars == 2 ||
        pattern.bars == 4 || pattern.bars == 8)) {
    return false;
  }
  const auto step_limit = static_cast<std::uint32_t>(pattern.bars) * 16U;
  for (const auto& event : pattern.events) {
    if (!domain::is_valid_slot(event.slot) || event.velocity == 0 ||
        event.velocity > 127 || event.step >= step_limit) {
      return false;
    }
  }
  return true;
}

struct DecodedArtifact {
  std::uint64_t byte_length;
  std::shared_ptr<const PcmSample> sample;
};

foundation::Result<std::shared_ptr<const RuntimeSnapshot>> failure(
    foundation::ErrorCode code,
    std::string_view message) {
  return foundation::Result<std::shared_ptr<const RuntimeSnapshot>>::failure(
      foundation::Error{code, std::string(message)});
}

}  // namespace

foundation::Result<std::shared_ptr<const RuntimeSnapshot>> cook(
    const domain::ProjectState& project,
    foundation::PatternId pattern_id,
    ArtifactResolver resolve) {
  if (!domain::is_valid_uuid(project.id.value()) ||
      project.bpm < 40 || project.bpm > 240 ||
      !domain::is_valid_uuid(pattern_id.value()) || !resolve) {
    return failure(
        foundation::ErrorCode::invalid_project,
        "project or cook request is invalid");
  }
  const auto pattern = project.patterns.find(pattern_id);
  if (pattern == project.patterns.end()) {
    return failure(foundation::ErrorCode::not_found, "pattern does not exist");
  }
  if (pattern->second.id != pattern_id || !valid_pattern(pattern->second)) {
    return failure(foundation::ErrorCode::invalid_project, "pattern is invalid");
  }

  std::map<std::string, DecodedArtifact> decoded;
  std::vector<ResolvedEvent> events;
  events.reserve(pattern->second.events.size());
  for (const auto& event : pattern->second.events) {
    const auto asset = domain::resolve_slot_asset(project, event.slot);
    if (!asset.has_value()) {
      return failure(
          foundation::ErrorCode::missing_asset,
          "pattern event references an unassigned pad slot");
    }
    const auto& artifact = asset->artifact;
    if (!valid_sha256(artifact.sha256)) {
      return failure(
          foundation::ErrorCode::invalid_project,
          "asset artifact hash is invalid");
    }
    auto decoded_artifact = decoded.find(artifact.sha256);
    if (decoded_artifact == decoded.end()) {
      const auto resolved = resolve(artifact);
      if (!resolved.has_value()) {
        return foundation::Result<std::shared_ptr<const RuntimeSnapshot>>::failure(
            resolved.error());
      }
      const auto& bytes = resolved.value();
      const auto actual_byte_length = static_cast<std::uint64_t>(bytes.size());
      if (actual_byte_length != artifact.byte_length ||
          sha256_hex(bytes) != artifact.sha256) {
        return failure(
            foundation::ErrorCode::cook_failed,
            "artifact bytes do not match declared metadata");
      }
      const auto decoded_sample = decode_wav(bytes);
      if (!decoded_sample.has_value()) {
        return foundation::Result<std::shared_ptr<const RuntimeSnapshot>>::failure(
            decoded_sample.error());
      }
      decoded_artifact = decoded.emplace(
          artifact.sha256,
          DecodedArtifact{actual_byte_length, decoded_sample.value()}).first;
    } else if (decoded_artifact->second.byte_length != artifact.byte_length) {
      return failure(
          foundation::ErrorCode::cook_failed,
          "cached artifact bytes do not match declared metadata");
    }
    events.push_back(ResolvedEvent{
        event.slot,
        event.step,
        event.velocity,
        decoded_artifact->second.sample,
    });
  }

  return foundation::Result<std::shared_ptr<const RuntimeSnapshot>>::success(
      std::make_shared<const RuntimeSnapshot>(RuntimeSnapshot{
          project.id,
          project.revision,
          project.bpm,
          pattern->second.bars,
          std::move(events),
      }));
}

}  // namespace lmdj::cooker
