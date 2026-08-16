#pragma once

#if defined(LMDJ_PROJECT_IO_TESTING) && LMDJ_PROJECT_IO_TESTING

#include <atomic>
#include <filesystem>

#include <lmdj/foundation/error.hpp>

namespace lmdj::project_io::testing {

enum class FaultPoint {
  artifact_temp_sync,
  artifact_publish,
  transaction_temp_sync,
  transaction_publish,
  checkpoint_temp_sync,
  checkpoint_publish,
  manifest_temp_sync,
  manifest_publish,
  active_journal_sync,
  active_journal_remove,
  active_directory_sync,
  sealed_directory_sync,
  sample_after_staging,
  sample_after_event_preparation,
  sample_after_artifact_creation,
  sample_after_manifest_preparation,
  sample_after_manifest_publication,
};

using FaultHook = foundation::Result<void> (*)(
    FaultPoint,
    const std::filesystem::path&);

namespace detail {

inline std::atomic<FaultHook> fault_hook{nullptr};

inline foundation::Result<void> invoke_fault(
    FaultPoint point,
    const std::filesystem::path& path) {
  const auto hook = fault_hook.load(std::memory_order_acquire);
  return hook == nullptr ? foundation::Result<void>::success()
                         : hook(point, path);
}

}  // namespace detail

inline void set_fault_hook(FaultHook hook) {
  detail::fault_hook.store(hook, std::memory_order_release);
}

}  // namespace lmdj::project_io::testing

#endif
