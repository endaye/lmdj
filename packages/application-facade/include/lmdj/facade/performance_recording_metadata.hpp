#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <stop_token>
#include <variant>

#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/domain/project.hpp>
#include <lmdj/foundation/artifact.hpp>
#include <lmdj/foundation/error.hpp>

namespace lmdj::project_io {
class ProjectStoragePlatform;
}

namespace lmdj::facade {

struct PerformanceRecordingMetadataRequest {
  std::filesystem::path project_path;
  foundation::ProjectId project_id;
  domain::PerformanceId performance_id;
  std::uint64_t expected_revision;
  foundation::ArtifactRef artifact;
};

struct PerformanceRecordingMetadata {
  foundation::ProjectId project_id;
  domain::PerformanceId performance_id;
  std::uint64_t project_revision;
  std::uint64_t recording_revision;
  foundation::ArtifactRef artifact;
  // The complete raw Artifact and owner are verified even when this reports
  // UNSUPPORTED_AUDIO. Outer failures carry storage/integrity/owner errors.
  foundation::Result<cooker::WavMetadata> audio;
};

struct PerformanceRecordingReadCancelled {};
using PerformanceRecordingRead = std::variant<
    PerformanceRecordingMetadata, PerformanceRecordingReadCancelled>;

// Created by Application without I/O; retains only its exact storage platform,
// not mutable Application/session/history state. An idle reader can transfer to
// a worker and outlive Application. One sequential caller owns the reader and
// retires each call's leases on that caller; never call from audio or run a long
// scan on serialized Control. Destroy only after inspect has actually returned.
class PerformanceRecordingMetadataReader final {
 public:
  ~PerformanceRecordingMetadataReader();
  PerformanceRecordingMetadataReader(PerformanceRecordingMetadataReader&&) noexcept;
  PerformanceRecordingMetadataReader& operator=(PerformanceRecordingMetadataReader&&) noexcept;
  PerformanceRecordingMetadataReader(const PerformanceRecordingMetadataReader&) = delete;
  PerformanceRecordingMetadataReader& operator=(const PerformanceRecordingMetadataReader&) = delete;

  // Snapshots the complete request. Cooperative cancellation is observed before
  // I/O, per bounded window and before publishing a verified result. It cannot
  // interrupt an in-flight platform call or revoke a returned value. Async
  // consumers must additionally retire stale owner/generation completions.
  // Existing public list/inspect represent no-WAV; this reads one bound ref.
  foundation::Result<PerformanceRecordingRead> inspect(
      const PerformanceRecordingMetadataRequest& request,
      std::stop_token stop = {}) const;

 private:
  struct Impl;
  explicit PerformanceRecordingMetadataReader(
      std::shared_ptr<project_io::ProjectStoragePlatform> platform);
  std::unique_ptr<Impl> impl_;
  friend class Application;
};

}  // namespace lmdj::facade
