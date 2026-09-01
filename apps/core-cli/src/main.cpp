#include <algorithm>
#include <array>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include <lmdj/facade/application.hpp>
#include <lmdj/facade/assembly_loader.hpp>

#if defined(__APPLE__) || defined(__linux__)
#define LMDJ_CLI_HAS_POSIX_REQUEST_FILES 1
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#else
#define LMDJ_CLI_HAS_POSIX_REQUEST_FILES 0
#endif

namespace {

constexpr std::size_t kMaximumRequestBytes = 16U * 1024U * 1024U;
constexpr int kMaximumJsonContainerDepth = 64;
constexpr std::string_view kUsage =
    "usage: lmdj-core --workspace WORKSPACE "
    "[--assembly ASSEMBLY] "
    "(command|query) (--request JSON|--request-file FILE)\n";
constexpr std::string_view kInternalErrorFallback =
    "{\"error\":{\"code\":\"INTERNAL_ERROR\",\"details\":{},"
    "\"message\":\"unexpected CLI Host failure\"},\"ok\":false}\n";

enum class Mode {
  command,
  query,
};

struct Invocation {
  std::string_view workspace;
  std::optional<std::string_view> assembly;
  Mode mode;
  bool request_file;
  std::string_view request_source;
};

#if LMDJ_CLI_HAS_POSIX_REQUEST_FILES
class OwnedDescriptor {
 public:
  explicit OwnedDescriptor(int value) : value_(value) {}
  ~OwnedDescriptor() {
    if (value_ >= 0) {
      ::close(value_);
    }
  }

  OwnedDescriptor(const OwnedDescriptor&) = delete;
  OwnedDescriptor& operator=(const OwnedDescriptor&) = delete;

  OwnedDescriptor(OwnedDescriptor&& other) noexcept
      : value_(std::exchange(other.value_, -1)) {}
  OwnedDescriptor& operator=(OwnedDescriptor&&) = delete;

  int get() const { return value_; }

 private:
  int value_;
};
#endif

bool valid_utf8(std::string_view value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const auto first = static_cast<unsigned char>(value[offset]);
    if (first <= 0x7fU) {
      ++offset;
      continue;
    }
    std::size_t length = 0;
    std::uint32_t code_point = 0;
    if (first >= 0xc2U && first <= 0xdfU) {
      length = 2;
      code_point = first & 0x1fU;
    } else if (first >= 0xe0U && first <= 0xefU) {
      length = 3;
      code_point = first & 0x0fU;
    } else if (first >= 0xf0U && first <= 0xf4U) {
      length = 4;
      code_point = first & 0x07U;
    } else {
      return false;
    }
    if (offset + length > value.size()) {
      return false;
    }
    for (std::size_t index = 1; index < length; ++index) {
      const auto byte =
          static_cast<unsigned char>(value[offset + index]);
      if ((byte & 0xc0U) != 0x80U) {
        return false;
      }
      code_point = (code_point << 6U) | (byte & 0x3fU);
    }
    if ((length == 3 && code_point < 0x800U) ||
        (length == 4 && code_point < 0x10000U) ||
        code_point > 0x10ffffU ||
        (code_point >= 0xd800U && code_point <= 0xdfffU)) {
      return false;
    }
    offset += length;
  }
  return true;
}

std::optional<nlohmann::json> parse_bounded_json(
    std::string_view bytes) {
  bool depth_exceeded = false;
  const auto callback = [&depth_exceeded](
                            int depth,
                            nlohmann::json::parse_event_t event,
                            nlohmann::json&) {
    const bool container_start =
        event == nlohmann::json::parse_event_t::object_start ||
        event == nlohmann::json::parse_event_t::array_start;
    if (container_start && depth >= kMaximumJsonContainerDepth) {
      depth_exceeded = true;
      return false;
    }
    return true;
  };
  auto value = nlohmann::json::parse(
      bytes.begin(), bytes.end(), callback, false);
  if (depth_exceeded || value.is_discarded()) {
    return std::nullopt;
  }
  return value;
}

