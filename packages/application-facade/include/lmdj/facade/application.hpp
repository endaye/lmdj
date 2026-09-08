#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include <lmdj/audio/runtime_preparation_limits.hpp>
#include <lmdj/cooker/runtime_snapshot.hpp>
#include <lmdj/cooker/sample_analysis.hpp>
#include <lmdj/domain/command_handler.hpp>
#include <lmdj/facade/performance_replay.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/soundset_catalog_transport.hpp>
#include <lmdj/project_io/soundset_store.hpp>
#include <lmdj/provider/attempt_store.hpp>
#include <lmdj/provider/registry.hpp>

namespace lmdj::project_io {
class ProjectStoragePlatform;
}

namespace lmdj::facade {

class PerformanceClock {
public:
  virtual ~PerformanceClock() = default;
  // Authoritative musical time: 3840 ticks/bar in 4/4. Values are monotone
  // non-decreasing. A successful admission consumes exactly one read.
  virtual void anchor(std::uint16_t bpm, std::uint64_t at_tick) = 0;
  virtual foundation::Result<std::uint64_t> read_tick() = 0;
};

class PerformanceInputSequencer {
public:
  virtual ~PerformanceInputSequencer() = default;
  // Authoritative admission order. A successful admission consumes exactly
  // one sequence and replayed receipts consume none.
  virtual void seed(std::uint64_t last_input_sequence) = 0;
  virtual foundation::Result<std::uint64_t> next() = 0;
};

struct PatternLaunchReservation {
  std::uint64_t target_tick{};
  bool claimed{};
};

enum class PatternLaunchOutcomeKind : std::uint8_t {
  applied,
  cancelled,
  failed,
};

struct PatternLaunchOutcome {
  foundation::SequenceSessionId session_id;
  foundation::CommandId request_id;
  std::uint8_t pattern_slot{};
  std::uint64_t effective_tick{};
  PatternLaunchOutcomeKind kind{PatternLaunchOutcomeKind::failed};
};

class PatternLaunchAcknowledger {
public:
  virtual ~PatternLaunchAcknowledger() = default;
  // Core Runtime owns musical-boundary ordering and exactly-once outcomes.
  // The resolved material is immutable Core truth; Hosts never resolve slots.
  virtual foundation::Result<PatternLaunchReservation>
  reserve(const foundation::SequenceSessionId &session_id,
          const foundation::CommandId &request_id, std::uint8_t pattern_slot,
          std::uint64_t earliest_target_tick,
          std::shared_ptr<const cooker::RuntimeSnapshot> resolved_pattern) = 0;
  virtual std::vector<PatternLaunchOutcome>
  peek(const foundation::SequenceSessionId &session_id) = 0;
  virtual foundation::Result<void>
  commit(const foundation::SequenceSessionId &session_id,
         const foundation::CommandId &request_id) = 0;
  virtual void
  cancel(const foundation::SequenceSessionId &session_id) noexcept = 0;
};

// Live application of an admitted Performance FX or HOLD gesture to the
// running master bus (P10-D7: live and Replay drive the same DSP). Core owns
// the translation, so no Host decides FX chain order, value scale or
// coalescing. The sink is absent when no engine is attached; admission then
// journals the event and changes no audio.
class PerformanceGestureSink {
public:
  virtual ~PerformanceGestureSink() = default;
  virtual foundation::Result<void> apply_gesture(audio::FxGesture gesture) = 0;
};

// S11-D6: the Catalog index itself. A `CatalogTransport` resolves exactly
// `{object_kind, sha256}`, so it can never name the index; the Host that owns
// the Catalog endpoint owns fetching it and hands Core the bytes. A local
// directory, an OPFS cache and a network endpoint are three implementations of
// this one read, and Core keeps every Contract, hash and eligibility check.
class SoundSetCatalogSource {
public:
  virtual ~SoundSetCatalogSource() = default;

  SoundSetCatalogSource(const SoundSetCatalogSource &) = delete;
  SoundSetCatalogSource &operator=(const SoundSetCatalogSource &) = delete;
  SoundSetCatalogSource(SoundSetCatalogSource &&) = delete;
  SoundSetCatalogSource &operator=(SoundSetCatalogSource &&) = delete;

