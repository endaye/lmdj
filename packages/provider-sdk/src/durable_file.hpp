#pragma once

#include <filesystem>
#include <string_view>

#include <lmdj/foundation/error.hpp>

namespace lmdj::provider::detail {

foundation::Result<void> sync_descriptor(
    int descriptor,
    const std::filesystem::path& path);

foundation::Result<void> sync_directory(
    const std::filesystem::path& path);

foundation::Result<void> write_bytes_durable(
    const std::filesystem::path& path,
    std::string_view bytes);

foundation::Result<void> publish_new_link(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path,
    foundation::ErrorCode existing_code);

foundation::Result<void> publish_replace(
    const std::filesystem::path& temp_path,
    const std::filesystem::path& final_path);

}  // namespace lmdj::provider::detail
