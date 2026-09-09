add_executable(
  lmdj_native_host
  src/main.cpp
  src/capture_writer.cpp
)
set_target_properties(
  lmdj_native_host
  PROPERTIES OUTPUT_NAME lmdj-native-host
)
target_link_libraries(
  lmdj_native_host
  PRIVATE
    lmdj::application
    lmdj::audio_runtime
)
set(lmdj_native_version_path "${CMAKE_SOURCE_DIR}/products/lmdj/version.json")
set_property(
  DIRECTORY
  APPEND
  PROPERTY CMAKE_CONFIGURE_DEPENDS "${lmdj_native_version_path}"
)
file(READ "${lmdj_native_version_path}" lmdj_native_version_json)
foreach(lmdj_native_version_part IN ITEMS milestone minor build patch)
  string(
    JSON lmdj_native_version_${lmdj_native_version_part}
    GET "${lmdj_native_version_json}" "${lmdj_native_version_part}"
  )
endforeach()
set(
  lmdj_native_product_build
  "${lmdj_native_version_milestone}.${lmdj_native_version_minor}.${lmdj_native_version_build}.${lmdj_native_version_patch}"
)
target_compile_definitions(
  lmdj_native_host
  PRIVATE LMDJ_NATIVE_PRODUCT_BUILD="${lmdj_native_product_build}"
)
if(APPLE)
  target_link_libraries(
    lmdj_native_host PRIVATE lmdj::audio_coreaudio
  )
endif()
file(
  GENERATE
  OUTPUT
    "${CMAKE_CURRENT_BINARY_DIR}/lmdj_native_host.link-libraries.txt"
  CONTENT
    "$<TARGET_PROPERTY:lmdj_native_host,LINK_LIBRARIES>\n"
)
lmdj_target_warnings(lmdj_native_host)
lmdj_target_sanitizers(lmdj_native_host)

if(BUILD_TESTING)
  lmdj_add_test(
    NAME host.native_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/native_host_source_boundary_test.py"
      "${CMAKE_CURRENT_SOURCE_DIR}"
      "${CMAKE_CURRENT_BINARY_DIR}/lmdj_native_host.link-libraries.txt"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME host.native_timeout_policy
    TIER unit
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/native_host_timeout_policy_test.py"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  # Cross-Host, but it needs this Host's binary, so it lives here rather than
  # beside the source-scan gate. The defect it catches is the one no per-Host
  # suite can see: two Hosts answering the same Catalog differently, each
  # green against its own idea of the answer.
  lmdj_add_test(
    NAME host.soundset_catalog_partition
    TIER host
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/soundset_catalog_partition_test.py"
      "$<TARGET_FILE:lmdj_native_host>"
      "$<TARGET_FILE:lmdj_core_cli>"
      "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
  lmdj_add_test(
    NAME host.native
    TIER host
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/native_host_test.py"
      "$<TARGET_FILE:lmdj_native_host>"
      "$<TARGET_FILE:lmdj_core_cli>"
      "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endif()