std::optional<Invocation> parse_invocation(
    int argc,
    char** argv) {
  if ((argc != 6 && argc != 8) ||
      std::string_view(argv[1]) != "--workspace") {
    return std::nullopt;
  }
  int mode_index = 3;
  std::optional<std::string_view> assembly;
  if (argc == 8) {
    if (std::string_view(argv[3]) != "--assembly") {
      return std::nullopt;
    }
    assembly = std::string_view(argv[4]);
    mode_index = 5;
  }
  Mode mode;
  if (std::string_view(argv[mode_index]) == "command") {
    mode = Mode::command;
  } else if (std::string_view(argv[mode_index]) == "query") {
    mode = Mode::query;
  } else {
    return std::nullopt;
  }
  const auto request_flag = std::string_view(argv[mode_index + 1]);
  if (request_flag != "--request" &&
      request_flag != "--request-file") {
    return std::nullopt;
  }
  return Invocation{
      std::string_view(argv[2]),
      assembly,
      mode,
      request_flag == "--request-file",
      std::string_view(argv[mode_index + 2]),
  };
}

nlohmann::json error_response(
    std::string_view code,
    std::string_view message) {
  return {
      {"ok", false},
      {"error",
       {
           {"code", code},
           {"message", message},
           {"details", nlohmann::json::object()},
       }},
  };
}

nlohmann::json invalid_request_response() {
  return error_response(
      "INVALID_ARGUMENT",
      "request must be a UTF-8 JSON object no larger than 16777216 bytes");
}

nlohmann::json request_file_error_response() {
  return error_response(
      "IO_ERROR",
      "request file must be a readable regular file");
}

nlohmann::json internal_error_response() {
  return error_response(
      "INTERNAL_ERROR", "unexpected CLI Host failure");
}

std::optional<std::string> read_request_file(
    const std::filesystem::path& path,
    nlohmann::json* error) {
#if LMDJ_CLI_HAS_POSIX_REQUEST_FILES
  int descriptor = -1;
  do {
    descriptor =
        ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
  } while (descriptor < 0 && errno == EINTR);
  if (descriptor < 0) {
    *error = request_file_error_response();
    return std::nullopt;
  }
  OwnedDescriptor owned(descriptor);

  struct stat metadata {};
  int stat_result = -1;
  do {
    stat_result = ::fstat(owned.get(), &metadata);
  } while (stat_result != 0 && errno == EINTR);
  if (stat_result != 0 || !S_ISREG(metadata.st_mode)) {
    *error = request_file_error_response();
    return std::nullopt;
  }
  if (metadata.st_size < 0 ||
      static_cast<std::uintmax_t>(metadata.st_size) >
          kMaximumRequestBytes) {
    *error = invalid_request_response();
    return std::nullopt;
  }

  std::string bytes;
  std::array<char, 64U * 1024U> chunk{};
  while (true) {
    const auto remaining_with_sentinel =
        kMaximumRequestBytes - bytes.size() + 1U;
    const auto requested =
        std::min(chunk.size(), remaining_with_sentinel);
    ssize_t count = -1;
    do {
      count = ::read(owned.get(), chunk.data(), requested);
    } while (count < 0 && errno == EINTR);
    if (count < 0) {
      *error = request_file_error_response();
      return std::nullopt;
    }
    if (count == 0) {
      return bytes;
    }
    const auto received = static_cast<std::size_t>(count);
    if (received > kMaximumRequestBytes - bytes.size()) {
      *error = invalid_request_response();
      return std::nullopt;
    }
    bytes.append(chunk.data(), received);
  }
#else
  (void)path;
  *error = error_response(
      "IO_ERROR",
      "request-file input is unsupported on this platform");
  return std::nullopt;
#endif
}

