#include <lmdj/domain/project.hpp>

#include <string>

namespace lmdj::domain {

foundation::Result<nlohmann::json> migrate_project_v3_to_v4(
    const nlohmann::json& project_v3) {
  if (!project_v3.is_object() || !project_v3.contains("contract") ||
      !project_v3.at("contract").is_string() ||
      project_v3.at("contract") != "lmdj.project.v3") {
    return foundation::Result<nlohmann::json>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_project,
            "v3 to v4 migration requires a v3-declared Project",
        });
  }
  if (project_v3.contains("performances") ||
      project_v3.contains("pattern_slots")) {
    return foundation::Result<nlohmann::json>::failure(
        foundation::Error{
            foundation::ErrorCode::invalid_project,
            "a v3-declared Project must not carry v4 fields",
        });
  }

  auto project_v4 = project_v3;
  project_v4["contract"] = "lmdj.project.v4";
  project_v4["pattern_slots"] = nlohmann::json::array();
  for (std::size_t slot = 0; slot < kPatternSlotCount; ++slot) {
    project_v4["pattern_slots"].push_back(nullptr);
  }
  project_v4["performances"] = nlohmann::json::array();
  return foundation::Result<nlohmann::json>::success(std::move(project_v4));
}

}  // namespace lmdj::domain
