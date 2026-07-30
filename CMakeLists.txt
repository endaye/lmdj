cmake_minimum_required(VERSION 3.24)
project(lmdj_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

include(CTest)
include(cmake/LmdjDependencies.cmake)
include(cmake/LmdjWarnings.cmake)

add_subdirectory(packages/foundation)
add_subdirectory(packages/authoring-domain)

find_program(BASH_EXECUTABLE bash REQUIRED)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

add_test(
  NAME build.active_tree
  COMMAND "${BASH_EXECUTABLE}" tests/build/test_active_tree.sh
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

add_test(
  NAME build.version
  COMMAND "${Python3_EXECUTABLE}" tests/build/version_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

add_test(
  NAME contract.schemas
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/schema_contract_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)
