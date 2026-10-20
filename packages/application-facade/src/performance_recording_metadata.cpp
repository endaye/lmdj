#include <lmdj/facade/performance_recording_metadata.hpp>

#include <optional>
#include <utility>

#include <lmdj/cooker/wav_metadata_inspector.hpp>
#include <lmdj/foundation/json.hpp>
#include <lmdj/project_io/project_store.hpp>

namespace lmdj::facade {
namespace {
using ReadResult = foundation::Result<PerformanceRecordingRead>;

ReadResult cancelled() {
  return ReadResult::success(PerformanceRecordingRead{PerformanceRecordingReadCancelled{}});
}
}  // namespace

struct PerformanceRecordingMetadataReader::Impl {
  explicit Impl(std::shared_ptr<project_io::ProjectStoragePlatform> platform)
      : projects(std::move(platform)) {}

  // Private read state: sharing the live AuthoringHistory here would hold its
  // mutex through the full hash and block Control mutations on the worker.
  // The scanner still checks the original committed revision/ref at the end.
  project_io::ProjectStore projects;
};

PerformanceRecordingMetadataReader::PerformanceRecordingMetadataReader(
    std::shared_ptr<project_io::ProjectStoragePlatform> platform)
    : impl_(std::make_unique<Impl>(std::move(platform))) {}
PerformanceRecordingMetadataReader::~PerformanceRecordingMetadataReader() = default;
PerformanceRecordingMetadataReader::PerformanceRecordingMetadataReader(
    PerformanceRecordingMetadataReader&&) noexcept = default;
PerformanceRecordingMetadataReader& PerformanceRecordingMetadataReader::operator=(
    PerformanceRecordingMetadataReader&&) noexcept = default;

foundation::Result<PerformanceRecordingRead>
PerformanceRecordingMetadataReader::inspect(
    const PerformanceRecordingMetadataRequest& requested,
    std::stop_token stop) const {
  try {
    const auto request = requested;
    if (stop.stop_requested()) return cancelled();
    const auto path = request.project_path.generic_string();
    if (!request.project_path.is_absolute() ||
        request.project_path.lexically_normal() != request.project_path ||
        !foundation::valid_utf8(path) || path.find('\0') != std::string::npos) {
      return ReadResult::failure({foundation::ErrorCode::invalid_argument,
                                 "Recording metadata Project path is invalid"});
    }
    cooker::WavMetadataInspector parser{request.artifact.byte_length};
    std::optional<foundation::Error> format_error;
    const project_io::PerformanceRecordingSelector selector{
        request.project_id, request.performance_id, request.expected_revision, request.artifact};
    const auto verified = impl_->projects.scan_performance_recording(
        request.project_path, selector, [&](std::span<const std::byte> input) {
          if (stop.stop_requested()) {
            // Internal abort only. The stopped token below converts this into
            // the explicit cancellation variant; no new public error code.
            return foundation::Result<void>::failure({foundation::ErrorCode::internal_error,
                                                       "Recording metadata inspection cancelled"});
          }
          const auto fed = parser.feed(input);
          if (!fed.has_value() && !format_error) format_error = fed.error();
          // A provisional format error never short-circuits the complete hash.
          return foundation::Result<void>::success();
        });
    if (stop.stop_requested()) return cancelled();
    if (!verified.has_value()) return ReadResult::failure(verified.error());
    auto audio = format_error
        ? foundation::Result<cooker::WavMetadata>::failure(*format_error)
        : parser.finish();
    if (stop.stop_requested()) return cancelled();
    const auto& receipt = verified.value();
    return ReadResult::success(PerformanceRecordingRead{PerformanceRecordingMetadata{
        receipt.project_id, receipt.performance_id, receipt.project_revision,
        receipt.recording_revision, receipt.artifact, std::move(audio)}});
  } catch (...) {
    return ReadResult::failure({foundation::ErrorCode::internal_error,
                               "unexpected Application Facade Host API failure"});
  }
}

}  // namespace lmdj::facade
