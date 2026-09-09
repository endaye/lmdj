#pragma once

#include <filesystem>
#include <memory>
#include <mutex>
#include <string>

#include <nlohmann/json.hpp>
#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/provider/attempt_store.hpp>

namespace lmdj::facade::detail {

// Workspace-only, Facade-owned state. None of these records are Project Truth
// or SDK terminal records. All mutations use the same owner lease.
class CandidateStore {
 public:
  struct Lease {
    std::shared_ptr<std::mutex> mutex;
    std::unique_lock<std::mutex> lock;
    std::unique_ptr<project_io::ProjectWriterLease> writer;
  };
  struct Eligibility {
    Lease mutation;
    nlohmann::json candidate_set;
  };
  struct Run {
    Lease execution;
    std::string job_id;
    std::string attempt_id;
  };

  CandidateStore(std::filesystem::path workspace_root,
                 std::shared_ptr<project_io::ProjectStoragePlatform> platform);

  // Intent is derived by Facade from a checked Project binding, never accepted
  // as a caller-provided recipe. Own the Job lease until completion/unwind.
  foundation::Result<Run> begin(const std::string& job_id,
                                const nlohmann::json& intent);
  foundation::Result<nlohmann::json> finish(const Run& run,
                                           const provider::AttemptStore& attempts);
  foundation::Result<nlohmann::json> inspect(const std::string& job_id,
                                            const provider::AttemptStore& attempts);

  // Pure eligibility: retain ownership through Project commit; no recovery.
  foundation::Result<Eligibility> lease_active(const std::string& job_id,
      const std::string& set_id, const provider::AttemptStore& attempts);

 private:
  foundation::Result<Lease> acquire(const std::filesystem::path& path) const;
  foundation::Result<nlohmann::json> read_state() const;
  foundation::Result<void> write_state(const nlohmann::json& state);
  foundation::Result<void> reconcile(nlohmann::json& state,
                                     nlohmann::json& entry,
                                     const provider::AttemptStore& attempts);
  foundation::Result<void> verify_sets(const nlohmann::json& state,
                                        const std::string& job_id,
                                        const provider::AttemptStore& attempts) const;
  nlohmann::json view(const nlohmann::json& state,
                      const std::string& job_id) const;

  std::filesystem::path root_;
  std::shared_ptr<project_io::ProjectStoragePlatform> platform_;
};

}  // namespace lmdj::facade::detail
