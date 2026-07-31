option(LMDJ_ENABLE_COVERAGE "Enable LLVM source-based code coverage" OFF)

if(NOT LMDJ_ENABLE_COVERAGE)
  return()
endif()

if(LMDJ_ENABLE_SANITIZERS)
  message(
    FATAL_ERROR
    "LMDJ_ENABLE_COVERAGE and LMDJ_ENABLE_SANITIZERS are mutually exclusive"
  )
endif()

if(MSVC)
  message(FATAL_ERROR "LMDJ_ENABLE_COVERAGE is unsupported with MSVC")
endif()

if(
  NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang"
  AND NOT CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang"
)
  message(
    FATAL_ERROR
    "LMDJ_ENABLE_COVERAGE requires Clang-compatible source-based coverage"
  )
endif()

add_compile_options(
  -fprofile-instr-generate
  -fcoverage-mapping
)
add_link_options(
  -fprofile-instr-generate
  -fcoverage-mapping
)