  // The current `lmdj.soundset-catalog.v1` index, never longer than
  // `maximum_bytes`. An unreachable Catalog fails with `IO_ERROR` and
  // `details.reason = catalog_unavailable`, which is never fatal: every Set
  // already published in the Workspace Set Store stays listable, inspectable
  // and installable (S11-D7).
  virtual foundation::Result<std::vector<std::byte>>
  read_index(std::uint64_t maximum_bytes) = 0;

protected:
  SoundSetCatalogSource() = default;
};

// The Workspace-local Catalog every Host wires in v1: a directory of
// content-addressed objects and the `lmdj.soundset-catalog.v1` index beside
// it, both under the Workspace the Host already owns. Core ships no network
// code, so a network Catalog is a Host-side `CatalogTransport` that replaces
// `transport` while `source` keeps supplying the index.
struct LocalSoundSetCatalog {
  std::shared_ptr<project_io::CatalogTransport> transport;
  std::shared_ptr<SoundSetCatalogSource> source;
};

// `workspace_root/.lmdj-host/soundset-catalog/{index.json,objects/<sha256>}`.
// Neither the index nor the object directory needs to exist: a Workspace with
// no Catalog reads as an unreachable Catalog, which S11-D7 makes non-fatal.
LocalSoundSetCatalog make_workspace_soundset_catalog(
    const std::filesystem::path &workspace_root);

// The Catalog for a Host that resolves the objects itself -- a browser `fetch`
// against a Host-configured endpoint, say. Core still ships no network code
// and still owns every Contract, hash and eligibility decision; the Host only
// moves bytes in.
//
// This is the whole of the Host-facing surface, and it is deliberately
// narrower than `CatalogTransport`: an object is named by its kind and its
// lowercase sha256 and by nothing else, so a Host cannot widen the S11-D6
// transport surface, and a Host never spells a `project_io` type to use it.
class SuppliedSoundSetCatalog {
public:
  // One address Core asked for and the Host has not supplied.
  struct PendingObject {
    // Exactly `"manifest"` or `"blob"`.
    std::string object_kind;
    std::string sha256;
  };

  struct PendingReads {
    // Core asked for the Catalog index and it was not supplied.
    bool index = false;
    // The object addresses, in the order Core asked for them, each once.
    std::vector<PendingObject> objects;
  };

  virtual ~SuppliedSoundSetCatalog() = default;

  SuppliedSoundSetCatalog(const SuppliedSoundSetCatalog &) = delete;
  SuppliedSoundSetCatalog &operator=(const SuppliedSoundSetCatalog &) = delete;
  SuppliedSoundSetCatalog(SuppliedSoundSetCatalog &&) = delete;
  SuppliedSoundSetCatalog &operator=(SuppliedSoundSetCatalog &&) = delete;

  // Supply one object. `object_kind` is `"manifest"` or `"blob"` and `sha256`
  // is 64 lowercase hex characters; anything else is refused without staging.
  // An object larger than one Host message arrives in order as a run of calls
  // carrying the same address and rising `offset`, and becomes readable only
  // once `byte_length` bytes have arrived; there is at most one incomplete
  // object at a time. Returns whether the object is now complete.
  //
  // The bytes are not hash-checked on the way in, because a Catalog that
  // answered with the wrong bytes must reach Core as
  // `soundset_content_mismatch` rather than disappear into a retry.
  virtual foundation::Result<bool> supply(
      std::string_view object_kind,
      std::string_view sha256,
      std::uint64_t offset,
      std::uint64_t byte_length,
      std::span<const std::byte> bytes) = 0;

  // Replace the supplied `lmdj.soundset-catalog.v1` index.
  virtual foundation::Result<void> supply_index(
      std::span<const std::byte> bytes) = 0;

  // Forget it. A Host whose own Catalog read failed calls this so that an
  // earlier pass's index cannot report a Catalog that is no longer reachable.
  virtual void forget_index() = 0;

  // Read and clear what Core asked for and could not be served, so one drain
  // reports the whole of the last pass and never repeats it.
  virtual PendingReads drain_pending() = 0;

