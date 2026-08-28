#pragma once

#include <string>
#include <string_view>
#include <utility>
#include <variant>

#include <nlohmann/json.hpp>

namespace lmdj::foundation {

enum class ErrorCode {
  invalid_argument,
  not_found,
  revision_conflict,
  duplicate_id,
  unsupported_audio,
  missing_asset,
  invalid_project,
  cook_failed,
  bank_quota_exhausted,
  project_quota_exhausted,
  provider_not_found,
  provider_failed,
  permission_denied,
  io_error,
  internal_error,
};

constexpr std::string_view error_code_name(ErrorCode code) {
  switch (code) {
    case ErrorCode::invalid_argument:
      return "INVALID_ARGUMENT";
    case ErrorCode::not_found:
      return "NOT_FOUND";
    case ErrorCode::revision_conflict:
      return "REVISION_CONFLICT";
    case ErrorCode::duplicate_id:
      return "DUPLICATE_ID";
    case ErrorCode::unsupported_audio:
      return "UNSUPPORTED_AUDIO";
    case ErrorCode::missing_asset:
      return "MISSING_ASSET";
    case ErrorCode::invalid_project:
      return "INVALID_PROJECT";
    case ErrorCode::cook_failed:
      return "COOK_FAILED";
    case ErrorCode::bank_quota_exhausted:
      return "BANK_QUOTA_EXHAUSTED";
    case ErrorCode::project_quota_exhausted:
      return "PROJECT_QUOTA_EXHAUSTED";
    case ErrorCode::provider_not_found:
      return "PROVIDER_NOT_FOUND";
    case ErrorCode::provider_failed:
      return "PROVIDER_FAILED";
    case ErrorCode::permission_denied:
      return "PERMISSION_DENIED";
    case ErrorCode::io_error:
      return "IO_ERROR";
    case ErrorCode::internal_error:
      return "INTERNAL_ERROR";
  }
  return "INTERNAL_ERROR";
}

struct Error {
  ErrorCode code;
  std::string message;
  nlohmann::json details = nlohmann::json::object();
};

template <typename T>
class Result {
 public:
  static Result success(T value) {
    return Result(std::move(value));
  }

  static Result failure(Error error) {
    return Result(std::move(error));
  }

  bool has_value() const noexcept {
    return std::holds_alternative<T>(storage_);
  }

  const T& value() const { return std::get<T>(storage_); }
  T& value() { return std::get<T>(storage_); }
  const Error& error() const { return std::get<Error>(storage_); }

 private:
  explicit Result(T value) : storage_(std::move(value)) {}
  explicit Result(Error error) : storage_(std::move(error)) {}

  std::variant<T, Error> storage_;
};

template <>
class Result<void> {
 public:
  static Result success() { return Result(std::monostate{}); }

  static Result failure(Error error) {
    return Result(std::move(error));
  }

  bool has_value() const noexcept {
    return std::holds_alternative<std::monostate>(storage_);
  }

  const Error& error() const { return std::get<Error>(storage_); }

 private:
  explicit Result(std::monostate value) : storage_(value) {}
  explicit Result(Error error) : storage_(std::move(error)) {}

  std::variant<std::monostate, Error> storage_;
};

}  // namespace lmdj::foundation
