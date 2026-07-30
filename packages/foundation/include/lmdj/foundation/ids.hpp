#pragma once

#include <compare>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>

namespace lmdj::foundation {

template <typename Tag>
class StrongId {
 public:
  explicit StrongId(std::string value) : value_(std::move(value)) {}

  const std::string& value() const noexcept { return value_; }

  auto operator<=>(const StrongId&) const = default;

 private:
  std::string value_;
};

template <typename Tag>
void to_json(nlohmann::json& output, const StrongId<Tag>& id) {
  output = id.value();
}

template <typename Tag>
void from_json(const nlohmann::json& input, StrongId<Tag>& id) {
  id = StrongId<Tag>(input.get<std::string>());
}

struct ProjectIdTag;
struct CommandIdTag;
struct AssetIdTag;
struct PatternIdTag;
struct TakeIdTag;
struct AttemptIdTag;
struct CandidateIdTag;

using ProjectId = StrongId<ProjectIdTag>;
using CommandId = StrongId<CommandIdTag>;
using AssetId = StrongId<AssetIdTag>;
using PatternId = StrongId<PatternIdTag>;
using TakeId = StrongId<TakeIdTag>;
using AttemptId = StrongId<AttemptIdTag>;
using CandidateId = StrongId<CandidateIdTag>;

}  // namespace lmdj::foundation