std::optional<nlohmann::json> decode_request(
    const Invocation& invocation,
    nlohmann::json* error) {
  std::string owned;
  std::string_view bytes = invocation.request_source;
  if (invocation.request_file) {
    auto loaded = read_request_file(
        std::filesystem::path(invocation.request_source), error);
    if (!loaded.has_value()) {
      return std::nullopt;
    }
    owned = std::move(*loaded);
    bytes = owned;
  } else if (bytes.size() > kMaximumRequestBytes) {
    *error = invalid_request_response();
    return std::nullopt;
  }
  if (bytes.empty() || !valid_utf8(bytes)) {
    *error = invalid_request_response();
    return std::nullopt;
  }
  auto parsed = parse_bounded_json(bytes);
  if (!parsed.has_value() || !parsed->is_object()) {
    *error = invalid_request_response();
    return std::nullopt;
  }
  return std::move(*parsed);
}

bool valid_workspace(
    std::string_view value,
    std::filesystem::path* path) {
  if (value.empty() || !valid_utf8(value)) {
    return false;
  }
  *path = std::filesystem::path(value);
  return path->is_absolute() && path->lexically_normal() == *path;
}

int write_response(const nlohmann::json& response) {
  const auto encoded = response.dump();
  std::cout.write(
      encoded.data(), static_cast<std::streamsize>(encoded.size()));
  std::cout.put('\n');
  std::cout.flush();
  if (!std::cout) {
    return 2;
  }
  const auto ok = response.find("ok");
  return ok != response.end() && ok->is_boolean() &&
                 ok->template get<bool>()
             ? 0
             : 2;
}

int run(const Invocation& invocation) {
  std::filesystem::path workspace;
  if (!valid_workspace(invocation.workspace, &workspace)) {
    return write_response(
        error_response(
            "INVALID_ARGUMENT",
            "workspace must be non-empty UTF-8, absolute, and normalized"));
  }
  nlohmann::json host_error;
  auto request = decode_request(invocation, &host_error);
  if (!request.has_value()) {
    return write_response(host_error);
  }
  auto providers = std::make_shared<lmdj::provider::Registry>();
  lmdj::provider::ProviderPolicy provider_policy;
  if (invocation.assembly.has_value()) {
    std::filesystem::path assembly;
    if (!valid_workspace(*invocation.assembly, &assembly)) {
      return write_response(
          error_response(
              "INVALID_ARGUMENT",
              "assembly must be non-empty UTF-8, absolute, and normalized"));
    }
    auto loaded = lmdj::facade::load_installed_assembly(assembly);
    if (!loaded.has_value()) {
      return write_response(
          error_response(
              "INVALID_ARGUMENT",
              "assembly validation or composition failed"));
    }
    providers = std::move(loaded.value().providers);
    provider_policy = std::move(loaded.value().provider_policy);
  }
  lmdj::facade::Application application(
      lmdj::facade::ApplicationConfig{
          std::move(workspace),
          std::move(providers),
          std::move(provider_policy),
          {},
          std::nullopt,
          nullptr,
          nullptr,
          nullptr,
          nullptr,
          lmdj::facade::make_unavailable_performance_replay_controller(),
      });
  if (invocation.mode == Mode::command) {
    return write_response(application.command(*request));
  }
  return write_response(application.query(*request));
}

int write_fallback() noexcept {
  const auto written = std::fwrite(
      kInternalErrorFallback.data(),
      1,
      kInternalErrorFallback.size(),
      stdout);
  if (written != kInternalErrorFallback.size() ||
      std::fflush(stdout) != 0) {
    return 2;
  }
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
#if defined(SIGPIPE)
  (void)std::signal(SIGPIPE, SIG_IGN);
#endif
  const auto invocation = parse_invocation(argc, argv);
  if (!invocation.has_value()) {
    const auto written =
        std::fwrite(kUsage.data(), 1, kUsage.size(), stderr);
    if (written != kUsage.size()) {
      return 64;
    }
    return 64;
  }
  try {
    return run(*invocation);
  } catch (...) {
    try {
      return write_response(internal_error_response());
    } catch (...) {
      return write_fallback();
    }
  }
}
