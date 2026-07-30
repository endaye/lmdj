#include <lmdj/foundation/artifact.hpp>

#include <array>
#include <fstream>
#include <limits>
#include <system_error>
#include <utility>

#include <picosha2.h>

namespace lmdj::foundation {

void to_json(nlohmann::json& output, const ArtifactRef& artifact) {
  output = {
      {"sha256", artifact.sha256},
      {"media_type", artifact.media_type},
      {"byte_length", artifact.byte_length},
  };
}

void from_json(const nlohmann::json& input, ArtifactRef& artifact) {
  input.at("sha256").get_to(artifact.sha256);
  input.at("media_type").get_to(artifact.media_type);
  input.at("byte_length").get_to(artifact.byte_length);
}

Result<ArtifactRef> describe_artifact(
    const std::filesystem::path& path,
    std::string media_type) {
  std::error_code status_error;
  if (!std::filesystem::is_regular_file(path, status_error)) {
    return Result<ArtifactRef>::failure(
        Error{
            ErrorCode::not_found,
            "artifact path is not a regular file",
            {{"path", path.generic_string()}},
        });
  }

  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    return Result<ArtifactRef>::failure(
        Error{
            ErrorCode::io_error,
            "artifact file could not be opened",
            {{"path", path.generic_string()}},
        });
  }

  picosha2::hash256_one_by_one hasher;
  std::array<unsigned char, 64U * 1024U> buffer{};
  std::uint64_t byte_length = 0;

  while (stream) {
    stream.read(
        reinterpret_cast<char*>(buffer.data()),
        static_cast<std::streamsize>(buffer.size()));
    const auto count = stream.gcount();
    if (count <= 0) {
      continue;
    }
    const auto chunk_size = static_cast<std::uint64_t>(count);
    if (byte_length >
        std::numeric_limits<std::uint64_t>::max() - chunk_size) {
      return Result<ArtifactRef>::failure(
          Error{
              ErrorCode::io_error,
              "artifact byte length overflowed",
              {{"path", path.generic_string()}},
          });
    }
    hasher.process(buffer.begin(), buffer.begin() + count);
    byte_length += chunk_size;
  }

  if (!stream.eof()) {
    return Result<ArtifactRef>::failure(
        Error{
            ErrorCode::io_error,
            "artifact file could not be read completely",
            {{"path", path.generic_string()}},
        });
  }

  hasher.finish();
  return Result<ArtifactRef>::success(
      ArtifactRef{
          picosha2::get_hash_hex_string(hasher),
          std::move(media_type),
          byte_length,
      });
}

}  // namespace lmdj::foundation
