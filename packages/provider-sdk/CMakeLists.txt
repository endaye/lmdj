find_package(Threads REQUIRED)

add_library(
  lmdj_provider_sdk
  STATIC
    src/provider.cpp
    src/capability.cpp
    src/registry.cpp
    src/attempt_store.cpp
    src/durable_file.cpp
)
add_library(lmdj::provider_sdk ALIAS lmdj_provider_sdk)

target_include_directories(
  lmdj_provider_sdk
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_provider_sdk
  PUBLIC
    lmdj::foundation
  PRIVATE
    lmdj_picosha2
    Threads::Threads
)
lmdj_target_warnings(lmdj_provider_sdk)
lmdj_target_sanitizers(lmdj_provider_sdk)
