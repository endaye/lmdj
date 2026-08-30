add_library(
  lmdj_application
  STATIC
    src/application.cpp
    src/assembly_loader.cpp
    src/mutation_publish_scope.cpp
)
add_library(lmdj::application ALIAS lmdj_application)

target_include_directories(
  lmdj_application
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/internal"
)
target_link_libraries(
  lmdj_application
  PUBLIC
    lmdj::authoring_domain
    lmdj::project_io
    lmdj::project_cooker
    lmdj::audio_runtime
    lmdj::provider_sdk
)
lmdj_target_warnings(lmdj_application)
lmdj_target_sanitizers(lmdj_application)

add_library(
  lmdj_core_c
  SHARED
    src/c_api.cpp
)
target_include_directories(
  lmdj_core_c
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_core_c
  PRIVATE
    lmdj::application
)
target_compile_definitions(lmdj_core_c PRIVATE LMDJ_CORE_C_BUILD=1)
set_target_properties(
  lmdj_core_c
  PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
if(APPLE)
  set(lmdj_core_c_export_file "${CMAKE_CURRENT_SOURCE_DIR}/exports_macos.txt")
  target_link_options(
    lmdj_core_c
    PRIVATE
      "-Wl,-exported_symbols_list,${lmdj_core_c_export_file}"
  )
  set_property(
    TARGET lmdj_core_c
    APPEND
    PROPERTY LINK_DEPENDS "${lmdj_core_c_export_file}"
  )
elseif(UNIX)
  set(lmdj_core_c_export_file "${CMAKE_CURRENT_SOURCE_DIR}/exports_elf.map")
  target_link_options(
    lmdj_core_c
    PRIVATE
      "-Wl,--version-script=${lmdj_core_c_export_file}"
  )
  set_property(
    TARGET lmdj_core_c
    APPEND
    PROPERTY LINK_DEPENDS "${lmdj_core_c_export_file}"
  )
endif()
lmdj_target_warnings(lmdj_core_c)
lmdj_target_sanitizers(lmdj_core_c)

if(BUILD_TESTING)
  find_package(Threads REQUIRED)

  add_executable(
    lmdj_application_facade_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/application_test.cpp"
  )
  target_include_directories(
    lmdj_application_facade_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_application_facade_tests
    PRIVATE
      lmdj::application
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_application_facade_tests)
  # The three facade binaries share one body of scaffolding and each
  # exercises a subset of it, so unused-helper diagnostics report the
  # split rather than a defect. Everything else stays an error.
  target_compile_options(
    lmdj_application_facade_tests
    PRIVATE
      -Wno-unused-function
      -Wno-unused-const-variable
      -Wno-unneeded-internal-declaration
  )
  lmdj_target_sanitizers(lmdj_application_facade_tests)
  lmdj_add_test(
    NAME facade.application
    TIER component
    COMMAND lmdj_application_facade_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )

  add_executable(
    lmdj_facade_sequence_surface_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/sequence_surface_test.cpp"
  )
  target_include_directories(
    lmdj_facade_sequence_surface_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_facade_sequence_surface_tests
    PRIVATE
      lmdj::application
  )
  lmdj_target_warnings(lmdj_facade_sequence_surface_tests)
  lmdj_target_sanitizers(lmdj_facade_sequence_surface_tests)
  lmdj_add_test(
    NAME facade.sequence_surface
    TIER component
    COMMAND lmdj_facade_sequence_surface_tests --shard=lifecycle
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME facade.sequence_surface.recovery
    TIER component
    COMMAND lmdj_facade_sequence_surface_tests --shard=recovery
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME facade.sequence_surface.rebase
    TIER component
    COMMAND lmdj_facade_sequence_surface_tests --shard=rebase
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )

  add_executable(
    lmdj_facade_sample_surface_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/sample_surface_test.cpp"
  )
  target_include_directories(lmdj_facade_sample_surface_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(
    lmdj_facade_sample_surface_tests
    PRIVATE
      lmdj::application
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_facade_sample_surface_tests)
  # The three facade binaries share one body of scaffolding and each
  # exercises a subset of it, so unused-helper diagnostics report the
  # split rather than a defect. Everything else stays an error.
  target_compile_options(
    lmdj_facade_sample_surface_tests
    PRIVATE
      -Wno-unused-function
      -Wno-unused-const-variable
      -Wno-unneeded-internal-declaration
  )
  lmdj_target_sanitizers(lmdj_facade_sample_surface_tests)
  lmdj_add_test(
    NAME facade.sample_surface
    TIER component
    COMMAND lmdj_facade_sample_surface_tests --shard=mutation
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME facade.sample_surface.quota_replay
    TIER component
    COMMAND lmdj_facade_sample_surface_tests --shard=quota-replay
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME facade.sample_surface.projection
    TIER component
    COMMAND lmdj_facade_sample_surface_tests --shard=projection
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )

  add_executable(
    lmdj_facade_web_runtime_limit_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/web_runtime_limits_test.cpp"
  )
  target_include_directories(lmdj_facade_web_runtime_limit_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(
    lmdj_facade_web_runtime_limit_tests
    PRIVATE
      lmdj::application
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_facade_web_runtime_limit_tests)
  # The three facade binaries share one body of scaffolding and each
  # exercises a subset of it, so unused-helper diagnostics report the
  # split rather than a defect. Everything else stays an error.
  target_compile_options(
    lmdj_facade_web_runtime_limit_tests
    PRIVATE
      -Wno-unused-function
      -Wno-unused-const-variable
      -Wno-unneeded-internal-declaration
  )
  lmdj_target_sanitizers(lmdj_facade_web_runtime_limit_tests)
  lmdj_add_test(
    NAME facade.web_runtime_limits
    TIER component
    COMMAND lmdj_facade_web_runtime_limit_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )

  add_executable(
    lmdj_application_facade_failure_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/failure_contract_test.cpp"
  )
  target_include_directories(
    lmdj_application_facade_failure_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_application_facade_failure_tests
    PRIVATE
      lmdj::application
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_application_facade_failure_tests)
  lmdj_target_sanitizers(lmdj_application_facade_failure_tests)
  lmdj_add_test(
    NAME facade.failure_contracts
    TIER component
    COMMAND lmdj_application_facade_failure_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )

  add_executable(
    lmdj_assembly_loader_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/assembly_loader_test.cpp"
  )
  target_include_directories(
    lmdj_assembly_loader_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_assembly_loader_tests
    PRIVATE
      lmdj::application
  )
  lmdj_target_warnings(lmdj_assembly_loader_tests)
  lmdj_target_sanitizers(lmdj_assembly_loader_tests)
  lmdj_add_test(
    NAME facade.assembly_loader
    TIER component
    COMMAND lmdj_assembly_loader_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS assembly
  )

  add_executable(
    lmdj_application_c_api_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/c_api_test.cpp"
  )
  target_include_directories(
    lmdj_application_c_api_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_application_c_api_tests
    PRIVATE
      lmdj_core_c
      lmdj_picosha2
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  lmdj_target_warnings(lmdj_application_c_api_tests)
  lmdj_target_sanitizers(lmdj_application_c_api_tests)
  lmdj_add_test(
    NAME facade.c_api
    TIER component
    COMMAND lmdj_application_c_api_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS abi
  )

  add_executable(
    lmdj_application_c_api_stress_tests
    src/c_api.cpp
    "${CMAKE_SOURCE_DIR}/tests/core/facade/c_api_stress_test.cpp"
  )
  target_include_directories(
    lmdj_application_c_api_stress_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_application_c_api_stress_tests
    PRIVATE
      lmdj::application
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_application_c_api_stress_tests
    PRIVATE
      LMDJ_CORE_C_BUILD=1
      LMDJ_C_API_TESTING=1
  )
  lmdj_target_warnings(lmdj_application_c_api_stress_tests)
  lmdj_target_sanitizers(lmdj_application_c_api_stress_tests)
  lmdj_add_test(
    NAME facade.c_api_stress
    TIER stress
    COMMAND lmdj_application_c_api_stress_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS abi concurrency
    TIMEOUT 180
  )

  add_executable(
    lmdj_application_dynamic_load_tests
    "${CMAKE_SOURCE_DIR}/tests/core/facade/dynamic_load_test.cpp"
  )
  target_include_directories(
    lmdj_application_dynamic_load_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_compile_definitions(
    lmdj_application_dynamic_load_tests
    PRIVATE
      LMDJ_CORE_C_LIBRARY_PATH="$<TARGET_FILE:lmdj_core_c>"
  )
  target_link_libraries(
    lmdj_application_dynamic_load_tests
    PRIVATE
      "${CMAKE_DL_LIBS}"
  )
  add_dependencies(lmdj_application_dynamic_load_tests lmdj_core_c)
  lmdj_target_warnings(lmdj_application_dynamic_load_tests)
  lmdj_target_sanitizers(lmdj_application_dynamic_load_tests)
  lmdj_add_test(
    NAME facade.dynamic_load
    TIER contract
    COMMAND lmdj_application_dynamic_load_tests
    LABELS abi
  )
endif()
