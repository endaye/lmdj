#pragma once

#include <filesystem>
#include <initializer_list>
#include <string>
#include <system_error>
#include <vector>

#if defined(__unix__) || defined(__APPLE__)
#include <spawn.h>
extern char** environ;
#endif

namespace lmdj::test::process {

inline std::string executable;

inline void initialize(const char* argv0) {
  executable = std::filesystem::canonical(argv0).string();
}

// Launch a fresh process image. Darwin's libSystem child handlers can allocate
// before pthread_atfork unlocks the ASan stack depot, so even an immediate exec
// after a test-side fork would leave the original hazard in place.
#if defined(__unix__) || defined(__APPLE__)
inline pid_t spawn(std::initializer_list<std::string> arguments,
                   std::initializer_list<int> close_descriptors = {}) {
  std::vector<std::string> storage{executable};
  storage.insert(storage.end(), arguments.begin(), arguments.end());
  std::vector<char*> argv;
  for (auto& argument : storage) argv.push_back(argument.data());
  argv.push_back(nullptr);

  posix_spawn_file_actions_t actions;
  const auto initialized = posix_spawn_file_actions_init(&actions);
  if (initialized != 0)
    throw std::system_error(initialized, std::generic_category(), "spawn file actions");
  for (const auto descriptor : close_descriptors) {
    const auto added = posix_spawn_file_actions_addclose(&actions, descriptor);
    if (added != 0) {
      posix_spawn_file_actions_destroy(&actions);
      throw std::system_error(added, std::generic_category(), "spawn close action");
    }
  }
  pid_t child = -1;
  const auto result = posix_spawn(&child, executable.c_str(), &actions,
                                nullptr, argv.data(), environ);
  posix_spawn_file_actions_destroy(&actions);
  if (result != 0)
    throw std::system_error(result, std::generic_category(), "spawn test child");
  return child;
}
#endif

}  // namespace lmdj::test::process