  // Drop every supplied object. The Set Store owns what it published; this is
  // only the crossing point.
  virtual void clear_staged() = 0;

protected:
  SuppliedSoundSetCatalog() = default;
};

// The same object in its three roles: Core's transport, Core's index source,
// and the Host's control surface.
struct SuppliedSoundSetCatalogHandle {
  std::shared_ptr<project_io::CatalogTransport> transport;
  std::shared_ptr<SoundSetCatalogSource> source;
  std::shared_ptr<SuppliedSoundSetCatalog> control;
};

// `maximum_staged_bytes` bounds everything the Host has supplied and Core has
// not yet published, and `maximum_staged_objects` bounds how many addresses
// that may span. Both are Host capacity decided before an allocation: a
// supply that would cross either bound is refused whole and stages nothing.
SuppliedSoundSetCatalogHandle make_supplied_soundset_catalog(
    std::uint64_t maximum_staged_bytes,
    std::size_t maximum_staged_objects);

// Hosts configure the Set Store through the Facade, so the limit type is
// named here too: a Host that reached for `project_io::SoundSetStoreLimits`
// would be using Project I/O directly, which the Host source boundary forbids.
using SoundSetStoreLimits = project_io::SoundSetStoreLimits;

struct ApplicationConfig {
  std::filesystem::path workspace_root;
  std::shared_ptr<provider::Registry> providers;
  provider::ProviderPolicy provider_policy;
  provider::TimestampSource timestamp_source;
  std::optional<audio::RuntimePreparationLimits> runtime_preparation_limits =
      std::nullopt;
  std::shared_ptr<project_io::ProjectStoragePlatform> storage_platform =
      nullptr;
  std::shared_ptr<PerformanceClock> performance_clock = nullptr;
  std::shared_ptr<PerformanceInputSequencer> performance_input_sequencer =
      nullptr;
  std::shared_ptr<PatternLaunchAcknowledger> pattern_launch_acknowledger =
      nullptr;
  std::shared_ptr<PerformanceReplayController> performance_replay_controller;
  std::shared_ptr<PerformanceGestureSink> performance_gesture_sink = nullptr;
  // Sound Set members are appended, never inserted. Every brace
  // initialisation of this struct in the repository is positional, and each
  // trailing member is a `shared_ptr` or an `optional`, so an insertion in the
  // middle would silently rebind Hosts' collaborators by type instead of
  // failing to compile.
  std::shared_ptr<project_io::CatalogTransport> soundset_catalog_transport =
      nullptr;
  std::shared_ptr<SoundSetCatalogSource> soundset_catalog_source = nullptr;
  std::optional<project_io::SoundSetStoreLimits> soundset_store_limits =
      std::nullopt;
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
  std::optional<foundation::SequenceSessionId> sequence_session_id;

  SampleImportBeginRequest(
      std::string import_token_value,
      std::filesystem::path project_path_value,
      domain::CommandMeta meta_value,
      domain::PadSlotId slot_value,
      foundation::AssetId asset_id_value,
      std::uint64_t byte_length_value,
      std::optional<foundation::SequenceSessionId> sequence_session_id_value =
          std::nullopt)
      : import_token(std::move(import_token_value)),
        project_path(std::move(project_path_value)),
        meta(std::move(meta_value)),
        slot(slot_value),
        asset_id(std::move(asset_id_value)),
        byte_length(byte_length_value),
        sequence_session_id(std::move(sequence_session_id_value)) {}
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
  std::optional<domain::PadSlotId> armed_capture_slot;

  SequenceBeginRequest(
      std::filesystem::path project_path_value,
      foundation::SequenceSessionId session_id_value,
      foundation::PatternId pattern_id_value,
      std::uint64_t expected_revision_value,
      std::uint64_t runtime_frame_value,
      std::optional<domain::PadSlotId> armed_capture_slot_value = std::nullopt)
      : project_path(std::move(project_path_value)),
        session_id(std::move(session_id_value)),
        pattern_id(std::move(pattern_id_value)),
        expected_revision(expected_revision_value),
        runtime_frame(runtime_frame_value),
        armed_capture_slot(armed_capture_slot_value) {}
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

struct SequenceCaptureDisarmRequest {
  std::filesystem::path project_path;
  foundation::SequenceSessionId session_id;
  domain::PadSlotId slot;
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

  foundation::Result<void> service_performance();
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
  foundation::Result<void> disarm_sequence_capture(
      const SequenceCaptureDisarmRequest& request);
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
