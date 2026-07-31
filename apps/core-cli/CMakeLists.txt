add_executable(
  lmdj_core_cli
  src/main.cpp
)
set_target_properties(
  lmdj_core_cli
  PROPERTIES OUTPUT_NAME lmdj-core
)
target_link_libraries(
  lmdj_core_cli
  PRIVATE
    lmdj::application
)
file(
  GENERATE
  OUTPUT
    "${CMAKE_CURRENT_BINARY_DIR}/lmdj_core_cli.link-libraries.txt"
  CONTENT
    "$<TARGET_PROPERTY:lmdj_core_cli,LINK_LIBRARIES>\n"
)
lmdj_target_warnings(lmdj_core_cli)
lmdj_target_sanitizers(lmdj_core_cli)

if(BUILD_TESTING)
  lmdj_add_test(
    NAME host.cli
    TIER host
    COMMAND
      "${Python3_EXECUTABLE}"
    "${CMAKE_SOURCE_DIR}/tests/host/cli_test.py"
    "$<TARGET_FILE:lmdj_core_cli>"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 60
  )
endif()
