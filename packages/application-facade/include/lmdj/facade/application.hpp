#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/domain/command_handler.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::project_io {
class ProjectStoragePlatform;
}

namespace lmdj::facade {

struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource timestamp_source;
  std::optional<audio::RuntimePreparationLimits> runtime_preparation_limits =
      std::nullopt;
  std::shared_ptr<project_io::ProjectStoragePlatform> storage_platform =
      nullptr;
};

struct RuntimeSnapshotRequest {
  std::filesystem::path project_path;
  foundation::PatternId pattern_id;
  std::optional<audio::RuntimePreparationLimits> limits = std::nullopt;
};

struct InitialProjectRequest {
  std::filesystem::path project_path;
  foundation::ProjectId project_id;
  std::uint16_t bpm;
  domain::Pattern initial_pattern;
};

class RuntimeProjectWriterLease final {
 public:
  ~RuntimeProjectWriterLease();
  RuntimeProjectWriterLease(RuntimeProjectWriterLease&&) noexcept;
  RuntimeProjectWriterLease& operator=(
      RuntimeProjectWriterLease&&) noexcept;

  RuntimeProjectWriterLease(const RuntimeProjectWriterLease&) = delete;
  RuntimeProjectWriterLease& operator=(
      const RuntimeProjectWriterLease&) = delete;

 private:
  struct Impl;
  explicit RuntimeProjectWriterLease(std::unique_ptr<Impl> impl);

  std::unique_ptr<Impl> impl_;
  friend class Application;
};

struct ArtifactBytesImportRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  foundation::AssetId asset_id;
  std::string media_type;
  std::span<const std::byte> bytes;
};

struct ProjectBundleImportBeginRequest {
  std::string import_token;
  std::uint64_t index_bytes;
  std::string index_sha256;
};

struct LocalProjectSummary {
  foundation::ProjectId project_id;
  foundation::PatternId pattern_id;
  std::uint64_t revision;
  std::uint16_t bpm;
  std::size_t asset_count;
  std::size_t assigned_pad_count;
  std::string bundle_digest;
  friend bool operator==(const LocalProjectSummary&, const LocalProjectSummary&) =
      default;
};

struct ProjectBundleImportSession {
  std::string token;
  std::uint64_t expected_index_bytes;
};

struct ProjectBundleImportIdentity {
  foundation::ProjectId project_id;
  std::string bundle_digest;
  std::uint32_t entry_count;
};

struct SampleInspectRequest {
  std::filesystem::path project_path;
  domain::PadSlotId slot;
};

struct SampleInspectResult {
  std::uint64_t project_revision;
  domain::PadSlotId slot;
  std::optional<foundation::AssetId> asset_id;
  domain::PadPlayback playback;
  std::optional<cooker::WavMetadata> metadata;
  std::optional<std::string> waveform_cache_identity;
};

struct SampleWaveformRequest {
  std::filesystem::path project_path;
  domain::PadSlotId slot;
  cooker::WaveformRequest window;
};

struct SampleQuotaRequest {
  std::filesystem::path project_path;
  domain::PadSlotId slot;
};

struct SampleQuotaConsumed {
  domain::PadSlotId slot;
  std::uint64_t prepared_bytes;
  std::uint64_t prepared_frames;

  friend bool operator==(
      const SampleQuotaConsumed&,
      const SampleQuotaConsumed&) = default;
};

struct SampleQuotaResult {
  std::uint64_t project_revision;
  domain::PadSlotId slot;
  std::uint64_t bank_quota_bytes;
  std::uint64_t bank_used_bytes;
  std::uint64_t bank_remaining_bytes;
  std::uint64_t project_quota_bytes;
  std::uint64_t project_used_bytes;
  std::uint64_t project_remaining_bytes;
  std::uint64_t effective_remaining_bytes;
  std::uint64_t effective_remaining_frames;
  std::vector<SampleQuotaConsumed> consumed;
};

struct SampleMutationResult {
  std::uint64_t committed_revision;
  bool runtime_prepare_required;
};

struct SampleUpdateRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
  domain::PadPlayback playback;
};

struct SampleResetRequest {
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
};

struct SampleImportBeginRequest {
  std::string import_token;
  std::filesystem::path project_path;
  domain::CommandMeta meta;
  domain::PadSlotId slot;
  foundation::AssetId asset_id;
  std::uint64_t byte_length;
  std::optional<foundation::SequenceSessionId> sequence_session_id =
      std::nullopt;
};

struct SampleImportSession {
  std::string token;
  std::uint64_t expected_bytes;
};

enum class SequenceRecordState : std::uint8_t {
  inactive,
  active,
  switching,
  recoverable,
};

struct SequenceBeginRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint64_t expected_revision;
  std::uint64_t runtime_frame;
  std::optional<domain::PadSlotId> armed_capture_slot = std::nullopt;
};

struct SequencePadEvent {
  domain::PadSlotId slot;
  std::uint8_t velocity;
  std::uint64_t runtime_frame;
  std::uint64_t input_sequence;
  bool pressed;
};

struct SequenceEventRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  SequencePadEvent event;
};

