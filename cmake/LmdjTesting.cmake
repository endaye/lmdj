include(CMakeParseArguments)

set(lmdj_test_tiers unit component contract host e2e stress)
set(lmdj_test_timeout_unit 10)
set(lmdj_test_timeout_component 30)
set(lmdj_test_timeout_contract 30)
set(lmdj_test_timeout_host 120)
set(lmdj_test_timeout_e2e 180)
set(lmdj_test_timeout_stress 300)

function(lmdj_add_test)
  cmake_parse_arguments(
    TEST
    ""
    "NAME;TIER;TIMEOUT;WORKING_DIRECTORY"
    "COMMAND;LABELS"
    ${ARGN}
  )

  if(NOT TEST_NAME)
    message(FATAL_ERROR "lmdj_add_test requires NAME")
  endif()
  if(NOT TEST_COMMAND)
    message(FATAL_ERROR "lmdj_add_test ${TEST_NAME} requires COMMAND")
  endif()
  if(NOT TEST_TIER IN_LIST lmdj_test_tiers)
    message(FATAL_ERROR
      "lmdj_add_test ${TEST_NAME} requires one valid TIER")
  endif()

  if(NOT TEST_TIMEOUT)
    set(TEST_TIMEOUT "${lmdj_test_timeout_${TEST_TIER}}")
  endif()
  if(LMDJ_SANITIZER STREQUAL "address")
    math(EXPR TEST_TIMEOUT "${TEST_TIMEOUT} * 3")
  elseif(LMDJ_SANITIZER STREQUAL "thread")
    math(EXPR TEST_TIMEOUT "${TEST_TIMEOUT} * 4")
  endif()

  add_test(NAME "${TEST_NAME}" COMMAND ${TEST_COMMAND})

  set(lmdj_test_labels "${TEST_TIER};${TEST_LABELS}")
  list(GET TEST_COMMAND 0 lmdj_test_executable)
  if(TARGET "${lmdj_test_executable}")
    list(APPEND lmdj_test_labels native)
  endif()
  set(lmdj_test_working_directory_property)
  if(TEST_WORKING_DIRECTORY)
    list(APPEND lmdj_test_working_directory_property
      WORKING_DIRECTORY "${TEST_WORKING_DIRECTORY}"
    )
  endif()
  set_tests_properties(
    "${TEST_NAME}"
    PROPERTIES
      LABELS "${lmdj_test_labels}"
      TIMEOUT "${TEST_TIMEOUT}"
      ${lmdj_test_working_directory_property}
  )
endfunction()
