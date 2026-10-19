#include <lmdj/cooker/wav_metadata_inspector.hpp>

#include <algorithm>
#include <string>

namespace lmdj::cooker {
namespace {

bool fourcc(std::span<const std::byte> bytes, std::string_view expected) {
  for (std::size_t i = 0; i < expected.size(); ++i) {
    if (std::to_integer<char>(bytes[i]) != expected[i]) return false;
  }
  return true;
}

std::uint16_t u16(std::span<const std::byte> bytes, std::size_t at) {
  return static_cast<std::uint16_t>(std::to_integer<unsigned int>(bytes[at]) |
      (std::to_integer<unsigned int>(bytes[at + 1]) << 8));
}

std::uint32_t u32(std::span<const std::byte> bytes, std::size_t at) {
  std::uint32_t value = 0;
  for (unsigned int i = 0; i < 4; ++i) {
    value |= std::to_integer<std::uint32_t>(bytes[at + i]) << (8U * i);
  }
  return value;
}

}  // namespace

WavMetadataInspector::WavMetadataInspector(std::uint64_t byte_length)
    : byte_length_(byte_length) {
  if (byte_length < 12) reject("audio is not a RIFF/WAVE file");
}

void WavMetadataInspector::reject(std::string_view message) {
  if (!error_) error_.emplace(foundation::Error{
      foundation::ErrorCode::unsupported_audio, std::string{message}});
}

void WavMetadataInspector::end_payload() {
  stage_ = needs_padding_ ? Stage::padding : Stage::chunk_header;
  if (needs_padding_ && received_bytes_ == byte_length_) {
    reject("WAV odd-sized chunk is missing padding");
  }
}

foundation::Result<void> WavMetadataInspector::feed(std::span<const std::byte> bytes) {
  using Result = foundation::Result<void>;
  if (error_) return Result::failure(*error_);
  if (bytes.size() > byte_length_ - received_bytes_) {
    reject("WAV stream exceeds declared file length");
    return Result::failure(*error_);
  }
  std::size_t cursor = 0;
  while (cursor < bytes.size() && !error_) {
    if (stage_ == Stage::payload) {
      const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(
          payload_remaining_, bytes.size() - cursor));
      cursor += count;
      received_bytes_ += count;
      payload_remaining_ -= count;
      if (payload_remaining_ == 0) end_payload();
      continue;
    }
    if (stage_ == Stage::padding) {
      ++cursor;
      ++received_bytes_;
      stage_ = Stage::chunk_header;
      continue;
    }
    if (stage_ == Stage::chunk_header && header_bytes_ == 0 &&
        byte_length_ - received_bytes_ < 8) {
      reject("WAV chunk header exceeds file length");
      break;
    }
    const std::size_t needed = stage_ == Stage::riff ? 12 : stage_ == Stage::format ? 16 : 8;
    const auto count = std::min(needed - header_bytes_, bytes.size() - cursor);
    std::copy_n(bytes.data() + cursor, count, header_.data() + header_bytes_);
    cursor += count;
    received_bytes_ += count;
    header_bytes_ += count;
    if (header_bytes_ != needed) continue;
    header_bytes_ = 0;
    if (stage_ == Stage::riff) {
      if (!fourcc(header_, "RIFF") || !fourcc(std::span{header_}.subspan(8), "WAVE")) {
        reject("audio is not a RIFF/WAVE file");
      } else if (static_cast<std::uint64_t>(u32(header_, 4)) + 8 != byte_length_) {
        reject("RIFF chunk size does not match file length");
      } else {
        stage_ = Stage::chunk_header;
      }
      continue;
    }
    if (stage_ == Stage::format) {
      audio_format_ = u16(header_, 0);
      channels_ = u16(header_, 2);
      sample_rate_ = u32(header_, 4);
      byte_rate_ = u32(header_, 8);
      block_align_ = u16(header_, 12);
      bits_per_sample_ = u16(header_, 14);
      stage_ = Stage::chunk_header;
      continue;
    }
    const auto chunk_bytes = static_cast<std::uint64_t>(u32(header_, 4));
    if (chunk_bytes > byte_length_ - received_bytes_) {
      reject("WAV chunk exceeds file length");
      continue;
    }
    needs_padding_ = (chunk_bytes & 1U) != 0;
    if (fourcc(header_, "fmt ")) {
      if (have_fmt_ || chunk_bytes != 16) {
        reject("WAV must contain one PCM fmt chunk");
      } else {
        have_fmt_ = true;
        stage_ = Stage::format;
      }
    } else {
      if (fourcc(header_, "data")) {
        if (have_data_) {
          reject("WAV must contain one data chunk");
          continue;
        }
        have_data_ = true;
        data_bytes_ = chunk_bytes;
      }
      payload_remaining_ = chunk_bytes;
      stage_ = Stage::payload;
      if (payload_remaining_ == 0) end_payload();
    }
  }
  return error_ ? Result::failure(*error_) : Result::success();
}

foundation::Result<WavMetadata> WavMetadataInspector::finish() {
  using Result = foundation::Result<WavMetadata>;
  const auto fail = [this](std::string_view message) {
    reject(message);
    return Result::failure(*error_);
  };
  if (error_) return Result::failure(*error_);
  if (received_bytes_ != byte_length_) return fail("WAV stream ended before file length");
  if (stage_ != Stage::chunk_header || header_bytes_ != 0 || !have_fmt_ || !have_data_) {
    return fail("WAV must contain one fmt and one data chunk");
  }
  if (audio_format_ != 1 || (channels_ != 1 && channels_ != 2) ||
      (sample_rate_ != 44'100 && sample_rate_ != 48'000) || bits_per_sample_ != 16 ||
      block_align_ != channels_ * 2U || byte_rate_ != sample_rate_ * static_cast<std::uint32_t>(block_align_)) {
    return fail("WAV encoding must be 44.1 or 48 kHz PCM16 mono or stereo");
  }
  if (data_bytes_ == 0 || data_bytes_ % block_align_ != 0) {
    return fail("WAV data is not aligned to complete frames");
  }
  return Result::success(WavMetadata{sample_rate_, channels_, data_bytes_ / block_align_});
}

}  // namespace lmdj::cooker
