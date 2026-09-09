#include <lmdj/providers/local_sample_slice/validation.hpp>

#include <cmath>
#include <string_view>
#include <nlohmann/json.hpp>

namespace lmdj::providers::sample_slice {
namespace {
using foundation::Error;
using foundation::ErrorCode;
using foundation::Result;

Error unsupported() {
  return {ErrorCode::unsupported_audio, "source does not satisfy PCM16 WAV profile",
          {{"reason", "source_audio_unsupported"}}};
}
Error invalid_output() {
  return {ErrorCode::invalid_argument, "Slice output does not match schema and source context"};
}
std::uint16_t u16(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint16_t>(std::to_integer<unsigned>(bytes[offset]) |
      (std::to_integer<unsigned>(bytes[offset + 1]) << 8));
}
std::uint32_t u32(std::span<const std::byte> bytes, std::size_t offset) {
  return static_cast<std::uint32_t>(u16(bytes, offset)) |
      (static_cast<std::uint32_t>(u16(bytes, offset + 2)) << 16);
}
bool tag(std::span<const std::byte> bytes, std::size_t offset, std::string_view value) {
  for (std::size_t i = 0; i < value.size(); ++i)
    if (std::to_integer<unsigned char>(bytes[offset + i]) !=
        static_cast<unsigned char>(value[i])) return false;
  return true;
}

// Only root -> points array -> point is admitted. Key bitsets detect duplicate
// names after JSON escape decoding, without a DOM or unbounded nesting stack.
class SliceSax final : public nlohmann::json_sax<nlohmann::json> {
 public:
  SliceSax(const foundation::ArtifactRef& source, std::uint32_t rate, std::uint64_t count)
      : source_(source), rate_(rate), count_(count) {}
  bool null() override { return false; }
  bool boolean(bool) override { return false; }
  bool binary(binary_t&) override { return false; }
  bool number_integer(number_integer_t value) override {
    return value >= 0 && integer(static_cast<std::uint64_t>(value));
  }
  bool number_unsigned(number_unsigned_t value) override { return integer(value); }
  bool number_float(number_float_t value, const string_t&) override {
    if (level_ != 3 || key_ != 2 || !std::isfinite(value) || value < 0 || value > 1)
      return false;
    key_ = 0;
    return true;
  }
  bool string(string_t& value) override {
    bool valid = false;
    if (level_ == 1 && key_ == 1) valid = value == "lmdj.slice-points.v1";
    if (level_ == 1 && key_ == 2) valid = value == source_.sha256;
    if (level_ == 3 && key_ == 4) valid = !value.empty() && value.size() <= 128;
    key_ = 0;
    return valid;
  }
  bool start_object(std::size_t) override {
    if (level_ == 0 && !finished_) { level_ = 1; return true; }
    if (level_ == 2 && points_ < 4096) {
      level_ = 3; point_keys_ = 0; key_ = 0; return true;
    }
    return false;
  }
  bool key(string_t& value) override {
    unsigned bit = 0;
    if (level_ == 1) {
      if (value == "contract") bit = 1;
      else if (value == "source_sha256") bit = 2;
      else if (value == "frame_rate") bit = 4;
      else if (value == "points") bit = 8;
      if (!bit || (root_keys_ & bit)) return false;
      root_keys_ |= bit;
    } else if (level_ == 3) {
      if (value == "frame") bit = 1;
      else if (value == "confidence") bit = 2;
      else if (value == "label") bit = 4;
      if (!bit || (point_keys_ & bit)) return false;
      point_keys_ |= bit;
    } else return false;
    key_ = bit;
    return true;
  }
  bool end_object() override {
    if (level_ == 3 && (point_keys_ & 1) && !key_) {
      ++points_; level_ = 2; return true;
    }
    if (level_ == 1 && root_keys_ == 15 && !key_) {
      level_ = 0; finished_ = true; return true;
    }
    return false;
  }
  bool start_array(std::size_t) override {
    if (level_ != 1 || key_ != 8) return false;
    level_ = 2; key_ = 0; return true;
  }
  bool end_array() override {
    if (level_ != 2) return false;
    level_ = 1; return true;
  }
  bool parse_error(std::size_t, const std::string&, const nlohmann::detail::exception&) override {
    return false;
  }
  bool complete() const { return finished_ && level_ == 0; }
 private:
  bool integer(std::uint64_t value) {
    bool valid = false;
    if (level_ == 1 && key_ == 4) valid = value == rate_;
    if (level_ == 3 && key_ == 1) {
      valid = value <= 9007199254740991ULL && value < count_ &&
          (points_ == 0 || value > previous_);
      previous_ = value;
    }
    if (level_ == 3 && key_ == 2) valid = value <= 1;
    key_ = 0;
    return valid;
  }
  const foundation::ArtifactRef& source_;
  std::uint32_t rate_;
  std::uint64_t count_;
  unsigned level_ = 0, root_keys_ = 0, point_keys_ = 0, key_ = 0;
  std::size_t points_ = 0;
  std::uint64_t previous_ = 0;
  bool finished_ = false;
};
}  // namespace

Result<Pcm16Audio> inspect_pcm16_wav(std::span<const std::byte> bytes) {
  const auto fail = [] { return Result<Pcm16Audio>::failure(unsupported()); };
  if (bytes.size() < 12 || !tag(bytes, 0, "RIFF") || !tag(bytes, 8, "WAVE") ||
      static_cast<std::uint64_t>(u32(bytes, 4)) + 8 != bytes.size()) return fail();
  bool have_fmt = false, have_data = false;
  std::uint16_t channels = 0, block = 0;
  std::uint32_t rate = 0;
  std::span<const std::byte> samples;
  std::size_t offset = 12;
  while (offset < bytes.size()) {
    if (bytes.size() - offset < 8) return fail();
    const auto size = u32(bytes, offset + 4);
    const auto payload = offset + 8;
    if (size > bytes.size() - payload) return fail();
    const auto end = payload + size;
    if ((size & 1U) && end == bytes.size()) return fail();
    if (tag(bytes, offset, "fmt ")) {
      if (have_fmt || size < 16 || size == 17 ||
          (size >= 18 && u16(bytes, payload + 16) != size - 18) ||
          u16(bytes, payload) != 1 || u16(bytes, payload + 14) != 16) return fail();
      channels = u16(bytes, payload + 2);
      rate = u32(bytes, payload + 4);
      block = u16(bytes, payload + 12);
      if ((channels != 1 && channels != 2) || (rate != 44100 && rate != 48000) ||
          block != channels * 2 || u32(bytes, payload + 8) != rate * block) return fail();
      have_fmt = true;
    } else if (tag(bytes, offset, "data")) {
      if (have_data || size == 0) return fail();
      samples = bytes.subspan(payload, size); have_data = true;
    }
    offset = end + (size & 1U);
  }
  if (!have_fmt || !have_data || samples.size() % block != 0) return fail();
  return Result<Pcm16Audio>::success({rate, channels, samples.size() / block, samples});
}

Result<void> validate_slice_points(std::span<const std::byte> bytes,
    const foundation::ArtifactRef& source, std::uint32_t rate, std::uint64_t count) {
  if (bytes.empty() || bytes.size() > 262144 || !rate || !count ||
      source.sha256.size() != 64 || source.media_type != "audio/wav" ||
      source.sha256.find_first_not_of("0123456789abcdef") != std::string::npos ||
      (bytes.size() >= 3 && bytes[0] == std::byte{0xef} &&
       bytes[1] == std::byte{0xbb} && bytes[2] == std::byte{0xbf}))
    return Result<void>::failure(invalid_output());
  SliceSax sax(source, rate, count);
  const auto* first = reinterpret_cast<const char*>(bytes.data());
  if (!nlohmann::json::sax_parse(first, first + bytes.size(), &sax) || !sax.complete())
    return Result<void>::failure(invalid_output());
  return Result<void>::success();
}

provider::OutputValidation slice_points_validation() {
  return {"sample.slice.v1", "slice_points",
      [](const provider::CapabilityRequest& request,
         std::span<const provider::ValidatedInput> inputs,
         const provider::ArtifactBinding& output, std::span<const std::byte> bytes,
         std::span<std::byte>) -> Result<void> {
        if (request.capability != "sample.slice.v1" || inputs.size() != 1 ||
            inputs[0].binding.port != "source_audio" || !inputs[0].handle ||
            inputs[0].handle->reference() != inputs[0].binding.artifact ||
            output.port != "slice_points" || output.artifact.media_type != "application/json" ||
            output.artifact.byte_length != bytes.size()) return Result<void>::failure(invalid_output());
        const auto audio = inspect_pcm16_wav(inputs[0].handle->bytes());
        if (!audio.has_value()) return Result<void>::failure(invalid_output());
        return validate_slice_points(bytes, inputs[0].binding.artifact,
            audio.value().frame_rate, audio.value().frame_count);
      }, 0};
}
}  // namespace lmdj::providers::sample_slice