struct SequenceFlushRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  foundation::CommandId command_id;
  std::uint64_t runtime_frame;
};

struct SequenceSwitchRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  foundation::PatternId next_pattern_id;
  std::optional<std::uint64_t> runtime_frame{};
};

struct SequenceStatusRequest {
  std::filesystem::path project_path;
};

struct SequenceOverlayRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
};

struct SequenceOverlayProjection {
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint64_t generation{};
  std::vector<domain::PatternEvent> events;

  bool operator==(const SequenceOverlayProjection&) const = default;
};

struct SequenceRecoveryRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  std::optional<foundation::PatternId> destination_pattern_id;
};

struct SequenceStatus {
  SequenceRecordState state{SequenceRecordState::inactive};
  std::optional<foundation::SequenceSessionId> session_id;
  std::optional<foundation::PatternId> pattern_id;
  std::optional<foundation::PatternId> pending_pattern_id;
  std::uint64_t expected_revision{};
  std::uint64_t next_flush_seq{};
  std::uint64_t pending_event_count{};
  std::optional<std::uint64_t> effective_runtime_frame;

  bool operator==(const SequenceStatus&) const = default;
};

struct SequenceMutationResult {
  SequenceStatus status;
  std::optional<std::uint64_t> committed_revision;
  bool replayed{};
  std::optional<foundation::PatternId> committed_pattern_id;
};

struct SequenceRecoveryInfo {
  foundation::SequenceSessionId session_id;
  foundation::PatternId pattern_id;
  std::uint8_t bars{};
  std::string reason;
  std::uint64_t event_count{};
};

class Application {
 public:
  explicit Application(ApplicationConfig config);
  ~Application();

  Application(const Application&) = delete;
  Application& operator=(const Application&) = delete;
  Application(Application&&) noexcept;
  Application& operator=(Application&&) noexcept;

  nlohmann::json command(const nlohmann::json& request);
  nlohmann::json query(const nlohmann::json& request) const;
  foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
  prepare_runtime_snapshot(const RuntimeSnapshotRequest& request);
  foundation::Result<RuntimeProjectWriterLease> acquire_project_writer(
      const std::filesystem::path& project_path);
  foundation::Result<domain::ProjectState> create_initial_project(
      const InitialProjectRequest& request);
  foundation::Result<domain::AppliedCommand> import_artifact_bytes(
      const ArtifactBytesImportRequest& request);
  foundation::Result<std::vector<LocalProjectSummary>> list_local_projects();
  foundation::Result<ProjectBundleImportSession>
  begin_project_bundle_import(
      const ProjectBundleImportBeginRequest& request);
  foundation::Result<std::optional<ProjectBundleImportIdentity>>
  append_project_bundle_index(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<void> append_project_bundle_entry(
      std::string_view token,
      std::uint32_t entry_index,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<LocalProjectSummary> commit_project_bundle_import(
      std::string_view token);
  foundation::Result<void> abort_project_bundle_import(
      std::string_view token);
  foundation::Result<SampleInspectResult> inspect_sample(
      const SampleInspectRequest& request) const;
  foundation::Result<cooker::WaveformEnvelope> query_sample_waveform(
      const SampleWaveformRequest& request);
  foundation::Result<SampleQuotaResult> query_sample_quota(
      const SampleQuotaRequest& request) const;
  foundation::Result<SampleImportSession> begin_sample_import(
      const SampleImportBeginRequest& request);
  foundation::Result<void> append_sample_import(
      std::string_view token,
      std::uint64_t offset,
      std::span<const std::byte> bytes,
      bool final);
  foundation::Result<SampleMutationResult> commit_sample_import(
      std::string_view token);
  foundation::Result<void> abort_sample_import(std::string_view token);
  foundation::Result<SampleMutationResult> update_sample_pad(
      const SampleUpdateRequest& request);
  foundation::Result<SampleMutationResult> reset_sample_pad(
      const SampleResetRequest& request);
  foundation::Result<SequenceMutationResult> begin_sequence(
      const SequenceBeginRequest& request);
  foundation::Result<SequenceMutationResult> record_sequence_event(
      const SequenceEventRequest& request);
  foundation::Result<SequenceMutationResult> flush_sequence(
      const SequenceFlushRequest& request);
  foundation::Result<SequenceMutationResult> stop_sequence(
      const SequenceFlushRequest& request);
  foundation::Result<SequenceMutationResult> request_sequence_switch(
      const SequenceSwitchRequest& request);
  void abandon_sequence_sessions() noexcept;
  foundation::Result<SequenceStatus> query_sequence_status(
      const SequenceStatusRequest& request) const;
  foundation::Result<SequenceOverlayProjection> query_sequence_overlay(
      const SequenceOverlayRequest& request) const;
  foundation::Result<std::vector<SequenceRecoveryInfo>>
  list_sequence_recovery(const SequenceStatusRequest& request) const;
  foundation::Result<SequenceMutationResult> apply_sequence_recovery(
      const SequenceRecoveryRequest& request);
  foundation::Result<void> discard_sequence_recovery(
      const SequenceRecoveryRequest& request);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace lmdj::facade
