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

}  // namespace lmdj::foundation

namespace nlohmann {

template <typename Tag>
struct adl_serializer<lmdj::foundation::StrongId<Tag>> {
  using Id = lmdj::foundation::StrongId<Tag>;

  static void to_json(json& output, const Id& id) {
    output = id.value();
  }

  static Id from_json(const json& input) {
    return Id(input.get<std::string>());
  }
};

}  // namespace nlohmann

namespace lmdj::foundation {

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
